"""Opt-in CV/ICA numerical methods; no automatic scientific claim.

Inputs use SI units and retain their order and signs. Processing choices are
explicit and outputs are new arrays; Call through the explicit analysis contract.
"""

from __future__ import annotations

import math
from functools import wraps
from numbers import Real

import numpy as np


FARADAY_C_PER_MOL = 96485.33212331002
GAS_CONSTANT_J_PER_MOL_K = 8.31446261815324
RS_CONDITIONS = frozenset({
    "reversible", "planar", "semi_infinite", "solution_species",
    "migration_negligible",
})
CDL_CONDITIONS = frozenset({
    "nonfaradaic_window", "sampling_checked", "ohmic_drop_assessed",
    "repeatability_checked",
})


def _guarded_math(function):
    """Never turn a nonzero underflow or an overflow into a plausible result."""
    @wraps(function)
    def checked(*args, **kwargs):
        try:
            with np.errstate(over="raise", under="raise", invalid="raise", divide="raise"):
                return function(*args, **kwargs)
        except (FloatingPointError, OverflowError, np.linalg.LinAlgError) as exc:
            raise ValueError("arithmetic: overflow, underflow or invalid result") from exc
    return checked


def _array(value, name, ndim=1):
    """Reject strings, booleans, complex/nonfinite and unrepresentable values."""
    try:
        obj = np.asarray(value, dtype=object)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name}: numeric array required") from exc
    if obj.ndim != ndim:
        raise ValueError(f"{name}: expected {ndim} dimensions")
    values = []
    for item in obj.flat:
        if isinstance(item, (bool, np.bool_)) or not isinstance(item, Real):
            raise ValueError(f"{name}: real numbers required, not booleans")
        try:
            number = float(item)
        except (OverflowError, ValueError) as exc:
            raise ValueError(f"{name}: unrepresentable number") from exc
        if not math.isfinite(number) or (number == 0 and item != 0):
            raise ValueError(f"{name}: nonfinite or underflowing number")
        values.append(number)
    return np.array(values, dtype=float).reshape(obj.shape)


def _positive(value, name):
    number = _array([value], name)[0]
    if number <= 0:
        raise ValueError(f"{name}: positive value required")
    return float(number)


def _finite(value, name):
    if not np.all(np.isfinite(value)):
        raise ValueError(f"{name}: unrepresentable result")
    return value


def _difference(values, name):
    with np.errstate(over="ignore", invalid="ignore"):
        return _finite(np.diff(values), name)


def _branch(values, name, *, strict=True):
    delta = _difference(values, name)
    if len(delta) == 0:
        raise ValueError(f"{name}: at least two nodes required")
    if (np.all(delta > 0) if strict else np.all(delta >= 0)) and values[-1] > values[0]:
        return delta, 1
    if (np.all(delta < 0) if strict else np.all(delta <= 0)) and values[-1] < values[0]:
        return delta, -1
    raise ValueError(f"{name}: one monotonic branch required")


def _equal_lengths(*arrays):
    if len({len(a) for a in arrays}) != 1:
        raise ValueError("paired arrays must have identical lengths")


@_guarded_math
def integrate_branch(t_s, E_V, I_A):
    """Q=integral I dt; Q_mAh=Q_C/3.6; apparent_F=abs(Q)/abs(delta E).

    Time must strictly increase. Voltage may contain repeated sampled values
    but must represent one monotonic branch. Signed current is never flipped;
    zero/cancelling current is valid. The quotient is not an EDLC/Cdl claim.
    """
    t, e, i = (_array(x, n) for x, n in [(t_s, "t_s"), (E_V, "E_V"), (I_A, "I_A")])
    _equal_lengths(t, e, i)
    dt = _difference(t, "t_s")
    if len(dt) == 0 or not np.all(dt > 0):
        raise ValueError("t_s: at least two strictly increasing times required")
    _, direction = _branch(e, "E_V", strict=False)
    with np.errstate(over="ignore", invalid="ignore"):
        terms = _finite((i[:-1] / 2 + i[1:] / 2) * dt, "charge trapezoids")
    try:
        charge = math.fsum(terms)
    except OverflowError as exc:
        raise ValueError("charge: unrepresentable result") from exc
    span = float(_finite(abs(e[-1] - e[0]), "voltage span"))
    result = {"signed_charge_C": charge, "signed_charge_mAh": float(np.divide(charge, 3.6)),
              "apparent_F": float(np.divide(abs(charge), span)), "voltage_span_V": span,
              "duration_s": float(t[-1] - t[0]), "voltage_direction": direction,
              "time_s": t, "potential_V": e, "current_A": i}
    for key in ["signed_charge_C", "signed_charge_mAh", "apparent_F", "duration_s"]:
        _finite(result[key], key)
    return result


def peak_window(E_V, I_A, window_V, polarity):
    """Select a signed raw-node extremum; no fit, smoothing or baseline subtraction.

    polarity='anodic' selects a positive maximum; 'cathodic' a negative minimum.
    Window endpoints are inclusive. Missing/edge peaks return explicit statuses.
    Ties use the first original node and retain all tied original indices.
    """
    e, i, window = _array(E_V, "E_V"), _array(I_A, "I_A"), _array(window_V, "window_V")
    _equal_lengths(e, i)
    _branch(e, "E_V", strict=False)
    if len(window) != 2 or window[0] >= window[1]:
        raise ValueError("window_V: ordered lower/upper bounds required")
    if polarity not in ("anodic", "cathodic"):
        raise ValueError("polarity: anodic or cathodic required")
    indices = np.flatnonzero((e >= window[0]) & (e <= window[1]))
    result = {"status": "missing", "index": None, "potential_V": None,
              "current_A": None, "candidate_count": len(indices),
              "window_V": window, "polarity": polarity, "tie_indices": np.array([], dtype=int)}
    if not len(indices):
        result["reason"] = "no_nodes_in_window"
        return result
    local = int(np.argmax(i[indices]) if polarity == "anodic" else np.argmin(i[indices]))
    index = int(indices[local])
    if (polarity == "anodic" and i[index] <= 0) or (polarity == "cathodic" and i[index] >= 0):
        result["reason"] = "no_peak_with_declared_sign"
        return result
    edge = local in (0, len(indices) - 1)
    result.update(status="edge" if edge else "ok", index=index,
                  potential_V=float(e[index]), current_A=float(i[index]),
                  tie_indices=indices[i[indices] == i[index]],
                  reason="window_edge" if edge else None)
    return result


def _rates(value):
    rates = _array(value, "rates_V_s")
    if len(rates) < 3 or np.any(rates <= 0) or len(np.unique(rates)) < 3:
        raise ValueError("rates_V_s: at least three distinct positive scan rates required")
    return rates


def _ols(design, observed):
    """Column-scaled SVD least squares; report both physical and scaled conditioning."""
    scale = np.max(np.abs(design), axis=0)
    if np.any(scale == 0):
        raise ValueError("rank-deficient fit design")
    scaled = design / scale
    coefficients, _, rank, singular = np.linalg.lstsq(scaled, observed, rcond=None)
    if rank != design.shape[1]:
        raise ValueError("rank-deficient fit design")
    coefficients = coefficients / (scale[:, None] if observed.ndim == 2 else scale)
    prediction = design @ coefficients
    return {"coefficients": _finite(coefficients, "coefficients"),
            "prediction": _finite(prediction, "prediction"),
            "residual": _finite(observed - prediction, "residual"),
            "rank": int(rank), "condition": float(np.linalg.cond(design)),
            "scaled_condition": float(singular[0] / singular[-1])}


def scan_rate_fit(rates_V_s, peak_current_A):
    """Descriptive OLS of abs(Ip) vs sqrt(v), and log(abs(Ip)) vs log(v).

    Returns the b exponent without a surface/diffusion/mechanism label. Absolute
    peak magnitude is an explicit analysis quantity; original signed Ip is kept.
    Zero peaks fail because log(0) is undefined. No origin-constrained fit.
    """
    rates, current = _rates(rates_V_s), _array(peak_current_A, "peak_current_A")
    _equal_lengths(rates, current)
    magnitude = np.abs(current)
    if np.any(magnitude == 0):
        raise ValueError("zero peak current: logarithmic fit is undefined")
    sqrt_fit = _ols(np.column_stack((np.sqrt(rates), np.ones(len(rates)))), magnitude)
    log_fit = _ols(np.column_stack((np.log(rates), np.ones(len(rates)))), np.log(magnitude))
    return {"rates_V_s": rates, "peak_current_A": current, "peak_magnitude_A": magnitude,
            "mixed_sign_peaks": bool(np.any(current > 0) and np.any(current < 0)),
            "b": float(log_fit["coefficients"][0]),
            "log_intercept": float(log_fit["coefficients"][1]),
            "sqrt_slope_A_per_sqrt_V_s": float(sqrt_fit["coefficients"][0]),
            "sqrt_intercept_A": float(sqrt_fit["coefficients"][1]),
            "sqrt_fit": sqrt_fit, "log_fit": log_fit,
            "log_base": "natural", "fit_quantity": "absolute_peak_current"}


@_guarded_math
def dunn(rates_V_s, current_A, *, fit_space="raw", polarity="preserve", condition_limit=1e8):
    """Fit I(E,v)=k1(E)*v+k2(E)*sqrt(v), columns=current potential nodes.

    raw minimizes sum residual_I**2. normalized minimizes sum residual_I**2/v
    by equal-weight fitting I/sqrt(v). Both are linear-in-coefficients models.
    preserve retains any signed input; anodic/cathodic check nonnegative/
    nonpositive inputs without flipping them. Negative cathodic coefficients
    are normal sign conventions; coefficients/components are never clipped.
    This conditional empirical decomposition does not identify a mechanism.
    A scaled-design condition above the explicit condition_limit gives
    HOLD_ILL_CONDITIONED while retaining all coefficients and reconstructions.
    This numerical threshold is not a scientific identifiability proof. Raw
    SSE units are A^2; normalized SSE units are A^2/(V/s), because its original
    current residual weights are 1/v. No reference rate silently changes them.
    """
    rates, current = _rates(rates_V_s), _array(current_A, "current_A", ndim=2)
    if current.shape[0] != len(rates) or current.shape[1] < 1:
        raise ValueError("current_A: shape must be [scan_rates, potential_nodes]")
    if fit_space not in ("raw", "normalized"):
        raise ValueError("fit_space: raw or normalized required")
    if polarity not in ("preserve", "anodic", "cathodic"):
        raise ValueError("polarity: preserve, anodic or cathodic required")
    limit = _positive(condition_limit, "condition_limit")
    if limit <= 1:
        raise ValueError("condition_limit: finite value greater than one required")
    if (polarity == "anodic" and np.any(current < 0)) or (polarity == "cathodic" and np.any(current > 0)):
        raise ValueError("current sign conflicts with explicitly declared polarity")
    design = np.column_stack((rates, np.sqrt(rates)))
    with np.errstate(over="ignore", divide="ignore"):
        weights = _finite(np.ones(len(rates)) if fit_space == "raw" else 1 / rates,
                          "current residual weights")
    if fit_space == "normalized":
        sqrt_rate = np.sqrt(rates)[:, None]
        fit = _ols(design / sqrt_rate, current / sqrt_rate)
    else:
        fit = _ols(design, current)
    _finite([fit["condition"], fit["scaled_condition"]], "Dunn conditioning")
    k1, k2 = fit["coefficients"]
    c1, c2 = rates[:, None] * k1, np.sqrt(rates)[:, None] * k2
    reconstructed = _finite(c1 + c2, "reconstructed current")
    residual = _finite(current - reconstructed, "current residual")
    with np.errstate(over="ignore", invalid="ignore"):
        weighted_sse = _finite(np.sum((np.sqrt(weights)[:, None] * residual) ** 2, axis=0),
                               "weighted residual sum of squares")
    # Compare signs directly: multiplying tiny currents can underflow to zero.
    nonzero_current = current != 0
    ill_conditioned = fit["scaled_condition"] > limit
    return {"status": "HOLD_ILL_CONDITIONED" if ill_conditioned else "CONDITIONAL_EMPIRICAL_FIT",
            "hold_reasons": ["scaled_condition_exceeds_limit"] if ill_conditioned else [],
            "condition_limit": limit, "rates_V_s": rates, "current_A": current, "k1": k1, "k2": k2,
            "linear_component_A": c1, "sqrt_component_A": c2,
            "reconstructed_A": reconstructed, "residual_A": residual,
            "weighted_sse": weighted_sse,
            "weighted_sse_unit": "A^2" if fit_space == "raw" else "A^2/(V/s)",
            "linear_opposes_observed": (np.sign(c1) != np.sign(current)) & (c1 != 0) & nonzero_current,
            "sqrt_opposes_observed": (np.sign(c2) != np.sign(current)) & (c2 != 0) & nonzero_current,
            "rank": fit["rank"], "condition": fit["condition"],
            "scaled_condition": fit["scaled_condition"],
            "fit_space": fit_space, "current_residual_weights": weights,
            "current_residual_weight_unit": "dimensionless" if fit_space == "raw" else "s/V",
            "polarity": polarity, "coefficient_units": ["A/(V/s)", "A/sqrt(V/s)"]}


def _cv_charge(potential, current, rates):
    """Exact signed and absolute charge of piecewise-linear I(E), per rate.

    Taking abs only at sampled endpoints overestimates a segment crossing zero.
    The triangular areas on either side of its analytic zero are used instead.
    No interpolated nodes replace, remove or modify the supplied raw arrays.
    """
    width = np.abs(_difference(potential, "potential intervals"))
    signed, absolute = [], []
    for rate, row in zip(rates, current):
        duration = _finite(width / rate, "constant-rate segment duration")
        signed_terms, absolute_terms = [], []
        for left, right, dt in zip(row[:-1], row[1:], duration):
            signed_terms.append(float((left/2 + right/2) * dt))
            if (left < 0 < right) or (right < 0 < left):
                large, small = max(abs(left), abs(right)), min(abs(left), abs(right))
                ratio = small / large
                mean_abs = large/2 * (1 + ratio*ratio) / (1 + ratio)
            else:
                mean_abs = abs(left)/2 + abs(right)/2
            absolute_terms.append(float(mean_abs * dt))
        signed.append(math.fsum(signed_terms))
        absolute.append(math.fsum(absolute_terms))
    return {"signed_C": _finite(np.array(signed), "signed CV charge"),
            "abs_C": _finite(np.array(absolute), "absolute CV charge")}


def _opposition_charge(potential, first, second, rates):
    """Integral 2*min(abs(first),abs(second)) only where signs oppose.

    Split each linear segment analytically at zeros of either current and their
    sum. This evaluates cancellation directly rather than subtracting nearly
    equal absolute charges; the nonnegative quantity cannot hide cancellation.
    """
    width = np.abs(_difference(potential, "potential intervals"))
    result = []
    for rate, row_a, row_b in zip(rates, first, second):
        terms = []
        for a0, a1, b0, b1, dt in zip(row_a[:-1], row_a[1:], row_b[:-1], row_b[1:], width/rate):
            cuts = {0., 1.}
            for left, right in [(a0, a1), (b0, b1), (a0+b0, a1+b1)]:
                if (left < 0 < right) or (right < 0 < left):
                    scale = max(abs(left), abs(right))
                    cuts.add(float((abs(left)/scale) / (abs(left)/scale + abs(right)/scale)))
            cuts = sorted(cuts)
            for start, end in zip(cuts[:-1], cuts[1:]):
                middle = start/2 + end/2
                am, bm = a0+(a1-a0)*middle, b0+(b1-b0)*middle
                if not ((am < 0 < bm) or (bm < 0 < am)):
                    continue
                al, ar = a0+(a1-a0)*start, a0+(a1-a0)*end
                bl, br = b0+(b1-b0)*start, b0+(b1-b0)*end
                # The sum's zero also splits any change of the smaller magnitude.
                terms.append(float((min(abs(al), abs(bl)) + min(abs(ar), abs(br)))
                                   * (end-start) * dt))
        result.append(math.fsum(terms))
    return _finite(np.array(result), "opposed-sign cancellation charge")


def _contribution_rate_report(charges, cancellation, observed_opposition, index, *,
                              residual_tolerance, opposition_tolerance, path_denominator_tolerance,
                              charge_unit, extra_hold=()):
    quantities = {key: float(value[index]) for key, value in charges.items()}
    linear, sqrt = quantities["linear_abs_charge"], quantities["sqrt_abs_charge"]
    model, observed = quantities["model_abs_charge"], quantities["observed_abs_charge"]
    component_sum = _finite(linear + sqrt, "sum absolute component charges")
    cancellation_C, observed_opposition_C = float(cancellation[index]), float(observed_opposition[index])
    hold = list(extra_hold)
    if model == 0:
        hold.append("zero_model_absolute_charge")
    if observed == 0:
        hold.append("zero_observed_absolute_charge")
    if component_sum == 0:
        hold.append("zero_absolute_component_charge")

    def ratios(denominator):
        if denominator == 0:
            return None
        return {"linear": float(_finite(np.divide(linear, denominator), "linear charge ratio")),
                "sqrt": float(_finite(np.divide(sqrt, denominator), "sqrt charge ratio"))}

    residual_fraction = (float(_finite(np.divide(quantities["residual_abs_charge"], observed),
                                      "relative absolute residual charge")) if observed > 0 else None)
    cancellation_fraction = (float(_finite(np.divide(cancellation_C, component_sum),
                                          "component cancellation fraction")) if component_sum > 0 else None)
    observed_denominator = _finite(model + observed, "model plus observed absolute charge")
    observed_opposition_fraction = (float(_finite(np.divide(observed_opposition_C, observed_denominator),
                                                "model-observed opposition fraction"))
                                    if observed_denominator > 0 else None)
    if residual_fraction is not None and residual_fraction > residual_tolerance:
        hold.append("relative_absolute_residual_exceeds_tolerance")
    if cancellation_fraction is not None and cancellation_fraction > opposition_tolerance:
        hold.append("opposed_component_signs")
    if observed_opposition_fraction is not None and observed_opposition_fraction > opposition_tolerance:
        hold.append("model_opposes_observed")
    model_ratios = ratios(model)

    def path_ratios(denominator, magnitude, *, include_residual=False):
        if magnitude == 0 or denominator == 0 or abs(denominator)/magnitude <= path_denominator_tolerance:
            return None
        kinds = ("linear", "sqrt", "residual") if include_residual else ("linear", "sqrt")
        return {kind: float(_finite(np.divide(quantities[f"{kind}_path_area_charge"], denominator)*100,
                                    f"{kind} oriented path ratio percent")) for kind in kinds}

    derived = {"absolute_component_sum": float(component_sum), "cancellation_charge": cancellation_C,
               "absolute_charge_identity_error": float(_finite(component_sum-model-cancellation_C,
                                                               "absolute charge identity error")),
               "model_observed_opposition_charge": observed_opposition_C,
               "model_minus_observed_abs_charge": float(_finite(model-observed, "model-observed charge difference")),
               "path_component_closure_error": float(_finite(
                   quantities["linear_path_area_charge"]+quantities["sqrt_path_area_charge"]
                   -quantities["model_path_area_charge"], "path component closure error")),
               "path_observed_closure_error": float(_finite(
                   quantities["model_path_area_charge"]+quantities["residual_path_area_charge"]
                   -quantities["observed_path_area_charge"], "path observed closure error"))}
    # Unit-bearing aliases are honest: a density input never exposes a *_C value.
    suffix = "C" if charge_unit == "C" else "C_per_m2"
    aliases = {f"{key}_{suffix}": value for key, value in {**quantities, **derived}.items()}
    model_path = quantities["model_path_area_charge"]
    observed_path = quantities["observed_path_area_charge"]
    return {**quantities, **derived, **aliases, "charge_unit": charge_unit,
            "cancellation_fraction": cancellation_fraction,
            "model_observed_opposition_fraction": observed_opposition_fraction,
            "model_relative_abs_residual": residual_fraction,
            "formal_abs_component_shares": ratios(component_sum),
            "component_to_model_abs_charge_ratio": model_ratios,
            "component_to_observed_abs_charge_ratio": ratios(observed),
            "conditional_model_fractions": model_ratios if not hold else None,
            "path_model_fraction_percent": path_ratios(model_path, model),
            "path_observed_ratio_percent": path_ratios(observed_path, observed, include_residual=True),
            "model_path_to_absolute_charge_ratio": float(np.divide(abs(model_path), model)) if model > 0 else None,
            "observed_path_to_absolute_charge_ratio": float(np.divide(abs(observed_path), observed)) if observed > 0 else None,
            "path_ratio_claim": "Formal oriented model/observed path area; not accepted physical storage fractions.",
            "status": "HOLD" if hold else "CONDITIONAL_EMPIRICAL_FRACTIONS",
            "hold_reasons": list(dict.fromkeys(hold))}


@_guarded_math
def dunn_contributions(rates_V_s, branches, *, complete_cycle, residual_tolerance,
                       fit_space="raw", condition_limit=1e8, opposition_tolerance=1e-10,
                       current_basis="current_A", path_denominator_tolerance=1e-10):
    """Signed Dunn CV components and explicitly defined integrated proportions.

    branches is an ordered list of dictionaries with exactly name, potential_V,
    current_A. Each current matrix has shape [rates, shared raw potential nodes]
    and each potential branch strictly increases or decreases. No sorting,
    averaging, interpolation between scan rates, clipping or baseline change.
    Duplicate rates/nodes fail; replicate handling needs a separate contract.
    complete_cycle is an actual bool. True requires exactly two opposite ordered
    branches with identical raw closing endpoints; False retains individual
    branch estimates but gives aggregate HOLD_incomplete_cycle.

    current_basis='current_A' gives charge in C; 'current_density_A_m2' gives
    charge density in C/m2 and coefficient/residual units based on A/m2. No
    electrode area is guessed. Legacy dunn fit array key names ending _A hold
    numeric SI current density in the latter case and are explicitly annotated.

    Fit each branch with dunn, preserving its signed I1=k1*v and I2=k2*sqrt(v).
    Qsigned=integral I*abs(dE)/v; Qabs=integral abs(I)*abs(dE)/v, both in C.
    Integrals are exact under the declared piecewise-linear I(E) representation,
    including zero-crossing triangles. Cycle magnitudes sum branch Qabs; signed
    currents/charges are not flipped and a cancelling loop is not a denominator.

    formal_abs_component_shares divides Q1abs,Q2abs by Q1abs+Q2abs. These always
    describe the absolute fitted components when nonzero; they are NOT physical
    storage fractions if the components oppose. component_to_model ratios use
    integral abs(I1+I2) and may exceed one/sum above one; observed ratios use
    integral abs(Iobserved), and are not forced to sum to one. All are retained.

    The canonical CV oriented path area is sum(direction*Qsigned)=integral I dE/v,
    not the net signed time charge. Formal path_model_fraction_percent uses that
    model area; path_observed_ratio_percent also includes the signed residual,
    so its linear+sqrt+residual ratios sum to 100. Fractions outside 0..100 stay
    visible. A denominator with abs(path)/absolute-current charge <= the explicit
    path_denominator_tolerance is suppressed (None), with every area retained.

    conditional_model_fractions is None/HOLD for ill-conditioned fits, zero
    denominators, significant component cancellation or model-observed sign
    opposition, or charge residual above residual_tolerance. The explicit
    residual metric is integral abs(Iobserved-Imodel) / integral abs(Iobserved).
    opposition_tolerance in [0,1) compares integral 2*min(abs(I1),abs(I2)) on
    opposite-sign intervals with Q1abs+Q2abs; model/observed uses their sum of
    absolute charges. Default 1e-10 only tolerates numerical-scale opposition;
    the exact measured cancellation is always retained. The aggregate inherits
    every branch HOLD, so integration cannot hide a poor local branch.

    Conditional linear/sqrt proportions are empirical scan-rate model quantities,
    not independently verified capacitive/diffusion mechanisms or Cdl/ECSA.
    """
    rates = _rates(rates_V_s)
    if len(np.unique(rates)) != len(rates):
        raise ValueError("rates_V_s: duplicate scan rates need an explicit replicate contract")
    if type(complete_cycle) is not bool:
        raise ValueError("complete_cycle: actual bool required")
    residual_limit = _positive(residual_tolerance, "residual_tolerance")
    opposition_limit = float(_array([opposition_tolerance], "opposition_tolerance")[0])
    path_limit = float(_array([path_denominator_tolerance], "path_denominator_tolerance")[0])
    if residual_limit >= 1 or not 0 <= opposition_limit < 1 or not 0 <= path_limit < 1:
        raise ValueError("residual_tolerance in (0,1); opposition/path_denominator_tolerance in [0,1) required")
    if current_basis not in ("current_A", "current_density_A_m2"):
        raise ValueError("current_basis: current_A or current_density_A_m2 required")
    charge_unit = "C" if current_basis == "current_A" else "C/m2"
    input_unit = "A" if current_basis == "current_A" else "A/m2"
    if not isinstance(branches, (list, tuple)) or len(branches) == 0:
        raise ValueError("branches: nonempty ordered list required")
    prepared, names = [], set()
    for branch in branches:
        if not isinstance(branch, dict) or set(branch) != {"name", "potential_V", "current_A"}:
            raise ValueError("branch: exactly name, potential_V, current_A required")
        name = branch["name"]
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError("branch name: unique nonempty text required")
        names.add(name)
        potential = _array(branch["potential_V"], f"{name} potential_V")
        _, direction = _branch(potential, f"{name} potential_V")
        fit = dunn(rates, branch["current_A"], fit_space=fit_space, condition_limit=condition_limit)
        fit["current_basis"], fit["input_unit"] = current_basis, input_unit
        if current_basis == "current_density_A_m2":
            fit["coefficient_units"] = ["(A/m2)/(V/s)", "(A/m2)/sqrt(V/s)"]
            fit["weighted_sse_unit"] = "(A/m2)^2" if fit_space == "raw" else "(A/m2)^2/(V/s)"
        if fit["current_A"].shape[1] != len(potential):
            raise ValueError("branch current matrix must match its common raw potential grid")
        prepared.append({"name": name, "potential_V": potential, "direction": direction, "fit": fit,
                         "current_basis": current_basis, "input_unit": input_unit, "charge_unit": charge_unit})
    opposite_pair = len(prepared) == 2 and prepared[0]["direction"] != prepared[1]["direction"]
    endpoints_closed = (opposite_pair and prepared[0]["potential_V"][-1] == prepared[1]["potential_V"][0]
                        and prepared[1]["potential_V"][-1] == prepared[0]["potential_V"][0])
    if complete_cycle:
        if not opposite_pair:
            raise ValueError("complete_cycle: exactly two opposite monotonic branches required")
        if not endpoints_closed:
            raise ValueError("complete_cycle: raw branches must close at exactly matching endpoints")
    totals, total_cancellation, total_observed_opposition = {}, [], []
    for branch in prepared:
        potential, fit = branch["potential_V"], branch["fit"]
        charges = {}
        for name, current in [("linear", fit["linear_component_A"]), ("sqrt", fit["sqrt_component_A"]),
                               ("model", fit["reconstructed_A"]), ("observed", fit["current_A"]),
                               ("residual", fit["residual_A"])]:
            charge = _cv_charge(potential, current, rates)
            charges[f"{name}_signed_charge"] = charge["signed_C"]
            charges[f"{name}_abs_charge"] = charge["abs_C"]
            charges[f"{name}_path_area_charge"] = _finite(branch["direction"]*charge["signed_C"],
                                                         f"{name} oriented path area")
        cancellation = _opposition_charge(potential, fit["linear_component_A"], fit["sqrt_component_A"], rates)
        observed_opposition = _opposition_charge(potential, fit["reconstructed_A"], fit["current_A"], rates)
        branch["per_rate"] = [_contribution_rate_report(
            charges, cancellation, observed_opposition, index, residual_tolerance=residual_limit,
            opposition_tolerance=opposition_limit, path_denominator_tolerance=path_limit, charge_unit=charge_unit,
            extra_hold=fit["hold_reasons"]) for index in range(len(rates))]
        for key, value in charges.items():
            totals.setdefault(key, []).append(value)
        total_cancellation.append(cancellation)
        total_observed_opposition.append(observed_opposition)

    def sum_branches(arrays):
        return _finite(np.array([math.fsum(row) for row in zip(*arrays)]), "aggregate branch charges")

    totals = {key: sum_branches(value) for key, value in totals.items()}
    total_cancellation = sum_branches(total_cancellation)
    total_observed_opposition = sum_branches(total_observed_opposition)
    aggregate_rates = []
    for index in range(len(rates)):
        inherited = [f"branch:{branch['name']}:{reason}" for branch in prepared
                     for reason in branch["per_rate"][index]["hold_reasons"]]
        if not complete_cycle:
            inherited.append("incomplete_cycle")
        aggregate_rates.append(_contribution_rate_report(
            totals, total_cancellation, total_observed_opposition, index,
            residual_tolerance=residual_limit, opposition_tolerance=opposition_limit,
            path_denominator_tolerance=path_limit, charge_unit=charge_unit,
            extra_hold=inherited))
    return {"status": "HOLD" if any(row["status"] == "HOLD" for row in aggregate_rates)
            else "CONDITIONAL_EMPIRICAL_FRACTIONS", "rates_V_s": rates,
            "branches": prepared, "aggregate": {"scope": "complete_cycle" if complete_cycle else "selected_branches",
                                                 "per_rate": aggregate_rates,
                                                 "path_area_scope": ("complete_closed_cycle" if complete_cycle
                                                     else "recorded_path_complete_cycle_not_attested" if endpoints_closed
                                                     else "recorded_path_endpoints_not_closed")},
            "complete_cycle": complete_cycle, "residual_tolerance": residual_limit,
            "opposition_tolerance": opposition_limit, "fit_space": fit_space,
            "path_denominator_tolerance": path_limit, "current_basis": current_basis,
            "input_unit": input_unit, "charge_unit": charge_unit,
            "integration": "exact_piecewise_linear_current_vs_potential_with_abs_dE_over_rate",
            "claim_boundary": "Conditional empirical linear/sqrt scan-rate fractions; not mechanism or Cdl proof."}


@_guarded_math
def ica(V_V, Q_C, *, Q_convention, bin_edges_V=None):
    """Finite-volume ICA/DVA from an explicitly signed, monotonic Q(V) branch.

    signed_charge uses Q exactly as supplied; branch_capacity requires an
    increasing nonnegative cumulative branch capacity. Neither flips signs.
    Repeated V or Q fails: no division by zero, averaging, node removal or
    smoothing. Optional explicit bin edges cover exactly the original branch;
    piecewise-linear Q(V) evaluation preserves total Q, not sub-bin features.
    """
    v, q = _array(V_V, "V_V"), _array(Q_C, "Q_C")
    _equal_lengths(v, q)
    _, v_direction = _branch(v, "V_V")
    _, q_direction = _branch(q, "Q_C")
    if Q_convention not in ("signed_charge", "branch_capacity"):
        raise ValueError("Q_convention: signed_charge or branch_capacity required")
    if Q_convention == "branch_capacity" and (q_direction != 1 or np.any(q < 0)):
        raise ValueError("branch_capacity: nonnegative increasing Q required")
    edges_v, edges_q = v.copy(), q.copy()
    if bin_edges_V is not None:
        edges_v = _array(bin_edges_V, "bin_edges_V")
        _, edges_direction = _branch(edges_v, "bin_edges_V")
        if edges_direction != v_direction or edges_v[0] != v[0] or edges_v[-1] != v[-1]:
            raise ValueError("bin_edges_V: preserve orientation and exact full branch endpoints")
        edges_q = (np.interp(edges_v, v, q) if v_direction > 0
                   else np.interp(edges_v, v[::-1], q[::-1]))
        _branch(edges_q, "resampled Q_C")
    dv, dq = _difference(edges_v, "voltage intervals"), _difference(edges_q, "charge intervals")
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        ic = _finite(dq / dv, "dQ/dV")
        dvq = _finite(dv / dq, "dV/dQ")
    closure = math.fsum(ic * dv)
    total = float(q[-1] - q[0])
    return {"raw_V_V": v, "raw_Q_C": q, "V_edges_V": edges_v, "Q_edges_C": edges_q,
            "V_center_V": edges_v[:-1] / 2 + edges_v[1:] / 2,
            "Q_center_C": edges_q[:-1] / 2 + edges_q[1:] / 2,
            "dV_V": dv, "dQ_C": dq, "dQ_dV_C_per_V": ic, "dV_dQ_V_per_C": dvq,
            "integrated_charge_C": closure, "total_charge_C": total,
            "closure_error_C": closure - total, "Q_convention": Q_convention,
            "resampling": "piecewise_linear_Q_V" if bin_edges_V is not None else "none"}


@_guarded_math
def cdl(rates_V_s, potential_V, anodic_current_A, cathodic_current_A, *,
        conditions, linearity_tolerance, sample_potential_V=None, window_V=None,
        area_m2=None, mass_kg=None):
    """Conditional Cdl from (Ia-Ic)/2 = C*v + intercept, with C in F.

    Both current matrices have shape [rates, shared potential nodes], in A,
    with anodic-positive/cathodic-negative signs. Select exactly one raw node
    or an explicit window whose endpoints are raw nodes. Window currents are
    integral I(E) dE / delta E under piecewise-linear I(E), not a sample-count
    mean; descending potential order is retained. No interpolation or deletion.

    conditions must contain exactly CDL_CONDITIONS, with actual bool values.
    They are caller attestations, not verification by a linear fit. False
    conditions, reversed/nonpositive signed branches, or a nonpositive slope
    return HOLD with the signed apparent slope retained and cdl_F=None.
    linearity_tolerance is an explicit positive dimensionless QC threshold for
    max(abs(residual))/max(abs(current)) and the relative anodic/cathodic slope
    mismatch. It is not a universal scientific threshold. Individual branches
    are fitted and checked as well as their half difference. Passing these
    diagnostics still does not independently verify a nonfaradaic response.
    The intercept is fitted freely. No ECSA or pure-EDLC claim is calculated.
    Optional area/mass normalize by explicit m2/kg only; they are never guessed.
    """
    rates, potential = _rates(rates_V_s), _array(potential_V, "potential_V")
    anodic = _array(anodic_current_A, "anodic_current_A", ndim=2)
    cathodic = _array(cathodic_current_A, "cathodic_current_A", ndim=2)
    if len(potential) == 0 or anodic.shape != (len(rates), len(potential)) or cathodic.shape != anodic.shape:
        raise ValueError("current matrices must match [rates, shared potential nodes]")
    if len(potential) > 1:
        _branch(potential, "potential_V")
    if not isinstance(conditions, dict) or set(conditions) != CDL_CONDITIONS:
        raise ValueError("conditions: exactly CDL_CONDITIONS required")
    if any(type(value) is not bool for value in conditions.values()):
        raise ValueError("conditions: actual bool values required")
    tolerance = _positive(linearity_tolerance, "linearity_tolerance")
    if tolerance >= 1:
        raise ValueError("linearity_tolerance must be less than one")
    if (sample_potential_V is None) == (window_V is None):
        raise ValueError("select exactly one sample_potential_V or window_V")
    if sample_potential_V is not None:
        sample = float(_array([sample_potential_V], "sample_potential_V")[0])
        selected = np.flatnonzero(potential == sample)
        if len(selected) != 1:
            raise ValueError("sample_potential_V must equal exactly one shared raw node")
        ia, ic = anodic[:, selected[0]].copy(), cathodic[:, selected[0]].copy()
        selection = "raw_node"
    else:
        window = _array(window_V, "window_V")
        if len(window) != 2 or window[0] >= window[1]:
            raise ValueError("window_V: ordered lower/upper bounds required")
        if not all(np.any(potential == edge) for edge in window):
            raise ValueError("window_V endpoints must equal shared raw nodes")
        selected = np.flatnonzero((potential >= window[0]) & (potential <= window[1]))
        nodes = potential[selected]
        delta = _difference(nodes, "selected potential intervals")
        span = _finite(nodes[-1] - nodes[0], "selected voltage span")
        ia = np.sum((anodic[:, selected[:-1]]/2 + anodic[:, selected[1:]]/2) * delta, axis=1) / span
        ic = np.sum((cathodic[:, selected[:-1]]/2 + cathodic[:, selected[1:]]/2) * delta, axis=1) / span
        selection = "piecewise_linear_voltage_window_mean"
    half_difference = _finite(ia/2 - ic/2, "half branch-current difference")
    common_mode = _finite(ia/2 + ic/2, "common-mode current")
    design = np.column_stack((rates, np.ones(len(rates))))
    fit = _ols(design, half_difference)
    anodic_fit, cathodic_fit = _ols(design, ia), _ols(design, ic)
    slope, intercept = (float(x) for x in fit["coefficients"])
    hold = [key for key in sorted(CDL_CONDITIONS) if not conditions[key]]
    if np.any(anodic[:, selected] <= 0) or np.any(cathodic[:, selected] >= 0):
        hold.append("branch_signs_not_anodic_positive_cathodic_negative")
    if slope <= 0:
        hold.append("nonpositive_apparent_capacitance")
    diagnostic_residuals = {}
    for name, observed, fitted in [("half_difference", half_difference, fit),
                                    ("anodic", ia, anodic_fit), ("cathodic", ic, cathodic_fit)]:
        _finite([fitted["condition"], fitted["scaled_condition"]], f"{name} fit conditioning")
        norm = float(np.max(np.abs(observed)))
        relative = float(_finite(np.divide(np.max(np.abs(fitted["residual"])), norm),
                                 f"{name} fractional residual")) if norm > 0 else None
        diagnostic_residuals[f"{name}_max_fractional_residual"] = relative
        if relative is not None and relative > tolerance:
            hold.append(f"{name}_nonlinear_residual")
    anodic_slope, cathodic_slope = float(anodic_fit["coefficients"][0]), float(cathodic_fit["coefficients"][0])
    mismatch = float(_finite(np.divide(abs(anodic_slope/2 + cathodic_slope/2), abs(slope)),
                             "branch slope mismatch")) if slope != 0 else None
    if mismatch is not None and mismatch > tolerance:
        hold.append("branch_slope_mismatch")
    # Scale before squaring to avoid losing small but informative fit residuals.
    magnitude = float(np.max(np.abs(half_difference)))
    r_squared = None
    if magnitude > 0:
        scaled = half_difference / magnitude
        total = np.sum((scaled - np.mean(scaled)) ** 2)
        if total > 0:
            r_squared = float(_finite(1 - np.sum((fit["residual"] / magnitude) ** 2) / total,
                                      "r_squared"))
    normalizations = {}
    for value, name, unit in [(area_m2, "area_m2", "F_per_m2"), (mass_kg, "mass_kg", "F_per_kg")]:
        if value is not None:
            denominator = _positive(value, name)
            normalizations[name] = denominator
            normalized = float(_finite(np.divide(slope, denominator), unit))
            normalizations[f"apparent_capacitance_{unit}"] = normalized
            normalizations[f"cdl_{unit}"] = normalized if not hold else None
    return {"status": "HOLD" if hold else "ready", "hold_reasons": hold,
            "apparent_capacitance_F": slope, "cdl_F": slope if not hold else None,
            "intercept_A": intercept, "r_squared": r_squared, "fit": fit,
            "anodic_fit": anodic_fit, "cathodic_fit": cathodic_fit,
            "anodic_slope_F": anodic_slope, "cathodic_slope_F": cathodic_slope,
            "branch_slope_mismatch": mismatch, "linearity_tolerance": tolerance,
            **diagnostic_residuals,
            "half_difference_A": half_difference, "common_mode_A": common_mode,
            "selected_anodic_current_A": ia, "selected_cathodic_current_A": ic,
            "rates_V_s": rates, "potential_V": potential,
            "anodic_current_A": anodic, "cathodic_current_A": cathodic,
            "selected_indices": selected, "selection": selection,
            "conditions": dict(conditions), "normalizations": normalizations,
            "claim_boundary": "Conditional Cdl estimate; linearity is not nonfaradaic or ECSA proof."}


def _cycle_branch(Q_C, V_V, name):
    q, v = _array(Q_C, f"{name}_Q_C"), _array(V_V, f"{name}_V_V")
    _equal_lengths(q, v)
    dq = _difference(q, f"{name} charge increments")
    if len(dq) == 0 or q[0] != 0 or np.any(q < 0) or np.any(dq < 0) or q[-1] <= 0:
        raise ValueError(f"{name}: cumulative branch capacity must start at zero, never decrease and end positive")
    if np.any(v < 0):
        raise ValueError(f"{name}: nonnegative full-cell terminal voltage required")
    # Repeated Q nodes are kept; their zero dQ contributes zero work.
    terms = _finite((v[:-1]/2 + v[1:]/2) * dq, f"{name} energy intervals")
    energy = _positive(math.fsum(terms), f"{name} energy_J")
    capacity = float(q[-1])
    return {"Q_C": q, "V_V": v, "capacity_C": capacity, "energy_J": energy,
            "energy_Wh": float(_finite(np.divide(energy, 3600), f"{name} energy_Wh")),
            "mean_voltage_V": float(_finite(np.divide(energy, capacity), f"{name} mean voltage"))}


@_guarded_math
def cycle_efficiency(charge_Q_C, charge_V_V, discharge_Q_C, discharge_V_V, *,
                     Q_convention, complete_branches, voltage_basis):
    """Capacity/energy accounting for paired full-cell charge/discharge branches.

    Q_convention='branch_capacity': each Q array starts at zero and accumulates
    positively in source order; no abs/sign flip, sorting, smoothing or deletion.
    Repeated Q nodes are retained. voltage_basis must be 'cell_terminal', not
    potential vs a reference electrode. E=integral V dQ in J is exact for the
    explicitly assumed piecewise-linear V(Q), E_Wh=E_J/3600, mean_V=E/Q.
    This does not reconstruct integral V(t)I(t) from separately sampled signals.

    CE=Qdis/Qch; EE=Edis/Ech. Losses are Qch-Qdis and Ech-Edis, respectively;
    negative losses and efficiencies above 100% remain visible with flags.
    complete_branches is a strict bool attestation: False gives HOLD while
    preserving partial-branch descriptive quantities, not full-cycle efficiency.
    """
    if Q_convention != "branch_capacity":
        raise ValueError("Q_convention: explicit branch_capacity required")
    if voltage_basis != "cell_terminal":
        raise ValueError("voltage_basis: explicit full-cell cell_terminal required")
    if type(complete_branches) is not bool:
        raise ValueError("complete_branches: actual bool required")
    charge = _cycle_branch(charge_Q_C, charge_V_V, "charge")
    discharge = _cycle_branch(discharge_Q_C, discharge_V_V, "discharge")
    ce = float(_finite(np.divide(discharge["capacity_C"], charge["capacity_C"]), "CE"))
    ee = float(_finite(np.divide(discharge["energy_J"], charge["energy_J"]), "EE"))
    q_loss = float(_finite(charge["capacity_C"] - discharge["capacity_C"], "charge loss"))
    e_loss = float(_finite(charge["energy_J"] - discharge["energy_J"], "energy loss"))
    flags = []
    if ce > 1:
        flags.append("coulombic_efficiency_above_100_percent")
    if ee > 1:
        flags.append("energy_efficiency_above_100_percent")
    return {"status": "ready" if complete_branches else "HOLD",
            "hold_reasons": [] if complete_branches else ["incomplete_branches"],
            "anomaly_flags": flags, "charge_Q_C": charge["capacity_C"],
            "discharge_Q_C": discharge["capacity_C"],
            "charge_energy_J": charge["energy_J"], "discharge_energy_J": discharge["energy_J"],
            "charge_energy_Wh": charge["energy_Wh"], "discharge_energy_Wh": discharge["energy_Wh"],
            "charge_mean_voltage_V": charge["mean_voltage_V"],
            "discharge_mean_voltage_V": discharge["mean_voltage_V"],
            "coulombic_efficiency": ce, "energy_efficiency": ee,
            "coulombic_efficiency_pct": float(_finite(ce * 100, "CE percent")),
            "energy_efficiency_pct": float(_finite(ee * 100, "EE percent")),
            "charge_loss_C": q_loss, "energy_loss_J": e_loss,
            "raw_charge_Q_C": charge["Q_C"], "raw_charge_V_V": charge["V_V"],
            "raw_discharge_Q_C": discharge["Q_C"], "raw_discharge_V_V": discharge["V_V"],
            "Q_convention": Q_convention, "voltage_basis": voltage_basis,
            "complete_branches": complete_branches,
            "integration": "piecewise_linear_voltage_vs_branch_capacity"}


def _rs_prefactor(*, n, A_m2, c_mol_m3, T_K, conditions):
    if isinstance(n, (bool, np.bool_)) or not isinstance(n, (int, np.integer)) or n < 1:
        raise ValueError("n: positive integer electron count required")
    if isinstance(conditions, str) or not isinstance(conditions, (set, frozenset, list, tuple)):
        raise ValueError("conditions: explicit condition names required")
    if any(not isinstance(item, str) for item in conditions) or set(conditions) != RS_CONDITIONS:
        raise ValueError("Randles-Sevcik: explicit reversible planar semi-infinite solution conditions required")
    area, concentration, temperature = (_positive(x, name) for x, name in
        [(A_m2, "A_m2"), (c_mol_m3, "c_mol_m3"), (T_K, "T_K")])
    prefactor = 0.4463 * n * FARADAY_C_PER_MOL * area * concentration * math.sqrt(
        n * FARADAY_C_PER_MOL / (GAS_CONSTANT_J_PER_MOL_K * temperature))
    return _positive(prefactor, "Randles-Sevcik prefactor")


@_guarded_math
def randles_sevcik_peak(rates_V_s, *, n, A_m2, c_mol_m3, T_K, D_m2_s, conditions):
    """Ip=0.4463*n*F*A*c*sqrt(n*F*D*v/(R*T)), all inputs strictly SI.

    Positive peak magnitude only; conditions are caller attestations, not proof.
    No solid-state/porous electrode diffusion inference is offered.
    """
    rates = _array(rates_V_s, "rates_V_s")
    if len(rates) == 0 or np.any(rates <= 0):
        raise ValueError("rates_V_s: positive scan rates required")
    prefactor = _rs_prefactor(n=n, A_m2=A_m2, c_mol_m3=c_mol_m3, T_K=T_K, conditions=conditions)
    diffusivity = _positive(D_m2_s, "D_m2_s")
    peak = _finite(prefactor * math.sqrt(diffusivity) * np.sqrt(rates), "peak current")
    if np.any(peak == 0):
        raise ValueError("peak current underflow")
    return {"peak_current_A": peak, "rates_V_s": rates, "D_m2_s": diffusivity,
            "conditions": sorted(conditions), "model": "reversible_planar_semi_infinite_solution"}


@_guarded_math
def randles_sevcik_diffusivity(slope_A_per_sqrt_V_s, *, n, A_m2, c_mol_m3, T_K, conditions):
    """Recover SI D=(slope/prefactor)**2 under explicitly declared RS conditions."""
    slope = _positive(slope_A_per_sqrt_V_s, "slope_A_per_sqrt_V_s")
    prefactor = _rs_prefactor(n=n, A_m2=A_m2, c_mol_m3=c_mol_m3, T_K=T_K, conditions=conditions)
    diffusivity = _positive((slope / prefactor) ** 2, "D_m2_s")
    return {"D_m2_s": diffusivity, "conditions": sorted(conditions),
            "model": "reversible_planar_semi_infinite_solution"}
