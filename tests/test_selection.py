"""CLI recipe selection preserves measurements and strict provenance."""
import importlib.util
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/f'{name}.py')
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
D=module('ai2origin');C=module('check_reproducibility')


class SelectionTests(unittest.TestCase):
    def test_reordered_requests_repeat_in_catalog_order_with_identical_values(self):
        config=ROOT/'templates/paper.json'
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            with contextlib.redirect_stdout(io.StringIO()):
                D.main([str(config),'--out',str(root/'a'),'--select','nyquist','cv'])
                D.main([str(config),'--out',str(root/'b'),'--select','cv','nyquist'])
            self.assertEqual(C.check(root/'a',root/'b',config)['repeat'],'BYTE_IDENTICAL')
            plan=C.load_json(root/'a/origin-plan.json')
            self.assertEqual(plan['selected_plot_ids'],['cv','nyquist'])
            for plot in plan['plots']:
                spec=next(p for p in D.load_json(config)['plots'] if p['id']==plot['id'])
                rows=D.read_csv(config.parent/spec['csv'])
                self.assertEqual([r[0] for r in plot['books'][0]['rows']],[float(r[spec['x']]) for r in rows])
            self.assertFalse((root/'a/gitt.png').exists())

    def test_unknown_duplicate_selection_fails_before_creating_output(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'out'
            for ids in [('unknown',),('cv','cv'),('CV',)]:
                with self.assertRaisesRegex(ValueError,'selected recipe'):
                    D.main([str(ROOT/'templates/paper.json'),'--out',str(out),'--select',*ids])
                self.assertFalse(out.exists())

    def test_counterfeit_selection_rejected_even_without_original_config(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'out'
            with contextlib.redirect_stdout(io.StringIO()):
                D.main([str(ROOT/'templates/paper.json'),'--out',str(out),'--select','cv'])
            plan=C.load_json(out/'origin-plan.json');plan['selected_plot_ids']=['nyquist']
            path=out/'origin-plan.json';path.write_text(json.dumps(plan))
            receipt=C.load_json(out/'receipt.json')
            for entry in receipt['outputs']:
                if entry['name']==path.name:entry.update(sha256=C.sha(path),bytes=path.stat().st_size)
            (out/'receipt.json').write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError,'selection'):C.check(out)


if __name__=='__main__':unittest.main()
