import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
"""Independent BV, transport/charging counterexamples and strict LSV contracts."""
import importlib.util
from decimal import Decimal, localcontext
import math
from pathlib import Path
import unittest

import numpy as np

SPEC = importlib.util.spec_from_file_location("methods_tafel", Path(__file__).resolve().parents[1] / "scripts" / "methods_tafel.py")
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)
CONDITIONS = dict.fromkeys(M.CONDITIONS, True)
IR_NONE = {"Ru_ohm": 0., "input_compensation": "none", "prior_fraction": 0., "residual_fraction": 0.}
DIRECT = {"mode": "direct_RHE", "offset_V": 0., "provenance": "assigned synthetic RHE axis"}


def contract(eta, j, *, area=2., Eeq=0., **kwargs):
    return M.prepare_lsv(np.array(eta) + Eeq, np.array(j) * area, current_unit="A",
                         current_sign="anodic_positive", area_cm2=area, ir=IR_NONE,
                         reference=DIRECT, equilibrium_potential_RHE_V=Eeq, **kwargs)


def fit(prepared, *, polarity="anodic", **kwargs):
    return M.fit_tafel(prepared, window={"kind": "indices", "indices": list(range(len(prepared["raw_E_V"])))},
                       polarity=polarity, log_reference_value=1., log_reference_unit="A/cm2",
                       conditions=CONDITIONS, **kwargs)


class TafelTests(unittest.TestCase):
    def test_unrepresentable_scalars_and_rhe_shift_are_refused(self):
        for value in [np.longdouble('1e-400'), 10**400]:
            with self.subTest(value=str(value)), self.assertRaises(ValueError):
                M.prepare_lsv([.1, .2], [.001, .002], current_unit='A',
                    current_sign='anodic_positive', reference={**DIRECT, 'offset_V': value})
        with self.assertRaisesRegex(ValueError, 'pH shift.*underflow'):
            M.prepare_lsv([.1, .2], [.001, .002], current_unit='A',
                current_sign='anodic_positive', reference={'mode': 'reference_SHE',
                    'reference_to_SHE_V': 0., 'temperature_K': 1e-320, 'pH': 1.,
                    'reference_name': 'assigned', 'filling': 'assigned',
                    'junction_assumption': 'neglected'})

    def test_rhe_shift_avoids_intermediate_subnormal_precision_loss(self):
        reference = {'mode': 'reference_SHE', 'reference_to_SHE_V': 0.,
                     'temperature_K': 1e-319, 'pH': 1e308, 'reference_name': 'assigned',
                     'filling': 'assigned', 'junction_assumption': 'neglected'}
        result = M.prepare_lsv([.1, .2], [.001, .002], current_unit='A',
                              current_sign='anodic_positive', reference=reference)
        with localcontext() as context:
            context.prec = 80
            expected = float(Decimal.from_float(M.R) / Decimal.from_float(M.F) *
                       Decimal.from_float(math.log(10)) * Decimal.from_float(reference['temperature_K']) *
                       Decimal.from_float(reference['pH']))
        self.assertLess(abs(result['reference_metadata']['total_offset_V'] / expected - 1), 5e-16)

    def test_raw_lsv_available_without_reference_equilibrium_area(self):
        E, I = np.array([0., 0.1, 0.2]), np.array([-1e-3, 0., 1e-3])
        r = M.prepare_lsv(E, I, current_unit="A", current_sign="anodic_positive")
        np.testing.assert_array_equal(r["raw_E_V"], E)
        np.testing.assert_array_equal(r["raw_current"], I)
        self.assertIsNone(r["E_RHE_V"]); self.assertIsNone(r["eta_RHE_V"])
        result = fit(r)
        self.assertEqual(result["status"], "HOLD")
        self.assertIsNone(result["slope_signed_V_per_dec"])
        self.assertIn("MISSING_REFERENCE_CONVENTION", result["hold_reasons"])

    def test_signed_ir_corrects_both_polarities_with_A_not_current_density(self):
        E = np.array([0.4, 0.2, 0.0]); I = np.array([0.002, 0., -0.002])
        r = M.prepare_lsv(E, I, current_unit="A", current_sign="anodic_positive", area_cm2=0.5,
                         ir={"Ru_ohm": 20., "input_compensation": "none", "prior_fraction": 0., "residual_fraction": 0.95})
        np.testing.assert_allclose(r["E_internal_V"], [0.362, 0.2, 0.038], atol=1e-15)
        np.testing.assert_array_equal(E, [0.4, 0.2, 0.])
        density = M.prepare_lsv(E, I / 0.5 * 1e3, current_unit="mA/cm2", current_sign="anodic_positive",
                                area_cm2=0.5, ir={"Ru_ohm": 20., "input_compensation": "none", "prior_fraction": 0., "residual_fraction": 0.95})
        np.testing.assert_allclose(density["E_internal_V"], r["E_internal_V"], atol=1e-15)
        with self.assertRaises(ValueError):
            M.prepare_lsv(E, I, current_unit="A/cm2", current_sign="anodic_positive", ir=IR_NONE)

    def test_partial_and_full_compensation_refuse_double_correction(self):
        Eint = np.array([0.1, 0.2]); I = np.array([0.001, 0.002]); Ru = 25.
        already = Eint + I * Ru * 0.2
        r = M.prepare_lsv(already, I, current_unit="A", current_sign="anodic_positive",
                         ir={"Ru_ohm": Ru, "input_compensation": "partial", "prior_fraction": 0.8, "residual_fraction": 0.2})
        np.testing.assert_allclose(r["E_internal_V"], Eint, atol=1e-15)
        for state, prior, residual in [("partial", 0.8, 1.), ("full", 1., 0.1), ("none", 0.2, 0.2), ("unknown", 0., 0.)]:
            with self.assertRaises(ValueError):
                M.prepare_lsv(Eint, I, current_unit="A", current_sign="anodic_positive",
                              ir={"Ru_ohm": Ru, "input_compensation": state, "prior_fraction": prior, "residual_fraction": residual})

    def test_reference_routes_are_mutually_exclusive_and_temperature_explicit(self):
        ref = {"mode": "reference_SHE", "reference_to_SHE_V": 0.197, "temperature_K": 308.15,
               "pH": 14., "reference_name": "assigned Ag/AgCl", "filling": "assigned 3 M KCl",
               "junction_assumption": "neglected"}
        r = M.prepare_lsv([0., 0.1], [0.001, 0.002], current_unit="A", current_sign="anodic_positive", reference=ref)
        expected = 0.197 + 8.31446261815324 * 308.15 * math.log(10) / 96485.33212 * 14
        np.testing.assert_allclose(r["E_RHE_V"], [expected, expected + 0.1], rtol=1e-14)
        self.assertIn("not a validated calibration", r["reference_metadata"]["claim"])
        for bad in (ref | {"offset_V": 0.3}, DIRECT | {"pH": 14.}, ref | {"temperature_K": 0.},
                    ref | {"temperature_K": True}, ref | {"filling": ""}, ref | {"junction_assumption": "corrected"}):
            with self.assertRaises(ValueError):
                M.prepare_lsv([0., 0.1], [0.001, 0.002], current_unit="A", current_sign="anodic_positive", reference=bad)

    def test_strict_butler_volmer_high_field_both_signs_recover_conditional_slopes(self):
        T, alpha, n = 298.15, 0.5, 1.
        ideal = math.log(10) * 8.31446261815324 * T / (alpha * n * 96485.33212)
        for sign, polarity in ((1, "anodic"), (-1, "cathodic")):
            eta = sign * np.linspace(0.20, 0.35, 101)
            argument = n * 96485.33212 * eta / (8.31446261815324 * T)
            j = 1e-6 * (np.exp(alpha * argument) - np.exp(-(1 - alpha) * argument))
            r = fit(contract(eta, j), polarity=polarity)
            self.assertEqual(r["status"], "CONDITIONAL_APPARENT_FIT")
            self.assertAlmostEqual(r["slope_signed_V_per_dec"] / (sign * ideal), 1., delta=2e-4)
            self.assertEqual(r["scientific_validation"], "NOT_ESTABLISHED")
            self.assertFalse(r["automatic_exchange_current_alpha_RDS_icorr"])

    def test_low_field_butler_volmer_has_curvature_and_slope_sensitivity(self):
        eta = np.linspace(0.001, 0.05, 101)
        argument = 96485.33212 * eta / (8.31446261815324 * 298.15)
        j = 1e-6 * (np.exp(argument / 2) - np.exp(-argument / 2))
        r = fit(contract(eta, j), min_decades=0.2)
        self.assertTrue(set(r["hold_reasons"]) & {"CURVATURE_DIAGNOSTIC_FLAG", "FIT_WINDOW_SLOPE_SENSITIVITY"})

    def test_noisefree_and_noisy_assigned_slope_preserve_arrays_repeat(self):
        j = np.logspace(-5, -2, 121); eta = 0.4 + 0.06 * np.log10(j / 0.001)
        eta_noise = eta + 0.0003 * np.sin(np.arange(len(j)) * 0.37)
        for values in (eta, eta_noise):
            raw_eta, raw_j = values.copy(), j.copy()
            prepared = contract(values, j, Eeq=1.229)
            a, b = fit(prepared), fit(prepared)
            self.assertAlmostEqual(a["slope_signed_V_per_dec"], 0.06, delta=5e-5)
            self.assertEqual(a, b)
            np.testing.assert_array_equal(values, raw_eta); np.testing.assert_array_equal(j, raw_j)
            np.testing.assert_allclose(np.array(a["fit_eta_V"]) + a["residual_V"], a["eta_V"], atol=1e-15)

    def test_mass_transport_high_R2_still_biased_and_not_kinetic_acceptance(self):
        jk = np.logspace(-3.7, -2.7, 101)
        eta = 0.4 + 0.060 * np.log10(jk / 0.001)
        j = jk * 0.01 / (jk + 0.01)
        p = contract(eta, j)
        r = M.fit_tafel(p, window={"kind": "indices", "indices": list(range(len(j)))},
                        polarity="anodic", log_reference_value=1., log_reference_unit="A/cm2",
                        conditions=CONDITIONS | {"transport_negligible": False})
        self.assertGreater(r["r2"], 0.999)
        self.assertGreater(r["slope_magnitude_mV_per_dec"], 64.)
        self.assertIn("CONDITION_NOT_ESTABLISHED:transport_negligible", r["hold_reasons"])
        self.assertEqual(r["scientific_validation"], "NOT_ESTABLISHED")

    def test_capacitive_offset_high_R2_still_biased_and_flagged(self):
        jfar = np.logspace(-2.7, -1.7, 101)
        eta = 0.5 + 0.060 * np.log10(jfar / 0.001)
        j = jfar + 0.001
        p = contract(eta, j)
        r = M.fit_tafel(p, window={"kind": "indices", "indices": list(range(len(j)))},
                        polarity="anodic", log_reference_value=1., log_reference_unit="A/cm2",
                        conditions=CONDITIONS | {"charging_negligible": False})
        self.assertGreater(r["r2"], 0.99)
        self.assertGreater(r["slope_magnitude_mV_per_dec"], 65.)
        self.assertIn("CONDITION_NOT_ESTABLISHED:charging_negligible", r["hold_reasons"])

    def test_log_reference_unit_changes_intercept_only_and_current_window_retains_indices(self):
        j = np.logspace(-5, -2, 101); eta = 0.4 + 0.06 * np.log10(j / 0.001)
        p = contract(eta, j)
        a = fit(p)
        b = M.fit_tafel(p, window={"kind": "indices", "indices": list(range(len(j)))}, polarity="anodic",
                        log_reference_value=1., log_reference_unit="mA/cm2", conditions=CONDITIONS)
        self.assertAlmostEqual(a["slope_signed_V_per_dec"], b["slope_signed_V_per_dec"], places=14)
        self.assertAlmostEqual(a["intercept_V"] - b["intercept_V"], 3 * 0.06, places=14)
        c = M.fit_tafel(p, window={"kind": "current_abs", "unit": "mA/cm2", "range": [0.1, 1.]},
                        polarity="anodic", log_reference_value=1., log_reference_unit="mA/cm2", conditions=CONDITIONS,
                        min_decades=0.5)
        expected = np.flatnonzero((np.log10(j) + 3 >= -1) & (np.log10(j) + 3 <= 0)).tolist()
        self.assertEqual(c["source_indices_zero_based"], expected)

    def test_zero_opposite_current_nonmonotonic_branch_and_insufficient_range_refused(self):
        j = np.logspace(-5, -2, 101); eta = 0.4 + 0.06 * np.log10(j / 0.001)
        for bad in (np.where(np.arange(len(j)) == 10, 0., j), np.where(np.arange(len(j)) == 10, -j, j)):
            with self.assertRaises(ValueError): fit(contract(eta, bad))
        with self.assertRaises(ValueError): fit(contract(eta[::-1], j))
        altered = eta.copy(); altered[20] = altered[19]
        with self.assertRaises(ValueError): fit(contract(altered, j))
        with self.assertRaises(ValueError): fit(contract(eta, j), min_decades=5.)
        with self.assertRaises(ValueError): fit(contract(eta, j), min_points=200)

    def test_corrosion_mode_is_specialized_HOLD_not_automatic_icorr(self):
        p = contract([0.1, 0.2, 0.3], [0.001, 0.002, 0.003], mode="corrosion")
        r = fit(p)
        self.assertIn("CORROSION_REQUIRES_SPECIALIZED_MIXED_CURRENT_MODEL", r["hold_reasons"])
        self.assertIsNone(r["slope_signed_V_per_dec"])

    def test_millivolt_slope_overflow_is_refused_before_returning_inf(self):
        eta = np.linspace(1e306, 3e306, 31)
        j = np.logspace(-4, -2, 31)
        with self.assertRaisesRegex(ValueError, "mV/dec magnitude is unrepresentable"):
            fit(contract(eta, j, area=1.))

    def test_nonzero_ir_scale_underflow_is_refused_not_claimed_as_zero(self):
        with self.assertRaisesRegex(ValueError, "no false zero correction"):
            M.prepare_lsv([0.1, 0.2], [1., 2.], current_unit="A", current_sign="anodic_positive",
                          ir={"Ru_ohm": 1e-300, "input_compensation": "none", "prior_fraction": 0., "residual_fraction": 1e-300})

    def test_sparse_indices_cannot_hide_intervening_scan_turns(self):
        eta = np.r_[np.linspace(0.1, 0.3, 30), np.linspace(0.29, 0.09, 30), np.linspace(0.31, 0.5, 30)]
        j = 0.001 * 10 ** ((eta - 0.4) / 0.06)
        p = contract(eta, j)
        with self.assertRaisesRegex(ValueError, "pool separate scan branches"):
            M.fit_tafel(p, window={"kind": "indices", "indices": list(range(30)) + list(range(60, 90))},
                        polarity="anodic", log_reference_value=1., log_reference_unit="A/cm2", conditions=CONDITIONS)
        # Sparse points within a single reverse scan remain in acquisition order.
        r = M.fit_tafel(p, window={"kind": "indices", "indices": list(range(30, 60, 2))},
                        polarity="anodic", log_reference_value=1., log_reference_unit="A/cm2", conditions=CONDITIONS,
                        min_decades=0.5)
        self.assertAlmostEqual(r["slope_magnitude_mV_per_dec"], 60., places=10)
        self.assertEqual(r["source_branch_interval_zero_based"], [30, 58])
        self.assertEqual(r["source_indices_zero_based"], list(range(30, 60, 2)))

    def test_invalid_units_missing_metadata_boolean_and_nonfinite_refused(self):
        for unit in ("ohm", "A/m2", "mAcm2"):
            with self.assertRaises(ValueError): M.prepare_lsv([0.1, 0.2], [0.01, 0.02], current_unit=unit, current_sign="anodic_positive")
        with self.assertRaises(ValueError): M.prepare_lsv([0.1, np.nan], [0.01, 0.02], current_unit="A", current_sign="anodic_positive")
        with self.assertRaises(ValueError): M.prepare_lsv([0.1, 0.2], [0.01, 0.02], current_unit="A", current_sign="cathodic_positive")
        with self.assertRaises(ValueError): M.prepare_lsv([0.1, 0.2], [0.01, 0.02], current_unit="A", current_sign="anodic_positive", area_cm2=True)
        p = contract(np.linspace(0.2, 0.4, 31), np.logspace(-5, -2, 31))
        with self.assertRaises(ValueError):
            M.fit_tafel(p, window={"kind": "indices", "indices": [0, 2, 1]}, polarity="anodic", log_reference_value=1., log_reference_unit="A/cm2", conditions=CONDITIONS)
        with self.assertRaises(ValueError):
            M.fit_tafel(p, window={"kind": "indices", "indices": list(range(31))}, polarity="anodic", log_reference_value=True, log_reference_unit="A/cm2", conditions=CONDITIONS)


if __name__ == "__main__":
    unittest.main()
