import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
"""Synthetic mathematical regressions for portable CV/ICA methods."""

import unittest

import numpy as np

from methods_cv import (CDL_CONDITIONS, RS_CONDITIONS, cdl, cycle_efficiency, dunn, dunn_contributions,
                        ica, integrate_branch, peak_window, randles_sevcik_diffusivity,
                        randles_sevcik_peak, scan_rate_fit)


class BranchTests(unittest.TestCase):
    def test_ideal_capacitor_both_directions_and_units(self):
        t = np.array([0, .1, .8, 2., 3.])
        capacitance, rate = 2.4, .2
        for direction in (1, -1):
            e = .9 + direction * rate * t
            current = np.full(len(t), direction * capacitance * rate)
            result = integrate_branch(t, e, current)
            self.assertAlmostEqual(result["apparent_F"], capacitance)
            self.assertAlmostEqual(result["signed_charge_C"], direction * 1.44)
            self.assertAlmostEqual(result["signed_charge_mAh"], direction * .4)
            np.testing.assert_array_equal(result["current_A"], current)
        # The net reversible-loop charge is zero; mean branch F is not zero.
        self.assertAlmostEqual(integrate_branch(t, .9 + rate*t, current * -1)["signed_charge_C"]
                               + integrate_branch(t, .9 - rate*t, current)["signed_charge_C"], 0)

    def test_zero_and_cancelling_current_remain_zero(self):
        for current in ([0, 0, 0], [1, 0, -1]):
            result = integrate_branch([0, 1, 2], [0, 1, 2], current)
            self.assertEqual(result["signed_charge_C"], 0)
            self.assertEqual(result["apparent_F"], 0)

    def test_bad_time_branch_types_and_shapes_are_rejected(self):
        invalid = [([0, 0, 2], [0, 1, 2], [1, 1, 1]),
                   ([0, 2, 1], [0, 1, 2], [1, 1, 1]),
                   ([0, 1, 2], [0, 1, 0], [1, 1, 1]),
                   ([0, True, 2], [0, 1, 2], [1, 1, 1]),
                   ([0, 1, 2], [0, 1, 2], [1, np.nan, 1]),
                   ([0, 1], [0, 1, 2], [1, 1, 1])]
        for args in invalid:
            with self.subTest(args=args), self.assertRaises(ValueError):
                integrate_branch(*args)

    def test_unrepresentable_span_and_nonzero_underflow_are_rejected(self):
        with self.assertRaises(ValueError):
            integrate_branch([0, 1, 2], [-1e308, 0, 1e308], [1, 1, 1])
        with self.assertRaises(ValueError):
            integrate_branch([0, 1], [0, 1], [5e-324, 5e-324])
        with self.assertRaises(ValueError):
            ica([0, 1, 2], [-1e308, 0, 1e308], Q_convention="signed_charge")

    def test_peak_is_raw_signed_node_with_edge_missing_and_ties(self):
        e = [0, .1, .3, .9, 1.]
        result = peak_window(e, [-.1, -.6, -1.2, -.4, -.2], [0, 1], "cathodic")
        self.assertEqual((result["status"], result["index"], result["current_A"]), ("ok", 2, -1.2))
        self.assertEqual(peak_window(e, [1, 2, 3, 4, 5], [0, 1], "anodic")["status"], "edge")
        self.assertEqual(peak_window(e, [1, 2, 3, 4, 5], [2, 3], "anodic")["reason"], "no_nodes_in_window")
        self.assertEqual(peak_window(e, [1, 2, 3, 4, 5], [0, 1], "cathodic")["status"], "missing")
        self.assertEqual(peak_window(e, [0, 0, 0, 0, 0], [0, 1], "anodic")["status"], "missing")
        tied = peak_window(e, [0, 3, 3, 1, 0], [0, 1], "anodic")
        self.assertEqual(tied["index"], 1)
        np.testing.assert_array_equal(tied["tie_indices"], [1, 2])


class RateAndDunnTests(unittest.TestCase):
    rates = np.array([.0001, .0003, .0008, .0015, .003])

    def test_b_and_sqrt_current_magnitude_keep_original_sign(self):
        current = -.7 * np.sqrt(self.rates)
        result = scan_rate_fit(self.rates, current)
        self.assertAlmostEqual(result["b"], .5)
        self.assertAlmostEqual(result["sqrt_slope_A_per_sqrt_V_s"], .7)
        self.assertAlmostEqual(result["sqrt_intercept_A"], 0)
        np.testing.assert_array_equal(result["peak_current_A"], current)
        self.assertEqual(result["sqrt_fit"]["rank"], 2)
        self.assertTrue(np.isfinite(result["sqrt_fit"]["condition"]))
        self.assertLess(np.max(np.abs(result["log_fit"]["residual"])), 1e-12)

    def test_exact_positive_and_negative_pure_mixed_components(self):
        k1 = np.array([.7, 0., .4, -.3])
        k2 = np.array([0., .9, .2, .5])
        current = self.rates[:, None]*k1 + np.sqrt(self.rates)[:, None]*k2
        before = current.copy()
        for sign in (1, -1):
            for space in ("raw", "normalized"):
                result = dunn(self.rates, sign*current, fit_space=space)
                np.testing.assert_allclose(result["k1"], sign*k1, atol=1e-12)
                np.testing.assert_allclose(result["k2"], sign*k2, atol=1e-12)
                np.testing.assert_allclose(result["reconstructed_A"], sign*current, atol=1e-14)
                self.assertTrue(result["linear_opposes_observed"][:, 3].all())
                self.assertEqual(result["rank"], 2)
        np.testing.assert_array_equal(current, before)
        negative = dunn(self.rates, -current[:, :3], polarity="cathodic")
        self.assertTrue(np.all(negative["k1"] <= 1e-12))
        self.assertFalse(negative["sqrt_opposes_observed"].any())

    def test_raw_and_normalized_have_distinct_declared_objectives(self):
        rates = np.array([.1, .2, .8, 1.6, 3.2])
        current = (2*rates + 3*np.sqrt(rates) + np.array([.3, -.1, .15, -.25, .1]))[:, None]
        raw, normalized = dunn(rates, current), dunn(rates, current, fit_space="normalized")
        self.assertGreater(abs(raw["k1"][0] - normalized["k1"][0]), .01)
        raw_obj = np.sum(raw["residual_A"]**2)
        normalized_in_raw = np.sum(normalized["residual_A"]**2)
        self.assertLess(raw_obj, normalized_in_raw)
        weighted_obj = np.sum(normalized["residual_A"]**2/rates[:, None])
        raw_in_weighted = np.sum(raw["residual_A"]**2/rates[:, None])
        self.assertLess(weighted_obj, raw_in_weighted)
        np.testing.assert_array_equal(normalized["current_residual_weights"], 1/rates)

    def test_missing_rank_zero_rate_zero_peak_and_wrong_polarity_rejected(self):
        for rates in ([1, 1, 1], [1, 2], [1, 1, 2], [0, 1, 2], [True, 1, 2], [np.inf, 1, 2]):
            with self.subTest(rates=rates), self.assertRaises(ValueError):
                dunn(rates, np.ones((len(rates), 1)))
        with self.assertRaises(ValueError):
            scan_rate_fit([1, 2, 3], [1, 0, 3])
        with self.assertRaises(ValueError):
            dunn([1, 2, 3], [[-1], [-2], [-3]], polarity="anodic")
        with self.assertRaises(ValueError):
            dunn([1, 2, 3], [[1], [2], [3]], polarity="cathodic")

    def test_unrepresentable_squared_residual_is_rejected(self):
        # All inputs/coefficients are finite, but the requested SSE exceeds float.
        with self.assertRaisesRegex(ValueError, "weighted residual sum of squares"):
            dunn([1, 2, 3, 4], [[1e200], [-1e200], [1e200], [-1e200]])

    def test_narrow_rates_full_rank_hold_and_residual_objective_units(self):
        narrow = 1+np.arange(4)*1e-12
        noise = np.array([0, 1e-14, -1e-14, 0])
        original = (.2*narrow+.1*np.sqrt(narrow))[:, None]
        exact = dunn(narrow, original)
        perturbed = dunn(narrow, original+noise[:, None])
        self.assertEqual(perturbed["rank"], 2)
        self.assertEqual(perturbed["status"], "HOLD_ILL_CONDITIONED")
        self.assertGreater(perturbed["scaled_condition"], perturbed["condition_limit"])
        np.testing.assert_array_equal(perturbed["current_A"], original+noise[:, None])
        np.testing.assert_allclose(perturbed["reconstructed_A"]+perturbed["residual_A"],
                                   perturbed["current_A"], atol=1e-16)
        wide = np.array([.005, .01, .02, .04])
        wide_original = (.2*wide+.1*np.sqrt(wide))[:, None]
        wide_exact = dunn(wide, wide_original)
        wide_perturbed = dunn(wide, wide_original+noise[:, None])
        self.assertEqual(wide_perturbed["status"], "CONDITIONAL_EMPIRICAL_FIT")
        self.assertGreater(abs(perturbed["k1"][0]-exact["k1"][0]),
                           1e6*abs(wide_perturbed["k1"][0]-wide_exact["k1"][0]))
        normalized = dunn(wide, wide_original, fit_space="normalized")
        self.assertEqual(wide_exact["weighted_sse_unit"], "A^2")
        self.assertEqual(normalized["weighted_sse_unit"], "A^2/(V/s)")
        self.assertEqual(normalized["current_residual_weight_unit"], "s/V")
        for limit in [True, 1, 0, np.inf, np.nan]:
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                dunn(wide, wide_original, condition_limit=limit)


class DunnContributionTests(unittest.TestCase):
    rates = np.array([.003, .0001, .0015, .0003, .0008])
    parameters = dict(complete_cycle=True, residual_tolerance=1e-10)

    def exact_branches(self, rates=None):
        rates = self.rates if rates is None else np.asarray(rates)
        branches = []
        for name, potential, sign in [("forward", np.array([0., .1, .4, 1.]), 1),
                                       ("reverse", np.array([1., .7, .3, 0.]), -1)]:
            k1, k2 = sign*(.2+.1*potential), sign*(.015+.02*potential)
            branches.append(dict(name=name, potential_V=potential,
                                 current_A=rates[:, None]*k1+np.sqrt(rates)[:, None]*k2))
        return branches

    def test_analytic_cycle_low_rate_bar_units_and_oriented_not_net_charge(self):
        # Independent antiderivatives over [0,1]: integral k1=.25, integral k2=.025.
        branches = self.exact_branches()
        for space in ("raw", "normalized"):
            result = dunn_contributions(self.rates, branches, fit_space=space, **self.parameters)
            self.assertEqual(result["status"], "CONDITIONAL_EMPIRICAL_FRACTIONS")
            np.testing.assert_array_equal(result["rates_V_s"], self.rates)
            for rate, row in zip(self.rates, result["aggregate"]["per_rate"]):
                expected_total = .5+.05/np.sqrt(rate)
                expected_linear = .5/expected_total
                self.assertAlmostEqual(row["linear_abs_charge_C"], .5, places=12)
                self.assertAlmostEqual(row["sqrt_abs_charge_C"], .05/np.sqrt(rate), places=12)
                self.assertAlmostEqual(row["observed_abs_charge_C"], expected_total, places=12)
                self.assertAlmostEqual(row["model_path_area_charge_C"], expected_total, places=12)
                self.assertAlmostEqual(row["observed_signed_charge_C"], 0, places=12)
                self.assertAlmostEqual(row["conditional_model_fractions"]["linear"], expected_linear)
                self.assertAlmostEqual(row["formal_abs_component_shares"]["linear"], expected_linear)
                self.assertAlmostEqual(row["path_model_fraction_percent"]["linear"], expected_linear*100)
                self.assertAlmostEqual(sum(row["path_observed_ratio_percent"].values()), 100)
                self.assertEqual(row["charge_unit"], "C")
            lowest = result["aggregate"]["per_rate"][1]
            self.assertAlmostEqual(lowest["path_model_fraction_percent"]["linear"], 100/11)
            cathodic = result["branches"][1]
            self.assertTrue(all(row["observed_signed_charge_C"] < 0 for row in cathodic["per_rate"]))
            np.testing.assert_array_equal(cathodic["potential_V"], branches[1]["potential_V"])
            np.testing.assert_array_equal(cathodic["fit"]["current_A"], branches[1]["current_A"])

    def test_density_units_no_area_inference_and_no_false_absolute_C_alias(self):
        branches = self.exact_branches()
        result = dunn_contributions(self.rates, branches, current_basis="current_density_A_m2",
                                    **self.parameters)
        self.assertEqual((result["input_unit"], result["charge_unit"]), ("A/m2", "C/m2"))
        self.assertEqual(result["branches"][0]["fit"]["coefficient_units"],
                         ["(A/m2)/(V/s)", "(A/m2)/sqrt(V/s)"])
        self.assertEqual(result["branches"][0]["fit"]["weighted_sse_unit"], "(A/m2)^2")
        row = result["aggregate"]["per_rate"][0]
        self.assertAlmostEqual(row["linear_abs_charge_C_per_m2"], .5)
        self.assertNotIn("linear_abs_charge_C", row)
        self.assertAlmostEqual(row["path_model_fraction_percent"]["linear"],
                               .5/(.5+.05/np.sqrt(self.rates[0]))*100)

    def test_zero_crossing_absolute_integral_is_exact_not_endpoint_trapezoid(self):
        rates = np.array([.25, 1., 4.])
        e = np.array([0., 1.])
        k1, k2 = e-.25, 2*(e-.25)
        branch = dict(name="crossing", potential_V=e,
                      current_A=rates[:, None]*k1+np.sqrt(rates)[:, None]*k2)
        result = dunn_contributions(rates, [branch], complete_cycle=False, residual_tolerance=1e-10)
        # integral abs(E-.25) from0to1=(.25**2+.75**2)/2=.3125, not .5.
        for rate, row in zip(rates, result["branches"][0]["per_rate"]):
            self.assertAlmostEqual(row["linear_abs_charge_C"], .3125)
            self.assertAlmostEqual(row["sqrt_abs_charge_C"], .625/np.sqrt(rate))
            self.assertAlmostEqual(row["linear_signed_charge_C"], .25)
            self.assertEqual(row["status"], "CONDITIONAL_EMPIRICAL_FRACTIONS")
        self.assertEqual(result["aggregate"]["scope"], "selected_branches")
        self.assertIn("incomplete_cycle", result["aggregate"]["per_rate"][0]["hold_reasons"])
        self.assertIsNone(result["aggregate"]["per_rate"][0]["conditional_model_fractions"])

    def test_opposition_between_nodes_is_found_and_absolute_identity_closes(self):
        rates, e = np.array([.25, 1., 4.]), np.array([0., 1.])
        k1, k2 = e-.25, e-.75
        current = rates[:, None]*k1+np.sqrt(rates)[:, None]*k2
        result = dunn_contributions(rates, [dict(name="crossing", potential_V=e, current_A=current)],
                                    complete_cycle=False, residual_tolerance=1e-10)
        row = result["branches"][0]["per_rate"][1]
        # At both nodes components share signs; between roots .25,.75 they oppose.
        self.assertFalse(np.any(np.sign(k1) != np.sign(k2)))
        self.assertAlmostEqual(row["cancellation_charge_C"], .125)
        self.assertAlmostEqual(row["cancellation_fraction"], .2)
        self.assertAlmostEqual(row["absolute_component_sum_C"], .625)
        self.assertAlmostEqual(row["model_abs_charge_C"], .5)
        self.assertAlmostEqual(row["absolute_charge_identity_error_C"], 0)
        self.assertIn("opposed_component_signs", row["hold_reasons"])
        self.assertIsNone(row["conditional_model_fractions"])
        self.assertAlmostEqual(row["formal_abs_component_shares"]["linear"], .5)
        self.assertAlmostEqual(sum(row["component_to_model_abs_charge_ratio"].values()), 1.25)

    def test_negative_and_above100_path_ratios_are_retained_without_clipping(self):
        rates, e = np.array([.25, 1., 4.]), np.array([0., .2, 1.])
        current = np.repeat((3*rates-2*np.sqrt(rates))[:, None], len(e), axis=1)
        branches = [dict(name="forward", potential_V=e, current_A=current),
                    dict(name="reverse", potential_V=e[::-1], current_A=-current[:, ::-1])]
        result = dunn_contributions(rates, branches, **self.parameters)
        row = result["aggregate"]["per_rate"][1]
        self.assertAlmostEqual(row["path_model_fraction_percent"]["linear"], 300)
        self.assertAlmostEqual(row["path_model_fraction_percent"]["sqrt"], -200)
        self.assertAlmostEqual(sum(row["path_observed_ratio_percent"].values()), 100)
        self.assertAlmostEqual(row["formal_abs_component_shares"]["linear"], .6)
        self.assertEqual(row["status"], "HOLD")
        self.assertIsNone(row["conditional_model_fractions"])

    def test_cancelling_path_denominator_is_suppressed_but_raw_areas_remain(self):
        rates, e = np.array([.25, 1., 4.]), np.array([0., 1.])
        current = (rates[:, None]+2*np.sqrt(rates)[:, None])*(e-.5)
        branches = [dict(name="forward", potential_V=e, current_A=current),
                    dict(name="reverse", potential_V=e[::-1], current_A=-current[:, ::-1])]
        result = dunn_contributions(rates, branches, **self.parameters)
        for row in result["aggregate"]["per_rate"]:
            self.assertAlmostEqual(row["observed_path_area_charge_C"], 0)
            self.assertGreater(row["observed_abs_charge_C"], 0)
            self.assertIsNone(row["path_model_fraction_percent"])
            self.assertIsNone(row["path_observed_ratio_percent"])
            self.assertIsNotNone(row["formal_abs_component_shares"])

    def test_fit_condition_and_branch_residual_holds_propagate_to_cycle(self):
        narrow = 1+np.arange(4)*1e-12
        narrow_result = dunn_contributions(narrow, self.exact_branches(narrow), **self.parameters)
        for branch in narrow_result["branches"]:
            self.assertEqual(branch["fit"]["status"], "HOLD_ILL_CONDITIONED")
            self.assertIn("scaled_condition_exceeds_limit", branch["per_rate"][0]["hold_reasons"])
        self.assertIsNone(narrow_result["aggregate"]["per_rate"][0]["conditional_model_fractions"])
        rates = [.1, .2, .4, .8]
        branches = self.exact_branches(rates)
        # Deliberately poor reverse branch cannot be masked by the aggregate.
        branches[1]["current_A"] += np.array([.01, -.01, .01, -.01])[:, None]
        noisy = dunn_contributions(rates, branches, complete_cycle=True, residual_tolerance=1e-5)
        self.assertTrue(any("relative_absolute_residual_exceeds_tolerance" in reason
                            for row in noisy["aggregate"]["per_rate"] for reason in row["hold_reasons"]))
        row = noisy["branches"][1]["per_rate"][0]
        self.assertAlmostEqual(row["model_relative_abs_residual"],
                               row["residual_abs_charge_C"]/row["observed_abs_charge_C"])
        self.assertAlmostEqual(sum(row["path_observed_ratio_percent"].values()), 100)

    def test_model_observed_opposition_is_an_independent_gate_and_threshold_is_explicit(self):
        rates, e = np.array([.25, 1., 4., 9.]), np.array([0., 1.])
        current = (rates[:, None]+np.sqrt(rates)[:, None])*(e-.5)
        # [8,-6,1,0] is orthogonal to both rates and sqrt(rates), so the raw
        # least-squares coefficients are unchanged while the recorded zeros move.
        noise = 1e-3*np.array([8, -6, 1, 0])
        current += noise[:, None]
        result = dunn_contributions(rates, [dict(name="shifted_zeros", potential_V=e, current_A=current)],
                                    complete_cycle=False, residual_tolerance=.1)
        row = result["branches"][0]["per_rate"][0]
        self.assertLess(row["model_relative_abs_residual"], .1)
        self.assertLess(row["cancellation_fraction"], 1e-10)
        self.assertGreater(row["model_observed_opposition_charge_C"], 0)
        self.assertIn("model_opposes_observed", row["hold_reasons"])
        self.assertIsNone(row["conditional_model_fractions"])
        self.assertEqual(result["aggregate"]["path_area_scope"], "recorded_path_endpoints_not_closed")
        relaxed = dunn_contributions(rates, [dict(name="shifted_zeros", potential_V=e, current_A=current)],
                                     complete_cycle=False, residual_tolerance=.1, opposition_tolerance=.01)
        self.assertNotIn("model_opposes_observed", relaxed["branches"][0]["per_rate"][0]["hold_reasons"])
        self.assertAlmostEqual(row["model_observed_opposition_charge_C"],
                               relaxed["branches"][0]["per_rate"][0]["model_observed_opposition_charge_C"])

    def test_zero_current_has_no_fractions_and_preserves_original_nodes(self):
        branches = self.exact_branches()
        for branch in branches:
            branch["current_A"][:] = 0
        result = dunn_contributions(self.rates, branches, **self.parameters)
        row = result["aggregate"]["per_rate"][0]
        self.assertEqual(row["observed_abs_charge_C"], 0)
        self.assertIsNone(row["formal_abs_component_shares"])
        self.assertIsNone(row["conditional_model_fractions"])
        self.assertIsNone(row["model_relative_abs_residual"])
        self.assertIn("zero_model_absolute_charge", row["hold_reasons"])
        self.assertTrue(np.all(result["branches"][0]["fit"]["current_A"] == 0))

    def test_invalid_raw_grids_shapes_closure_names_duplicates_and_booleans_fail(self):
        for field, value in [("complete_cycle", 1), ("residual_tolerance", True),
                             ("residual_tolerance", 0), ("opposition_tolerance", False),
                             ("opposition_tolerance", -1), ("path_denominator_tolerance", True),
                             ("path_denominator_tolerance", 1), ("current_basis", "mA/cm2")]:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                dunn_contributions(self.rates, self.exact_branches(), **{**self.parameters, field: value})
        for mutate in [lambda b: b[0].update(potential_V=[0, .1, .1, 1]),
                       lambda b: b[0].update(potential_V=[0, .4, .1, 1]),
                       lambda b: b[0].update(potential_V=[0, .1, .4]),
                       lambda b: b[1].update(potential_V=[1, .7, .3, .00001]),
                       lambda b: b[1].update(name="forward"),
                       lambda b: b[0].update(extra=True)]:
            branches = self.exact_branches()
            mutate(branches)
            with self.subTest(branches=branches), self.assertRaises(ValueError):
                dunn_contributions(self.rates, branches, **self.parameters)
        with self.assertRaises(ValueError):
            dunn_contributions([.01, .01, .02, .04], self.exact_branches([.01, .01, .02, .04]),
                               **self.parameters)
        with self.assertRaises(ValueError):
            dunn_contributions(self.rates, self.exact_branches()[:1], **self.parameters)

    def test_nonrepresentable_math_fails_instead_of_false_zero_or_overflow(self):
        branches = self.exact_branches()
        branches[0]["potential_V"] = [-1e308, 0, 1e308, 1.1e308]
        with self.assertRaises(ValueError):
            dunn_contributions(self.rates, branches, complete_cycle=False, residual_tolerance=1e-10)
        branches = [dict(name="tiny", potential_V=[0, 5e-324],
                         current_A=np.ones((3, 2))*1e-100)]
        with self.assertRaises(ValueError):
            dunn_contributions([1, 2, 3], branches, complete_cycle=False, residual_tolerance=1e-10)
        branches = self.exact_branches()
        branches[0]["current_A"][0, 0] = np.nan
        with self.assertRaises(ValueError):
            dunn_contributions(self.rates, branches, **self.parameters)


class ICATests(unittest.TestCase):
    def test_nonuniform_finite_volume_integral_and_dva(self):
        v = np.array([2., 2.01, 2.04, 2.11, 2.4])
        q = 4*v + 2*v*v
        result = ica(v, q, Q_convention="signed_charge")
        np.testing.assert_allclose(result["dQ_dV_C_per_V"], 4 + 4*result["V_center_V"])
        np.testing.assert_allclose(result["dQ_dV_C_per_V"]*result["dV_dQ_V_per_C"], 1)
        self.assertAlmostEqual(result["integrated_charge_C"], q[-1]-q[0])
        self.assertAlmostEqual(result["closure_error_C"], 0)
        np.testing.assert_array_equal(result["raw_V_V"], v)
        np.testing.assert_array_equal(result["raw_Q_C"], q)

    def test_discharge_conventions_do_not_silently_flip(self):
        v = [4., 3.8, 3.3, 3.]
        signed = ica(v, [0, -.2, -.7, -1], Q_convention="signed_charge")
        branch = ica(v, [0, .2, .7, 1], Q_convention="branch_capacity")
        np.testing.assert_allclose(signed["dQ_dV_C_per_V"], 1)
        np.testing.assert_allclose(branch["dQ_dV_C_per_V"], -1)
        self.assertEqual(signed["total_charge_C"], -1)
        self.assertEqual(branch["total_charge_C"], 1)

    def test_explicit_full_bins_preserve_charge_raw_arrays_and_orientation(self):
        v = np.array([4., 3.99, 3.81, 3.6, 3.])
        q = np.array([0., .01, .04, .2, .9])
        bins = [4., 3.7, 3.2, 3.]
        result = ica(v, q, Q_convention="branch_capacity", bin_edges_V=bins)
        self.assertEqual(result["resampling"], "piecewise_linear_Q_V")
        self.assertAlmostEqual(result["integrated_charge_C"], .9)
        np.testing.assert_array_equal(result["raw_V_V"], v)
        np.testing.assert_array_equal(result["raw_Q_C"], q)
        np.testing.assert_array_equal(result["V_edges_V"], bins)

    def test_repeated_voltage_zero_q_reverse_branch_and_partial_bins_reject(self):
        for v, q in [([1, 1, 2], [0, 1, 2]), ([1, 2, 3], [0, 0, 1]),
                     ([1, 3, 2], [0, 1, 2]), ([1, 2, 3], [0, 2, 1]),
                     ([1, True, 3], [0, 1, 2])]:
            with self.subTest(v=v, q=q), self.assertRaises(ValueError):
                ica(v, q, Q_convention="signed_charge")
        for bins in ([1.1, 2, 3], [1, 2, 3.1], [3, 2, 1]):
            with self.subTest(bins=bins), self.assertRaises(ValueError):
                ica([1, 2, 3], [0, 1, 2], Q_convention="branch_capacity", bin_edges_V=bins)
        with self.assertRaises(ValueError):
            ica([3, 2, 1], [0, -1, -2], Q_convention="branch_capacity")


class CdlTests(unittest.TestCase):
    rates = np.array([.08, .005, .04, .02, .12, .01])
    potential = np.array([.15, .18, .2, .23, .25])
    parameters = dict(conditions={key: True for key in CDL_CONDITIONS},
                      linearity_tolerance=1e-10)

    def currents(self, capacitance=.018):
        # Independent i=C*dE/dt capacitor response; common-mode current cancels.
        capacitive = self.rates[:, None] * np.full((1, len(self.potential)), capacitance)
        offset = 2e-5 + 1e-5*(self.potential-.2)
        return capacitive + offset, -capacitive + offset

    def test_exact_node_common_mode_intercept_normalization_and_source_order(self):
        ia, ic = self.currents()
        result = cdl(self.rates, self.potential, ia, ic, sample_potential_V=.2,
                     area_m2=2e-4, mass_kg=3e-6, **self.parameters)
        self.assertEqual(result["status"], "ready")
        self.assertAlmostEqual(result["cdl_F"], .018)
        self.assertAlmostEqual(result["intercept_A"], 0)
        self.assertAlmostEqual(result["anodic_slope_F"], .018)
        self.assertAlmostEqual(result["cathodic_slope_F"], -.018)
        np.testing.assert_allclose(result["half_difference_A"], .018*self.rates, rtol=1e-14)
        np.testing.assert_allclose(result["common_mode_A"], 2e-5, atol=1e-18)
        np.testing.assert_array_equal(result["rates_V_s"], self.rates)
        np.testing.assert_array_equal(result["anodic_current_A"], ia)
        self.assertEqual(result["selected_indices"].tolist(), [2])
        self.assertAlmostEqual(result["normalizations"]["cdl_F_per_m2"], 90)
        self.assertAlmostEqual(result["normalizations"]["cdl_F_per_kg"], 6000)
        # A branch-asymmetric DC offset is diagnosed by a freely fitted intercept.
        biased = cdl(self.rates, self.potential, ia+3e-5, ic-3e-5,
                     sample_potential_V=.2, **self.parameters)
        self.assertAlmostEqual(biased["intercept_A"], 3e-5)
        self.assertAlmostEqual(biased["apparent_capacitance_F"], .018)

    def test_explicit_nonuniform_window_voltage_mean_and_descending_grid(self):
        # C(E) is linear: exact voltage-weighted window mean is its midpoint value.
        capacitance = .018 + .01*(self.potential-.2)
        ia = self.rates[:, None]*capacitance
        ic = -ia
        for potential, anodic, cathodic in [(self.potential, ia, ic),
                                            (self.potential[::-1], ia[:, ::-1], ic[:, ::-1])]:
            result = cdl(self.rates, potential, anodic, cathodic,
                         window_V=[.15, .25], **self.parameters)
            self.assertAlmostEqual(result["cdl_F"], .018)
            self.assertEqual(result["selection"], "piecewise_linear_voltage_window_mean")
            np.testing.assert_array_equal(result["potential_V"], potential)
        self.assertGreater(abs(float(np.mean(capacitance))-.018), 1e-6)

    def test_linear_faradaic_counterexample_and_reversed_sign_keep_apparent_values(self):
        # Exact linearity cannot distinguish assigned Cdl from a linear Faradaic term.
        ia, ic = self.currents(.018+.012)
        params = {**self.parameters, "conditions": {**self.parameters["conditions"],
                                                     "nonfaradaic_window": False}}
        result = cdl(self.rates, self.potential, ia, ic, sample_potential_V=.2, **params)
        self.assertEqual(result["status"], "HOLD")
        self.assertIsNone(result["cdl_F"])
        self.assertAlmostEqual(result["apparent_capacitance_F"], .03)
        self.assertAlmostEqual(result["r_squared"], 1)
        self.assertIn("nonfaradaic_window", result["hold_reasons"])
        reverse = cdl(self.rates, self.potential, ic, ia,
                      sample_potential_V=.2, **self.parameters)
        self.assertAlmostEqual(reverse["apparent_capacitance_F"], -.03)
        self.assertEqual(reverse["status"], "HOLD")
        self.assertIsNone(reverse["cdl_F"])
        np.testing.assert_array_equal(reverse["anodic_current_A"], ic)

    def test_nonlinearity_and_branch_slope_mismatch_are_holds(self):
        ia = np.repeat((.018*np.sqrt(self.rates))[:, None], len(self.potential), axis=1)
        nonlinear = cdl(self.rates, self.potential, ia, -ia,
                        sample_potential_V=.2, **self.parameters)
        self.assertIn("half_difference_nonlinear_residual", nonlinear["hold_reasons"])
        self.assertIsNone(nonlinear["cdl_F"])
        ia, ic = self.currents()
        mismatch = cdl(self.rates, self.potential, ia*2, ic,
                       sample_potential_V=.2, **self.parameters)
        self.assertIn("branch_slope_mismatch", mismatch["hold_reasons"])

    def test_invalid_selection_conditions_shapes_units_and_arithmetic_fail(self):
        ia, ic = self.currents()
        cases = [dict(sample_potential_V=.201), dict(window_V=[.16, .25]),
                 dict(sample_potential_V=.2, window_V=[.15, .25]),
                 dict(sample_potential_V=True), dict(sample_potential_V=.2, area_m2=0),
                 dict(sample_potential_V=.2, mass_kg=False),
                 dict(sample_potential_V=.2, linearity_tolerance=True),
                 dict(sample_potential_V=.2, conditions={key: 1 for key in CDL_CONDITIONS})]
        for extra in cases:
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                cdl(self.rates, self.potential, ia, ic, **{**self.parameters, **extra})
        with self.assertRaises(ValueError):
            cdl([.01, .01, .01], [.2], [[.1]]*3, [[-.1]]*3,
                 sample_potential_V=.2, **self.parameters)
        with self.assertRaises(ValueError):
            cdl(self.rates, self.potential, ia[:, :-1], ic,
                 sample_potential_V=.2, **self.parameters)
        with self.assertRaises(ValueError):
            cdl(self.rates, self.potential, ia, ic, sample_potential_V=.2,
                 area_m2=5e-324, **self.parameters)


class CycleEfficiencyTests(unittest.TestCase):
    parameters = dict(Q_convention="branch_capacity", complete_branches=True,
                      voltage_basis="cell_terminal")

    def test_independent_linear_voltage_capacity_integrals_and_si_units(self):
        qc = np.array([0, .2, 1.7, 4., 6.8])
        qd = np.array([0, .4, 2.1, 3., 6.12])
        # Analytic integrals from antiderivatives, independently of the function.
        vc, vd = 2+.2*qc, 3.36-.18*qd
        ec, ed = 2*qc[-1]+.1*qc[-1]**2, 3.36*qd[-1]-.09*qd[-1]**2
        result = cycle_efficiency(qc, vc, qd, vd, **self.parameters)
        self.assertAlmostEqual(result["charge_energy_J"], ec)
        self.assertAlmostEqual(result["discharge_energy_J"], ed)
        self.assertAlmostEqual(result["charge_energy_Wh"], ec/3600)
        self.assertAlmostEqual(result["charge_mean_voltage_V"], ec/qc[-1])
        self.assertAlmostEqual(result["discharge_mean_voltage_V"], ed/qd[-1])
        self.assertAlmostEqual(result["coulombic_efficiency"], .9)
        self.assertAlmostEqual(result["energy_efficiency"], ed/ec)
        self.assertAlmostEqual(result["energy_loss_J"], ec-ed)
        self.assertAlmostEqual(result["charge_loss_C"], qc[-1]-qd[-1])
        np.testing.assert_array_equal(result["raw_discharge_Q_C"], qd)

    def test_reversible_capacitor_energy_closure_on_nonuniform_grids(self):
        qc, qd = np.array([0, .04, .3, .7, 1.2]), np.array([0, .1, .42, .91, 1.2])
        capacitance, minimum, maximum = .4, .2, 3.2
        result = cycle_efficiency(qc, minimum+qc/capacitance, qd,
                                  maximum-qd/capacitance, **self.parameters)
        expected = capacitance*(maximum**2-minimum**2)/2
        self.assertAlmostEqual(result["charge_energy_J"], expected)
        self.assertAlmostEqual(result["discharge_energy_J"], expected)
        self.assertAlmostEqual(result["energy_efficiency"], 1)
        self.assertAlmostEqual(result["coulombic_efficiency"], 1)

    def test_duplicate_capacity_partial_branches_and_anomalies_preserved(self):
        result = cycle_efficiency([0, 0, .2, .2, 1], [2, 2, 2, 2, 2],
                                  [0, 1.2], [2, 2], **self.parameters)
        self.assertEqual(len(result["raw_charge_Q_C"]), 5)
        self.assertAlmostEqual(result["coulombic_efficiency_pct"], 120)
        self.assertAlmostEqual(result["energy_efficiency_pct"], 120)
        self.assertLess(result["charge_loss_C"], 0)
        self.assertLess(result["energy_loss_J"], 0)
        self.assertEqual(len(result["anomaly_flags"]), 2)
        partial = cycle_efficiency([0, 1], [2, 2], [0, .8], [2, 2],
                                   **{**self.parameters, "complete_branches": False})
        self.assertEqual(partial["status"], "HOLD")
        self.assertEqual(partial["hold_reasons"], ["incomplete_branches"])

    def test_bad_conventions_signs_nodes_types_and_arithmetic_fail(self):
        cases = [([0, -1], [2, 2]), ([0, 1, .5], [2, 2, 2]),
                 ([1, 2], [2, 2]), ([0, 0], [2, 2]),
                 ([0, 1], [0, 0]), ([0, 1], [-1, 2]),
                 ([0, 1], [2, True]), ([0, 1], [2, np.nan]),
                 ([0, 1], [2]), ([0, 1e308], [10, 10]),
                 ([0, 1e-200], [1e-200, 1e-200])]
        for q, v in cases:
            with self.subTest(q=q, v=v), self.assertRaises(ValueError):
                cycle_efficiency(q, v, [0, 1], [2, 2], **self.parameters)
        for name, value in [("Q_convention", "signed_charge"),
                            ("voltage_basis", "reference_electrode"),
                            ("complete_branches", 1)]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                cycle_efficiency([0, 1], [2, 2], [0, 1], [2, 2],
                                 **{**self.parameters, name: value})


class RandlesSevcikTests(unittest.TestCase):
    parameters = dict(n=1, A_m2=1e-4, c_mol_m3=1., T_K=298.15, conditions=RS_CONDITIONS)

    def test_si_forward_inverse_and_cm_conversion(self):
        rates, diffusivity = np.array([.01, .03, .1, .3]), 1e-9
        forward = randles_sevcik_peak(rates, D_m2_s=diffusivity, **self.parameters)
        fit = scan_rate_fit(rates, forward["peak_current_A"])
        recovered = randles_sevcik_diffusivity(fit["sqrt_slope_A_per_sqrt_V_s"], **self.parameters)
        self.assertAlmostEqual(recovered["D_m2_s"]/diffusivity, 1)
        self.assertAlmostEqual(fit["b"], .5)
        # Same physical system: A=1 cm2, c=1e-6 mol/cm3, D=1e-5 cm2/s.
        expected_A = 2.69e5 * 1 * 1e-6 * np.sqrt(1e-5) * np.sqrt(rates)
        np.testing.assert_allclose(forward["peak_current_A"], expected_A, rtol=.002)

    def test_missing_conditions_boolean_bad_units_and_zero_reject(self):
        for name, value in [("conditions", set()), ("n", True), ("n", 1.0),
                            ("A_m2", 0), ("c_mol_m3", False), ("T_K", -1)]:
            args = dict(self.parameters, **{name: value})
            with self.subTest(name=name), self.assertRaises(ValueError):
                randles_sevcik_peak([.1], D_m2_s=1e-9, **args)
        with self.assertRaises(ValueError):
            randles_sevcik_peak([0], D_m2_s=1e-9, **self.parameters)
        with self.assertRaises(ValueError):
            randles_sevcik_diffusivity(-1, **self.parameters)
        with self.assertRaises(ValueError):
            randles_sevcik_diffusivity(1e308, **self.parameters)
        with self.assertRaises(ValueError):
            randles_sevcik_peak([.1], D_m2_s=1e-9,
                                **{**self.parameters, "n": 10**400})


if __name__ == "__main__":
    unittest.main()
