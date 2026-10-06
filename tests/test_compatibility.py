"""Exercise dependency boundaries and canonical family recipe consistency."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CompatibilityTests(unittest.TestCase):
    def test_text_inventory_needs_only_standard_library_and_preserves_lexemes(self):
        with tempfile.TemporaryDirectory(prefix='intake space ') as temporary:
            folder = Path(temporary)
            source = folder/'数据.txt'
            source.write_text('time current\n0 -0.000\n1 1.2345678901234567\n', encoding='utf-8')
            options = folder/'options.json'
            options.write_text('{"delimiter":"whitespace"}', encoding='utf-8')
            before = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir()}
            result = subprocess.run([sys.executable, '-I', '-S', '-B', str(ROOT/'scripts/intake.py'),
                                     '--inspect', str(source), '--table', str(options)],
                                    cwd=folder, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)['files'][0]
            self.assertEqual(report['status'], 'TABLE_INSPECTED')
            self.assertEqual(report['preview'], [['0','-0.000'],['1','1.2345678901234567']])
            self.assertEqual(before, {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir()})

    def test_basic_drawing_and_checker_repeat_without_scipy(self):
        # An import blocker proves SciPy is optional even on a machine that has it.
        code = '''import importlib.abc, runpy, sys
class BlockSciPy(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] == 'scipy':
            raise ImportError('SciPy deliberately unavailable in this regression')
sys.meta_path.insert(0, BlockSciPy())
script = sys.argv[1]
sys.argv = sys.argv[1:]
runpy.run_path(script, run_name='__main__')
'''
        with tempfile.TemporaryDirectory(prefix='drawing space ') as temporary:
            folder = Path(temporary)
            for suffix in ('a','b'):
                result = subprocess.run([sys.executable, '-I', '-B', '-c', code,
                                         str(ROOT/'scripts/ai2origin.py'), str(ROOT/'samples/demo.json'),
                                         '--out', str(folder/suffix), '--backend', 'python',
                                         '--font', 'DejaVu Sans', '--svg'], cwd=folder,
                                        capture_output=True, text=True, timeout=90)
                self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([sys.executable, '-I', '-B', '-c', code,
                                     str(ROOT/'scripts/check_reproducibility.py'),
                                     str(folder/'a'), str(folder/'b'), '--config', str(ROOT/'samples/demo.json')],
                                    cwd=folder, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['repeat'], 'BYTE_IDENTICAL')
            ids = [p['id'] for p in json.loads((ROOT/'samples/demo.json').read_text())['plots']]
            self.assertEqual(len(ids), 3)
            for identifier in ids:
                self.assertTrue((folder/'a'/f'{identifier}.png').is_file())
                self.assertTrue((folder/'a'/f'{identifier}.svg').is_file())

    def test_canonical_recipes_have_unique_ids_and_complete_source_roles(self):
        import csv
        seen=set()
        for file in ('samples/demo.json','samples/colors.json','templates/paper.json','templates/battery.json','templates/clouds.json'):
            path=ROOT/file;catalog=json.loads(path.read_text(encoding='utf-8'))
            for plot in catalog['plots']:
                self.assertNotIn(plot['id'],seen);seen.add(plot['id'])
                with (path.parent/plot['csv']).open(encoding='utf-8',newline='') as handle:
                    header=next(csv.reader(handle))
                roles={plot[k] for k in ('x','y','z','group','value') if k in plot}
                for trace in plot.get('series',[]):
                    roles.update(trace[k] for k in ('x','column','lower','upper') if k in trace)
                self.assertTrue(roles.issubset(header),plot['id'])
        self.assertEqual(len(seen),42)


if __name__ == '__main__':
    unittest.main()
