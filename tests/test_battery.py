"""Synthetic battery branches must retain signs, resets and original nodes."""
import csv, importlib.util, json, tempfile, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def module(name):
    s=importlib.util.spec_from_file_location(name,ROOT/'scripts'/(name+'.py'))
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
GEN, INTAKE, DRAW = module('make_battery'), module('intake'), module('ai2origin')

class BatteryTests(unittest.TestCase):
    def test_sources_regenerate_and_physical_units_are_assigned(self):
        for name, expected in [('battery-time.csv',GEN.time_rows()),('battery-capacity.csv',GEN.capacity_rows()),('battery-rate.csv',GEN.capacity_rows(True))]:
            with (ROOT/'templates'/name).open() as f: rows=list(csv.reader(f))[1:]
            self.assertEqual(rows,expected)
        rows=GEN.time_rows();self.assertEqual(len(rows),101)
        self.assertEqual(rows[50][4:8],['charge','500','1.8','0.72'])
        self.assertEqual(rows[51][4:8],['discharge','510','1.684','-0.72'])
        self.assertLess(float(rows[51][-1]),float(rows[50][-1]))

    def test_flat_battery_mapping_keeps_all_identifiers_and_nodes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp); columns={k:{'source':k,'type':'text'} for k in ('sample','channel','cycle','step','branch')}
            columns.update({role:{'source':name,'type':'numeric','unit':unit} for role,name,unit in [('time','time_s','s'),('voltage','voltage_V','V'),('current','current_mA','mA'),('capacity','branch_capacity_mAh','mAh')]})
            config={'schema_version':1,'synthetic':True,'profile':'battery','columns':columns,'metadata':{'level':'record','current_sign_convention':'positive charge, negative discharge; absolute branch capacity'},'plot':{'x':'time','y':['voltage'],'group_by':['sample','channel','cycle']}}
            mapping=p/'map.json';mapping.write_text(json.dumps(config))
            INTAKE.convert(ROOT/'templates/battery-time.csv',mapping,p/'out')
            q=json.loads((p/'out/summary.json').read_text())
            self.assertEqual(q['source_rows'],101);self.assertEqual(q['groups'][0]['rows'],101)
            self.assertEqual(q['columns']['current']['range'],[-.72,.72])
            self.assertIn('001',(p/'out/mapped.csv').read_text())
            self.assertEqual(INTAKE.verify(p/'out')['status'],'PASS')

    def test_separate_capacity_series_have_no_branch_bridge(self):
        config=DRAW.load_json(ROOT/'templates/battery.json');style,_=DRAW.STYLE.resolve(DRAW.load_json,project=config['style'])
        for i,spec in enumerate(config['plots'],1):
            rows=DRAW.read_csv(ROOT/'templates'/spec['csv']);plan=DRAW.prepare_plot(spec,rows,i,style)
            self.assertEqual(plan['metadata']['row_count'],len(rows))
            self.assertEqual(plan['metadata']['connect_order'],'acquisition')
        for spec in config['plots'][1:]:
            self.assertEqual(spec['kind'],'line')
            self.assertEqual(spec['labels']['x'],'Specific capacity (mAh g^-1)')
            self.assertEqual(spec['labels']['y'],'Voltage (V)')
            self.assertTrue(all('x' in s for s in spec['series']))
            self.assertEqual(sum(s.get('legend',True) for s in spec['series']),len(spec['series'])//2)
            for s in spec['series']:
                appearance=DRAW.STYLE.series(style,s['id'],0,s['color'])
                self.assertEqual(appearance['line_style'],'solid')

    def test_independent_x_binding_and_legend_do_not_change_y(self):
        config=DRAW.load_json(ROOT/'templates/battery.json');style,_=DRAW.STYLE.resolve(DRAW.load_json,project=config['style'])
        for i,spec in enumerate(config['plots'][1:],2):
            rows=DRAW.read_csv(ROOT/'templates'/spec['csv']);plan=DRAW.prepare_plot(spec,rows,i,style)
            book=plan['books'][0]
            for j,s in enumerate(spec['series']):
                self.assertEqual([r[2*j] for r in book['rows']],[float(r[s['x']]) for r in rows])
                self.assertEqual([r[2*j+1] for r in book['rows']],[float(r[s['column']]) for r in rows])
            self.assertFalse(any(' -k ' in command for command in plan['commands']))
            self.assertEqual(sum('label -n SeriesKey' in c for c in plan['commands']),len(spec['series'])//2)
        invalid=json.loads(json.dumps(config['plots'][1]));invalid['series'][0]['legend']='false'
        with self.assertRaisesRegex(ValueError,'boolean'):DRAW.prepare_plot(invalid,rows,1,style)
        invalid['series'][0]['legend']=True;invalid['x_scale']='log10';invalid['x_range']=[1,1000]
        with self.assertRaisesRegex(ValueError,'positive'):DRAW.prepare_plot(invalid,DRAW.read_csv(ROOT/'templates'/invalid['csv']),1,style)

    def test_series_x_log_validation_and_malformed_csv(self):
        config={'id':'branches','kind':'line','x':'default','x_scale':'log10','x_range':[1,100],
                'labels':{'x':'Time (s)','y':'Voltage (V)'},'series':[{'x':'branch','column':'voltage','label':'Branch'}]}
        style,_=DRAW.STYLE.resolve(DRAW.load_json)
        with self.assertRaisesRegex(ValueError,'positive'):
            DRAW.prepare_plot(config,[{'default':'1','branch':'-1','voltage':'2'},{'default':'2','branch':'3','voltage':'1'}],1,style)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'bad.csv'
            for text in ('X,Y\n1,"2\n','"X,Y\n1,2\n'):
                p.write_text(text)
                with self.assertRaisesRegex(ValueError,'Malformed'):DRAW.read_csv(p)

if __name__=='__main__':unittest.main()
