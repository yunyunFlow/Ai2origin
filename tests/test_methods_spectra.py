import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
"""Synthetic methods: analytic fixtures and explicit failure/identifiability QA."""
import importlib.util
import math
from pathlib import Path
import unittest

import numpy as np

try:
    import scipy
except ImportError:
    raise unittest.SkipTest("Optional numerical analysis requires requirements-analysis.txt")

_trap = np.trapezoid if hasattr(np, "trapezoid") else np.trapz

SPEC = importlib.util.spec_from_file_location("methods_spectra", Path(__file__).resolve().parents[1] / "scripts" / "methods_spectra.py")
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


class SpectraTests(unittest.TestCase):
    def test_normalized_profiles_and_half_maximum_use_independent_formulas(self):
        x = np.linspace(-100, 100, 100001)
        g = M.gaussian(x, 0, 2, 3)
        l = M.lorentzian(x, 0, 2, 3)
        self.assertAlmostEqual(_trap(g, x), 3, places=10)
        expected_lorentz_window = 6 / math.pi * math.atan(100)
        self.assertAlmostEqual(_trap(l, x), expected_lorentz_window, places=8)
        for profile in (M.gaussian, M.lorentzian):
            values = profile([-1., 0., 1.], 0, 2, 3)
            np.testing.assert_allclose(values[[0, 2]], values[1] / 2, rtol=1e-14)
        with self.assertRaises(ValueError): M.gaussian([0., 1.], 0, 0, 3)
        with self.assertRaises(ValueError): M.lorentzian([0., 1.], 0, 1e-320, 1e300)

    def test_representable_tails_survive_intermediate_overflow_or_underflow(self):
        # Independent whole-profile log formulas; a zero here would be a
        # numerical artifact rather than an unrepresentable final intensity.
        for x, width, area in ((1., 1e-155, 1.), (1e155, 1., 1e308)):
            expected = math.exp(math.log(area) + math.log(width) - math.log(2 * math.pi) - 2 * math.log(x))
            actual = M.lorentzian([x], 0., width, area)[0]
            self.assertAlmostEqual(actual / expected, 1., places=11)
            self.assertGreater(actual, 0)
        z = math.sqrt(800 / (4 * math.log(2)))
        for width, area in ((1., 1e308), (1e-155, 1.)):
            expected = math.exp(math.log(area) - math.log(width) + .5 * math.log(4 * math.log(2) / math.pi) - 800)
            actual = M.gaussian([z * width], 0., width, area)[0]
            self.assertAlmostEqual(actual / expected, 1., places=11)
            self.assertGreater(actual, 0)
        np.testing.assert_array_equal(M.gaussian([0., 1.], 0, 1, 0), [0., 0.])
        np.testing.assert_array_equal(M.lorentzian([0., 1.], 0, 1, 0), [0., 0.])

    def test_two_gaussians_and_explicit_baseline_recover_area_width(self):
        x = np.linspace(1100, 1800, 351)
        # Independent Gaussian sigma formula, not the implementation under test.
        def assigned(c, w, a):
            sigma = w / math.sqrt(8 * math.log(2))
            return a / (sigma * math.sqrt(2 * math.pi)) * np.exp(-0.5 * ((x - c) / sigma) ** 2)
        baseline = 0.05 + (x - 1100) * 1e-4
        y = baseline + assigned(1350, 90, 20) + assigned(1590, 55, 12)
        before = y.copy()
        r = M.fit_peaks(x, y, centers=[1350., 1590.], width_bounds=[20., 130.],
                        baseline={"kind": "linear_anchors", "anchors": [[1100., 0.05], [1800., 0.12]]})
        self.assertTrue(r["accepted_numeric_fit"])
        np.testing.assert_allclose([p["area"] for p in r["peaks"]], [20, 12], rtol=2e-8)
        np.testing.assert_allclose([p["fwhm"] for p in r["peaks"]], [90, 55], rtol=2e-8)
        np.testing.assert_array_equal(y, before)
        np.testing.assert_array_equal(r["raw_y"], y)
        np.testing.assert_allclose(np.sum(r["components"], axis=0) + r["baseline"], r["fit"], rtol=1e-14)
        np.testing.assert_allclose(np.array(r["residual"]) + r["fit"], y, atol=1e-14)
        self.assertEqual(len(r["multistart"]), 5)

    def test_lorentzian_joint_baseline_center_and_intensity_scaling(self):
        x = np.linspace(-12, 12, 241)
        y = 0.3 + 0.002 * x + 2 / (math.pi * 0.75) / (1 + ((x - 1.2) / 0.75) ** 2)
        fits = [M.fit_peaks(x, y * scale, centers=[1.], center_bounds=[[0.5, 1.8]],
                           width_bounds=[0.6, 2.5], baseline={"kind": "joint_linear"}, kind="lorentzian")
                for scale in (1., 1e-3, 1e-12, 1e-200)]
        for scale, r in zip((1., 1e-3, 1e-12, 1e-200), fits):
            self.assertTrue(r["accepted_numeric_fit"])
            self.assertAlmostEqual(r["peaks"][0]["center"], 1.2, places=6)
            self.assertAlmostEqual(r["peaks"][0]["fwhm"], 1.5, places=6)
            self.assertAlmostEqual(r["peaks"][0]["area"] / scale, 2, places=6)
            self.assertAlmostEqual(r["parameters"]["baseline_slope"] / scale, 0.002, places=7)
            if scale == 1e-200:
                self.assertIsNone(r["weighted_sse"])
                self.assertLess(r["weighted_sse_log"], -745)

    def test_weighted_sse_matches_raw_units_after_internal_scaling(self):
        x = np.linspace(-5, 5, 101)
        y = np.exp(-x ** 2 / 2) / math.sqrt(2 * math.pi) + 0.001 * np.sin(3 * x)
        weights = np.where(x >= 0, 4., 1.)
        args = dict(centers=[0.], width_bounds=[1., 3.], baseline={"kind": "none"}, weights=weights)
        first, second = M.fit_peaks(x, y, **args), M.fit_peaks(x, y, **args)
        expected_sse = np.dot(weights, np.array(first["residual"]) ** 2)
        self.assertAlmostEqual(first["weighted_sse"] / expected_sse, 1., places=12)
        self.assertEqual(first["parameters"], second["parameters"])
        self.assertEqual(first["fit"], second["fit"])

    def test_descending_source_needs_explicit_paired_reversal(self):
        x = np.linspace(-4, 4, 81); y = np.exp(-x ** 2 / 2) / math.sqrt(2 * math.pi)
        args = dict(centers=[0.], width_bounds=[1., 3.], baseline={"kind": "none"})
        with self.assertRaises(ValueError): M.fit_peaks(x[::-1], y[::-1], **args)
        r = M.fit_peaks(x[::-1], y[::-1], reverse_working_copy=True, **args)
        self.assertTrue(r["working_copy_reversed"])
        np.testing.assert_array_equal(r["raw_x"], x[::-1])
        np.testing.assert_array_equal(r["raw_y"], y[::-1])
        np.testing.assert_array_equal(r["x_working"], x)
        with self.assertRaises(ValueError): M.fit_peaks([0., 2., 1., 3.], [1., 2., 3., 4.], **args)

    def test_doublet_constraints_are_in_optimizer_and_source_unchanged(self):
        x = np.linspace(280, 300, 401)
        sigma = 1.2 / math.sqrt(8 * math.log(2))
        y = 0.1 + sum(a / (sigma * math.sqrt(2 * math.pi)) * np.exp(-0.5 * ((x - c) / sigma) ** 2)
                      for c, a in [(285.2, 8), (291.2, 4)])
        r = M.fit_doublet(x, y, center=285., center_bounds=[284.5, 285.8], split_eV=6., area_ratio=2.,
                          width_bounds=[0.5, 2.], baseline={"kind": "joint_linear"})
        self.assertTrue(r["accepted_numeric_fit"])
        a, b = r["peaks"]
        self.assertAlmostEqual(a["area"], 8., places=6)
        self.assertAlmostEqual(b["area"], 4., places=6)
        self.assertEqual(a["fwhm"], b["fwhm"])
        self.assertAlmostEqual(b["center"] - a["center"], 6., places=12)
        self.assertEqual(a["area"] / b["area"], 2.)
        np.testing.assert_array_equal(r["raw_y"], y)

    def test_bound_hit_retains_diagnostics_but_does_not_accept_model(self):
        x = np.linspace(-5, 5, 101)
        y = np.exp(-x ** 2 / 2) / math.sqrt(2 * math.pi)
        r = M.fit_peaks(x, y, centers=[0.], width_bounds=[0.2, 1.], baseline={"kind": "none"})
        self.assertFalse(r["accepted_numeric_fit"])
        self.assertIn("PARAMETER_BOUND_HIT", r["hold_reasons"])
        self.assertTrue(r["bound_hits"])
        self.assertEqual(len(r["residual"]), len(y))

    def test_coincident_peaks_expose_rank_or_condition_failure(self):
        x = np.linspace(-5, 5, 101); y = np.exp(-x ** 2 / 2) / math.sqrt(2 * math.pi)
        r = M.fit_peaks(x, y, centers=[0., 0.], width_bounds=[1., 3.], baseline={"kind": "none"})
        self.assertFalse(r["accepted_numeric_fit"])
        self.assertTrue(set(r["hold_reasons"]) & {"RANK_DEFICIENT", "ILL_CONDITIONED"})

    def test_unimplemented_background_and_invalid_inputs_refused(self):
        args = dict(centers=[0.], width_bounds=[0.5, 3.])
        x = np.linspace(-4, 4, 81); y = np.exp(-x ** 2)
        for baseline in ({"kind": "shirley"}, {"kind": "joint_linear", "extra": 1},
                         {"kind": "linear_anchors", "anchors": [[-2, 0], [2, 0]]}):
            with self.assertRaises(ValueError): M.fit_peaks(x, y, baseline=baseline, **args)
        with self.assertRaises(ValueError): M.fit_peaks(x, y, baseline={"kind": "none"}, starts=1, **args)
        with self.assertRaises(ValueError): M.fit_peaks(x, y, baseline={"kind": "none"}, weights=np.zeros_like(x), **args)
        with self.assertRaises(ValueError): M.fit_peaks(x, np.full_like(x, np.nan), baseline={"kind": "none"}, **args)

    def test_ftir_conversion_no_clipping_and_subnormal_precision(self):
        T = np.array([100., 10., 1., 0.01])
        np.testing.assert_allclose(M.percentT_to_A(T), [0., 1., 2., 4.], atol=1e-15)
        np.testing.assert_array_equal(T, [100., 10., 1., 0.01])
        self.assertLess(M.percentT_to_A([110.], allow_over_100=True)[0], 0)
        self.assertTrue(np.isfinite(M.percentT_to_A([np.nextafter(0., 1.)])[0]))
        for bad in ([0.], [-1.], [101.], [np.inf], [True]):
            with self.assertRaises(ValueError): M.percentT_to_A(bad)
        with self.assertRaises(ValueError): M.percentT_to_A([True, 50.])

    def test_xps_conversion_requires_all_conventions_not_c1s_default(self):
        ke = np.array([1199.6, 1200.6])
        r = M.xps_energy(ke, energy_type="kinetic", photon_energy_eV=1486.6,
                         work_function_eV=4., assigned_shift_eV=0.2)
        np.testing.assert_allclose(r["binding_energy_eV"], [283.2, 282.2], atol=1e-12)
        np.testing.assert_array_equal(ke, [1199.6, 1200.6])
        self.assertFalse(M.xps_energy([281.3], energy_type="binding")["shift_declared"])
        self.assertEqual(M.xps_energy([281.3], energy_type="binding")["binding_energy_eV"], [281.3])
        with self.assertRaises(ValueError): M.xps_energy(ke, energy_type="kinetic", photon_energy_eV=1486.6)
        with self.assertRaises(ValueError): M.xps_energy(ke, energy_type="kinetic", photon_energy_eV=True, work_function_eV=0.)
        with self.assertRaises(ValueError): M.xps_energy([-1., 2.], energy_type="kinetic", photon_energy_eV=1486.6, work_function_eV=4.)
        self.assertEqual(M.xps_energy([-0.2], energy_type="binding")["binding_energy_eV"], [-0.2])


class GITTTests(unittest.TestCase):
    @staticmethod
    def fick(D=2e-14, L=1e-5, tau=10., sign=1, ir=0.):
        # Independent semi-infinite constant-flux Fick solution:
        # delta(c_surface)=2*J*sqrt(t/(pi*D)); equilibrium delta(c)=J*tau/L.
        t = np.linspace(0, tau, 101)
        J_dEdc = sign * 3e-10
        pre = 3.1
        E = pre + ir + 2 * J_dEdc * np.sqrt(t / (math.pi * D))
        post = pre + J_dEdc * tau / L
        args = dict(pulse_tau_s=tau, pre_eq=pre, post_eq=post, length_m=L,
                    fit_window_s=[1., 9.], equilibrium_confirmed=True, transient_excluded=True)
        return t, E, args

    def test_independent_fick_solution_recovers_diffusivity_and_both_signs(self):
        for sign in (1, -1):
            t, E, args = self.fick(sign=sign)
            r = M.gitt_pulse(t, E, **args)
            self.assertEqual(r["status"], "CONDITIONAL_MODEL_RESULT")
            self.assertAlmostEqual(r["D_conditional_m2_s"] / 2e-14, 1., places=9)
            self.assertAlmostEqual(r["short_time_tau_D_over_L_squared"], 0.002, places=12)
            self.assertEqual(math.copysign(1, r["delta_E_s_V"]), sign)

    def test_ir_offset_does_not_change_slope_diffusion_result_or_source(self):
        results = []
        for ir in (0., 0.04):
            t, E, args = self.fick(ir=ir); before = E.copy()
            args["known_iR_drop_V"] = ir
            r = M.gitt_pulse(t, E, **args); results.append(r)
            np.testing.assert_array_equal(E, before)
            np.testing.assert_array_equal(r["raw_E_V"], E)
            self.assertAlmostEqual(r["intercept_minus_pre_minus_known_iR_V"], 0., places=12)
        self.assertAlmostEqual(results[0]["D_conditional_m2_s"] / results[1]["D_conditional_m2_s"], 1., places=10)

    def test_finite_slab_independent_eigenfunction_solution_short_time_and_long_time(self):
        # Finite slab, prescribed flux at x=0 and no flux at x=L. At the
        # surface, delta(c)=J*t/L+J*L/(3D)-2*J*L/(pi^2*D)*sum(exp(-n^2*pi^2*D*t/L^2)/n^2).
        # This fixture uses the full finite-geometry solution rather than
        # rearranging the GITT estimator or assigning a sqrt(t) voltage curve.
        L, tau, J_dEdc = 1e-5, 10., 3e-10
        t = np.linspace(0, tau, 101)
        n = np.arange(1., 6001.)[:, None]
        for D, expect_accept in ((2e-14, True), (2e-12, False)):
            q = D * t[None, :] / L ** 2
            series = np.sum(np.exp(-n ** 2 * math.pi ** 2 * q) / n ** 2, axis=0)
            response = J_dEdc * t / L + J_dEdc * L / (3 * D) - 2 * J_dEdc * L / (math.pi ** 2 * D) * series
            response[0] = 0.  # Exact t=0 limit; finite truncation has a known initial remainder.
            r = M.gitt_pulse(t, 3.1 + 0.02 + response, pulse_tau_s=tau, pre_eq=3.1,
                             post_eq=3.1 + J_dEdc * tau / L, length_m=L,
                             fit_window_s=[1., 9.], equilibrium_confirmed=True, transient_excluded=True)
            if expect_accept:
                self.assertEqual(r["status"], "CONDITIONAL_MODEL_RESULT")
                self.assertAlmostEqual(r["D_conditional_m2_s"] / D, 1., places=8)
            else:
                self.assertEqual(r["status"], "HOLD")
                self.assertIn("SHORT_TIME_APPROXIMATION_FAILED", r["hold_reasons"])
                self.assertIsNone(r["D_conditional_m2_s"])

    def test_opposite_equilibrium_and_pulse_response_directions_hold(self):
        t, E, args = self.fick()
        positive = M.gitt_pulse(t, E, **args)
        opposite = M.gitt_pulse(t, E, **(args | {"post_eq": 2 * args["pre_eq"] - args["post_eq"]}))
        self.assertIn("INCONSISTENT_PULSE_RESPONSE_DIRECTION", opposite["hold_reasons"])
        self.assertIsNone(opposite["D_conditional_m2_s"])
        self.assertAlmostEqual(positive["D_candidate_m2_s"] / opposite["D_candidate_m2_s"], 1., places=12)

    def test_short_time_equilibrium_and_geometry_holds_keep_observed_diagnostics(self):
        t, E, args = self.fick(D=1e-11)
        r = M.gitt_pulse(t, E, **args)
        self.assertIn("SHORT_TIME_APPROXIMATION_FAILED", r["hold_reasons"])
        self.assertIsNone(r["D_conditional_m2_s"])
        t, E, args = self.fick()
        for key, value, reason in [("length_m", None, "MISSING_EFFECTIVE_GEOMETRY"),
                                   ("equilibrium_confirmed", False, "EQUILIBRIUM_NOT_CONFIRMED"),
                                   ("transient_excluded", False, "IR_OR_EARLY_TRANSIENT_NOT_EXCLUDED"),
                                   ("post_eq", args["pre_eq"], "EQUILIBRIUM_CHANGE_TOO_SMALL")]:
            r = M.gitt_pulse(t, E, **(args | {key: value}))
            self.assertIn(reason, r["hold_reasons"])
            self.assertIsNone(r["D_conditional_m2_s"])
            self.assertTrue(r["fit_E_V"])

    def test_early_nonlinear_transient_window_and_invalid_declared_windows(self):
        t, E, args = self.fick()
        E = E + 0.05 * np.exp(-t / 0.2)
        r = M.gitt_pulse(t, E, **(args | {"fit_window_s": [0.1, 1.]}))
        self.assertIn("NONLINEAR_SQRT_TIME_WINDOW", r["hold_reasons"])
        for window in ([0., 1.], [8., 11.], [2., 2.], [0.1, 0.2]):
            with self.assertRaises(ValueError): M.gitt_pulse(t, E, **(args | {"fit_window_s": window}))
        with self.assertRaises(ValueError): M.gitt_pulse(t[::-1], E[::-1], **args)
        with self.assertRaises(ValueError): M.gitt_pulse(t, E, **(args | {"length_m": True}))

    def test_declared_pulse_endpoint_must_be_an_actual_source_observation(self):
        t = np.array([0., 1., 2., 3., 4., 6., 8., 11.])
        E = 3.1 + .002 * np.sqrt(t)
        with self.assertRaisesRegex(ValueError, "endpoint must be recorded"):
            M.gitt_pulse(t, E, pulse_tau_s=10., pre_eq=3.1, post_eq=3.1001, length_m=1e-5,
                         fit_window_s=[1., 8.], equilibrium_confirmed=True, transient_excluded=True)


if __name__ == "__main__":
    unittest.main()
