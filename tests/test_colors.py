import importlib.util
from pathlib import Path
import tempfile
import unittest
import numpy as np
from matplotlib.colors import to_hex

ROOT=Path(__file__).resolve().parents[1]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
a=module('colors_renderer',ROOT/'scripts/ai2origin.py')
g=module('colors_samples',ROOT/'scripts/make_samples.py')

class ColorTests(unittest.TestCase):
    def test_author_stops_and_endpoints_are_exact(self):
        expected={'reimu26':['#440154','#31688E','#35B779','#90D743','#FDE725'],
                  'reimu27':['#0D0887','#7E03A8','#CC4778','#F89441','#F0F921']}
        for name,stops in expected.items():
            cmap=a.color_map({'cmap':name,'color_levels':5})
            self.assertEqual([to_hex(cmap(v)).upper() for v in np.linspace(0,1,5)],stops)

    def test_reverse_is_exact_at_all_supported_level_counts(self):
        for levels in (2,3,16,17,255,256):
            forward=a.color_map({'cmap':'rainbow','color_levels':levels})
            reverse=a.color_map({'cmap':'rainbow_r','color_levels':levels})
            np.testing.assert_array_equal(np.array(reverse.colors),np.array(forward.colors)[::-1])

    def test_seven_default_identities_and_neutral_default_map(self):
        style,_=a.STYLE.resolve(a.load_json)
        self.assertEqual(style['colors']['palette'],['#B2182B','#2166AC','#1B9E77','#7560A8','#E4872A','#737373','#CC79A7'])
        self.assertEqual(len(set(style['colors']['palette'])),7)
        self.assertEqual(to_hex(a.color_map({})(.5)).upper(),'#F7F7F7')

    def test_palette_changes_no_data_or_display_grid(self):
        config=a.load_json(ROOT/'samples/colors.json');style,_=a.STYLE.resolve(a.load_json)
        values=[]
        for plot in config['plots'][1:]:
            rows=a.read_csv(ROOT/'samples'/plot['csv']);result=a.prepare_plot(plot,rows,1,style)
            values.append(result['books'])
            self.assertEqual(len(result['metadata']['colorbar_palette']),256)
        for books in values[1:]:self.assertEqual(books,values[0])

    def test_color_examples_regenerate_from_toy_formulas(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'new';g.make_samples(target)
            for name in ['colors.json','colors-map.csv','colors-lines.csv']:
                self.assertEqual((target/name).read_bytes(),(ROOT/'samples'/name).read_bytes())

    def test_walkthrough_retains_all_360_points_and_regenerates(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'new';g.make_samples(target)
            for name in ['walkthrough.json','walkthrough.csv']:
                self.assertEqual((target/name).read_bytes(),(ROOT/'samples'/name).read_bytes())
        config=a.load_json(ROOT/'samples/walkthrough.json');style,_=a.STYLE.resolve(a.load_json,project=config['style'])
        plot=config['plots'][0];rows=a.read_csv(ROOT/'samples/walkthrough.csv');prepared=a.prepare_plot(plot,rows,1,style)
        matrix=np.array(prepared['books'][0]['rows'])
        self.assertEqual(matrix.shape,(120,12))
        for i,letter in enumerate('abc'):
            np.testing.assert_array_equal(matrix[:,4*i],np.arange(1,121))
            np.testing.assert_array_equal(matrix[:,4*i+1],[float(r['capacity_'+letter]) for r in rows])
            np.testing.assert_array_equal(matrix[:,4*i:4*i+2],matrix[:,4*i+2:4*i+4])

if __name__=='__main__':unittest.main()
