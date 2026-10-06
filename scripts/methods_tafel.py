"""Opt-in LSV/Tafel numerical methods with explicit data contracts.

This module preserves source order and signed anodic-positive current. It does
not infer reference/area/equilibrium potential, steady state, kinetics, alpha,
exchange current, corrosion current or a rate-determining step. R2, declared
conditions and reproducibility do not establish a Tafel regime.
"""
from __future__ import annotations

import math
from numbers import Real

import numpy as np

R = 8.31446261815324
F = 96485.33212
UNITS = {"A": ("current", 1.), "mA": ("current", 1e-3),
         "A/cm2": ("density", 1.), "mA/cm2": ("density", 1e-3)}
CONDITIONS = ("steady_state", "charging_negligible", "transport_negligible",
              "uniform_access", "single_kinetic_regime")


def _number(value, name, *, positive=False):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(name + " requires an explicit finite number")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(name + " is unrepresentable") from exc
    if not math.isfinite(result) or (result == 0 and value != 0) or positive and result <= 0:
        raise ValueError(name + " is outside its finite allowed range")
    return result


def _vector(values, name):
    if isinstance(values, (list, tuple)) and any(not isinstance(v, Real) or isinstance(v, (bool, np.bool_)) for v in values):
        raise ValueError(name + " cannot coerce text/boolean observations")
    raw = np.asarray(values)
    if raw.ndim != 1 or raw.size < 2 or raw.dtype.kind not in "iuf":
        raise ValueError(name + " must be a one-dimensional numerical array")
    with np.errstate(over="ignore", under="ignore"):
        values = np.array(raw, dtype=float, copy=True)
    if not np.all(np.isfinite(values)) or np.any((raw != 0) & (values == 0)):
        raise ValueError(name + " contains nonfinite or unrepresentable observations")
    return values


def _product(values, name):
    """Separate exponents to avoid intermediate overflow/subnormal range loss."""
    if any(value == 0 for value in values):
        return 0.
    parts = [math.frexp(value) for value in values]
    try:
        result = math.ldexp(math.prod(part[0] for part in parts),
                            sum(part[1] for part in parts))
    except OverflowError as exc:
        raise ValueError(name + ' overflow') from exc
    if not math.isfinite(result) or result == 0:
        raise ValueError(name + ' overflow/underflow')
    return result


def _scaled(values, factor, name):
    with np.errstate(over="ignore", under="ignore"):
        result = values * factor
    if not np.all(np.isfinite(result)) or np.any((values != 0) & (result == 0)):
        raise ValueError(name + " conversion overflow/underflow")
    return result


def _range(pair, name, *, positive=False):
    if not isinstance(pair, (tuple, list, np.ndarray)) or len(pair) != 2:
        raise ValueError(name + " requires an increasing pair")
    low, high = [_number(v, name, positive=positive) for v in pair]
    if high <= low or not math.isfinite(high - low):
        raise ValueError(name + " requires a representable increasing range")
    return low, high


def _ir(E, I, spec):
    if spec is None:
        return E.copy(), {"status": "NOT_DECLARED_NO_CORRECTION", "claim": "No iR assumption or correction made."}
    expected = {"Ru_ohm", "input_compensation", "prior_fraction", "residual_fraction"}
    if not isinstance(spec, dict) or set(spec) != expected:
        raise ValueError("iR requires Ru_ohm, input_compensation, prior_fraction and residual_fraction")
    if I is None:
        raise ValueError("iR uses signed I in A, not j; current-density input needs an explicit area")
    Ru = _number(spec["Ru_ohm"], "Ru_ohm")
    prior = _number(spec["prior_fraction"], "prior_fraction")
    residual = _number(spec["residual_fraction"], "residual_fraction")
    if Ru < 0 or not 0 <= prior <= 1 or not 0 <= residual <= 1:
        raise ValueError("Ru must be nonnegative and compensation fractions must be [0,1]")
    state = spec["input_compensation"]
    if state not in ("none", "partial", "full"):
        raise ValueError("Preexisting compensation must be explicitly none, partial or full")
    if state == "none" and prior != 0 or state == "partial" and not 0 < prior < 1 or state == "full" and prior != 1:
        raise ValueError("Compensation state/fraction mismatch")
    if prior + residual > 1 + 4 * np.finfo(float).eps:
        raise ValueError("Refusing double iR correction: prior plus additional fraction exceeds one")
    # The extra fraction refers to the original declared Ru, not to a second
    # unrecorded fraction of a residual resistance. No abs(I) or j*ohm shortcut.
    scale = Ru * residual
    if Ru and residual and scale == 0:
        raise ValueError("iR correction scale underflow; no false zero correction")
    drop = _scaled(I, scale, "iR") if scale else np.zeros_like(I)
    corrected = E - drop
    if not np.all(np.isfinite(corrected)):
        raise ValueError("iR-corrected potential overflow")
    return corrected, {"status": "EXPLICIT_SIGNED_CORRECTION", **spec,
                       "correction_V": drop.tolist(),
                       "formula": "E_internal_V = E_supplied_V - I_signed_A * Ru_ohm * residual_fraction",
                       "residual_fraction_definition": "Additional fraction of the original declared Ru; prior+additional <= 1.",
                       "claim": "Declared resistance/fraction only; resistance constancy and measured provenance are not established."}


def _reference(E, spec):
    if spec is None:
        return None, {"status": "NOT_DECLARED", "claim": "No RHE conversion guessed."}
    if not isinstance(spec, dict):
        raise ValueError("reference must be an explicit object")
    mode = spec.get("mode")
    if mode == "direct_RHE":
        if set(spec) != {"mode", "offset_V", "provenance"} or not isinstance(spec["provenance"], str) or not spec["provenance"].strip():
            raise ValueError("direct_RHE requires only an offset and its provenance; do not add pH/SHE terms")
        offset = _number(spec["offset_V"], "RHE offset_V")
        statement = "Assigned/measured direct reference-to-RHE offset; this module does not validate calibration."
    elif mode == "reference_SHE":
        keys = {"mode", "reference_to_SHE_V", "temperature_K", "pH", "reference_name", "filling", "junction_assumption"}
        if set(spec) != keys:
            raise ValueError("reference_SHE requires explicit reference/SHE, T, pH, reference identity/filling and junction assumption")
        if any(not isinstance(spec[k], str) or not spec[k].strip() for k in ("reference_name", "filling")):
            raise ValueError("Reference identity and filling cannot be inferred")
        if spec["junction_assumption"] != "neglected":
            raise ValueError("This formula route only supports an explicitly neglected junction potential; use a measured direct offset otherwise")
        temperature = _number(spec["temperature_K"], "temperature_K", positive=True)
        pH = _number(spec["pH"], "pH")
        ref = _number(spec["reference_to_SHE_V"], "reference_to_SHE_V")
        pH_shift = _product([(R / F) * math.log(10), temperature, pH], 'RHE pH shift')
        offset = ref + pH_shift
        if not math.isfinite(offset):
            raise ValueError("RHE reference offset overflow")
        statement = "Conditional ideal aqueous/standard-H2 reference algebra; junction potential neglected, not a validated calibration."
    else:
        raise ValueError("Choose exactly one reference route: direct_RHE or reference_SHE")
    result = E + offset
    if not np.all(np.isfinite(result)):
        raise ValueError("RHE potential conversion overflow")
    return result, {"status": "EXPLICIT_REFERENCE_CONVENTION", **spec, "total_offset_V": offset,
                    "formula": "E_RHE = E_internal + direct_offset" if mode == "direct_RHE" else "E_RHE = E_internal + E_ref_vs_SHE + R*T*ln(10)/F*pH",
                    "claim": statement}


def prepare_lsv(E_V, current, *, current_unit, current_sign, area_cm2=None,
                ir=None, reference=None, equilibrium_potential_RHE_V=None, mode="catalysis"):
    """Retain raw LSV and optionally apply explicitly declared conventions.

    E_V is supplied potential in V, not automatically RHE. Without reference,
    area or equilibrium metadata the raw LSV remains available; no Tafel or RHE
    numbers are invented. Current sign must already be anodic-positive.
    """
    E, signal = _vector(E_V, "potential_V"), _vector(current, "current")
    if len(E) != len(signal):
        raise ValueError("Every potential must retain its matching current observation")
    if current_sign != "anodic_positive":
        raise ValueError("Explicit anodic_positive sign convention is required; no silent branch inversion")
    if current_unit not in UNITS:
        raise ValueError("Declare A/mA or A/cm2/mA/cm2; no impedance/current-density unit inference")
    if mode not in ("catalysis", "corrosion"):
        raise ValueError("Unknown electrochemical mode")
    area = None if area_cm2 is None else _number(area_cm2, "area_cm2", positive=True)
    basis, factor = UNITS[current_unit]
    canonical = _scaled(signal, factor, "current unit")
    if basis == "current":
        I = canonical
        j = None if area is None else _scaled(I, 1 / area, "current density")
    else:
        j = canonical
        I = None if area is None else _scaled(j, area, "signed current")
    Eint, ir_metadata = _ir(E, I, ir)
    Erhe, reference_metadata = _reference(Eint, reference)
    Eeq = None if equilibrium_potential_RHE_V is None else _number(equilibrium_potential_RHE_V, "equilibrium_potential_RHE_V")
    eta = None if Erhe is None or Eeq is None else Erhe - Eeq
    if eta is not None and not np.all(np.isfinite(eta)):
        raise ValueError("Overpotential overflow")
    return {"schema_version": 1, "mode": mode, "status": "LSV_PRESERVED",
            "raw_E_V": E.tolist(), "raw_current": signal.tolist(), "raw_current_unit": current_unit,
            "current_sign": current_sign, "source_indices_zero_based": list(range(len(E))),
            "I_A": None if I is None else I.tolist(), "j_A_cm2": None if j is None else j.tolist(),
            "area_cm2": area, "E_internal_V": Eint.tolist(), "ir_metadata": ir_metadata,
            "E_RHE_V": None if Erhe is None else Erhe.tolist(), "reference_metadata": reference_metadata,
            "equilibrium_potential_RHE_V": Eeq, "eta_RHE_V": None if eta is None else eta.tolist(),
            "raw_order_preserved": True, "scientific_validation": "NOT_ESTABLISHED"}


def _basis_values(prepared, unit):
    if unit not in UNITS:
        raise ValueError("Explicit current reference/window unit required")
    basis, factor = UNITS[unit]
    value = prepared["I_A" if basis == "current" else "j_A_cm2"]
    if value is None:
        return None, factor
    return _vector(value, "canonical current"), factor


def _select(prepared, window):
    if not isinstance(window, dict):
        raise ValueError("An explicit fit window is required; no automatic maximum-R2 selection")
    count = len(prepared["raw_E_V"])
    kind = window.get("kind")
    if kind == "indices":
        if set(window) != {"kind", "indices"} or not isinstance(window["indices"], (list, tuple)):
            raise ValueError("indices window requires an explicit ordered list")
        indices = window["indices"]
        if not indices or any(type(v) is not int or not 0 <= v < count for v in indices) or any(b <= a for a, b in zip(indices, indices[1:])):
            raise ValueError("Indices must preserve source order and be unique/in bounds")
        return np.array(indices, dtype=int)
    if kind == "overpotential_V":
        if set(window) != {"kind", "range"}:
            raise ValueError("Overpotential window requires only an explicit V range")
        low, high = _range(window["range"], "overpotential window")
        values = _vector(prepared["eta_RHE_V"], "overpotential")
        return np.flatnonzero((values >= low) & (values <= high))
    if kind == "current_abs":
        if set(window) != {"kind", "unit", "range"}:
            raise ValueError("Current window requires range and its explicit unit")
        low, high = _range(window["range"], "absolute current window", positive=True)
        values, factor = _basis_values(prepared, window["unit"])
        if values is None:
            raise ValueError("Current window needs its explicit current/area basis")
        # Compare logs to avoid silently underflowing a positive current bound.
        magnitudes = np.abs(values)
        selected = magnitudes > 0
        logs = np.full(len(values), -np.inf)
        logs[selected] = np.log10(magnitudes[selected]) - math.log10(factor)
        return np.flatnonzero((logs >= math.log10(low)) & (logs <= math.log10(high)))
    raise ValueError("Unsupported explicit fit-window kind")


def _ols(x, y):
    xm, ym = float(np.mean(x)), float(np.mean(y))
    dx, dy = x - xm, y - ym
    scale = float(np.max(np.abs(dy)))
    denominator = float(np.dot(dx, dx))
    if scale == 0 or denominator <= 0 or not math.isfinite(denominator):
        raise ValueError("Zero/unrepresentable Tafel ordinate or logarithmic range")
    normalized = dy / scale
    scaled_slope = float(np.dot(dx, normalized) / denominator)
    slope = scaled_slope * scale
    intercept = ym - slope * xm
    if not math.isfinite(slope) or not math.isfinite(intercept) or scaled_slope and slope == 0:
        raise ValueError("Tafel slope/intercept overflow or underflow")
    fitted = intercept + slope * x
    normalized_residual = normalized - scaled_slope * dx
    r2 = 1 - float(np.dot(normalized_residual, normalized_residual) / np.dot(normalized, normalized))
    return slope, intercept, fitted, y - fitted, r2, dx, normalized, scale


def fit_tafel(prepared, *, window, polarity, log_reference_value, log_reference_unit,
              conditions, min_points=6, min_decades=0.5, trim_fraction=0.15,
              curvature_limit=0.05, slope_spread_limit=0.05):
    """Conditional apparent eta/log10(abs(current)/declared reference) slope.

    polarity is anodic/cathodic. Window and log current/density unit are explicit;
    no points are sorted/dropped to improve R2. Subwindows are diagnostics,
    never an automatic choice of a publication slope or an inferred mechanism.
    """
    if not isinstance(prepared, dict) or prepared.get("schema_version") != 1:
        raise ValueError("Use an explicitly prepared LSV contract")
    if polarity not in ("anodic", "cathodic"):
        raise ValueError("Declare anodic or cathodic branch")
    reference_value = _number(log_reference_value, "log_reference_value", positive=True)
    values, unit_factor = _basis_values(prepared, log_reference_unit)
    if type(min_points) is not int or min_points < 4:
        raise ValueError("min_points must be an integer at least four")
    minimum_span = _number(min_decades, "min_decades", positive=True)
    trim = _number(trim_fraction, "trim_fraction", positive=True)
    curvature_threshold = _number(curvature_limit, "curvature_limit", positive=True)
    spread_threshold = _number(slope_spread_limit, "slope_spread_limit", positive=True)
    if trim >= 0.4:
        raise ValueError("trim_fraction must be below 0.4")
    if not isinstance(conditions, dict) or set(conditions) - set(CONDITIONS) or any(v is not None and type(v) is not bool for v in conditions.values()):
        raise ValueError("Conditions must be explicit boolean/unknown declarations, not inferred from R2")
    missing = []
    if prepared["mode"] == "corrosion": missing.append("CORROSION_REQUIRES_SPECIALIZED_MIXED_CURRENT_MODEL")
    if prepared["E_RHE_V"] is None: missing.append("MISSING_REFERENCE_CONVENTION")
    if prepared["equilibrium_potential_RHE_V"] is None: missing.append("MISSING_EQUILIBRIUM_POTENTIAL")
    if values is None: missing.append("MISSING_CURRENT_OR_AREA_BASIS")
    if missing:
        return {"status": "HOLD", "hold_reasons": missing, "raw_lsv_available": True,
                "scientific_validation": "NOT_ESTABLISHED", "slope_signed_V_per_dec": None,
                "claim": "Raw LSV retained; no RHE/area/equilibrium/corrosion parameters guessed."}
    indices = _select(prepared, window)
    if len(indices) < min_points:
        raise ValueError("Selected window has too few actual source observations")
    # Sparse explicit indices may sample one branch, but they cannot hide an
    # intervening scan turn and stitch two forward/reverse branches together.
    source_interval = _vector(prepared["raw_E_V"], "source potential")[indices[0]:indices[-1] + 1]
    source_steps = np.diff(source_interval)
    if not (np.all(source_steps > 0) or np.all(source_steps < 0)):
        raise ValueError("Source interval crosses a potential turn/repeat; selected indices cannot pool separate scan branches")
    selected = values[indices]
    if np.any(selected == 0) or (polarity == "anodic" and np.any(selected < 0)) or (polarity == "cathodic" and np.any(selected > 0)):
        raise ValueError("Selected current contains zero/opposite polarity; no abs before branch validation")
    eta = _vector(prepared["eta_RHE_V"], "overpotential")[indices]
    if (polarity == "anodic" and np.any(eta <= 0)) or (polarity == "cathodic" and np.any(eta >= 0)):
        raise ValueError("Overpotential sign contradicts declared reaction branch/equilibrium")
    steps = np.diff(eta)
    if not (np.all(steps > 0) or np.all(steps < 0)):
        raise ValueError("Select one strictly monotonic potential branch; no sorting/pooled scan turns")
    x = np.log10(np.abs(selected)) - math.log10(unit_factor) - math.log10(reference_value)
    span = float(np.max(x) - np.min(x))
    if span < minimum_span:
        raise ValueError("Selected logarithmic current range is below the explicit minimum")
    slope, intercept, predicted, residual, r2, dx, normalized, yscale = _ols(x, eta)
    if slope == 0 or (polarity == "anodic" and slope < 0) or (polarity == "cathodic" and slope > 0):
        raise ValueError("Slope sign contradicts the declared branch; no sign flipping")
    slope_magnitude = 1000 * abs(slope)
    if not math.isfinite(slope_magnitude):
        raise ValueError("Tafel mV/dec magnitude is unrepresentable")
    design = np.column_stack((np.ones(len(x)), dx, dx * dx))
    coefficients, _, rank, _ = np.linalg.lstsq(design, normalized, rcond=None)
    if rank < 3:
        raise ValueError("Curvature diagnostics require a resolvable log-current grid")
    curvature = float(np.max(np.abs(coefficients[2] * dx * dx)) / np.ptp(normalized))
    subwindows = []
    edge = max(1, int(math.floor(len(x) * trim)))
    for name, start, stop in (("trim_high_source_edge", 0, len(x) - edge),
                              ("trim_low_source_edge", edge, len(x)),
                              ("trim_both_source_edges", edge, len(x) - edge)):
        if stop - start < min_points or np.ptp(x[start:stop]) < minimum_span:
            subwindows.append({"name": name, "status": "INSUFFICIENT_POINTS_OR_LOG_SPAN"})
            continue
        b, a, _, _, sub_r2, _, _, _ = _ols(x[start:stop], eta[start:stop])
        subwindows.append({"name": name, "status": "DIAGNOSTIC", "source_indices": indices[start:stop].tolist(),
                           "slope_signed_V_per_dec": b, "intercept_V": a, "r2": sub_r2})
    secondary_slopes = [p["slope_signed_V_per_dec"] for p in subwindows if p["status"] == "DIAGNOSTIC"]
    spread = None if len(secondary_slopes) < 2 else (max(secondary_slopes) - min(secondary_slopes)) / abs(slope)
    reasons = ["CONDITION_NOT_ESTABLISHED:" + key for key in CONDITIONS if conditions.get(key) is not True]
    if prepared["ir_metadata"]["status"] == "NOT_DECLARED_NO_CORRECTION": reasons.append("IR_STATE_NOT_DECLARED")
    if curvature > curvature_threshold: reasons.append("CURVATURE_DIAGNOSTIC_FLAG")
    if spread is None: reasons.append("INSUFFICIENT_WINDOW_SENSITIVITY")
    elif spread > spread_threshold: reasons.append("FIT_WINDOW_SLOPE_SENSITIVITY")
    return {"status": "CONDITIONAL_APPARENT_FIT" if not reasons else "HOLD_MODEL_DIAGNOSTICS",
            "hold_reasons": reasons, "source_indices_zero_based": indices.tolist(), "window": window,
            "source_branch_interval_zero_based": [int(indices[0]), int(indices[-1])],
            "polarity": polarity, "log10_abs_current_over_reference": x.tolist(),
            "log_reference_value": reference_value, "log_reference_unit": log_reference_unit,
            "eta_V": eta.tolist(), "fit_eta_V": predicted.tolist(), "residual_V": residual.tolist(),
            "slope_signed_V_per_dec": slope, "slope_magnitude_mV_per_dec": slope_magnitude,
            "intercept_V": intercept, "r2": r2, "log_span_decades": span, "min_decades": minimum_span,
            "quadratic_curvature_fraction": curvature, "curvature_limit": curvature_threshold,
            "quadratic_coefficient_V_per_dec2": float(coefficients[2] * yscale),
            "subwindows": subwindows, "relative_subwindow_slope_spread": spread,
            "slope_spread_limit": spread_threshold, "conditions": conditions,
            "raw_order_preserved": True, "scientific_validation": "NOT_ESTABLISHED",
            "uncertainty": "NOT_ESTIMATED", "automatic_exchange_current_alpha_RDS_icorr": False,
            "claim": "Apparent slope of an explicitly selected branch/window only. R2, local linearity and declared assumptions do not prove steady-state charge-transfer kinetics or identify an elementary step."}
