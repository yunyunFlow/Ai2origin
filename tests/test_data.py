import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ai2origin", ROOT / "scripts" / "ai2origin.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DataTests(unittest.TestCase):
    def assert_synthetic_csv_matches(self, actual, expected):
        with actual.open(newline='', encoding='utf-8') as handle:
            actual_rows = list(csv.reader(handle))
        with expected.open(newline='', encoding='utf-8') as handle:
            expected_rows = list(csv.reader(handle))
        self.assertEqual(actual_rows[0], expected_rows[0])
        self.assertEqual(len(actual_rows), len(expected_rows))
        for got, wanted in zip(actual_rows[1:], expected_rows[1:]):
            self.assertEqual(len(got), len(wanted))
            for value, original in zip(got, wanted):
                try:
                    number = float(original)
                except ValueError:
                    self.assertEqual(value, original)
                else:
                    self.assertTrue(np.isfinite(number) and np.isfinite(float(value)))
                    np.testing.assert_allclose(float(value), number, rtol=1e-12, atol=1e-12)

    def test_scott_cloud_fill_preserves_geometry_and_observations(self):
        config=module.load_json(ROOT/'templates/clouds.json')
        plot=next(p for p in config['plots'] if p['id']=='violin-vertical')
        rows=module.read_csv(ROOT/'samples/raincloud.csv')
        groups=module.raincloud_geometry(rows,plot)
        for group in groups:
            values=group['values']
            self.assertAlmostEqual(group['bandwidth'],np.std(values,ddof=1)*len(values)**(-.2))
            segment=group['segments'][0]
            self.assertEqual(segment['grid'][0],min(values))
            self.assertEqual(segment['grid'][-1],max(values))
        style,_=module.STYLE.resolve(module.load_json,project=config['style'])
        prepared=module.prepare_plot(plot,rows,5,style)
        book=prepared['books'][0]
        for i,group in enumerate(groups):
            offset=4*i
            polygon=np.array([[r[offset],r[offset+1]] for r in book['rows'] if r[offset] is not None])
            np.testing.assert_array_equal(polygon[0],polygon[-1])
            self.assertEqual(len(polygon),1025)
            observations=[r[offset+3] for r in book['rows'] if r[offset+3] is not None]
            np.testing.assert_array_equal(observations,group['values'])
        self.assertEqual(sum(len(g['values']) for g in groups),76)
        self.assertEqual(sum(c.endswith(' -w 0') for c in prepared['commands']),3)

    def test_public_maps_are_toy_rwb_and_no_psd_source(self):
        self.assertFalse((ROOT / 'samples/psd.csv').exists())
        maps = []
        for family in ('samples/demo.json', 'templates/paper.json'):
            config = module.load_json(ROOT / family)
            for plot in config['plots']:
                if plot['kind'] == 'heatmap':
                    maps.append(plot)
                    self.assertEqual(plot['cmap'], ['#2166AC', '#F7F7F7', '#B2182B'])
                    self.assertTrue(plot['synthetic'])
                    if 'caption' in plot:
                        self.assertIn('invented', plot['caption'].lower())
                    self.assertNotIn('psd', plot['csv'].lower())
        self.assertEqual(len(maps), 3)
        raw = module.read_csv(ROOT / 'samples/xrd.csv')
        self.assertEqual(len(raw), 9 * 141)
        raw = module.read_csv(ROOT / 'templates/drt-map.csv')
        self.assertEqual(len(raw), 9 * 81)

    def test_log_display_preserves_nodes_and_native_axis(self):
        rows = [{'x':x,'y':y,'z':np.log10(x)+y} for y in (0,2) for x in (1e-3,1,1e5)]
        spec={'x':'x','y':'y','z':'z','x_scale':'log10','interpolation':{'method':'bilinear','factor':8}}
        x,y,z,raw,_=module.heatmap_display(rows,spec)
        np.testing.assert_array_equal(x[::8],raw[0])
        np.testing.assert_array_equal(z[::8,::8],raw[2])
        np.testing.assert_allclose(z,np.log10(x)[None,:]+y[:,None])
        config=module.load_json(ROOT/'templates/paper.json')
        drt=next(p for p in config['plots'] if p['id']=='drt')
        style,_=module.STYLE.resolve(module.load_json,project=config['style'])
        data=module.read_csv(ROOT/'templates/drt.csv')
        plan=module.prepare_plot(drt,data,1,style)
        self.assertIn('layer.x.type=2',plan['commands'])
        self.assertEqual(plan['metadata']['x_range'],[1e-3,1e5])
        with self.assertRaises(ValueError):
            module.prepare_plot(dict(drt,equal_xy=True),data,1,style)

    def test_neb_pchip_retains_nodes_and_interval_bounds(self):
        x=np.arange(7,dtype=float);y=np.array([0,.12,.4,.7,.45,.2,.06])
        dx,dy=module.pchip_connection(x,y,16)
        np.testing.assert_array_equal(dx[::16],x)
        np.testing.assert_allclose(dy[::16],y,atol=1e-15)
        for i in range(6):
            self.assertGreaterEqual(dy[i*16:(i+1)*16+1].min(),min(y[i:i+2])-1e-15)
            self.assertLessEqual(dy[i*16:(i+1)*16+1].max(),max(y[i:i+2])+1e-15)

    def test_legend_avoids_occupied_corner_and_opposite_ticks_off(self):
        spec={'id':'corner','kind':'line','x':'x','series':[{'column':'y','label':'A'}],
              'labels':{'x':'x','y':'y'},'x_range':[0,1],'y_range':[0,1]}
        rows=[{'x':x,'y':.94} for x in np.linspace(0,.4,41)]
        corner,_,_,costs=module.legend_corner(spec,rows)
        self.assertEqual(costs[corner],0)
        self.assertGreater(costs['upper left'],0)
        style,_=module.STYLE.resolve(module.load_json)
        plan=module.prepare_plot(spec,rows,1,style)
        self.assertIn('layer.x2.ticks=0',plan['commands'])
        self.assertIn('layer.y2.ticks=0',plan['commands'])
        self.assertEqual(module.display_label('Wavenumber (cm^-1)',True),'"Wavenumber (cm\\+(-1))"')
        with self.assertRaises(ValueError):
            module.display_label('cm^-1";run',True)

    def test_article_sources_and_stored_ols_regenerate(self):
        generator_spec = importlib.util.spec_from_file_location("make_templates", ROOT / "scripts/make_templates.py")
        generator = importlib.util.module_from_spec(generator_spec)
        generator_spec.loader.exec_module(generator)
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "templates"
            generator.make_templates(target)
            for path in target.iterdir():
                if path.suffix == ".json":
                    self.assertEqual(module.load_json(path), module.load_json(ROOT / "templates" / path.name))
                else:
                    actual = module.read_csv(path)
                    stored = module.read_csv(ROOT / "templates" / path.name)
                    self.assertEqual(len(actual), len(stored))
                    self.assertEqual(list(actual[0]), list(stored[0]))
                    for key in actual[0]:
                        # BLAS/LAPACK roundoff may change the last OLS digits.
                        np.testing.assert_allclose(module.column(actual, key), module.column(stored, key), rtol=3e-14, atol=1e-14)
        rows = module.read_csv(ROOT / "templates/analysis.csv")
        x, y, fitted, residual = (module.column(rows, k) for k in ("x", "y", "fitted", "residual"))
        design = np.column_stack([x, np.ones_like(x)])
        np.testing.assert_allclose(fitted, design @ np.linalg.lstsq(design, y, rcond=None)[0], atol=1e-14)
        np.testing.assert_allclose(y, fitted + residual, atol=1e-14)
        np.testing.assert_allclose(design.T @ residual, 0, atol=1e-13)

    def test_mixed_series_and_equal_xy_contract(self):
        config = module.load_json(ROOT / "templates/paper.json")
        style, _ = module.STYLE.resolve(module.load_json, project=config["style"])
        for index, spec in enumerate(config["plots"], 1):
            rows = module.read_csv(ROOT / "templates" / spec["csv"])
            plan = module.prepare_plot(spec, rows, index, style)
            self.assertFalse(any(c.startswith("label -n Legend ") for c in plan["commands"]))
            if spec["id"] == "nyquist":
                height = float(next(c.split("=")[1] for c in reversed(plan["commands"]) if c.startswith("layer.height=")))
                width = float(next(c.split("=")[1] for c in reversed(plan["commands"]) if c.startswith("layer.width=")))
                self.assertEqual(spec['x_range'],spec['y_range'])
                self.assertAlmostEqual((width*90/30)/(height*70/30), 1)
            if spec["id"] == "association":
                plot_commands = [c for c in plan["commands"] if c.startswith("plotxy ")]
                self.assertIn("plot:=201", plot_commands[0])
                self.assertIn("plot:=200", plot_commands[1])
                broken = dict(spec, series=[dict(spec["series"][0], kind="line")])
                with self.assertRaisesRegex(ValueError, "increasing"):
                    module.prepare_plot(broken, list(reversed(rows)), index, style)
        bad = dict(next(p for p in config['plots'] if p['id']=='cv'), x_tick_step=0)
        with self.assertRaisesRegex(ValueError, "Tick step"):
            module.prepare_plot(bad, module.read_csv(ROOT / "templates/electrochem.csv"), 1, style)

    def test_checked_in_synthetic_sources_regenerate(self):
        generator_spec = importlib.util.spec_from_file_location("make_samples", ROOT / "scripts" / "make_samples.py")
        generator = importlib.util.module_from_spec(generator_spec)
        generator_spec.loader.exec_module(generator)
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "synthetic"
            generator.make_samples(target)
            for name in ("xy.csv", "heatmap.csv", "raincloud.csv", "xrd.csv", "demo.json"):
                if name.endswith(".json"):
                    self.assertEqual(module.load_json(target / name), module.load_json(ROOT / "samples" / name))
                else:
                    self.assert_synthetic_csv_matches(target / name, ROOT / "samples" / name)

    def test_synthetic_regeneration_roundoff_and_meaningful_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            actual = Path(tmp) / 'xy.csv'
            expected = ROOT / 'samples' / 'xy.csv'
            with expected.open(newline='', encoding='utf-8') as handle:
                rows = list(csv.reader(handle))

            def write(changed):
                with actual.open('w', newline='', encoding='utf-8') as handle:
                    csv.writer(handle).writerows(changed)

            rounded = [list(row) for row in rows]
            rounded[1][1] = str(np.nextafter(float(rounded[1][1]), np.inf))
            write(rounded)
            self.assert_synthetic_csv_matches(actual, expected)

            shifted = [list(row) for row in rows]
            shifted[1][1] = str(float(shifted[1][1]) + 0.001)
            renamed = [list(row) for row in rows]
            renamed[0][1] = 'wrong_column'
            for name, changed in [('value', shifted), ('column', renamed), ('row', rows[:-1])]:
                with self.subTest(changed=name):
                    write(changed)
                    with self.assertRaises(AssertionError):
                        self.assert_synthetic_csv_matches(actual, expected)

            expected = ROOT / 'samples' / 'raincloud.csv'
            with expected.open(newline='', encoding='utf-8') as handle:
                grouped = list(csv.reader(handle))
            grouped[1][1] = 'wrong_group'
            write(grouped)
            with self.assertRaises(AssertionError):
                self.assert_synthetic_csv_matches(actual, expected)

    def test_heatmap_orientation_and_irregular_coordinates(self):
        rows = [{"x": x, "y": y, "z": x + 10*y} for y in (2, 7) for x in (1, 3, 9)]
        xs, ys, matrix = module.heatmap_grid(rows, "x", "y", "z")
        np.testing.assert_array_equal(xs, [1, 3, 9])
        np.testing.assert_array_equal(ys, [2, 7])
        np.testing.assert_array_equal(matrix, [[21, 23, 29], [71, 73, 79]])

    def test_duplicate_and_missing_cells_refused(self):
        rows = [{"x": x, "y": y, "z": x+y} for y in (0, 1) for x in (0, 1)]
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            module.heatmap_grid(rows + [rows[0]], "x", "y", "z")
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            module.heatmap_grid(rows[:-1], "x", "y", "z")

    def test_smooth_display_preserves_irregular_grid_nodes_and_bounds(self):
        rows = [{"x": x, "y": y, "z": 2*x + 3*y} for y in (2, 7, 8) for x in (1, 3, 9)]
        spec = {"x":"x", "y":"y", "z":"z", "interpolation":{"method":"bilinear", "factor":3}}
        x, y, z, raw, method = module.heatmap_display(rows, spec)
        np.testing.assert_array_equal(z[::3, ::3], raw[2])
        np.testing.assert_allclose(z, 2*x[None,:]+3*y[:,None])
        self.assertGreaterEqual(z.min(), raw[2].min())
        self.assertLessEqual(z.max(), raw[2].max())
        self.assertEqual(method, "bilinear factor=3")
        with self.assertRaises(ValueError):
            module.heatmap_display(rows[:-1], spec)

    def test_full_vertical_cloud_is_symmetric_and_preserves_rain_values(self):
        config = module.load_json(ROOT / "templates/clouds.json")
        spec = next(p for p in config['plots'] if p['id']=='violin-vertical')
        rows = module.read_csv(ROOT / "samples/raincloud.csv")
        geometry = module.raincloud_geometry(rows, spec)
        for g in geometry:
            np.testing.assert_allclose(g["cloud_top"]+g["cloud_bottom"], 2*g["index"])
        style, _ = module.STYLE.resolve(module.load_json, project=config["style"])
        book = module.prepare_plot(spec, rows, 5, style)["books"][0]
        columns = [i for i,h in enumerate(book["headers"]) if h.startswith("observations") and h.endswith("_y")]
        values = [row[i] for i in columns for row in book["rows"] if row[i] is not None]
        np.testing.assert_array_equal(sorted(values), sorted(module.column(rows, "value")))

    def test_cv_acquisition_order_and_stack_raw_values_are_preserved(self):
        style, _ = module.STYLE.resolve(module.load_json)
        rows = [{"x":x,"y":y} for x,y in zip([0,1,0], [3,5,4])]
        spec = {"id":"cv", "kind":"line", "x":"x", "series":[{"column":"y", "label":"Cycle", "offset":2}],
                "labels":{"x":"x", "y":"y"}, "connect_order":"acquisition"}
        plot = module.prepare_plot(spec, rows, 1, style)
        np.testing.assert_array_equal(plot["books"][0]["rows"], [[0,3,0,5],[1,5,1,7],[0,4,0,6]])
        with self.assertRaises(ValueError):
            module.prepare_plot(dict(spec, connect_order="increasing"), rows, 1, style)
        with self.assertRaises(ValueError):
            module.prepare_plot(dict(spec, log_y=True), rows, 1, style)

    def test_negative_outlier_and_duplicate_observations_preserved(self):
        values = [-9, -1, -1, 0, 2, 12]
        rows = [{"group": "A", "value": v} for v in values]
        result = module.raincloud_geometry(rows, {"group": "group", "value": "value", "bandwidth": 0.4})
        np.testing.assert_array_equal(result[0]["values"], values)
        self.assertEqual(len(result[0]["jitter_y"]), len(values))
        self.assertEqual(result[0]["median"], -0.5)
        self.assertEqual(result[0]["whiskers"], [-1, 2])
        self.assertLess(result[0]["grid"][0], -9)
        self.assertGreater(result[0]["grid"][-1], 12)

    def test_observed_cloud_keeps_exact_kde_and_all_points(self):
        values=[-2,-1.9,-1.8,2,2.1,2.2]
        rows=[{'group':'A','value':v} for v in values]
        spec={'id':'cloud','kind':'raincloud','group':'group','value':'value','bandwidth':.2,
              'cloud_support':'observed','summary':False,'labels':{'x':'Value','y':'Group'}}
        g=module.raincloud_geometry(rows,spec)[0]
        self.assertEqual(len(g['segments']),1)
        np.testing.assert_array_equal(g['values'],values)
        for seg in g['segments']:
            self.assertGreaterEqual(seg['grid'][0],min(values))
            self.assertLessEqual(seg['grid'][-1],max(values))
            exact=module.density(np.array(values),seg['grid'],.2)
            peak=float(g['density'].max())
            np.testing.assert_allclose(seg['top'],1.10+.30*exact/peak)
        style,_=module.STYLE.resolve(module.load_json)
        p=module.prepare_plot(spec,rows,1,style)
        self.assertFalse(any('median' in h or 'box' in h or 'whisker' in h for h in p['books'][0]['headers']))

    def test_jitter_seed_deterministic_and_values_unchanged(self):
        rows = [{"group": "A", "value": v} for v in [0, 1, 2, 3]]
        config = {"group": "group", "value": "value", "bandwidth": 0.3, "seed": 7}
        a = module.raincloud_geometry(rows, config)[0]
        b = module.raincloud_geometry(rows, config)[0]
        c = module.raincloud_geometry(rows, dict(config, seed=8))[0]
        np.testing.assert_array_equal(a["jitter_y"], b["jitter_y"])
        self.assertFalse(np.array_equal(a["jitter_y"], c["jitter_y"]))
        np.testing.assert_array_equal(a["values"], c["values"])

    def test_constant_and_small_samples_do_not_fabricate_kde(self):
        rows = [{"group": group, "value": v} for group, vals in [("one", [2]), ("constant", [4, 4, 4])] for v in vals]
        result = module.raincloud_geometry(rows, {"group": "group", "value": "value", "bandwidth": 0.3})
        self.assertTrue(all(g["density"] is None for g in result))
        self.assertEqual(sum(len(g["values"]) for g in result), 4)

    def test_reflected_density_normalization_and_bound_refusal(self):
        rows = [{"group": "A", "value": v} for v in [0.02, 0.05, 0.15, 0.6]]
        spec = {"group": "group", "value": "value", "bandwidth": 0.15, "bounds": [0, 1]}
        result = module.raincloud_geometry(rows, spec)[0]
        integrate = getattr(np, "trapezoid", np.trapz if hasattr(np, "trapz") else None)
        # Density is normalized by analytic Gaussian mass; quadrature is an
        # independent approximation rather than the normalization itself.
        self.assertAlmostEqual(float(integrate(result["density"], result["grid"])), 1, places=6)
        with self.assertRaisesRegex(ValueError, "outside"):
            module.raincloud_geometry(rows, dict(spec, bounds=[0.1, 1]))

    def test_nonfinite_and_csv_schema_refused(self):
        with self.assertRaisesRegex(ValueError, "Non-finite"):
            module.column([{"x": "NaN"}], "x")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.csv"
            path.write_text("x,x\n1,2\n")
            with self.assertRaisesRegex(ValueError, "unique"):
                module.read_csv(path)
            path.write_text("x,y\n1\n")
            with self.assertRaisesRegex(ValueError, "width"):
                module.read_csv(path)

    def test_duplicate_json_and_injected_labels_refused(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            json.loads('{"x":1,"x":2}', object_pairs_hook=module.unique_object)
        with self.assertRaisesRegex(ValueError, "control"):
            module.lt_string('Axis";run')

    def test_native_rain_coordinates_preserve_actual_sample_count(self):
        config = module.load_json(ROOT / "templates/clouds.json")
        spec = next(p for p in config['plots'] if p['id']=='cloud-horizontal')
        rows = module.read_csv(ROOT / "samples" / "raincloud.csv")
        style, _ = module.STYLE.resolve(module.load_json, project=config["style"])
        plot = module.prepare_plot(spec, rows, 3, style)
        book = plot["books"][0]
        columns = [i for i, h in enumerate(book["headers"]) if h.startswith("observations") and h.endswith("_x")]
        values = [row[i] for i in columns for row in book["rows"] if row[i] is not None]
        np.testing.assert_allclose(sorted(values), sorted(module.column(rows, "value")), rtol=0, atol=0)
        self.assertEqual(sum(g["n"] for g in plot["metadata"]["groups"]), 76)
        self.assertEqual(len(book["headers"]), len(set(book["headers"])))

    def test_generation_refuses_existing_directory_before_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "existing"
            out.mkdir()
            sentinel = out / "keep.txt"
            sentinel.write_text("keep")
            with self.assertRaises(FileExistsError):
                module.main([str(ROOT / "samples" / "demo.json"), "--out", str(out)])
            self.assertEqual(list(out.iterdir()), [sentinel])
            self.assertEqual(sentinel.read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
