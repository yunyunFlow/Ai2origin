import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
"""Synthetic numerical checks, independent of any measured project data."""
import unittest

import numpy as np

try:
    import scipy
except ImportError:
    raise unittest.SkipTest("Optional numerical analysis requires requirements-analysis.txt")

_trap = np.trapezoid if hasattr(np, "trapezoid") else np.trapz

from methods_impedance import (drt_forward, drt_tikhonov, fit_rc,
                               ln_trapezoid_weights, rc_impedance)


class ImpedanceMethods(unittest.TestCase):
    def setUp(self):
        self.f = np.geomspace(1e5, 1e-2, 71)

    def test_analytic_single_rc_hz_and_inductance(self):
        tau, R, Rs, L = .01, 20., 3., 2e-6
        f = np.array([1 / (2 * np.pi * tau)])
        observed = rc_impedance(f, Rs, [R], [tau], L)
        np.testing.assert_allclose(observed, [Rs + R / 2 + 1j * (-R / 2 + L / tau)], rtol=1e-14)

    def test_preserves_both_legal_frequency_directions(self):
        z = rc_impedance(self.f, 2, [15], [.1])
        np.testing.assert_array_equal(z[::-1], rc_impedance(self.f[::-1], 2, [15], [.1]))
        self.assertTrue(np.all(z.imag < 0))

    def test_single_rc_parameter_recovery(self):
        z = 3 + 20 / (1 + 2j * np.pi * self.f * .03)
        result = fit_rc(self.f, z, 1, initial_guesses=[[2, 8, .01], [5, 40, .3]],
                        bounds=([.01, .01, 1e-6], [100, 1000, 100]), weighting="unit")
        np.testing.assert_allclose(result["parameters"], [3, 20, .03], rtol=1e-7)
        self.assertLess(result["relative_complex_rmse"], 1e-9)
        self.assertEqual(result["KK_status"], "HOLD_NOT_PERFORMED")
        self.assertEqual(result["physical_assignment"], "MODEL_ELEMENTS_ONLY")

    def test_two_rc_multistart_recovery(self):
        z = 4 + 15 / (1 + 2j * np.pi * self.f * .002) + 60 / (1 + 2j * np.pi * self.f * .4)
        result = fit_rc(self.f, z, 2,
                        initial_guesses=[[2, 8, .0001, 80, 2], [6, 100, .3, 10, .003]],
                        bounds=([.01, .01, 1e-6, .01, 1e-6], [100, 1000, 100, 1000, 100]),
                        weighting="modulus")
        order = np.argsort(result["tau_s"])
        np.testing.assert_allclose(result["tau_s"][order], [.002, .4], rtol=1e-5)
        np.testing.assert_allclose(result["R_ohm"][order], [15, 60], rtol=1e-5)
        self.assertEqual(len(result["starts"]), 2)
        self.assertEqual(result["jacobian_rank"], 5)
        self.assertIsNotNone(result["covariance_physical"])
        self.assertFalse(any(result["bound_hit"]))
        self.assertIn("modelR1_ohm", result["parameter_names"])
        self.assertNotIn("Rct", result["parameter_names"])

    def test_coincident_tau_is_unidentifiable(self):
        z = 5 + 50 / (1 + 2j * np.pi * self.f * .01)
        np.testing.assert_allclose(z, rc_impedance(self.f, 5, [20, 30], [.01, .01]))
        result = fit_rc(self.f, z, 2, initial_guesses=[[5, 20, .01, 30, .01]],
                        bounds=([.001, .001, 1e-6, .001, 1e-6], [100, 1000, 1, 1000, 1]),
                        weighting="unit")
        self.assertLess(result["relative_complex_rmse"], 1e-10)
        self.assertEqual(result["identifiability"], "HOLD_ILL_CONDITIONED")
        self.assertIsNone(result["covariance_physical"])

    def test_noisy_recovery_has_finite_conditional_residual(self):
        rng = np.random.default_rng(81)
        clean = rc_impedance(self.f, 4, [15, 60], [.002, .4])
        z = clean + .008 * np.abs(clean) * (rng.normal(size=len(clean)) + 1j * rng.normal(size=len(clean)))
        result = fit_rc(self.f, z, 2, initial_guesses=[[3, 12, .001, 50, .5], [6, 30, .01, 80, 1]],
                        bounds=([.01, .01, 1e-6, .01, 1e-6], [100, 1000, 100, 1000, 100]),
                        weighting="modulus")
        self.assertTrue(.003 < result["relative_complex_rmse"] < .025)
        self.assertTrue(np.all(np.isfinite(result["parameters"])))
        self.assertTrue(np.all(np.isfinite(result["covariance_physical"])))

    def test_impedance_scaling_preserves_rmse_and_exposes_unrepresentable_uncertainty(self):
        rng = np.random.default_rng(301)
        reference = 3 + 20 / (1 + 2j * np.pi * self.f * .03)
        z = reference + .003 * np.abs(reference) * (rng.normal(size=len(self.f)) + 1j * rng.normal(size=len(self.f)))
        fits, drts = [], []
        for scale in (1., 1e-200, 1e200):
            fits.append(fit_rc(self.f, z * scale, 1, initial_guesses=[[2 * scale, 8 * scale, .01]],
                               bounds=([.01 * scale, .01 * scale, 1e-6], [100 * scale, 1000 * scale, 100]),
                               weighting="modulus"))
            drts.append(drt_tikhonov(self.f, z * scale, np.geomspace(1e-5, 10, 31), [1e-5]))
        for scale, fit, drt in zip((1., 1e-200, 1e200), fits, drts):
            np.testing.assert_allclose(fit["parameters"] / [scale, scale, 1.], fits[0]["parameters"], rtol=1e-7)
            self.assertAlmostEqual(fit["relative_complex_rmse"], fits[0]["relative_complex_rmse"], places=12)
            self.assertAlmostEqual(drt["solutions"][0]["relative_complex_rmse"], drts[0]["solutions"][0]["relative_complex_rmse"], places=11)
            if scale == 1.:
                self.assertIsNotNone(fit["covariance_physical"])
            else:
                self.assertIsNone(fit["covariance_physical"])
                self.assertEqual(fit["covariance_status"], "HOLD_UNREPRESENTABLE_PHYSICAL_UNCERTAINTY")

    def test_large_finite_omega_tau_keeps_analytic_jacobian_finite(self):
        f = np.geomspace(1e200, 1e199, 5)
        z = 3 + 20 / (1 + 2j * np.pi * f * .03)
        with np.errstate(over="raise", invalid="raise"):
            result = fit_rc(f, z, 1, initial_guesses=[[2, 8, .01]],
                            bounds=([.01, .01, 1e-6], [100, 1000, 100]), weighting="unit")
        self.assertEqual(result["identifiability"], "HOLD_ILL_CONDITIONED")
        self.assertTrue(np.isfinite(result["relative_complex_rmse"]))

    def test_series_L_fit(self):
        z = rc_impedance(self.f, 3, [20], [.03], 2e-5)
        result = fit_rc(self.f, z, 1, initial_guesses=[[2, 12, .01, 1e-5], [5, 30, .1, 5e-5]],
                        bounds=([.01, .01, 1e-6, 0], [100, 1000, 100, .001]),
                        weighting="modulus", fit_inductance=True)
        np.testing.assert_allclose(result["parameters"], [3, 20, .03, 2e-5], rtol=1e-5)
        self.assertGreater(z[0].imag, 0)

    def test_bound_hit_does_not_report_symmetric_covariance(self):
        z = rc_impedance(self.f, 4, [20], [.03])
        result = fit_rc(self.f, z, 1, initial_guesses=[[1, 10, .01]],
                        bounds=([.01, .01, 1e-6], [2, 1000, 100]), weighting="unit")
        self.assertTrue(result["bound_hit"][0])
        self.assertEqual(result["identifiability"], "HOLD_BOUND_HIT")
        self.assertIsNone(result["covariance_physical"])

    def test_frequency_and_physical_failures(self):
        for bad in ([0, 1], [-1, 1], [1, 1], [1, 3, 2], [1, np.nan], [True, False], [True, 2], [1j, 2j]):
            with self.subTest(f=bad), self.assertRaises(ValueError):
                rc_impedance(bad, 2, [1], [.1])
        for Rs, R, tau, L in ((-1, [1], [.1], 0), (1, [-1], [.1], 0),
                              (1, [1], [0], 0), (1, [1], [.1], -1), (1, [1], [np.inf], 0)):
            with self.subTest(values=(Rs, R, tau, L)), self.assertRaises(ValueError):
                rc_impedance(self.f, Rs, R, tau, L)
        with self.assertRaises(ValueError): rc_impedance(self.f, 1, [True, 20], [.01, .1])

    def test_fitting_requires_explicit_valid_contract(self):
        z = rc_impedance(self.f, 2, [10], [.1])
        base = dict(initial_guesses=[[2, 10, .1]], bounds=([.01, .01, 1e-6], [100, 1000, 100]), weighting="unit")
        for override in ({"weighting": "auto"}, {"initial_guesses": []},
                         {"bounds": ([0, .01, 1e-6], [100, 1000, 100])},
                         {"initial_guesses": [[-1, 10, .1]]}, {"weighting": [1]},
                         {"fit_inductance": "yes"}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                fit_rc(self.f, z, 1, **(base | override))
        z[0] = np.nan + 1j
        with self.assertRaises(ValueError):
            fit_rc(self.f, z, 1, **base)
        with self.assertRaises(ValueError):
            fit_rc(self.f, [True] + [1 + 1j] * (len(self.f) - 1), 1, **base)

    def test_natural_log_quadrature_and_area(self):
        tau = np.geomspace(1e-3, 1e5, 81)
        gamma = np.full(len(tau), 2.)
        weights = ln_trapezoid_weights(tau)
        natural_area = float(weights @ gamma)
        decimal_area = float(_trap(gamma, np.log10(tau)))
        self.assertAlmostEqual(natural_area, np.log(10) * decimal_area, places=12)
        z = drt_forward(np.array([1e-13]), tau, gamma, Rinf=3)
        self.assertAlmostEqual(z[0].real - 3, natural_area, places=9)
        self.assertNotAlmostEqual(natural_area, decimal_area)

    def test_drt_synthetic_fine_to_coarse_lambda_sensitivity(self):
        fine = np.geomspace(1e-5, 100, 2049)
        x = np.log(fine)
        gamma = (20 * np.exp(-.5 * ((x - np.log(.002)) / .35)**2) / (.35 * np.sqrt(2*np.pi))
                 + 60 * np.exp(-.5 * ((x - np.log(.4)) / .6)**2) / (.6 * np.sqrt(2*np.pi)))
        clean = drt_forward(self.f, fine, gamma, Rinf=4)
        rng = np.random.default_rng(7)
        z = clean + .002 * np.abs(clean) * (rng.normal(size=len(clean)) + 1j * rng.normal(size=len(clean)))
        coarse = np.geomspace(1e-5, 100, 81)
        result = drt_tikhonov(self.f, z, coarse, [1e-8, 1e-6, 1e-4])
        self.assertEqual(result["selection"], "NOT_SELECTED_SENSITIVITY_ONLY")
        self.assertEqual(result["KK_status"], "HOLD_NOT_PERFORMED")
        self.assertEqual(result["scientific_resolution"], "NOT_CERTIFIED")
        self.assertGreater(result["outside_sampled_tau_nodes"], 0)
        sols = result["solutions"]
        self.assertLess(sols[0]["relative_complex_rmse"], .015)
        self.assertGreaterEqual(sols[-1]["data_term"] + 1e-9, sols[0]["data_term"])
        self.assertLessEqual(sols[-1]["roughness"], sols[0]["roughness"] + 1e-9)
        for sol in sols:
            self.assertTrue(np.all(sol["gamma_ohm"] >= 0))
            integral = result["ln_quadrature_weights"] @ sol["gamma_ohm"]
            self.assertAlmostEqual(sol["gamma_integral_ohm"], integral, places=10)
            np.testing.assert_allclose(sol["Z_fit"], drt_forward(self.f, coarse, sol["gamma_ohm"], Rinf=sol["Rinf_ohm"]), rtol=1e-13)
        # No number-of-peaks or mechanistic recovery assertion is made.

    def test_drt_analytic_rc_and_series_L_reconstruction(self):
        z = 3 + 20 / (1 + 2j * np.pi * self.f * .03) + 2j * np.pi * self.f * 2e-5
        result = drt_tikhonov(self.f, z, np.geomspace(1e-6, 10, 91), [1e-9], fit_inductance=True)
        sol = result["solutions"][0]
        self.assertLess(sol["relative_complex_rmse"], .025)
        self.assertAlmostEqual(sol["L_H"] / 2e-5, 1, delta=.03)
        self.assertAlmostEqual(sol["gamma_integral_ohm"], 20, delta=.7)

    def test_drt_invalid_inputs_rejected(self):
        tau = np.geomspace(1e-5, 100, 31)
        z = rc_impedance(self.f, 2, [10], [.1])
        for bad in ([0, 1], [1, 1], [2, 1], [1, np.nan]):
            with self.subTest(tau=bad), self.assertRaises(ValueError):
                ln_trapezoid_weights(bad)
        with self.assertRaises(ValueError):
            drt_forward(self.f, tau, -np.ones(len(tau)))
        for lambdas, order in (([0], 2), ([-1], 2), ([1, 1], 2), ([np.inf], 2), ([1], 0), ([1], True), ([1], 2.0)):
            with self.subTest(values=(lambdas, order)), self.assertRaises(ValueError):
                drt_tikhonov(self.f, z, tau, lambdas, order)
        with self.assertRaises(ValueError):
            drt_tikhonov(self.f, z, np.array([.001, .01, 1.]), [1e-3])

    def test_unrepresentable_log_grid_or_kernel_rejected(self):
        tau = np.array([1e300, np.nextafter(1e300, np.inf)])
        with self.assertRaises(ValueError):
            ln_trapezoid_weights(tau)
        with self.assertRaises(ValueError):
            rc_impedance([1e300], 1, [1], [1e300])


if __name__ == "__main__":
    unittest.main()
