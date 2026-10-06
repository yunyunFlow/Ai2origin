import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ai2origin", ROOT / "scripts" / "ai2origin.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class StyleTests(unittest.TestCase):
    def test_stacked_spectra_hide_ticks_without_editing_values(self):
        import copy
        config = module.load_json(ROOT / 'templates/paper.json')
        stack = next(p for p in config['plots'] if p['id'] == 'stack')
        rows = module.read_csv(ROOT / 'templates/characterization.csv')
        style, _ = module.STYLE.resolve(module.load_json, project=config['style'])
        old = copy.deepcopy(stack)
        old.pop('y_ticks')
        old['y_range'] = [0, 5]
        before = module.prepare_plot(old, rows, 1, style)
        after = module.prepare_plot(stack, rows, 1, style)
        self.assertEqual(before['books'], after['books'])
        self.assertFalse(after['metadata']['y_ticks'])
        self.assertGreater((min(float(r['a']) for r in rows) - stack['y_range'][0]) /
                           (stack['y_range'][1] - stack['y_range'][0]), .06)
        self.assertIn('layer.y.showLabels=0', after['commands'])
        self.assertIn('layer.y.ticks=0', after['commands'])
        for invalid in (None, 0, 1, 'false'):
            with self.subTest(value=invalid), self.assertRaisesRegex(ValueError, 'boolean'):
                module.prepare_plot(dict(stack, y_ticks=invalid), rows, 1, style)
        with self.assertRaisesRegex(ValueError, 'visible Y ticks'):
            module.prepare_plot(dict(stack, y_tick_step=1), rows, 1, style)

    def test_precedence_recursive_merge_and_array_replacement(self):
        original = module.STYLE.DEFAULT_PATH.read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            user = Path(tmp) / "user.json"
            task = Path(tmp) / "task.json"
            user.write_text('{"font":{"tick_size_pt":8},"colors":{"palette":["#112233"]},"series_overrides":{"a":{"color":"#445566"}}}')
            task.write_text('{"font":{"tick_size_pt":12},"series_overrides":{"a":{"width_pt":2}}}')
            style, layers = module.STYLE.resolve(module.load_json, user=user,
                project={"font":{"tick_size_pt":10,"axis_title_size_pt":11}}, task=task)
            self.assertEqual(style["font"]["tick_size_pt"], 12)
            self.assertEqual(style["font"]["axis_title_size_pt"], 11)
            self.assertEqual(style["colors"]["palette"], ["#112233"])
            self.assertEqual(style["series_overrides"]["a"], {"color":"#445566", "width_pt":2})
            self.assertEqual(layers, ["built-in", "user", "project", "task"])
        self.assertEqual(module.STYLE.DEFAULT_PATH.read_bytes(), original)

    def test_unsupported_bad_and_unknown_values_fail(self):
        for update in ({"unknown":1}, {"font":{"family":None}}, {"figure":{"width_mm":-1}},
                       {"colors":{"palette":["red"]}}, {"axes":{"minor_grid":True}},
                       {"font":{"tick_size_pt":True}}, {"export":{"raster_dpi":float("inf")}},
                       {"export":{"raster_dpi":96}}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                module.STYLE.resolve(module.load_json, project=update)

    def test_style_changes_drawing_without_changing_geometry(self):
        config = module.load_json(ROOT / "samples" / "demo.json")
        rows = module.read_csv(ROOT / "samples" / "xy.csv")
        baseline, _ = module.STYLE.resolve(module.load_json)
        changed, _ = module.STYLE.resolve(module.load_json, task=ROOT / "samples" / "project.style.json")
        a = module.prepare_plot(config["plots"][0], rows, 1, baseline)
        b = module.prepare_plot(config["plots"][0], rows, 1, changed)
        self.assertEqual(a["books"], b["books"])
        self.assertNotEqual(a["commands"], b["commands"])
        self.assertIn("set Curve3 -w 1000", b["commands"])
        self.assertIn("set Curve3 -d 1", b["commands"])
        self.assertEqual(module.STYLE.LINE_IDS["solid"], 0)


if __name__ == "__main__":
    unittest.main()
