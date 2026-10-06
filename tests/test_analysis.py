"""Actual file contracts, CLI/repeats and independent numerical truth."""
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np

try:
    import scipy
except ImportError:
    raise unittest.SkipTest('Optional analysis QA requires requirements-analysis.txt')

ROOT=Path(__file__).resolve().parents[1]
def module(name):
    s=importlib.util.spec_from_file_location('test_'+name,ROOT/'scripts'/(name+'.py'))
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
A=module('analyze');S=module('methods_spectra');G=module('make_analysis');P=module('ai2origin')


class AnalysisTests(unittest.TestCase):
    def test_nondecade_frequency_and_tau_analysis_outputs_prepare_without_resampling(self):
        cfg=self.one('eis');cfg['jobs'][0]['parameters']['n_rc']=1
        cfg['jobs'][0]['parameters']['initial_guesses']=[[2,17,.04],[6,30,.08]]
        cfg['jobs'][0]['parameters']['bounds']=[[.01,.01,1e-5],[100,1000,100]]
        f=np.geomspace(.037,73100,49);z=4.6+24/(1+2j*np.pi*f*.061)
        source=self.work/'new-frequency.csv';source.write_bytes(A.csv_bytes(['f','real','imag'],zip(f,z.real,z.imag)))
        item=cfg['jobs'][0]['inputs'][0];item['file']=str(source)
        cfg['jobs'][0]['inputs']=cfg['jobs'][0]['inputs'][:1]
        rcjob=cfg['jobs'][0];drtjob=json.loads(json.dumps(rcjob));drtjob['id']='nondecade';drtjob['method']='drt'
        tau=np.geomspace(.002,60000,33)
        drtjob['inputs']=[json.loads(json.dumps(item)),json.loads(json.dumps(item))]
        drtjob['parameters']={'tau':tau.tolist(),'lambdas':[1e-4],'selected_lambda':1e-4,'order':2,'weighting':'modulus','condition_axis':{'label':'Assigned condition','unit':'a.u.','values':[0,1]}}
        cfg['jobs'].append(drtjob);self.call(cfg)
        results=json.loads((self.work/'out/results.json').read_text())['jobs']
        np.testing.assert_allclose(results[0]['result']['inputs'][0]['parameters'],[4.6,24,.061],rtol=1e-7)
        np.testing.assert_array_equal(results[1]['result']['inputs'][0]['tau_s'],tau)
        for plot in json.loads((self.work/'out/plot.json').read_text())['plots']:
            P.prepare_plot(plot,P.read_csv(self.work/'out'/plot['csv']),1,P.STYLE.resolve(P.load_json,project={'figure':{'width_mm':110,'height_mm':80}})[0])
            if plot.get('equal_xy'):
                self.assertEqual(plot['x_tick_step'],plot['y_tick_step'])
                span=plot['x_range'][1]-plot['x_range'][0]
                self.assertLessEqual(span/plot['x_tick_step'],7)
            if plot.get('x_scale')=='log10':
                self.assertEqual(plot['x_range'],[.01,100000.] if plot['id'].find('residual')>=0 else [.001,100000.])

    def test_job_identifier_bound_keeps_all_derived_plot_names_valid(self):
        cfg=self.one('cv');cfg['jobs'][0]['id']='A'*32
        self.call(cfg)
        for plot in json.loads((self.work/'out/plot.json').read_text())['plots']:
            self.assertLessEqual(len(plot['id']),48)
            P.prepare_plot(plot,P.read_csv(self.work/'out'/plot['csv']),1,P.STYLE.resolve(P.load_json)[0])
        cfg['jobs'][0]['id']='A'*33;p=self.work/'too-long.json';p.write_text(json.dumps(cfg))
        with self.assertRaisesRegex(ValueError,'Unsafe job ID'):A.run(p,self.work/'refused-long')
        self.assertFalse((self.work/'refused-long').exists())
    @classmethod
    def setUpClass(cls):
        cls.temporary=tempfile.TemporaryDirectory();cls.base=Path(cls.temporary.name)
        cls.inputs=cls.base/'中文 inputs space';G.generate(cls.inputs)
        cls.a=cls.base/'output a';cls.b=cls.base/'output b'
        A.run(cls.inputs/'analysis.json',cls.a);A.run(cls.inputs/'analysis.json',cls.b)
        cls.reports={j['id']:j for j in json.loads((cls.a/'results.json').read_text())['jobs']}
        cls.truth=json.loads((cls.inputs/'truth.json').read_text())

    @classmethod
    def tearDownClass(cls):cls.temporary.cleanup()

    def setUp(self):self.sandbox=tempfile.TemporaryDirectory();self.work=Path(self.sandbox.name)
    def tearDown(self):self.sandbox.cleanup()

    def one(self,identifier):
        config=json.loads((self.inputs/'analysis.json').read_text());job=next(j for j in config['jobs'] if j['id']==identifier)
        for item in job['inputs']:item['file']=str(self.inputs/item['file'])
        return {'schema_version':1,'jobs':[job]}

    def call(self,config):
        path=self.work/'input.json';path.write_text(json.dumps(config));return A.run(path,self.work/'out')

    def test_exact_repeat_source_hash_and_complete_inventory(self):
        result=A.verify(self.a,self.b,self.inputs/'analysis.json')
        self.assertEqual(result['repeat'],'BYTE_IDENTICAL')
        self.assertEqual(len(self.reports),15)
        (self.b/'rogue').mkdir()
        with self.assertRaises(ValueError):A.verify(self.b)
        (self.b/'rogue').rmdir()
        (self.b/'RESULTS.json').write_text('{}')
        with self.assertRaises(ValueError):A.verify(self.b)
        (self.b/'RESULTS.json').unlink()

    def test_parse_cache_is_readonly_contract_specific_and_rejects_changed_input(self):
        counts=[];reader=A.module('intake').read_table
        def tracked(path,options):counts.append((Path(path).name,options));return reader(path,options)
        cache=A.TableCache(tracked);p=self.work/'values.csv';p.write_text('x,y\n0,1.2300\n1,-2\n')
        first=cache.read(p)[1];second=cache.read(p)[1]
        self.assertIs(first,second);self.assertEqual(len(counts),1);self.assertEqual(first[1][0][1],'1.2300')
        with self.assertRaises(ValueError):cache.read(p,[])
        with self.assertRaises(TypeError):first[1][0][1]='altered'
        cache.read(p,{'encoding':'utf-8'});self.assertEqual(len(counts),2)
        p.write_text('x,y\n0,9.2300\n1,-2\n')
        with self.assertRaisesRegex(ValueError,'Input changed'):cache.read(p)
        with self.assertRaisesRegex(ValueError,'Input changed'):cache.verify()

    def test_full_analysis_parses_multibranch_cv_once_without_changing_results(self):
        from unittest.mock import patch
        counts=[];reader=A.module('intake').read_table;cache_type=A.TableCache
        def tracked(path,options):counts.append(Path(path).name);return reader(path,options)
        with patch.object(A,'TableCache',lambda:cache_type(tracked)):
            A.run(self.inputs/'analysis.json',self.work/'cached')
        self.assertEqual(counts.count('analysis-cv.csv'),1)
        self.assertEqual((self.work/'cached/results.json').read_bytes(),(self.a/'results.json').read_bytes())
        self.assertEqual((self.work/'cached/plot.json').read_bytes(),(self.a/'plot.json').read_bytes())

    def test_real_cli_outside_package_and_readonly_check(self):
        before={p.name:A.sha(p) for p in self.inputs.iterdir()}
        args=[sys.executable,'-I','-B',str(ROOT/'scripts/analyze.py'),'--check',str(self.a),'--repeat',str(self.b)]
        result=subprocess.run(args,cwd=self.work,capture_output=True,text=True,timeout=60)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(json.loads(result.stdout)['status'],'PASS')
        self.assertEqual(before,{p.name:A.sha(p) for p in self.inputs.iterdir()})

    def test_dunn_recovers_independent_assigned_components_no_clipping(self):
        result=self.reports['cv']['result'];self.assertEqual(result['status'],'CONDITIONAL_EMPIRICAL_FRACTIONS')
        for b in result['branches']:
            fit=b['fit'];current=np.array(fit['current_A']);reconstruction=np.array(fit['reconstructed_A'])
            np.testing.assert_allclose(current,reconstruction,atol=3e-19,rtol=1e-12)
            self.assertTrue(np.all(np.sign(fit['linear_component_A'])==np.sign(current)))
        fractions=result['aggregate']['per_rate']
        self.assertGreater(fractions[-1]['conditional_model_fractions']['linear'],fractions[0]['conditional_model_fractions']['linear'])
        self.assertEqual(len(self.reports['cv']['plots']),7)

    def test_paired_cv_map_preserves_branch_nodes_rates_and_signed_values(self):
        plots=json.loads((self.a/'plot.json').read_text())['plots']
        spec=next(p for p in plots if p['id']=='cv-map')
        rows=P.read_csv(self.a/spec['csv']);x,y,z=P.heatmap_grid(rows,'x','y','z')
        branches=self.reports['cv']['result']['branches'];rates=np.asarray(self.reports['cv']['result']['rates_V_s'])
        np.testing.assert_array_equal(z[:len(rates)],np.asarray(branches[1]['fit']['current_A'])[::-1,::-1]*1000)
        np.testing.assert_array_equal(z[len(rates):],np.asarray(branches[0]['fit']['current_A'])*1000)
        np.testing.assert_array_equal(x,branches[0]['potential_V'])
        self.assertEqual(spec['y_tick_labels'],[f'R:{r*1000:g}' for r in rates[::-1]]+[f'F:{r*1000:g}' for r in rates])
        prepared=P.prepare_plot(spec,rows,1,P.STYLE.resolve(P.load_json)[0])
        self.assertEqual(prepared['metadata']['category_y_labels'],spec['y_tick_labels'])
        self.assertIn('layer.y.label.type=10',prepared['commands'])
        self.assertNotIn('layer -b s 1',prepared['commands'])  # Origin resets the accepted color scale.
        self.assertEqual(prepared['metadata']['interpolation'],'none')
        self.assertEqual(spec['color_range'][0],-spec['color_range'][1])

    def test_categorical_map_rejects_false_geometry_or_cross_branch_interpolation(self):
        spec=next(p for p in json.loads((self.a/'plot.json').read_text())['plots'] if p['id']=='cv-map')
        rows=P.read_csv(self.a/spec['csv']);style=P.STYLE.resolve(P.load_json)[0]
        for change in [{'y_tick_labels':['F:1']},{'y_tick_labels':['bad;code']*12},
                       {'interpolation':{'method':'bilinear','factor':2}}, {'y_range':[-1,12]}, {'y_tick_step':2}]:
            changed=json.loads(json.dumps(spec));changed.update(change)
            with self.assertRaises(ValueError):P.prepare_plot(changed,rows,1,style)

    def test_short_time_gitt_recovers_independent_finite_slab_D(self):
        results=self.reports['gitt']['result']['pulses']
        for actual,truth in zip(results,self.truth['gitt_D_m2_s']):
            self.assertLess(abs(actual['D_conditional_m2_s']/truth-1),1e-8)
            self.assertLess(actual['short_time_tau_D_over_L_squared'],.01)
            self.assertEqual(len(actual['raw_t_s']),121)
        cfg=self.one('gitt');cfg['jobs'][0]['inputs'][0]['metadata']['equilibrium_confirmed']=False
        self.call(cfg);held=json.loads((self.work/'out/results.json').read_text())['jobs'][0]['result']
        self.assertIsNone(held['pulses'][0]['D_conditional_m2_s']);self.assertEqual(held['held_pulse_ids'],['P1'])

    def test_capacitance_ica_and_tafel_units(self):
        self.assertAlmostEqual(self.reports['cdl']['result']['cdl_F'],.018,places=12)
        ica=self.reports['ica']['result'];self.assertLess(abs(ica['closure_error_C']),1e-15)
        tafel=self.reports['tafel']['result']['fit'];self.assertAlmostEqual(tafel['slope_magnitude_mV_per_dec'],60,places=8)
        self.assertEqual(tafel['status'],'CONDITIONAL_APPARENT_FIT')

    def test_circuit_fit_recovers_independent_physical_values(self):
        result=self.reports['eis']['result']['inputs'][0]
        np.testing.assert_allclose(result['parameters'],self.truth['eis_Rs_R1_tau1_R2_tau2'],rtol=1e-7)
        self.assertEqual(result['KK_status'],'HOLD_NOT_PERFORMED')
        self.assertEqual(result['physical_assignment'],'MODEL_ELEMENTS_ONLY')
        self.assertEqual(result['displayed_fit_quality']['status'],'CONDITIONAL_MODEL_RESIDUAL')

    def test_model_mismatch_is_held_without_deleting_residuals(self):
        cfg=self.one('eis');job=cfg['jobs'][0];job['parameters']={'n_rc':1,'initial_guesses':[[2,30,.5]],
            'bounds':[[.01,.01,1e-5],[100,1000,1000]],'weighting':'modulus','model_residual_limit':.01}
        self.call(cfg);r=json.loads((self.work/'out/results.json').read_text())['jobs'][0]['result']
        self.assertEqual(r['status'],'HOLD_MODEL_RESIDUAL');self.assertEqual(len(r['inputs'][0]['residual_ohm']),71)

    def test_drt_has_explicit_sensitivity_and_correct_ln_measure(self):
        result=self.reports['drt']['result'];self.assertEqual(result['selected_display_lambda'],1e-4)
        for r in result['inputs']:
            self.assertEqual(r['selection'],'NOT_SELECTED_SENSITIVITY_ONLY')
            self.assertEqual(len(r['solutions']),3)
            for s in r['solutions']:
                self.assertTrue(np.all(np.array(s['gamma_ohm'])>=0))
                self.assertLess(s['relative_complex_rmse'],.08)
                self.assertAlmostEqual(s['gamma_integral_ohm'],np.dot(r['ln_quadrature_weights'],s['gamma_ohm']))

    def test_peak_profiles_keep_independent_area_and_width_units(self):
        for identifier in ['raman','ftir','xps']:
            fit=self.reports[identifier]['result'];areas=[p['area'] for p in fit['peaks']]
            np.testing.assert_allclose(areas,self.truth[identifier+'_areas'],rtol=1e-8)
            self.assertTrue(fit['raw_order_preserved']);self.assertEqual(fit['uncertainty'],'NOT_ESTIMATED')

    def test_rejects_bad_mapping_unknown_parameters_duplicate_json_and_boolean(self):
        for kind in ['role','unit','parameter','identity','boolean']:
            cfg=self.one('ica');job=cfg['jobs'][0];item=job['inputs'][0]
            if kind=='role':item['roles']['charge']['column']='missing'
            if kind=='unit':item['roles']['charge']['unit']='mAh/g'
            if kind=='parameter':job['parameters']['silent_smoothing']=True
            if kind=='identity':item['sample_id']='another sample'
            if kind=='boolean':job['synthetic']='true'
            p=self.work/(kind+'.json');p.write_text(json.dumps(cfg))
            with self.assertRaises(ValueError):A.run(p,self.work/kind)
        p=self.work/'duplicate.json';p.write_text('{"schema_version":1,"schema_version":2,"jobs":[]}')
        with self.assertRaises(ValueError):A.run(p,self.work/'duplicate')

    def test_unsupported_processing_source_changes_and_failed_markers(self):
        cfg=self.one('xps');cfg['jobs'][0]['inputs'][0]['metadata']['background_state']='subtracted'
        with self.assertRaises(ValueError):self.call(cfg)
        self.assertTrue((self.work/'out/FAILED.txt').is_file())
        with self.assertRaises((ValueError,OSError)):A.verify(self.work/'out')
        with self.assertRaises(ValueError):A.run(self.inputs/'analysis.json',self.a)

    def test_plot_recipes_prepare_actual_geometry_and_log_y(self):
        plots=json.loads((self.a/'plot.json').read_text())['plots'];self.assertEqual(len(plots),46)
        style=P.STYLE.resolve(P.load_json)[0]
        for i,spec in enumerate(plots,1):
            rows=P.read_csv(self.a/spec['csv']);prepared=P.prepare_plot(spec,rows,i,style)
            if spec['kind']=='line' and spec.get('x_scale','linear')=='linear':
                xs=np.concatenate([P.column(rows,s.get('x',spec['x'])) for s in spec['series']])
                self.assertLessEqual((float(xs.max())-float(xs.min()))/spec['x_tick_step'],7)
            if spec.get('y_scale')=='log10':
                self.assertEqual(prepared['metadata']['y_scale'],'log10')
                self.assertIn('layer.y.type=2',prepared['commands'])
                self.assertLessEqual(60/spec['x_tick_step'],7)
        self.assertIn('\\+(0.5)',P.display_label('V^0.5 s^-0.5',True))

    def test_explicit_correction_and_full_cell_accounting_cli(self):
        corrected=self.reports['correction']['result']
        self.assertEqual(corrected['status'],'CONDITIONAL_EXPLICIT_PROCESSING')
        np.testing.assert_allclose(corrected['corrected_current_A'],self.truth['correction_redox_A'],atol=2e-16)
        cycle=self.reports['cycle']['result'];self.assertAlmostEqual(cycle['coulombic_efficiency'],.92)
        self.assertAlmostEqual(cycle['energy_efficiency'],.805)
        cfg=self.one('cycle');cfg['jobs'][0]['parameters']['complete_branches']=False;self.call(cfg)
        r=json.loads((self.work/'out/results.json').read_text())['jobs'][0]['result'];self.assertEqual(r['status'],'HOLD')

    def test_xps_doublet_kinetic_conversion_and_shirley_cli(self):
        fit=self.reports['doublet']['result'];self.assertTrue(fit['accepted_numeric_fit'])
        np.testing.assert_allclose([p['area'] for p in fit['peaks']],[800,400],rtol=1e-8)
        self.assertEqual(fit['energy_transform']['energy_type'],'kinetic')
        fit=self.reports['shirley']['result'];self.assertTrue(fit['accepted_numeric_fit'])
        np.testing.assert_allclose([p['area'] for p in fit['peaks']],[1000,500],rtol=1e-4)
        self.assertEqual(fit['background_algorithm']['status'],'CONDITIONAL_SHIRLEY')

    def test_shirley_against_independent_error_function_background(self):
        x=np.linspace(-5,5,2001);peak=np.exp(-x*x);cdf=np.array([math.erf(t) for t in x]);cdf=(cdf-cdf[0])/(cdf[-1]-cdf[0])
        expected=.2+.3*cdf;y=peak+expected
        result=S.shirley_background(x,y,endpoints=[.2,.5],source='Independent analytic erf fixture',tolerance=1e-11)
        self.assertEqual(result['status'],'CONDITIONAL_SHIRLEY')
        np.testing.assert_allclose(result['background_source_order'],expected,atol=8e-7)
        np.testing.assert_array_equal(result['raw_intensity'],y)
        reverse=S.shirley_background(x[::-1],y[::-1],endpoints=[.2,.5],source='Assigned endpoints',reverse_working_copy=True,tolerance=1e-11)
        np.testing.assert_allclose(reverse['background_source_order'],np.array(result['background_source_order'])[::-1])
        with self.assertRaises(ValueError):S.shirley_background(x,y,endpoints=[10,20],source='Impossible background')
        fail=S.shirley_background(x,y,endpoints=[.2,.5],source='Explicit one-step diagnostic',max_iterations=1,tolerance=1e-14)
        self.assertEqual(fail['status'],'HOLD_SHIRLEY_NOT_CONVERGED')


if __name__=='__main__':unittest.main()
