"""Cross-platform contracts: inspect without mutation; exact geometry and failure refusal."""
import base64
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts'/(name+'.py'))
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value
D, I, C = (module(n) for n in ('ai2origin','intake','check_reproducibility'))


class ContractTests(unittest.TestCase):
    def test_public_analysis_previews_bind_their_actual_native_plot_and_file(self):
        record=json.loads((ROOT/'samples/analysis.validation.json').read_text())
        plots={p['id']:p for p in record['plots']}
        self.assertEqual(len(plots),record['figures'])
        for preview in record['included_previews']:
            digest=hashlib.sha256((ROOT/'samples'/preview['file']).read_bytes()).hexdigest()
            self.assertEqual(digest,preview['sha256'])
            self.assertEqual(digest,plots[preview['plot_id']]['native_png_sha256'])

    def test_equal_axis_geometry_tolerates_roundoff_at_the_page_boundary(self):
        spec={'id':'arc','kind':'line','csv':'unused.csv','x':'x','equal_xy':True,
              'x_range':[-1.5132664541174583,32.686555408937096],
              'y_range':[-1.5132664541174583,32.686555408937096],
              'labels':{'x':'Re(Z) (ohm)','y':'-Im(Z) (ohm)'},'series':[{'column':'y','label':'A'}]}
        style=D.STYLE.resolve(D.load_json,project={'figure':{'width_mm':110,'height_mm':80}})[0]
        result=D.prepare_plot(spec,[{'x':'4','y':'3'},{'x':'7','y':'9'}],1,style)
        commands=result['commands'];width=float([c.split('=')[1] for c in commands if c.startswith('layer.width=')][-1])
        height=float([c.split('=')[1] for c in commands if c.startswith('layer.height=')][-1])
        self.assertAlmostEqual(width*110,height*80,places=10)
        self.assertEqual(height,62.)

    def test_impedance_prime_glyphs_and_actual_font_text(self):
        self.assertEqual(D.math_text("Z' (Ω)"),'Z′ (Ω)')
        self.assertEqual(D.math_text("-Z'' (Ω)"),'-Z″ (Ω)')
        self.assertEqual(D.math_text("Author's note"),"Author's note")
        spec={'kind':'line','labels':{'x':"Z' (Ω)",'y':"-Z'' (Ω)"},'series':[{'label':'A'}]}
        self.assertIn('Z′ (Ω)',D.plot_text(spec,[]))
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root/'源 数据.csv'
        self.source.write_text('x,y\n0,1e-20\n1,1.2345678901234567\n2,-0.0\n',encoding='utf-8')
        self.plot = {'id':'curve','kind':'line','csv':self.source.name,'x':'x',
                     'labels':{'x':'x','y':'y'},'series':[{'column':'y','label':'Demo'}]}
        self.config = self.root/'配置.json'
        self.save()
    def save(self):
        self.config.write_text(json.dumps({'schema_version':1,'plots':[self.plot]}),encoding='utf-8')
    def generate(self, folder='out', extra=()):
        with contextlib.redirect_stdout(io.StringIO()):
            D.main([str(self.config),'--out',str(self.root/folder),*extra])
        return self.root/folder
    def test_exact_payload_csv_and_json_are_identical(self):
        a,b = self.generate('a'),self.generate('b')
        self.assertEqual(C.check(a,b,self.config)['repeat'],'BYTE_IDENTICAL')
        plan = C.load_json(a/'origin-plan.json')
        book = plan['plots'][0]['books'][0]
        values = [v for row in book['rows'] for v in row]
        raw = base64.b64decode(book['data_f64le'])
        self.assertEqual(raw,struct.pack('<6d',*values))
        self.assertEqual(struct.unpack('<6d',raw)[1],1e-20)
        # Even an updated file hash cannot bless geometry that no longer
        # matches the prepared data. This is consistency, not authenticity.
        csvpath=a/'curve-Data1.csv'
        csvpath.write_text(csvpath.read_text().replace('9.9999999999999995e-21','0'))
        receipt=C.load_json(a/'receipt.json')
        for entry in receipt['outputs']:
            if entry['name']==csvpath.name:
                entry.update(sha256=C.sha(csvpath),bytes=csvpath.stat().st_size)
        (a/'receipt.json').write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError,'geometry'): C.check(a)
    def test_partial_preparation_is_marked_failed(self):
        original=Path.open
        def fail(path,*args,**kwargs):
            if path.name=='curve-Data1.csv': raise OSError('Synthetic disk write failure')
            return original(path,*args,**kwargs)
        with patch.object(Path,'open',fail),self.assertRaisesRegex(OSError,'Synthetic'):
            self.generate()
        self.assertTrue((self.root/'out/FAILED.txt').is_file())
        with self.assertRaisesRegex(ValueError,'failure marker'):C.check(self.root/'out')
    def test_inspection_routes_mixed_files_without_writes(self):
        from PIL import Image
        photo=self.root/'reference.png';Image.new('RGB',(10,12),'white').save(photo)
        project=self.root/'project.opju';project.write_bytes(b'synthetic unsupported project fixture')
        before={p.name:C.sha(p) for p in self.root.iterdir()}
        report=I.inspect_sources([self.source,photo,project])
        self.assertEqual([r['status'] for r in report['files']],
                         ['TABLE_INSPECTED','IMAGE_REFERENCE_ONLY','HOLD_ADAPTER'])
        self.assertEqual(report['files'][0]['preview'][0],['0','1e-20'])
        self.assertEqual(before,{p.name:C.sha(p) for p in self.root.iterdir()})
    def test_inspection_requires_explicit_text_options(self):
        txt=self.root/'光谱.txt';txt.write_text('wave value\n900 1.0\n850 -2\n')
        self.assertEqual(I.inspect_sources([txt])['files'][0]['status'],'HOLD_TABLE_OPTIONS_OR_ADAPTER')
        r=I.inspect_sources([txt],{'delimiter':'whitespace'})['files'][0]
        self.assertEqual(r['status'],'TABLE_INSPECTED');self.assertEqual(r['rows'],2)
        with self.assertRaisesRegex(ValueError,'files'):I.inspect_sources([self.root])
    def test_duplicate_and_nonfinite_json_cannot_change_receipt_meaning(self):
        p=self.root/'bad.json'
        for raw in ('{"status":"FAIL","status":"PASS"}','{"value":NaN}'):
            p.write_text(raw)
            for loader in (C.load_json,I.load_json):
                with self.assertRaises(ValueError):loader(p)
    def test_reserved_names_fail_before_generation(self):
        for name in ('CON','aux','COM1','lpt9'):
            self.plot['id']=name;self.save()
            with self.assertRaisesRegex(ValueError,'reserved'):self.generate()
            self.assertFalse((self.root/'out').exists())
    def test_excel_boolean_cells_are_not_silent_numeric_observations(self):
        ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
        file=self.root/'logical.xlsx'
        with zipfile.ZipFile(file,'w') as z:
            z.writestr('xl/workbook.xml','<workbook xmlns="'+ns+'" xmlns:r="'+I.REL+'"><sheets><sheet name="Data" sheetId="1" r:id="r1"/></sheets></workbook>')
            z.writestr('xl/_rels/workbook.xml.rels','<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>')
            z.writestr('xl/worksheets/sheet1.xml','<worksheet xmlns="'+ns+'"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Signal</t></is></c></row><row r="2"><c r="A2" t="b"><v>1</v></c></row></sheetData></worksheet>')
        with self.assertRaisesRegex(ValueError,'explicit handling'):I.read_table(file)
    def test_legacy_local_font_option_still_works(self):
        from matplotlib import font_manager
        font=font_manager.findfont('DejaVu Sans')
        out=self.generate(extra=('--backend','python','--font-file',font))
        receipt=C.load_json(out/'receipt.json')
        self.assertEqual(receipt['actual_python_fonts'],['DejaVu Sans'])
        self.assertFalse((out/'curve.svg').exists())
        C.check(out,config=self.config)
    def test_derived_filename_collisions_fail_before_mkdir(self):
        grid=self.root/'grid.csv';grid.write_text('x,y,z\n0,0,0\n1,0,0.2\n0,1,0.4\n1,1,1\n')
        heat={'id':'map','kind':'heatmap','csv':grid.name,'x':'x','y':'y','z':'z','color_range':[0,1],
              'labels':{'x':'x','y':'y','color':'z'}}
        for identifier in ('map-colorbar','MAP-COLORBAR'):
            curve=dict(self.plot,id=identifier)
            self.config.write_text(json.dumps({'schema_version':1,'plots':[heat,curve]}))
            with self.assertRaisesRegex(ValueError,'filename collision'):self.generate()
            self.assertFalse((self.root/'out').exists())
        self.plot['id']='curve-reopened';self.save()
        with self.assertRaisesRegex(ValueError,'reserved'):self.generate()
        self.assertFalse((self.root/'out').exists())
    def test_series_contract_reports_missing_or_wrong_roles(self):
        rows=D.read_csv(self.source);style,_=D.STYLE.resolve(D.load_json)
        for series in ({'column':'y'}, {'column':'y','label':True}, {'column':None,'label':'A'},
                       {'column':'y','label':'A','id':1}, {'column':'y','label':'A','uncertainty_definition':True}):
            with self.assertRaises(ValueError):D.prepare_plot(dict(self.plot,series=[series]),rows,1,style)
    def test_plain_minus_sign_changes_labels_not_values(self):
        self.assertEqual(D.lt_string('−Z″ (Ω)'), '"-Z″ (Ω)"')
        self.assertEqual(D.display_label('−Z″ (Ω)'), '-Z″ (Ω)')
        self.assertEqual(D.column([{'y':'-1e-20'}],'y')[0],-1e-20)
    def test_native_legend_units_use_the_same_formatter_as_axes(self):
        rows=D.read_csv(self.source);style,_=D.STYLE.resolve(D.load_json)
        plot=dict(self.plot,series=[{'column':'y','label':'0.2 A g^-1'}])
        plan=D.prepare_plot(plot,rows,1,style)
        self.assertTrue(any('0.2 A g\\+(-1)' in c and 'SeriesKey1' in c for c in plan['commands']))
        self.assertEqual(plan['books'][0]['rows'],[[float(r['x']),float(r['y'])] for r in rows])
    def test_legend_placement_is_invariant_to_unit_scale(self):
        results=[]
        for scale in (1.,1e-20,1e20):
            rows=[{'x':v*scale,'y':.94*scale} for v in (.6,.7,.8,.9,1.)]
            spec=dict(self.plot,x_range=[0,scale],y_range=[0,scale])
            results.append(D.legend_corner(spec,rows))
        self.assertEqual(results[0],results[1]);self.assertEqual(results[0],results[2])
        self.assertEqual(results[0][0],'upper left')
        for scale in (1.,1e-20,1e20):
            result=D.legend_corner(self.plot,[{'x':scale,'y':scale}])
            self.assertIn(result[0],('upper right','upper left','lower right','lower left'))
    def test_excel_date_styles_are_not_measurement_numbers(self):
        ns=I.NS['s'];file=self.root/'dated.xlsx'
        for identifier,code,date in [(14,None,True),(164,'yyyy-mm-dd hh:mm:ss',True),
                                     (164,'[h]:mm:ss',True),(11,None,False),
                                     (164,'0.000 "seconds"',False)]:
            with zipfile.ZipFile(file,'w') as z:
                z.writestr('xl/workbook.xml','<workbook xmlns="'+ns+'" xmlns:r="'+I.REL+'"><sheets><sheet name="Data" r:id="r1"/></sheets></workbook>')
                z.writestr('xl/_rels/workbook.xml.rels','<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>')
                fmt='<numFmts><numFmt numFmtId="164" formatCode="'+code.replace('"','&quot;')+'"/></numFmts>' if code else ''
                z.writestr('xl/styles.xml','<styleSheet xmlns="'+ns+'">'+fmt+'<cellXfs><xf numFmtId="0"/><xf numFmtId="'+str(identifier)+'"/></cellXfs></styleSheet>')
                z.writestr('xl/worksheets/sheet1.xml','<worksheet xmlns="'+ns+'"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Value</t></is></c></row><row r="2"><c r="A2" s="1"><v>45000</v></c></row></sheetData></worksheet>')
            if date:
                with self.assertRaisesRegex(ValueError,'date/time serial'):I.read_table(file)
            else:self.assertEqual(I.read_table(file)[1],[['45000']])


if __name__=='__main__':unittest.main()
