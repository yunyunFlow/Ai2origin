"""Synthetic flat-export fixtures; source lexemes and order must survive."""
import csv
from fractions import Fraction
import importlib.util
import json
import math
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('table_intake', ROOT / 'scripts/intake.py')
INTAKE = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(INTAKE)


class IntakeTests(unittest.TestCase):
    def test_cv_representable_subnormal_trapezoids_match_exact_reference(self):
        columns = {'voltage': {'source': 'X', 'type': 'numeric', 'unit': 'V'},
                   'current': {'source': 'Y', 'type': 'numeric', 'unit': 'A'}}
        currents = [5e-324, 1e-323, -1e-323]
        for width in (1., 2., 4.):
            rows = [{'voltage': str(x), 'current': str(y)}
                    for x, y in zip((0., width, 0.), currents)]
            result = INTAKE.cv_summary(rows, columns,
                {'kind': 'cv_loop_capacitance', 'scan_rate_V_s': .1})
            exact_terms = [float((Fraction(a) + Fraction(b)) * Fraction(dx) / 2)
                           for a, b, dx in zip(currents, currents[1:], (width, -width))]
            self.assertEqual(result['signed_loop_integral_A_V'], math.fsum(exact_terms))
            self.assertEqual(result['apparent_capacitance_F'], abs(math.fsum(exact_terms)) / (.2 * width))

    def test_cv_huge_integer_rate_is_contextual_failure_before_output(self):
        columns = {'voltage': {'source': 'X', 'type': 'numeric', 'unit': 'V'},
                   'current': {'source': 'Y', 'type': 'numeric', 'unit': 'A'}}
        source = self.source('X,Y\n0,1\n1,0\n0,-1\n')
        mapping = self.mapping(columns=columns, analysis={
            'kind': 'cv_loop_capacitance', 'scan_rate_V_s': 10**308})
        out = self.root / 'huge-integer'
        run = subprocess.run([sys.executable, '-I', '-B', str(ROOT / 'scripts/intake.py'),
                              str(source), '--map', str(mapping), '--out', str(out)],
                             capture_output=True, text=True, cwd=self.root)
        self.assertEqual(run.returncode, 1)
        self.assertIn('FAIL: CV analysis scale overflow/underflow', run.stderr)
        self.assertNotIn('Traceback', run.stderr)
        self.assertFalse(out.exists())

    def test_missing_invalid_indices_follow_original_records_after_header_skip(self):
        source = self.source('instrument metadata\nX,Y\n1,2\n2,\n3,broken\n')
        mapping = self.mapping(table={'skip_rows': 1})
        out = self.root / 'record-indices'
        INTAKE.convert(source, mapping, out)
        result = json.loads((out / 'summary.json').read_text())
        self.assertEqual(result['source_provenance']['source_records'], [3, 4, 5])
        self.assertEqual(result['columns']['y']['missing_record_indices'], [4])
        self.assertEqual(result['columns']['y']['invalid_record_indices'], [5])
        self.assertEqual(result['columns']['y']['record_index_space'], 'source_records')
        self.assertIn('4,2,', (out / 'mapped.csv').read_text())

    def test_mean_extremes_remain_within_observed_range(self):
        for values,expected in [(['5e-324']*2,5e-324),([str(sys.float_info.max)]*3,sys.float_info.max),
                                (['1e308','1e-100','-1e308'],1e-100/3)]:
            result=INTAKE.profile(values,True)
            self.assertEqual(result['mean_finite_only'],expected)
            self.assertLessEqual(result['range'][0],result['mean_finite_only'])
            self.assertGreaterEqual(result['range'][1],result['mean_finite_only'])

    def test_unrepresentable_nonzero_lexeme_retained_audit_but_not_plotted(self):
        p=self.source('X,Y\n1,1e-400\n2,0e-999\n')
        INTAKE.convert(p,self.mapping(),self.root/'audit')
        report=json.loads((self.root/'audit/summary.json').read_text())
        self.assertEqual(report['columns']['y']['nonfinite_or_nonnumeric_count'],1)
        self.assertIn('1e-400',(self.root/'audit/source-table.csv').read_text())
        with self.assertRaisesRegex(ValueError,'complete finite'):
            INTAKE.convert(p,self.mapping(plot={'x':'x','y':['y']}),self.root/'refused')
        self.assertFalse((self.root/'refused').exists())

    def test_cv_underflow_is_refused_instead_of_false_zero(self):
        cols={'voltage':{'source':'X','type':'numeric','unit':'V'},
              'current':{'source':'Y','type':'numeric','unit':'A'}}
        cases=[('X,Y\n0,1e-250\n1e-100,1e-250\n0,-1e-250\n',{},'A'),
               ('X,Y\n0,5e-324\n1,5e-324\n0,-5e-324\n',{},'mA'),
               ('X,Y\n0,1e-200\n1,1e-200\n0,-1e-200\n',{'scan_rate_V_s':1e100,'mass_g':1e100},'A'),
               ('X,Y\n0,1e-250\n1,1e-250\n0,-1e-250\n',{'scan_rate_V_s':1e100},'A')]
        for index,(text,extra,unit) in enumerate(cases):
            p=self.source(text);cols['current']['unit']=unit
            request={'kind':'cv_loop_capacitance','scan_rate_V_s':1,**extra}
            out=self.root/('underflow'+str(index))
            with self.subTest(case=index),self.assertRaisesRegex(ValueError,'underflow'):
                INTAKE.convert(p,self.mapping(columns=cols,analysis=request),out)
            self.assertFalse(out.exists())

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / '中文 space'; self.root.mkdir()

    def mapping(self, **extras):
        result = {'schema_version': 1, 'synthetic': True,
                  'columns': {'x': {'source': 'X', 'type': 'numeric', 'unit': 's'},
                              'y': {'source': 'Y', 'type': 'numeric', 'unit': 'mA'}}}
        result.update(extras)
        path = self.root / 'map.json'; path.write_text(json.dumps(result))
        return path

    def source(self, text, suffix='.csv'):
        p = self.root / ('observations' + suffix); p.write_text(text, encoding='utf-8')
        return p

    def test_csv_lexemes_order_missing_duplicate_and_repeat(self):
        p = self.source('X,Y,ID\n2,-1e-3,001\n1,,002\n1,3.00,002\n1,3.00,002\n')
        mapping = self.mapping()
        for name in ('a', 'b'): INTAKE.convert(p, mapping, self.root / name)
        self.assertEqual(INTAKE.verify(self.root / 'a', self.root / 'b')['repeat'], 'BYTE_IDENTICAL')
        with (self.root / 'a/source-table.csv').open() as f:
            self.assertEqual(list(csv.reader(f))[1:], [['2', '-1e-3', '001'], ['1', '', '002'], ['1', '3.00', '002'], ['1', '3.00', '002']])
        report = json.loads((self.root / 'a/summary.json').read_text())
        self.assertEqual(report['exact_duplicate_rows'], 1)
        self.assertEqual(report['columns']['y']['missing_count'], 1)
        self.assertEqual(report['columns']['y']['finite_count'], 3)
        self.assertEqual(report['columns']['x']['sampling']['zero_steps'], 2)
        self.assertFalse((self.root / 'a/plot.json').exists())

    def test_tsv_and_headerless_txt_explicit_mapping(self):
        for suffix, text, options in [('.tsv', 'X\tY\n1\t2\n3\t4\n', {}),
                                       ('.txt', 'instrument metadata\n1 2\n3 4\n', {'delimiter': 'whitespace', 'skip_rows': 1, 'header': False, 'names': ['X', 'Y']})]:
            p = self.source(text, suffix)
            mapping = self.mapping(table=options)
            output = self.root / suffix[1:]
            INTAKE.convert(p, mapping, output)
            self.assertEqual(json.loads((output / 'intake-receipt.json').read_text())['rows'], 2)
        with self.assertRaisesRegex(ValueError, 'explicit delimiter'): INTAKE.read_table(self.source('1 2\n', '.txt'))

    def test_invalid_data_is_retained_but_not_plotted(self):
        p = self.source('X,Y\n1,NaN\n2,broken\n3,\n')
        INTAKE.convert(p, self.mapping(), self.root / 'audit')
        report = json.loads((self.root / 'audit/summary.json').read_text())
        self.assertEqual(report['columns']['y']['nonfinite_or_nonnumeric_count'], 2)
        self.assertEqual(report['source_rows'], 3)
        out = self.root / 'invalid'
        with self.assertRaisesRegex(ValueError, 'complete finite'): INTAKE.convert(p, self.mapping(plot={'x': 'x', 'y': ['y']}), out)
        self.assertFalse(out.exists())

    def test_plot_unit_and_marker_options_preserve_values(self):
        p = self.source('X,Y\n2,-1e-3\n1,3.00\n1,2.0\n')
        INTAKE.convert(p, self.mapping(plot={'x': 'x', 'y': ['y'], 'marker_size_pt': 6}), self.root / 'plot')
        result = json.loads((self.root / 'plot/plot.json').read_text())
        self.assertEqual(result['style']['marker']['size_pt'], 6)
        self.assertEqual(result['plots'][0]['labels']['y'], 'y (mA)')
        self.assertEqual(INTAKE.verify(self.root / 'plot')['status'], 'PASS')

    def test_battery_keeps_channel_branch_signed_current_and_ids(self):
        p = self.source('Sample,Channel,Cycle,Step,Branch,Time,Voltage,Current,Capacity\nA,001,1,2,charge,0,1,2,0\nA,001,1,3,discharge,1,0.9,-2,0.01\nB,002,1,2,charge,0,1,2,0\n')
        cols = {role: {'source': name, 'type': 'text'} for role, name in [('sample', 'Sample'), ('channel', 'Channel'), ('cycle', 'Cycle'), ('step', 'Step'), ('branch', 'Branch')]}
        cols.update({role: {'source': name, 'type': 'numeric', 'unit': unit} for role, name, unit in [('time', 'Time', 's'), ('voltage', 'Voltage', 'V'), ('current', 'Current', 'mA'), ('capacity', 'Capacity', 'mAh')]})
        m = self.mapping(profile='battery', columns=cols, metadata={'level': 'record', 'current_sign_convention': 'positive charge, negative discharge'}, plot={'x': 'time', 'y': ['current'], 'group_by': ['sample', 'channel', 'cycle', 'branch']})
        INTAKE.convert(p, m, self.root / 'battery')
        q = json.loads((self.root / 'battery/summary.json').read_text()); self.assertEqual(len(q['groups']), 3)
        self.assertEqual(q['columns']['current']['range'], [-2, 2])
        self.assertIn('001', (self.root / 'battery/mapped.csv').read_text())
        wrong = json.loads(m.read_text()); wrong['columns']['current']['type'] = 'text'; m.write_text(json.dumps(wrong))
        with self.assertRaisesRegex(ValueError, 'must be numeric'): INTAKE.convert(p, m, self.root / 'text-current')
        m.write_text(json.dumps({**wrong, 'columns': cols}))
        raw = json.loads(m.read_text()); raw['plot']['group_by'] = ['cycle']; m.write_text(json.dumps(raw))
        with self.assertRaisesRegex(ValueError, 'separate'): INTAKE.convert(p, m, self.root / 'pooled')

    def test_xps_requires_semantics_without_calibrating(self):
        p = self.source('Sample,Region,E,I\nA,Survey,1350,20\nA,Survey,1349,21\n')
        cols = {'sample': {'source': 'Sample', 'type': 'text'}, 'region': {'source': 'Region', 'type': 'text'},
                'energy': {'source': 'E', 'type': 'numeric', 'unit': 'eV'}, 'intensity': {'source': 'I', 'type': 'numeric', 'unit': 'counts'}}
        m = self.mapping(profile='xps', columns=cols)
        with self.assertRaisesRegex(ValueError, 'energy type'): INTAKE.convert(p, m, self.root / 'ambiguous')
        raw = json.loads(m.read_text()); raw['metadata'] = {'energy_type': 'binding', 'scan_type': 'survey', 'processing': 'raw counts, previously converted from kinetic energy by source parser'}; m.write_text(json.dumps(raw))
        INTAKE.convert(p, m, self.root / 'xps')
        self.assertEqual(json.loads((self.root / 'xps/summary.json').read_text())['columns']['energy']['sampling']['step_range'], [-1, -1])
        raw['metadata']['processing']=True; m.write_text(json.dumps(raw))
        with self.assertRaisesRegex(ValueError,'previous processing'):INTAKE.convert(p,m,self.root/'ambiguous-processing')

    def workbook(self, formula=False, merged=False):
        p = self.root / 'flat.xlsx'
        ns = INTAKE.NS['s']
        with zipfile.ZipFile(p, 'w') as z:
            z.writestr('xl/workbook.xml', '<workbook xmlns="' + ns + '" xmlns:r="' + INTAKE.REL + '"><sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets></workbook>')
            z.writestr('xl/_rels/workbook.xml.rels', '<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
            z.writestr('xl/worksheets/sheet1.xml', '<worksheet xmlns="' + ns + '"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>X</t></is></c><c r="B1" t="inlineStr"><is><t>Y</t></is></c></row><row r="2"><c r="A2"><v>1</v></c><c r="B2">' + ('<f>A2+1</f>' if formula else '') + '<v>2.00</v></c></row><row r="3"><c r="A3"><v>2</v></c></row></sheetData>' + ('<mergeCells><mergeCell ref="A1:B1"/></mergeCells>' if merged else '') + '</worksheet>')
        return p

    def test_excel_sparse_cells_and_numeric_lexemes(self):
        p = self.workbook(); headers, rows, info = INTAKE.read_table(p)
        self.assertEqual(headers, ['X', 'Y']); self.assertEqual(rows, [['1', '2.00'], ['2', '']])
        self.assertEqual(info['source_records'], [2, 3])
        INTAKE.convert(p, self.mapping(), self.root / 'excel')
        self.assertEqual(INTAKE.verify(self.root / 'excel')['status'], 'PASS')

    def test_excel_formulas_merged_and_vendor_formats_refused(self):
        for option, message in [({'formula': True}, 'formulas'), ({'merged': True}, 'Merged')]:
            with self.assertRaisesRegex(ValueError, message): INTAKE.read_table(self.workbook(**option))
        with self.assertRaisesRegex(ValueError, 'Unsupported format'): INTAKE.read_table(self.source('binary placeholder', '.nda'))

    def test_excel_absent_rows_and_negative_shared_index_refused(self):
        for old, new, message in [('r="3"', 'r="4"', 'Absent Excel rows'),
                                  ('<c r="B2"><v>2.00</v></c>', '<c r="B2" t="s"><v>-1</v></c>', 'shared string')]:
            p = self.workbook()
            with zipfile.ZipFile(p) as z:
                entries = {n: z.read(n) for n in z.namelist()}
            entries['xl/worksheets/sheet1.xml'] = entries['xl/worksheets/sheet1.xml'].decode().replace(old, new).encode()
            with zipfile.ZipFile(p, 'w') as z:
                for name, value in entries.items(): z.writestr(name, value)
            with self.assertRaisesRegex(ValueError, message): INTAKE.read_table(p)

    def test_receipt_cannot_omit_requested_plot_outputs(self):
        p = self.source('X,Y\n1,2\n2,3\n')
        INTAKE.convert(p, self.mapping(plot={'x': 'x', 'y': ['y']}), self.root / 'plot')
        receipt_path = self.root / 'plot/intake-receipt.json'
        receipt = json.loads(receipt_path.read_text())
        receipt['outputs'] = [e for e in receipt['outputs'] if e['name'] != 'plot.json']
        (self.root / 'plot/plot.json').unlink()
        receipt_path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError, 'requested plot'): INTAKE.verify(self.root / 'plot')

    def test_cv_quotient_units_and_explicit_mass_are_dimensional(self):
        p = self.source('X,Y\n0,2\n0.5,2\n1,0\n0.5,-2\n0,-2\n')
        columns = {'voltage': {'source': 'X', 'type': 'numeric', 'unit': 'V'}, 'current': {'source': 'Y', 'type': 'numeric', 'unit': 'mA'}}
        INTAKE.convert(p, self.mapping(columns=columns, analysis={'kind': 'cv_loop_capacitance', 'scan_rate_V_s': .1, 'mass_g': .01}), self.root / 'cv')
        q = json.loads((self.root / 'cv/summary.json').read_text())['analysis']
        self.assertAlmostEqual(q['signed_loop_integral_A_V'], .003)
        self.assertAlmostEqual(q['apparent_capacitance_F'], .015)
        self.assertAlmostEqual(q['apparent_capacitance_F_g'], 1.5)
        self.assertNotIn('mass_g', json.loads((self.root / 'cv/summary.json').read_text())['mapping']['columns'])

    def test_cv_incomplete_cycles_units_and_inferred_basis_refused(self):
        cols = {'voltage': {'source': 'X', 'type': 'numeric', 'unit': 'V'}, 'current': {'source': 'Y', 'type': 'numeric', 'unit': 'mA'}}
        for name, text, request in [('open', 'X,Y\n0,2\n1,2\n', {'scan_rate_V_s': .1}),
                                    ('rate', 'X,Y\n0,2\n1,0\n0,-2\n', {}),
                                    ('mass', 'X,Y\n0,2\n1,0\n0,-2\n', {'scan_rate_V_s': .1, 'mass_g': 0})]:
            m = self.mapping(columns=cols, analysis={'kind': 'cv_loop_capacitance', **request})
            with self.assertRaises(ValueError): INTAKE.convert(self.source(text), m, self.root / name)
            self.assertFalse((self.root / name).exists())

    def test_unknown_mapping_width_extra_outputs_and_overwrite_refused(self):
        with self.assertRaisesRegex(ValueError, 'width'): INTAKE.read_table(self.source('X,Y\n1\n'))
        p = self.source('X,Y\n1,2\n')
        with self.assertRaisesRegex(ValueError, 'Unsupported mapping'): INTAKE.convert(p, self.mapping(smooth=True), self.root / 'bad')
        m = self.mapping(); INTAKE.convert(p, m, self.root / 'a')
        with self.assertRaises(FileExistsError): INTAKE.convert(p, m, self.root / 'a')
        (self.root / 'a/unlisted.txt').write_text('extra')
        with self.assertRaisesRegex(ValueError, 'Unexpected'): INTAKE.verify(self.root / 'a')

    def test_malformed_quotes_bad_options_and_codec_refused(self):
        p=self.source('X,Y\n1,"2\n')
        with self.assertRaisesRegex(ValueError,'Malformed'):INTAKE.read_table(p)
        for options in (False,[],0):
            with self.assertRaisesRegex(ValueError,'table'):INTAKE.read_table(p,options)
        for codec in ('no-such-codec',False):
            with self.assertRaises(ValueError):INTAKE.read_table(p,{'encoding':codec})

    def test_excel_true_boolean_hidden_rows_and_columns_refused(self):
        for old,new in [('<row r="2">','<row r="2" hidden="true">'),('<sheetData>','<cols><col min="1" max="1" hidden="true"/></cols><sheetData>')]:
            p=self.workbook()
            with zipfile.ZipFile(p) as z:entries={n:z.read(n) for n in z.namelist()}
            entries['xl/worksheets/sheet1.xml']=entries['xl/worksheets/sheet1.xml'].decode().replace(old,new).encode()
            with zipfile.ZipFile(p,'w') as z:
                for name,value in entries.items():z.writestr(name,value)
            with self.assertRaisesRegex(ValueError,'Hidden'):INTAKE.read_table(p)

    def test_cv_unrepresentable_scales_fail_before_output(self):
        cols={'voltage':{'source':'X','type':'numeric','unit':'V'},'current':{'source':'Y','type':'numeric','unit':'A'}}
        for name,text,rate in [('tiny','X,Y\n0,1\n1e-308,0\n0,-1\n',1e-308),('overflow','X,Y\n0,1e308\n10,0\n0,-1e308\n',.1),('huge','X,Y\n0,1\n1,0\n0,-1\n',10**400)]:
            with self.assertRaises(ValueError):INTAKE.convert(self.source(text),self.mapping(columns=cols,analysis={'kind':'cv_loop_capacitance','scan_rate_V_s':rate}),self.root/name)
            self.assertFalse((self.root/name).exists())


if __name__ == '__main__': unittest.main()
