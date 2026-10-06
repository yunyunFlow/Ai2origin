import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
"""Synthetic correction regressions and independent known-artifact truth."""
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
import warnings
from decimal import Decimal, localcontext
import numpy as np

try:
    import scipy
except ImportError:
    raise unittest.SkipTest("Optional numerical analysis requires requirements-analysis.txt")

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('portable_cv_corrected', HERE.parent/'scripts/methods_cv_corrected.py')
cv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cv)


class CorrectedCVTests(unittest.TestCase):
    def test_signed_known_ir(self):
        e = np.array([0., .1, .2, .3])
        i = np.array([-.002, -.001, .001, .002])
        d = cv.ir_correct(e, i, resistance_ohm=10, resistance_source='independent Rs')
        np.testing.assert_array_equal(d['raw_potential_V'], e)
        np.testing.assert_array_equal(d['raw_current_A'], i)
        np.testing.assert_allclose(d['corrected_potential_V'], [.02, .11, .19, .28], atol=1e-16)

    def test_prior_compensation(self):
        d = cv.ir_correct([0, 1], [.1, .2], resistance_ohm=10,
                          already_compensated_fraction=.4, resistance_source='known residual fraction')
        np.testing.assert_allclose(d['corrected_potential_V'], [-.6, -.2], atol=1e-15)

    def test_fold_retained_and_alignment_refused(self):
        d = cv.ir_correct([0, .1, .2], [0, .03, 0], resistance_ohm=10,
                          resistance_source='independent control')
        self.assertEqual(d['status'], 'HOLD_NONMONOTONIC_GRID')
        np.testing.assert_allclose(d['corrected_potential_V'], [0, -.2, .2])
        with self.assertRaises(ValueError):
            cv.resample_branch(d['corrected_potential_V'], [0, .03, 0], [0, .1],
                               current_unit='A', interpolation='piecewise_linear')

    def test_declared_linear_alignment(self):
        d = cv.resample_branch([3, 2, 1], [9, 6, 3], [1, 1.5, 2, 3],
                               current_unit='mA/cm^2', interpolation='piecewise_linear')
        np.testing.assert_array_equal(d['raw_potential_V'], [3, 2, 1])
        np.testing.assert_array_equal(d['current'], [3, 4.5, 6, 9])
        self.assertEqual(d['interpolated_nodes'], 1)

    def test_no_extrapolation_duplicate_or_implicit_interpolation(self):
        for e, g, method in [([0, 1], [-.1, .9], 'piecewise_linear'),
                             ([0, 0, 1], [0, 1], 'piecewise_linear'),
                             ([0, 1], [0, 1], None)]:
            with self.assertRaises(ValueError):
                cv.resample_branch(e, list(e), g, current_unit='A', interpolation=method)

    def test_signed_tail_dimensionless_exponent(self):
        d = cv.exponential_tail([1, 1.1, 1.2], branch_direction=1, amplitude=-.02,
                                decay_scale_V=.1, current_unit='A', model_source='declared residual model')
        np.testing.assert_allclose(d['tail'], -.02*np.exp(-np.array([0, 1, 2])), rtol=2e-15)
        self.assertLess(d['tail'][0], 0)

    def test_tail_orientation(self):
        d = cv.exponential_tail([2, 1.9, 1.8], branch_direction=-1, amplitude=3,
                                decay_scale_V=.1, current_unit='mA', model_source='declared model')
        np.testing.assert_allclose(d['tail'], 3*np.exp(-np.array([0, 1, 2])), rtol=2e-15)
        with self.assertRaises(ValueError):
            cv.exponential_tail([2, 1.9], branch_direction=1, amplitude=3,
                                decay_scale_V=.1, current_unit='A', model_source='model')

    def test_known_tail_truth_and_independent_baseline(self):
        e = np.linspace(1, 1.2, 101)
        residual = -.012*np.exp(-(e-1)/.034)
        i = residual+.002
        d = cv.fit_exponential_tail(e, i, branch_direction=1, fit_window_V=[1, 1.12],
                                    baseline_current=.002, amplitude_bounds=[-.03, -.001],
                                    decay_scale_bounds_V=[.005, .2], current_unit='A',
                                    model_source='synthetic known tail+independent constant background',
                                    relative_rmse_limit=.01)
        self.assertEqual(d['status'], 'CONDITIONAL_TAIL_FIT')
        self.assertAlmostEqual(d['amplitude'], -.012, places=12)
        self.assertAlmostEqual(d['decay_scale_V'], .034, places=12)
        np.testing.assert_allclose(d['tail'], residual, atol=1e-13)
        self.assertGreater(d['model_extrapolated_nodes'], 0)

    def test_bad_tail_assumption_retained_hold(self):
        e = np.linspace(0, .1, 101)
        d = cv.fit_exponential_tail(e, 1+np.sin(e*80), branch_direction=1,
                                    fit_window_V=[0, .1], baseline_current=0,
                                    amplitude_bounds=[.01, 5], decay_scale_bounds_V=[.001, .5],
                                    current_unit='mA', model_source='wrong declared exponential',
                                    relative_rmse_limit=.01)
        self.assertEqual(d['status'], 'HOLD_TAIL_MODEL')
        self.assertGreater(d['relative_rmse'], .01)
        self.assertEqual(len(d['tail']), len(e))

    def test_correction_components_closure_without_zero_forcing(self):
        d = cv.subtract_terms([1, 2, 3], tail=[.1, .2, .3], background=[-.4, -.4, -.4],
                             current_unit='mA/cm^2', correction_source='explicit signed terms')
        np.testing.assert_allclose(d['corrected_current'], [1.3, 2.2, 3.1])
        np.testing.assert_allclose(d['corrected_current']+d['tail']+d['background'], d['raw_current'])

    def test_edlc_uses_actual_corrected_sweep_derivative(self):
        d = cv.edlc_interval_current([0, 1, 2, 3], [0, .1, .15, .12],
                                     capacitance_F=.02, control_source='known synthetic constant C')
        np.testing.assert_allclose(d['interval_current_A'], [.002, .001, -.0006])
        self.assertAlmostEqual(sum(d['interval_charge_C']), .02*.12, places=16)

    def test_known_combined_ir_tail_background_recovery(self):
        t = np.linspace(0, 20, 201)
        ee = .01*t
        bg = np.full_like(ee, .002)
        tail = -.01*np.exp(-ee/.03)
        true_far = .003*ee+.01*np.sqrt(ee)
        measured_i = true_far+tail+bg
        measured_e = ee+measured_i*15
        ir = cv.ir_correct(measured_e, measured_i, resistance_ohm=15,
                           resistance_source='independent known synthetic Ru')
        np.testing.assert_allclose(ir['corrected_potential_V'], ee, atol=1e-16)
        restored = cv.subtract_terms(measured_i, tail=tail, background=bg,
                                      current_unit='A', correction_source='known synthetic artifact terms')
        np.testing.assert_allclose(restored['corrected_current'], true_far, atol=2e-18)

    def test_invalid_scalars_units_boolean_and_time(self):
        with self.assertRaises(ValueError):
            cv.ir_correct([0, 1], [0, 1], resistance_ohm=True, resistance_source='control')
        with self.assertRaises(ValueError):
            cv.ir_correct([0, 1], [0, 1], resistance_ohm=-1, resistance_source='control')
        with self.assertRaises(ValueError):
            cv.ir_correct([0, True], [0, 1], resistance_ohm=1, resistance_source='control')
        with self.assertRaises(ValueError):
            cv.resample_branch([0, 1], [0, 1], [0, 1], current_unit='mA/g invented', interpolation='piecewise_linear')
        with self.assertRaises(ValueError):
            cv.edlc_interval_current([0, 0], [0, 1], capacitance_F=1, control_source='control')

    def test_nonzero_underflow_is_not_silent_zero(self):
        with self.assertRaises(ValueError):
            cv.ir_correct([0, 1], [1e-300, 1e-300], resistance_ohm=1e-300, resistance_source='control')
        with self.assertRaises(ValueError):
            cv.ir_correct([0, 1], [0, np.longdouble('1e-400')], resistance_ohm=1, resistance_source='control')
        with self.assertRaises(ValueError):
            cv.edlc_interval_current([0, 1], [0, 1e-300], capacitance_F=1e-300, control_source='control')

    def test_no_unit_or_baseline_identification_from_fit_success(self):
        e = np.linspace(0, .05, 51)
        target = .5*np.exp(-e/.02)+.01
        d = cv.fit_exponential_tail(e, target, branch_direction=1, fit_window_V=[0, .05],
                                    baseline_current=.01, amplitude_bounds=[.1, 1],
                                    decay_scale_bounds_V=[.005, .2], current_unit='mA/cm^2',
                                    model_source='hypothetical declared background, unverified real electrode',
                                    relative_rmse_limit=.01)
        self.assertEqual(d['status'], 'CONDITIONAL_TAIL_FIT')
        self.assertEqual(d['current_unit'], 'mA/cm^2')
        self.assertIn('unverified', d['model_source'])
        self.assertNotIn('capacitance_F', d)

    def test_complex_input_never_drops_imaginary_parts(self):
        inputs = [np.array([1+1j, 2+2j]), [1+0j, 2+0j],
                  np.array([1+1j, 2.0], dtype=object)]
        for values in inputs:
            with self.subTest(values=values), warnings.catch_warnings(record=True) as caught:
                with self.assertRaises(ValueError):
                    cv.ir_correct(values, [0, 0], resistance_ohm=0, resistance_source='control')
                self.assertEqual(len(caught), 0)
        for scalar in [1+1j, np.complex128(1+0j), np.array(1.0), object()]:
            with self.subTest(scalar=scalar), self.assertRaises(ValueError):
                cv.ir_correct([0, 1], [0, 0], resistance_ohm=scalar, resistance_source='control')

    def test_infinite_intervals_do_not_pass_monotonic_checks(self):
        extremes = [-1e308, 1e308]
        cases = [
            lambda: cv.ir_correct(extremes, [0, 0], resistance_ohm=0, resistance_source='control'),
            lambda: cv.resample_branch(extremes, [0, 1], [-1, 1], current_unit='A', interpolation='piecewise_linear'),
            lambda: cv.resample_branch([0, 1], extremes, [0, 1], current_unit='A', interpolation='piecewise_linear'),
            lambda: cv.exponential_tail(extremes, branch_direction=1, amplitude=1, decay_scale_V=1,
                                        current_unit='A', model_source='model'),
            lambda: cv.edlc_interval_current(extremes, [0, 1], capacitance_F=0, control_source='control'),
            lambda: cv.edlc_interval_current([0, 1], extremes, capacitance_F=0, control_source='control'),
            # All adjacent intervals are finite, but first-to-last progress is not.
            lambda: cv.exponential_tail([-1e308, 0, 1e308], branch_direction=1, amplitude=1,
                                        decay_scale_V=1e308, current_unit='A', model_source='model'),
        ]
        for idx, function in enumerate(cases):
            with self.subTest(idx=idx), warnings.catch_warnings(record=True) as caught:
                with self.assertRaises(ValueError): function()
                self.assertEqual(len(caught), 0)

    def test_ir_subnormal_intermediate_preserves_representable_product(self):
        current, ru, fraction = 1e300, 1e-320, .63
        d = cv.ir_correct([0, 1], [current, -current], resistance_ohm=ru,
                          already_compensated_fraction=fraction, resistance_source='arithmetic-only fixture')
        with localcontext() as ctx:
            ctx.prec = 100
            exact = Decimal.from_float(current)*Decimal.from_float(ru)*(Decimal(1)-Decimal.from_float(fraction))
        expected = float(exact)
        self.assertLess(abs(d['correction_V'][0]/expected-1), 3e-16)
        self.assertLess(abs(d['correction_V'][1]/(-expected)-1), 3e-16)
        # The ordinary multiply Ru*(1-f) loses precision before multiplying by I.
        self.assertGreater(abs(current*(ru*(1-fraction))/expected-1), 1e-4)


if __name__ == '__main__':
    unittest.main()
