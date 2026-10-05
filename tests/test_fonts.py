"""Installed font names are explicit; unavailable families never fall back."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET

from matplotlib import font_manager

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.util.spec_from_file_location('font_draw', ROOT / 'scripts/ai2origin.py')
DRAW = importlib.util.module_from_spec(loader)
loader.loader.exec_module(DRAW)


class FontTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / 'input.csv'
        self.source.write_text('x,y\n1,2\n2,1\n3,4\n', encoding='utf-8')
        self.config = self.root / 'input.json'
        self.plot = {'id': 'curve', 'kind': 'line_symbol', 'csv': 'input.csv', 'x': 'x',
                     'labels': {'x': 'Coordinate', 'y': 'Value'},
                     'series': [{'column': 'y', 'label': 'Demo'}]}
        self.write_config()

    def write_config(self, font=None):
        style = {'export': {'raster_dpi': 72}}
        if font is not None:
            style['font'] = font
        self.config.write_text(json.dumps({'schema_version': 1, 'style': style,
                                           'plots': [self.plot]}), encoding='utf-8')

    def reject_family(self, missing):
        original = font_manager.findfont

        def exact_lookup(properties, *args, **kwargs):
            families = properties.get_family() if isinstance(properties, font_manager.FontProperties) else \
                font_manager.FontProperties(properties).get_family()
            if missing in families:
                raise ValueError('Synthetic missing installed family: ' + missing)
            return original(properties, *args, **kwargs)
        return exact_lookup

    def test_missing_default_arial_requires_local_choice_before_output(self):
        output = self.root / 'missing'
        with patch.object(DRAW, 'installed_font_names', return_value=['DejaVu Sans']), \
                patch.object(font_manager, 'findfont', side_effect=self.reject_family('Arial')), \
                patch.object(DRAW, 'render') as render, self.assertRaises(ValueError) as caught:
            DRAW.main([str(self.config), '--out', str(output), '--backend', 'python'])
        message = str(caught.exception)
        self.assertIn('Arial', message)
        self.assertRegex(message.lower(), r'choose|select')
        self.assertIn('--font', message)
        render.assert_not_called()
        self.assertFalse(output.exists())

    def test_blank_explicit_font_name_is_refused_before_output(self):
        output = self.root / 'blank'
        for name in ('', '   '):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'Font names'):
                DRAW.main([str(self.config), '--out', str(output), '--font', name])
            self.assertFalse(output.exists())

    def test_declared_fallback_does_not_replace_requested_family(self):
        missing = 'Ai2origin Missing Family'
        self.write_config({'family': missing, 'fallback_families': ['DejaVu Sans']})
        output = self.root / 'fallback'
        with patch.object(DRAW, 'installed_font_names', return_value=['DejaVu Sans']), \
                patch.object(font_manager, 'findfont', side_effect=self.reject_family(missing)), \
                patch.object(DRAW, 'render') as render, self.assertRaises(ValueError) as caught:
            DRAW.main([str(self.config), '--out', str(output), '--backend', 'python'])
        self.assertIn(missing, str(caught.exception))
        render.assert_not_called()
        self.assertFalse(output.exists())

    def test_wrong_family_returned_by_lookup_is_refused_before_output(self):
        available = font_manager.findfont(font_manager.FontProperties(family='DejaVu Sans'),
                                          fallback_to_default=False)
        output = self.root / 'substitution'
        with patch.object(font_manager, 'findfont', return_value=available), \
                patch.object(DRAW, 'render') as render, self.assertRaisesRegex(ValueError, 'actual installed font name'):
            DRAW.main([str(self.config), '--out', str(output), '--backend', 'python'])
        render.assert_not_called()
        self.assertFalse(output.exists())

    def test_unrelated_unsupported_system_face_does_not_enable_fallback(self):
        unsupported, readable = '/synthetic/unsupported.ttf', '/synthetic/readable.ttf'
        resolved, _ = DRAW.STYLE.resolve(DRAW.load_json,
            project={'font': {'family': 'DejaVu Sans', 'fallback_families': []}})
        for problem in (OSError, RuntimeError):
            def register(path):
                if path == unsupported:
                    raise problem('Synthetic unsupported face')
            with self.subTest(problem=problem.__name__), \
                    patch.object(DRAW, '_SYSTEM_FONTS_LOADED', False), \
                    patch.object(Path, 'is_dir', return_value=True), \
                    patch.object(font_manager, 'findSystemFonts', return_value=[unsupported, readable]), \
                    patch.object(font_manager.fontManager, 'addfont', side_effect=register) as addfont:
                DRAW.ensure_system_fonts()
                self.assertEqual({call.args[0] for call in addfont.call_args_list}, {unsupported, readable})
                self.assertEqual(DRAW.preview_font(self.plot, [{'x': '1', 'y': '2'}], resolved), 'DejaVu Sans')
                default, _ = DRAW.STYLE.resolve(DRAW.load_json)
                with patch.object(font_manager, 'findfont', side_effect=self.reject_family('Arial')), \
                        self.assertRaisesRegex(ValueError, 'choose --font'):
                    DRAW.preview_font(self.plot, [{'x': '1', 'y': '2'}], default)

    def test_explicit_installed_name_is_recorded_and_svg_stays_editable(self):
        output = self.root / 'named'
        with contextlib.redirect_stdout(io.StringIO()):
            DRAW.main([str(self.config), '--out', str(output), '--backend', 'python',
                       '--font', 'DejaVu Sans', '--svg'])
        receipt = json.loads((output / 'receipt.json').read_text())
        self.assertEqual(receipt['requested_font'], 'DejaVu Sans')
        self.assertEqual(receipt['actual_python_fonts'], ['DejaVu Sans'])
        self.assertEqual([font['family'] for font in receipt['font_provenance']], ['DejaVu Sans'])
        self.assertRegex(receipt['font_provenance'][0]['sha256'], r'^[0-9a-f]{64}$')
        self.assertNotIn('provided_font', receipt)
        plan = json.loads((output / 'origin-plan.json').read_text())
        self.assertEqual(plan['style']['font']['family'], 'DejaVu Sans')
        svg = output / 'curve.svg'
        tree = ET.parse(svg)
        texts = [node for node in tree.iter() if node.tag.rsplit('}', 1)[-1] == 'text']
        self.assertTrue(texts)
        self.assertIn('DejaVu Sans', svg.read_text())
        self.assertFalse(any(path.suffix.lower() in ('.ttf', '.otf', '.ttc') for path in output.iterdir()))

    def test_font_listing_needs_no_config_output_or_drawing(self):
        available = ['Arial', 'DejaVu Sans']
        captured = io.StringIO()
        before = set(self.root.iterdir())
        with patch.object(DRAW, 'installed_font_names', return_value=available), \
                patch.object(DRAW, 'load_json', side_effect=AssertionError('Font listing must not read config')), \
                patch.object(DRAW, 'read_csv', side_effect=AssertionError('Font listing must not read data')), \
                patch.object(DRAW, 'prepare_plot', side_effect=AssertionError('Font listing must not prepare plots')), \
                patch.object(DRAW, 'render', side_effect=AssertionError('Font listing must not draw')), \
                contextlib.redirect_stdout(captured):
            DRAW.main(['--list-fonts'])
        self.assertEqual(json.loads(captured.getvalue()), available)
        self.assertEqual(set(self.root.iterdir()), before)

    def test_installed_family_listing_contains_available_local_font(self):
        DRAW.ensure_system_fonts()
        families = DRAW.installed_font_names()
        self.assertIsInstance(families, list)
        self.assertTrue(all(isinstance(name, str) and name.strip() for name in families))
        self.assertEqual(len(families), len(set(families)))
        self.assertIn('DejaVu Sans', families)


if __name__ == '__main__':
    unittest.main()
