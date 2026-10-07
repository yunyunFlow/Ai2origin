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
    def test_separated_scatter_legend_is_clear_for_actual_marker_shapes(self):
        from matplotlib import pyplot as plt
        for marker in ('o','s','^','x'):
            with self.subTest(marker=marker):
                fig,ax=plt.subplots(figsize=(4,3),dpi=100)
                try:
                    ax.set(xlim=(0,1),ylim=(0,1))
                    ax.scatter([.1,.2],[.1,.2],s=[30,80],marker=marker,label='Data')
                    ax.legend(loc='upper right',frameon=False)
                    report=DRAW.rendered_layout(fig,ax,100)
                    self.assertEqual(report['status'],'NO_GEOMETRIC_ISSUES_DETECTED')
                    self.assertFalse(report['geometry_unchecked'])
                finally:plt.close(fig)

    def test_line_and_scatter_marker_edges_overlap_or_are_separated(self):
        from matplotlib import pyplot as plt
        for kind in ('line','scatter'):
            for gap,hit in ((-2,True),(-14*100/144-3,False)):
                with self.subTest(kind=kind,gap=gap):
                    fig,ax=plt.subplots(figsize=(4,3),dpi=100)
                    try:
                        ax.set(xlim=(0,1),ylim=(0,1))
                        if kind=='line':artist,=ax.plot([.1],[.1],marker='o',markersize=14,label='Data')
                        else:artist=ax.scatter([.1],[.1],s=14**2,label='Data')
                        legend=ax.legend(loc='upper right',frameon=False);fig.canvas.draw()
                        box=legend.get_texts()[0].get_window_extent(fig.canvas.get_renderer())
                        x,y=ax.transData.inverted().transform([(box.x0+box.x1)/2,box.y0+gap])
                        if kind=='line':artist.set_data([x],[y])
                        else:artist.set_offsets([[x,y]])
                        report=DRAW.rendered_layout(fig,ax,100)
                        self.assertEqual(bool(report['legend_collisions']),hit)
                    finally:plt.close(fig)

    def test_invisible_line_or_marker_does_not_report_an_intersection(self):
        from matplotlib import pyplot as plt
        for invisible in ('artist','marker','color'):
            fig,ax=plt.subplots(figsize=(4,3),dpi=100)
            try:
                ax.set(xlim=(0,1),ylim=(0,1))
                line,=ax.plot([.1],[.1],linestyle='None',marker='o',markersize=14,label='Data')
                legend=ax.legend(loc='upper right',frameon=False);fig.canvas.draw()
                box=legend.get_texts()[0].get_window_extent(fig.canvas.get_renderer())
                x,y=ax.transData.inverted().transform(box.get_points().mean(axis=0));line.set_data([x],[y])
                if invisible=='artist':line.set_visible(False)
                elif invisible=='marker':line.set_marker('None')
                else:line.set_markerfacecolor('none');line.set_markeredgecolor('none')
                self.assertFalse(DRAW.rendered_layout(fig,ax,100)['legend_collisions'])
            finally:plt.close(fig)

    def test_legacy_matplotlib_legend_handle_access(self):
        from matplotlib import pyplot as plt
        from types import SimpleNamespace
        self.assertEqual(DRAW.layout_legend_handles(SimpleNamespace(legendHandles=['old'])),['old'])
        self.assertEqual(DRAW.layout_legend_handles(SimpleNamespace(legend_handles=['new'],legendHandles=['old'])),['new'])
        fig,ax=plt.subplots(figsize=(4,3),dpi=100)
        try:
            ax.set(xlim=(0,1),ylim=(0,1));ax.scatter([.1],[.1],label='Data')
            legend=ax.legend(loc='upper right',frameon=False)
            handles=DRAW.layout_legend_handles(legend)
            with patch.object(legend,'legend_handles',None,create=True),patch.object(legend,'legendHandles',handles,create=True):
                self.assertEqual(DRAW.rendered_layout(fig,ax,100)['status'],'NO_GEOMETRIC_ISSUES_DETECTED')
        finally:plt.close(fig)

    def test_invalid_legend_geometry_is_incomplete_instead_of_clear(self):
        from matplotlib import pyplot as plt
        from matplotlib.transforms import Bbox
        fig,ax=plt.subplots(figsize=(4,3),dpi=100)
        try:
            ax.set(xlim=(0,1),ylim=(0,1));ax.plot([.1,.2],[.1,.2],label='Data')
            handle=DRAW.layout_legend_handles(ax.legend(loc='upper right',frameon=False))[0]
            with patch.object(handle,'get_window_extent',return_value=Bbox.from_extents(float('inf'),float('inf'),float('-inf'),float('-inf'))):
                report=DRAW.rendered_layout(fig,ax,100)
            self.assertEqual(report['status'],'NEEDS_REVIEW')
            self.assertTrue(report['geometry_unchecked'])
            self.assertFalse(report['legend_collisions'])
        finally:plt.close(fig)

    def test_incomplete_geometry_report_cannot_claim_clear(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'input.csv').write_text('x,y\n1,2\n2,3\n')
            config=root/'input.json';config.write_text(json.dumps({'schema_version':1,'style':{'export':{'raster_dpi':72}},
                'plots':[{'id':'curve','kind':'line','csv':'input.csv','x':'x','labels':{'x':'X','y':'Y'},'series':[{'column':'y','label':'A'}]}]}))
            output=root/'output'
            with contextlib.redirect_stdout(io.StringIO()):DRAW.main([str(config),'--out',str(output),'--backend','python','--font','DejaVu Sans'])
            path=output/'curve-layout.json';report=json.loads(path.read_text())
            report.update(legend_collisions=[],text_outside_canvas=[],geometry_unchecked=[{'artist':'legend'}],status='NO_GEOMETRIC_ISSUES_DETECTED')
            path.write_text(json.dumps(report));receipt_path=output/'receipt.json';receipt=json.loads(receipt_path.read_text())
            entry=next(e for e in receipt['outputs'] if e['name']==path.name);entry.update(bytes=path.stat().st_size,sha256=CHECK.sha(path));receipt_path.write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError,'layout report status'):CHECK.check(output)

    def test_literal_percent_labels_render_without_native_commands(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'input.csv').write_text('x,y\n1,2\n2,1\n3,4\n')
            labels=['Coulombic efficiency (%)','Capacity retention (%)','Composition (at.%)','Composition (wt.%)']
            for i,label in enumerate(labels):
                with self.subTest(label=label):
                    config=root/'input.json'
                    config.write_text(json.dumps({'schema_version':1,'style':{'figure':{'height_mm':100},'export':{'raster_dpi':100}},
                        'plots':[{'id':'curve','kind':'line','csv':'input.csv','x':'x','title':'Share (%)',
                                  'labels':{'x':'Coordinate','y':label},'series':[{'column':'y','label':'95% sample'}]}]}))
                    output=root/str(i)
                    with contextlib.redirect_stdout(io.StringIO()):
                        DRAW.main([str(config),'--out',str(output),'--backend','python','--font','DejaVu Sans','--svg'])
                    self.assertIn(label,(output/'curve.svg').read_text())
                    plan=json.loads((output/'origin-plan.json').read_text())
                    self.assertEqual(plan['plots'][0]['books'][0]['rows'],[[1,2],[2,1],[3,4]])
                    self.assertEqual(plan['plots'][0]['commands'],[])
                    self.assertIn('UNAVAILABLE',plan['native_plan_status'])
                    self.assertEqual(CHECK.check(output,config=config)['status'],'PASS')

    def test_native_percent_and_text_commands_are_refused_before_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'input.csv').write_text('x,y\n1,2\n2,3\n')
            config=root/'input.json'
            cases=[('prepare','Composition (at.%)')]
            cases += [(backend,text) for backend in ('python','prepare')
                      for text in ('x;run evil','$(system)','bad"label',r'bad\command','bad\nlabel')]
            for i,(backend,text) in enumerate(cases):
                with self.subTest(backend=backend,text=text):
                    config.write_text(json.dumps({'schema_version':1,'plots':[{'id':'curve','kind':'line','csv':'input.csv','x':'x',
                        'labels':{'x':'X','y':text},'series':[{'column':'y','label':'A'}]}]}))
                    output=root/str(i)
                    with self.assertRaises(ValueError):DRAW.main([str(config),'--out',str(output),'--backend',backend])
                    self.assertFalse(output.exists())

    def test_rendered_geometry_detects_line_scatter_and_filled_legend_overlap(self):
        from matplotlib import pyplot as plt
        for kind in ('line','scatter','band','bar'):
            with self.subTest(kind=kind):
                fig,ax=plt.subplots(figsize=(4,3));ax.set(xlim=(0,1),ylim=(0,1))
                if kind=='line':ax.plot([0,1],[.95,.95],label='Data')
                elif kind=='scatter':ax.scatter([.8],[.95],label='Data')
                elif kind=='band':ax.fill_between([0,1],[.89,.89],[1,1],label='Data')
                else:ax.bar([.8],[1],width=.3,label='Data')
                ax.legend(loc='upper right',frameon=False)
                if kind in ('line','scatter'):
                    # Font/version metrics move the legend: cross its actual text.
                    fig.canvas.draw()
                    box=ax.get_legend().get_texts()[0].get_window_extent(fig.canvas.get_renderer())
                    x,y=ax.transData.inverted().transform(box.get_points().mean(axis=0))
                    if kind=='line':ax.lines[0].set_ydata([y,y])
                    else:ax.collections[0].set_offsets([[x,y]])
                report=DRAW.rendered_layout(fig,ax,100)
                self.assertEqual(report['status'],'NEEDS_REVIEW')
                self.assertTrue(report['legend_collisions']);plt.close(fig)
        fig,ax=plt.subplots(figsize=(4,3));ax.plot([0,1],[.2,.2],label='Data')
        ax.set(xlim=(0,1),ylim=(0,1));ax.legend(loc='upper right',frameon=False)
        self.assertEqual(DRAW.rendered_layout(fig,ax,100)['status'],'NO_GEOMETRIC_ISSUES_DETECTED');plt.close(fig)

    def test_rendered_text_bounds_detect_clipping_and_larger_canvas_control(self):
        from matplotlib import pyplot as plt
        for width,clipped in [(2,True),(12,False)]:
            fig,ax=plt.subplots(figsize=(width,3),layout='constrained')
            ax.set(xlabel='Capacity retention with a deliberately long scientific axis label (%)')
            report=DRAW.rendered_layout(fig,ax,100)
            self.assertEqual(bool(report['text_outside_canvas']),clipped);plt.close(fig)

    def test_layout_report_is_hash_bound_and_cannot_claim_clear_over_collisions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'input.csv').write_text('x,y\n1,2\n2,3\n')
            config=root/'input.json';config.write_text(json.dumps({'schema_version':1,'style':{'export':{'raster_dpi':72}},
                'plots':[{'id':'curve','kind':'line','csv':'input.csv','x':'x','labels':{'x':'X','y':'Y'},'series':[{'column':'y','label':'A'}]}]}))
            output=root/'output'
            with contextlib.redirect_stdout(io.StringIO()):DRAW.main([str(config),'--out',str(output),'--backend','python','--font','DejaVu Sans'])
            report_file=output/'curve-layout.json';report=json.loads(report_file.read_text())
            report['legend_collisions']=[{'data':'line','index':0,'legend':'text','legend_index':0}]
            report['status']='NO_GEOMETRIC_ISSUES_DETECTED';report_file.write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError,'hash/size mismatch'):CHECK.check(output)
            receipt_file=output/'receipt.json';receipt=json.loads(receipt_file.read_text())
            entry=next(e for e in receipt['outputs'] if e['name']==report_file.name)
            entry.update(bytes=report_file.stat().st_size,sha256=CHECK.sha(report_file));receipt_file.write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError,'layout report status'):CHECK.check(output)

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
