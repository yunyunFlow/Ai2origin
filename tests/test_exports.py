"""Exercise the actual CLI: PNG default, explicit SVG, same source geometry."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from matplotlib import font_manager

ROOT=Path(__file__).resolve().parents[1]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
DRAW=module('export_draw',ROOT/'scripts/ai2origin.py')
CHECK=module('export_check',ROOT/'scripts/check_reproducibility.py')

class ExportTests(unittest.TestCase):
    def test_changed_input_during_preparation_is_refused(self):
        for changed in ('data', 'config', 'style'):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);source=root/'input.csv';source.write_text('x,y\n1,2\n2,3\n')
                style=root/'style.json';style.write_text('{"line":{"width_pt":1.5}}')
                config=root/'input.json';config.write_text(json.dumps({'schema_version':1,'style_file':'style.json',
                    'plots':[{'id':'curve','kind':'line','csv':'input.csv','x':'x',
                              'labels':{'x':'Coordinate','y':'Value'},'series':[{'column':'y','label':'A'}]}]}))
                original=DRAW.read_csv
                def change_after_read(path):
                    rows=original(path)
                    target={'data':source,'config':config,'style':style}[changed]
                    if changed=='data':target.write_text('x,y\n1,9\n2,9\n')
                    else:target.write_text(target.read_text()+'\n')
                    return rows
                with patch.object(DRAW,'read_csv',side_effect=change_after_read), self.assertRaisesRegex(ValueError,'changed'):
                    DRAW.main([str(config),'--out',str(root/'rejected')])
                self.assertFalse((root/'rejected').exists())

    def test_actual_png_default_and_explicit_editable_svg_preserve_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'input.csv').write_text('x,y\n1,2\n2,1\n3,4\n')
            config=root/'input.json'
            config.write_text(json.dumps({'schema_version':1,'style':{'export':{'raster_dpi':72}},
                'plots':[{'id':'curve','kind':'line_symbol','csv':'input.csv','x':'x','synthetic':True,
                          'labels':{'x':'Coordinate','y':'Value'},'series':[{'column':'y','label':'Demo'}]}]}))
            font=font_manager.findfont(font_manager.FontProperties(family='DejaVu Sans'),fallback_to_default=False)
            for name,extra,formats in [('png',[],['png']),('vector',['--svg'],['png','svg'])]:
                folder=root/name
                with contextlib.redirect_stdout(io.StringIO()):
                    DRAW.main([str(config),'--out',str(folder),'--backend','python','--font-file',font]+extra)
                self.assertEqual(CHECK.check(folder,config=config)['status'],'PASS')
                self.assertEqual(json.loads((folder/'receipt.json').read_text())['python_export_formats'],formats)
                self.assertEqual((folder/'curve.svg').exists(),name=='vector')
            self.assertEqual((root/'png/curve.png').read_bytes(),(root/'vector/curve.png').read_bytes())
            first=json.loads((root/'png/origin-plan.json').read_text())
            second=json.loads((root/'vector/origin-plan.json').read_text())
            self.assertEqual(first,second)
            self.assertEqual(first['plots'][0]['books'][0]['rows'],[[1,2,1,2],[2,1,2,1],[3,4,3,4]])

    def test_changed_source_during_render_invalidates_partial_generation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'input.csv';source.write_text('x,y\n1,2\n2,3\n')
            config=root/'input.json';config.write_text(json.dumps({'schema_version':1,
                'plots':[{'id':'curve','kind':'line','csv':'input.csv','x':'x',
                          'labels':{'x':'Coordinate','y':'Value'},'series':[{'column':'y','label':'A'}]}]}))
            def changed_render(*args, **kwargs):
                source.write_text('x,y\n1,9\n2,9\n');return 'DejaVu Sans'
            output=root/'partial'
            with patch.object(DRAW,'render',side_effect=changed_render), self.assertRaisesRegex(ValueError,'changed'):
                DRAW.main([str(config),'--out',str(output),'--backend','python','--font','DejaVu Sans'])
            self.assertTrue((output/'FAILED.txt').exists())
            self.assertFalse((output/'receipt.json').exists())
            with self.assertRaisesRegex(ValueError,'failure marker'):CHECK.check(output)

    def test_svg_rejected_for_prepare_before_any_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary)/'not-created'
            with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
                DRAW.main(['not-a-config','--out',str(output),'--backend','prepare','--svg'])
            self.assertFalse(output.exists())
