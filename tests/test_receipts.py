"""Accepted outputs must remain hash-bound; failure markers override receipts."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

SCRIPT=Path(__file__).resolve().parents[1]/'scripts/check_reproducibility.py'
SPEC=importlib.util.spec_from_file_location('receipt_checker',SCRIPT)
CHECK=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(CHECK)


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def generation(self,name,native=False,rgba=False):
        folder=self.root/name;folder.mkdir()
        if native:
            Image.new('RGB',(8,8),'white').save(folder/'curve.png')
            Image.new('RGBA' if rgba else 'RGB',(8,8),'white').save(folder/'curve-reopened.png')
            (folder/'figures.opju').write_bytes(b'owned synthetic project placeholder')
            receipt=dict(status='NATIVE_EXPORTED',reopened_graph_count=1,project_reopen='PASS',
                         numeric_readback='PASS',style_readback='PASS_BEFORE_AND_AFTER_REOPEN',
                         numeric_readback_cells=4,reopened_readback_cells=4,plan_sha256='plan',
                         runner_sha256='runner',origin_version='Origin 2021')
        else:
            (folder/'origin-plan.json').write_text(json.dumps({'plots':[{'id':'curve','books':[{'name':'Data1'}]}]}))
            (folder/'curve-Data1.csv').write_text('x,y\n0,1\n1,2\n')
            (folder/'curve.png').write_bytes(b'synthetic raster fixture')
            (folder/'curve.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"><text>axis</text></svg>')
            receipt=dict(status='PYTHON_RENDERED')
        receipt['outputs']=[dict(name=p.name,bytes=p.stat().st_size,
                                sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                            for p in sorted(folder.iterdir())]
        target=folder/('native-receipt.json' if native else 'receipt.json')
        target.write_text(json.dumps(receipt))
        return folder,target,receipt

    def test_repeat_and_tampering(self):
        a,_,_=self.generation('a');b,_,_=self.generation('b')
        self.assertEqual(CHECK.check(a,b)['repeat'],'BYTE_IDENTICAL')
        (b/'curve.png').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'hash/size'):CHECK.check(a,b)

    def test_failure_marker_overrides_complete_receipt(self):
        folder,_,_=self.generation('a')
        (folder/'FAILED.json').write_text('{"status":"HOLD_TIMEOUT"}')
        with self.assertRaisesRegex(ValueError,'failure marker'):CHECK.inspect(folder)

    def test_unsafe_paths_empty_receipt_and_svg_text(self):
        folder,path,receipt=self.generation('a')
        receipt['outputs'][0]['name']='../curve.png';path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError,'Unsafe'):CHECK.inspect(folder)
        receipt['outputs']=[];path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError,'Empty'):CHECK.inspect(folder)
        folder,path,receipt=self.generation('b')
        (folder/'curve.svg').write_text('<svg/>')
        for output in receipt['outputs']:
            p=folder/output['name'];output.update(bytes=p.stat().st_size,sha256=CHECK.sha(p))
        path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError,'editable text'):CHECK.inspect(folder)

    def test_native_compares_visible_rgb_across_modes(self):
        a,_,_=self.generation('a',native=True,rgba=True)
        b,_,_=self.generation('b',native=True)
        self.assertEqual(CHECK.check(a,b)['repeat'],'NATIVE_RGB_IDENTICAL')
        Image.new('RGB',(8,8),'black').save(a/'curve-reopened.png')
        path=a/'native-receipt.json';receipt=json.loads(path.read_text())
        for output in receipt['outputs']:
            p=a/output['name'];output.update(bytes=p.stat().st_size,sha256=CHECK.sha(p))
        path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError,'RGB pixels'):CHECK.inspect(a)

    def test_native_inventory_and_readback_required(self):
        a,_,_=self.generation('a',native=True);b,path,receipt=self.generation('b',native=True)
        (b/'extra.png').write_bytes(b'extra')
        receipt['outputs'].append(dict(name='extra.png',bytes=5,sha256=CHECK.sha(b/'extra.png')))
        path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError,'inventory'):CHECK.check(a,b)
        receipt['style_readback']='FAIL';path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError,'acceptance'):CHECK.inspect(b)

    def test_backend_status_and_required_geometry_cannot_be_omitted(self):
        folder,path,receipt=self.generation('a')
        receipt['status']='NATIVE_EXPORTED';path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError,'backend status'):CHECK.inspect(folder)
        receipt['status']='PREPARED'
        (folder/'origin-plan.json').write_text(json.dumps({'plots':[{'id':'curve','books':[{'name':'Data1'}]}]}))
        (folder/'curve-Data1.csv').unlink()
        receipt['outputs']=[v for v in receipt['outputs'] if v['name']!='curve-Data1.csv']
        for output in receipt['outputs']:
            p=folder/output['name'];output.update(bytes=p.stat().st_size,sha256=CHECK.sha(p))
        path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError,'worksheet CSV missing'):CHECK.inspect(folder)
        native,_,_=self.generation('native',native=True)
        with self.assertRaisesRegex(ValueError,'requires a prepared'):CHECK.inspect(native,config=Path('not-an-input'))

    def test_live_project_style_identity_is_checked(self):
        folder,path,receipt=self.generation('a')
        source=self.root/'source.csv';source.write_text('x,y\n0,1\n1,2\n')
        style=self.root/'project.style.json';style.write_text('{"line":{"width_pt":1.5}}')
        config=self.root/'config.json'
        config.write_text(json.dumps({'style_file':style.name,'plots':[{'id':'curve','csv':source.name}]}))
        plan={'config_sha256':CHECK.sha(config),
              'style_inputs':[dict(layer='project-file',file_name=style.name,sha256=CHECK.sha(style))],
              'plots':[{'id':'curve','books':[{'name':'Data1'}],'metadata':{'source_sha256':CHECK.sha(source)}}]}
        (folder/'origin-plan.json').write_text(json.dumps(plan))
        for output in receipt['outputs']:
            p=folder/output['name'];output.update(bytes=p.stat().st_size,sha256=CHECK.sha(p))
        path.write_text(json.dumps(receipt))
        self.assertEqual(CHECK.check(folder,config=config)['status'],'PASS')
        style.write_text('{"line":{"width_pt":3.0}}')
        with self.assertRaisesRegex(ValueError,'style-file hash'):CHECK.check(folder,config=config)

    def test_empty_hash_bound_plan_is_not_a_completed_generation(self):
        folder,path,receipt=self.generation('a')
        (folder/'origin-plan.json').write_text('{"plots":[]}')
        for output in receipt['outputs']:
            p=folder/output['name'];output.update(bytes=p.stat().st_size,sha256=CHECK.sha(p))
        path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError,'plot inventory'):CHECK.inspect(folder)

    def test_declared_formats_and_legacy_svg_requirement(self):
        folder,path,receipt=self.generation('formats')
        self.assertEqual(CHECK.check(folder)['status'],'PASS')
        (folder/'curve.svg').unlink()
        receipt['outputs']=[v for v in receipt['outputs'] if v['name']!='curve.svg']
        path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError,'outputs missing'):CHECK.inspect(folder)
        receipt['python_export_formats']=['png'];path.write_text(json.dumps(receipt))
        self.assertEqual(CHECK.check(folder)['status'],'PASS')
        receipt['python_export_formats']=['png','svg'];path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError,'outputs missing'):CHECK.inspect(folder)
        receipt['python_export_formats']=['svg'];path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError,'export formats'):CHECK.inspect(folder)


    def test_unlisted_files_and_directories_are_refused(self):
        for native in (False, True):
            with self.subTest(native=native):
                folder,_,_=self.generation('extra-native' if native else 'extra-python',native=native)
                if native:
                    for name in ('_session.json','_assets.json','curve-layout.json'):
                        (folder/name).write_text('{}')
                    self.assertEqual(CHECK.check(folder)['status'],'PASS')
                extra=folder/'unlisted-note.txt';extra.write_text('synthetic fixture')
                with self.assertRaisesRegex(ValueError,'Unlisted output'):CHECK.inspect(folder)
                extra.unlink()
                extra=folder/'unlisted-directory';extra.mkdir()
                with self.assertRaisesRegex(ValueError,'Unexpected output entry'):CHECK.inspect(folder)
                extra.rmdir()
                self.assertEqual(CHECK.check(folder)['status'],'PASS')

    def test_metadata_names_and_symlinks_are_bounded(self):
        folder,_,_=self.generation('names',native=True)
        extra=folder/'unknown-layout.json';extra.write_text('{}')
        with self.assertRaisesRegex(ValueError,'Unlisted output'):CHECK.inspect(folder)
        extra.unlink()
        (folder/'_session.json').symlink_to(folder/'native-receipt.json')
        with self.assertRaisesRegex(ValueError,'Unexpected output entry'):CHECK.inspect(folder)
        folder,_,_=self.generation('python-metadata')
        (folder/'_session.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'Unlisted output'):CHECK.inspect(folder)


if __name__=='__main__':unittest.main()
