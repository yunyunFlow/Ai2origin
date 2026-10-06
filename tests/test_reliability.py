"""Independent numerical invariants and observed failure regressions."""
import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
loader=importlib.util.spec_from_file_location('a2o',ROOT/'scripts/ai2origin.py')
a=importlib.util.module_from_spec(loader);loader.loader.exec_module(a)


class ReliabilityTests(unittest.TestCase):
    def test_half_cloud_gap_translates_only_group_coordinate(self):
        rows=[{'g':'A','v':v} for v in [-2.,-.3,.4,.4,1.8]]
        spec={'group':'g','value':'v','bandwidth':'scott','cloud_shape':'half','cloud_support':'observed','seed':77}
        old=a.raincloud_geometry(rows,spec)[0]
        for orientation in ('horizontal','vertical'):
            new=a.raincloud_geometry(rows,dict(spec,point_cloud_gap=.24,orientation=orientation))[0]
            repeat=a.raincloud_geometry(rows,dict(spec,point_cloud_gap=.24,orientation=orientation))[0]
            for key in ('values','grid','density','cloud_top','cloud_bottom'):
                np.testing.assert_array_equal(new[key],old[key])
            np.testing.assert_allclose(new['jitter_y']-old['jitter_y'],.08,rtol=0,atol=3e-16)
            np.testing.assert_array_equal(new['jitter_y'],repeat['jitter_y'])
            self.assertTrue(np.all(new['jitter_y'] < 1.10))
        style,_=a.STYLE.resolve(a.load_json)
        prepared=a.prepare_plot(dict(spec,id='cloud',kind='raincloud',labels={'x':'Value','y':'Group'},point_cloud_gap=.24),rows,1,style)
        self.assertEqual(prepared['metadata']['point_cloud_gap'],.24)
    def test_half_cloud_gap_refuses_invalid_or_inert_settings(self):
        rows=[{'g':'A','v':v} for v in [1.,2.,3.]]
        spec={'group':'g','value':'v','bandwidth':'scott'}
        for gap in [True,False,-.2,0,.05,.46,float('nan'),float('inf')]:
            with self.subTest(gap=gap),self.assertRaises(ValueError):a.raincloud_geometry(rows,dict(spec,point_cloud_gap=gap))
        with self.assertRaises(ValueError):a.raincloud_geometry(rows,dict(spec,cloud_shape='full',point_cloud_gap=.24))
    def test_heatmap_center_refused_before_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'map.csv').write_text('x,y,z\n0,0,1\n0,1,1\n1,0,1\n1,1,1\n')
            plot = {'id':'map','kind':'heatmap','csv':'map.csv','x':'x','y':'y','z':'z',
                    'labels':{'x':'x','y':'y','color':'z'}}
            for bounds, center in [([0,2],True),([0,2],'1'),([0,2],None),
                                   ([0,2],float('inf')),([1,1.0000000001],1),
                                   ([1,1.0000000001],1.0000000001)]:
                (root/'config.json').write_text(json.dumps({'schema_version':1,
                    'plots':[dict(plot,color_range=bounds,center=center)]}))
                with self.subTest(center=center), self.assertRaises(ValueError):
                    a.main([str(root/'config.json'),'--out',str(root/'out'),'--backend','prepare'])
                self.assertFalse((root/'out').exists())
            rows = a.read_csv(root/'map.csv')
            self.assertEqual(a.prepare_plot(dict(plot,color_range=[0,2],center=1),rows,1,self.style)
                             ['metadata']['color_range'],[0,2])

    def test_implicit_cloud_labels_checked_before_output(self):
        style = {'font':{'family':'DejaVu Sans','fallback_families':[]}}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for observed, labels in [('\U0010ffff',{}),('A',{'A':'\U0010ffff'})]:
                (root/'cloud.csv').write_text('g,v\n'+''.join(f'{observed},{v}\n' for v in [1,2,3]))
                plot = dict(self.cloud,csv='cloud.csv',group_labels=labels)
                (root/'config.json').write_text(json.dumps({'schema_version':1,'style':style,'plots':[plot]}))
                with self.subTest(labels=labels), self.assertRaisesRegex(ValueError,'glyph'):
                    a.main([str(root/'config.json'),'--out',str(root/'out'),'--backend','python'])
                self.assertFalse((root/'out').exists())
            resolved,_=a.STYLE.resolve(a.load_json,project=style)
            self.assertEqual(a.preview_font(self.cloud,[{'g':'A','v':v} for v in [1,2,3]],resolved),'DejaVu Sans')

    def test_numeric_source_underflow_is_refused(self):
        with self.assertRaisesRegex(ValueError,'Underflow'):
            a.column([{'x':'1e-400'}],'x')
        np.testing.assert_array_equal(a.column([{'x':'0e-999'},{'x':'-0'},{'x':'5e-324'}],'x'),[0,-0.,5e-324])

    def setUp(self):
        self.style,_=a.STYLE.resolve(a.load_json)
        self.xy=[{'x':x,'y':y} for x,y in zip([1,2,3],[2,3,4])]
        self.line={'id':'curve','kind':'line','x':'x','series':[{'column':'y','label':'A'}],
                   'labels':{'x':'x','y':'y'}}
        self.cloud={'id':'cloud','kind':'raincloud','group':'g','value':'v','bandwidth':'scott',
                    'cloud_shape':'full','cloud_support':'observed','density_scale':'width',
                    'labels':{'x':'Group','y':'Value'}}

    def test_separated_cloud_scales_have_bounded_width(self):
        rows=[{'g':g,'v':v} for g,vs in [('A',[0,.001,.002]),('B',[100,101,102])] for v in vs]
        for scaling in ('width','shared'):
            gs=a.raincloud_geometry(rows,dict(self.cloud,density_scale=scaling))
            for g in gs:
                s=g['segments'][0]
                self.assertTrue(np.all(np.isfinite(s['top'])))
                self.assertLessEqual(float(np.max(s['top']-g['index'])),.26+1e-14)
                if scaling=='width':self.assertAlmostEqual(float(np.max(s['top']-g['index'])),.26)
                np.testing.assert_array_equal(g['values'],[r['v'] for r in rows if r['g']==g['group']])

    def test_narrow_central_mode_is_resolved(self):
        rows=[{'g':'A','v':v} for v in [0,50,50,50,100]]
        for support in ('kde','observed'):
            g=a.raincloud_geometry(rows,dict(self.cloud,bandwidth=.001,cloud_support=support))[0]
            center=np.flatnonzero(g['grid']==50)
            self.assertEqual(len(center),1)
            self.assertGreater(g['density'][center[0]],3*.999/(5*.001*np.sqrt(2*np.pi)))
            self.assertEqual(float(g['grid'][np.argmax(g['density'])]),50)

    def test_reflected_narrow_kernel_has_finite_exact_density(self):
        rows=[{'g':'A','v':v} for v in [.1,.100001,.100002]]
        g=a.raincloud_geometry(rows,dict(self.cloud,bandwidth=1e-6,bounds=[0,100],cloud_support='kde'))[0]
        self.assertTrue(np.all(np.isfinite(g['density'])))
        at=np.flatnonzero(g['grid']==.100001)[0]
        expected=(1+2*np.exp(-.5))/(3*1e-6*np.sqrt(2*np.pi))
        self.assertAlmostEqual(g['density'][at]/expected,1,places=8)

    def test_omitted_cloud_does_not_invent_bandwidth(self):
        rows=[{'g':'A','v':1},{'g':'B','v':2},{'g':'B','v':2},{'g':'B','v':2}]
        gs=a.raincloud_geometry(rows,self.cloud)
        self.assertTrue(all(g['bandwidth'] is None and not g['segments'] for g in gs))
        self.assertEqual(sum(len(g['values']) for g in gs),4)

    def test_unsorted_scatter_band_is_refused(self):
        spec=dict(self.line,kind='scatter',series=[{'column':'y','label':'A','lower':'lo','upper':'hi','uncertainty_definition':'stored interval'}])
        rows=[{'x':x,'y':2,'lo':1,'hi':3} for x in [1,3,2]]
        with self.assertRaisesRegex(ValueError,'increasing X'):a.prepare_plot(spec,rows,1,self.style)
        spec['series']=[{'column':'y','label':'A'}]
        p=a.prepare_plot(spec,rows,1,self.style)
        np.testing.assert_array_equal(p['books'][0]['rows'],[[1,2],[3,2],[2,2]])

    def test_boolean_and_string_provenance_are_refused(self):
        for bad in ('false',0,1,None):
            with self.subTest(value=bad),self.assertRaisesRegex(ValueError,'boolean'):
                a.prepare_plot(dict(self.line,synthetic=bad),self.xy,1,self.style)
        for valid in (False,True):a.prepare_plot(dict(self.line,synthetic=valid),self.xy,1,self.style)

    def test_seed_is_an_integer_without_truncation(self):
        for bad in (1.9,True,'1'):
            with self.subTest(value=bad),self.assertRaisesRegex(ValueError,'integer'):
                a.raincloud_geometry([{'g':'A','v':v} for v in [1,2,3]],dict(self.cloud,seed=bad))

    def test_boolean_numeric_settings_are_refused(self):
        for setting in ({'x_tick_step':True},{'x_range':[True,3]},
                        {'series':[{'column':'y','label':'A','offset':True}]}):
            with self.subTest(setting=setting),self.assertRaisesRegex(ValueError,'number'):
                a.prepare_plot(dict(self.line,**setting),self.xy,1,self.style)
        with self.assertRaisesRegex(ValueError,'number'):
            a.raincloud_geometry([{'g':'A','v':v} for v in [1,2,3]],dict(self.cloud,bandwidth=True))

    def test_unsupported_or_inert_connection_is_refused(self):
        rows=[{'x':x,'y':y,'z':x+y} for x in (0,1) for y in (0,1)]
        spec={'id':'map','kind':'heatmap','x':'x','y':'y','z':'z','color_range':[0,2],
              'labels':{'x':'x','y':'y','color':'z'}}
        for bad in ('pchip','garbage'):
            with self.assertRaisesRegex(ValueError,'Unsupported'):a.prepare_plot(dict(spec,connection=bad),rows,1,self.style)
        with self.assertRaisesRegex(ValueError,'requires pchip'):
            a.prepare_plot(dict(self.line,connection_factor=16),self.xy,1,self.style)

    def test_colorbar_tick_precision_retains_distinct_values(self):
        for limits in ([1,1.001],[1e-8,1.0001e-8],[-1,1],[0,1]):
            labels=a.colorbar_labels(limits)
            self.assertEqual(len(set(labels)),5)
            np.testing.assert_allclose([float(v) for v in labels],np.linspace(*limits,5),rtol=1e-4,atol=1e-12)
            self.assertLessEqual(max(abs(np.array([float(v) for v in labels])-np.linspace(*limits,5))),min(np.diff(np.linspace(*limits,5)))*.01)

    def test_declared_midpoint_is_exact_for_even_and_odd_palettes(self):
        from matplotlib.colors import to_hex
        for levels in (3,16,17,256):
            cmap=a.color_map({'cmap':['#2166AC','#F7F7F7','#B2182B'],'center':0,'color_levels':levels})
            self.assertEqual(to_hex(cmap(.5)).upper(),'#F7F7F7')
            self.assertEqual(to_hex(cmap(0.)).upper(),'#2166AC')
            self.assertEqual(to_hex(cmap(1.)).upper(),'#B2182B')

    def test_declared_color_levels_apply_to_python(self):
        cmap2=a.color_map({'cmap':['#2166AC','#F7F7F7','#B2182B'],'color_levels':2})
        cmap16=a.color_map({'cmap':['#2166AC','#F7F7F7','#B2182B'],'color_levels':16})
        self.assertEqual(len(np.unique(cmap2(np.linspace(0,1,100))[:,:3],axis=0)),2)
        self.assertEqual(len(np.unique(cmap16(np.linspace(0,1,100))[:,:3],axis=0)),16)

    def test_required_fields_report_context(self):
        for key in ('group','value','bandwidth'):
            spec=dict(self.cloud);del spec[key]
            with self.assertRaisesRegex(ValueError,'Missing plot settings: '+key):a.prepare_plot(spec,[{'g':'A','v':1}],1,self.style)
        spec=dict(self.line,labels={'y':'Y'})
        with self.assertRaisesRegex(ValueError,'labels must supply'):a.prepare_plot(spec,self.xy,1,self.style)

    def test_pchip_overflow_leaves_no_output_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);(p/'data.csv').write_text('x,y\n0,1e308\n1,-1e308\n2,1e308\n')
            cfg={'schema_version':1,'plots':[dict(self.line,csv='data.csv',kind='line_symbol',connection='pchip')]}
            (p/'config.json').write_text(json.dumps(cfg))
            with np.errstate(all='ignore'),self.assertRaises(ValueError):
                a.main([str(p/'config.json'),'--out',str(p/'result')])
            self.assertFalse((p/'result').exists())

    def test_schema_boolean_refused_before_output(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);(p/'config.json').write_text('{"schema_version":true,"plots":[{}]}')
            with self.assertRaisesRegex(ValueError,'schema_version'):
                a.main([str(p/'config.json'),'--out',str(p/'result')])
            self.assertFalse((p/'result').exists())

    def test_pchip_random_interval_bounds_and_affine_invariance(self):
        rng=np.random.default_rng(31415)
        for _ in range(120):
            x=np.r_[0,np.cumsum(rng.uniform(.01,2,6))];y=rng.normal(0,4,7)
            xx,yy=a.pchip_connection(x,y,16)
            np.testing.assert_array_equal(xx[::16],x);np.testing.assert_array_equal(yy[::16],y)
            for i in range(6):
                self.assertTrue(np.all(yy[i*16:(i+1)*16+1]>=min(y[i:i+2])-1e-12))
                self.assertTrue(np.all(yy[i*16:(i+1)*16+1]<=max(y[i:i+2])+1e-12))
            _,other=a.pchip_connection(3*x+2,2*y-1,16)
            np.testing.assert_allclose(other,2*yy-1,rtol=1e-11,atol=1e-11)

    def test_bilinear_random_planes_and_source_nodes(self):
        rng=np.random.default_rng(27182)
        for scale in ('linear','log10'):
            for _ in range(30):
                axis=np.sort(rng.uniform(-2,2,5));xs=10**axis if scale=='log10' else axis
                ys=np.sort(rng.uniform(-1,3,4));coeff=rng.normal(size=3)
                rows=[{'x':x,'y':y,'z':coeff[0]*u+coeff[1]*y+coeff[2]} for y in ys for x,u in zip(xs,axis)]
                rng.shuffle(rows)
                spec={'x':'x','y':'y','z':'z','x_scale':scale,'interpolation':{'method':'bilinear','factor':4}}
                dx,dy,z,raw,_=a.heatmap_display(rows,spec)
                np.testing.assert_array_equal(dx[::4],xs);np.testing.assert_array_equal(dy[::4],ys)
                np.testing.assert_array_equal(z[::4,::4],raw[2])
                ux=np.log10(dx) if scale=='log10' else dx
                np.testing.assert_allclose(z,coeff[0]*ux[None,:]+coeff[1]*dy[:,None]+coeff[2],atol=1e-12,rtol=1e-12)


if __name__=='__main__':unittest.main()
