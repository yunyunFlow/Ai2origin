"""Opt-in CV correction primitives; no automatic mechanism assignment.

Pu et al., doi:10.1002/anie.202104167 motivates the order potential / reversal
tail / background / branch alignment / regression. These are independent,
dimensionally explicit implementations, not copied third-party code. In
particular their printed exp(a*V)+b needs a current scale and sign; here the
declared model is A_current*exp(-progress_V/scale_V). Tail fit and background
identification remain conditional on independent experimental justification.

Correcting E by IR does not preserve a constant sweep derivative. A physical
constant-C background is C*dE_corrected/dt, not silently C*nominal_scan_rate.
Raw nodes and order are retained in every transformation. Resampling is a
separate explicit operation and refuses folds and extrapolation.
"""
from numbers import Real
import math
import numpy as np
from scipy.optimize import least_squares

UNITS = {"A", "mA", "A/cm^2", "mA/cm^2", "A/g"}


def _array(value, name):
    try:
        raw = np.asarray(value, dtype=object)
    except (TypeError, ValueError) as exc:
        raise ValueError(name + ": actual real numeric array required") from exc
    if raw.ndim != 1 or len(raw) < 2:
        raise ValueError(name + ": finite 1-D array with at least two nodes required")
    if any(isinstance(x, (bool, np.bool_)) or not isinstance(x, Real) for x in raw):
        raise ValueError(name + ": actual real numbers required, no bool/text/complex/object coercion")
    numbers = []
    for item in raw:
        try:
            number = float(item)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(name + ": unrepresentable real number") from exc
        if not np.isfinite(number) or (number == 0 and item != 0):
            raise ValueError(name + ": nonfinite or underflowing real number")
        numbers.append(number)
    return np.array(numbers, dtype=float)


def _scalar(value, name, positive=False):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(name + ": actual numeric scalar required")
    try:
        x = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(name + ": finite scalar required") from exc
    if not np.isfinite(x) or (positive and x <= 0):
        raise ValueError(name + ": finite" + (" positive" if positive else "") + " scalar required")
    if x == 0 and value != 0:
        raise ValueError(name + ": nonzero scalar underflows float representation")
    return x


def _same(*a):
    if len({len(x) for x in a}) != 1:
        raise ValueError("paired arrays must have identical lengths")


def _unit(unit):
    if not isinstance(unit, str) or unit not in UNITS:
        raise ValueError("declare a supported actual current/current-density unit")
    return unit


def _source(source):
    if not isinstance(source, str) or not source.strip():
        raise ValueError("explicit source/model assumption required")
    return source


def _direction(value):
    if type(value) is not int or value not in [-1, 1]:
        raise ValueError("branch_direction must be integer -1 or +1")
    return value


def _finite(a, name):
    if not np.isfinite(a).all():
        raise ValueError(name + ": unrepresentable arithmetic")
    return a


def _difference(values, name):
    with np.errstate(over='ignore', invalid='ignore'):
        return _finite(np.diff(values), name)


def _progress(potential, direction):
    with np.errstate(over='ignore', invalid='ignore'):
        return _finite(direction*(potential-potential[0]), 'branch potential progress')


def _product(*factors):
    """Separate exponents to avoid subnormal intermediate range/precision loss."""
    if any(value == 0 for value in factors):
        return 0.0
    mantissa, exponent = 1.0, 0
    for value in factors:
        m, e = math.frexp(value)
        mantissa *= m
        exponent += e
    try:
        result = math.ldexp(mantissa, exponent)
    except OverflowError as exc:
        raise ValueError('iR correction overflows float representation') from exc
    if not math.isfinite(result) or result == 0:
        raise ValueError('nonzero iR correction over/underflows float representation')
    return result


def ir_correct(potential_V, current_A, *, resistance_ohm,
               already_compensated_fraction=0.0, resistance_source):
    """E'=E-I*Ru*(1-f); signed I must be true A, Ru must be known ohms.

    current density cannot be substituted for A; conversion requires independently
    verified area. Already-compensated fraction is explicit to avoid double iR
    correction. A folded corrected path is retained and flagged, never sorted.
    """
    e, i = _array(potential_V, "potential_V"), _array(current_A, "current_A")
    _same(e, i)
    ru = _scalar(resistance_ohm, "resistance_ohm")
    f = _scalar(already_compensated_fraction, "already_compensated_fraction")
    if ru < 0 or not 0 <= f <= 1:
        raise ValueError("nonnegative Ru and compensation fraction in [0,1] required")
    correction = np.array([_product(float(value), ru, 1-f) for value in i])
    with np.errstate(over="ignore", invalid="ignore"):
        corrected = _finite(e-correction, "corrected potential")
    if ru > 0 and f < 1 and np.any((i != 0) & (correction == 0)):
        raise ValueError("nonzero iR correction underflows float representation")
    diff = _difference(corrected, 'corrected potential intervals')
    monotonic = bool(np.all(diff > 0) or np.all(diff < 0))
    return {"raw_potential_V": e, "raw_current_A": i,
            "corrected_potential_V": corrected, "correction_V": correction,
            "resistance_ohm": ru, "already_compensated_fraction": f,
            "resistance_source": _source(resistance_source),
            "corrected_strictly_monotonic": monotonic,
            "status": "CONDITIONAL_TRANSFORM" if monotonic else "HOLD_NONMONOTONIC_GRID",
            "resampling": "none", "source_order_preserved": True}


def resample_branch(potential_V, current, grid_V, *, current_unit, interpolation):
    """Explicit piecewise-linear I(E) on an increasing bounded target grid.

    A decreasing acquisition branch is reversed only in the derived interpolation
    view. Every original node/order remains in raw_* fields. No duplicate averaging,
    hidden sorting, smoothing, endpoint extension or cross-branch interpolation.
    """
    e, i, g = (_array(potential_V, "potential_V"), _array(current, "current"),
               _array(grid_V, "grid_V"))
    _same(e, i)
    if interpolation != "piecewise_linear":
        raise ValueError("explicit piecewise_linear interpolation required")
    d = _difference(e, 'source potential intervals')
    gd = _difference(g, 'target potential intervals')
    _difference(i, 'interpolation current intervals')
    if not (np.all(d > 0) or np.all(d < 0)) or not np.all(gd > 0):
        raise ValueError("fold/duplicate source or non-increasing target grid refused")
    if g[0] < min(e) or g[-1] > max(e):
        raise ValueError("extrapolation outside recorded branch refused")
    decreasing = bool(d[0] < 0)
    with np.errstate(over='ignore', invalid='ignore'):
        out = _finite(np.interp(g, e[::-1] if decreasing else e, i[::-1] if decreasing else i),
                      'interpolated current')
    return {"raw_potential_V": e, "raw_current": i, "grid_V": g,
            "current": out, "current_unit": _unit(current_unit),
            "interpolation": interpolation, "acquisition_direction": -1 if decreasing else 1,
            "interpolated_nodes": int(sum(not np.any(e == x) for x in g)),
            "source_order_preserved": True}


def exponential_tail(potential_V, *, branch_direction, amplitude,
                     decay_scale_V, current_unit, model_source):
    """Signed A*exp(-direction*(E-E_first)/lambda), dimensionless exponent.

    This is one declared reversal-tail model, not a universally identified reverse
    Faradaic current. lambda>0 and the branch must move strictly in its declared
    direction. An amplitude of either sign is retained; nothing is zero-forced.
    """
    e = _array(potential_V, "potential_V")
    direction = _direction(branch_direction)
    if not np.all(direction*_difference(e, 'tail source potential intervals') > 0):
        raise ValueError("declared branch direction conflicts with source nodes")
    amp = _scalar(amplitude, "amplitude")
    scale = _scalar(decay_scale_V, "decay_scale_V", positive=True)
    with np.errstate(over="ignore", under="ignore", invalid="ignore"):
        exponent = _finite(-_progress(e, direction)/scale, 'dimensionless tail exponent')
        values = amp*np.exp(exponent)
    _finite(values, "exponential tail")
    return {"tail": values, "current_unit": _unit(current_unit),
            "raw_potential_V": e, "amplitude": amp, "decay_scale_V": scale,
            "turn_potential_V": float(e[0]), "branch_direction": direction,
            "model_source": _source(model_source),
            "numerically_underflowed_nodes": int(np.sum(values == 0)) if amp else 0,
            "status": "CONDITIONAL_MODEL"}


def fit_exponential_tail(potential_V, current, *, branch_direction, fit_window_V,
                         baseline_current, amplitude_bounds, decay_scale_bounds_V,
                         current_unit, model_source, relative_rmse_limit):
    """Fit a declared tail-dominated raw window, with an explicitly supplied baseline.

    The baseline is fixed, not freely traded against the tail. Bounds, window and
    quality threshold are author-declared; a good residual alone does not prove
    identifiability. No automatic zero crossing, peak or first-point normalization.
    Fitted full-branch tail evaluation outside the fit window is explicit model
    extrapolation, recorded separately from data interpolation.
    """
    e, i = _array(potential_V, "potential_V"), _array(current, "current")
    _same(e, i)
    direction = _direction(branch_direction)
    if not np.all(direction*_difference(e, 'fit source potential intervals') > 0):
        raise ValueError("declared branch direction conflicts with source nodes")
    w, ab, sb = (_array(fit_window_V, "fit_window_V"),
                  _array(amplitude_bounds, "amplitude_bounds"),
                  _array(decay_scale_bounds_V, "decay_scale_bounds_V"))
    if len(w) != 2 or w[0] >= w[1] or len(ab) != 2 or ab[0] >= ab[1] or len(sb) != 2 or not 0 < sb[0] < sb[1]:
        raise ValueError("ordered window/amplitude bounds and positive scale bounds required")
    if ab[0] <= 0 <= ab[1]:
        raise ValueError("amplitude bounds must declare one current sign")
    if w[0] < min(e) or w[1] > max(e):
        raise ValueError("fit window outside recorded branch refused")
    ids = np.flatnonzero((e >= w[0]) & (e <= w[1]))
    if len(ids) < 4:
        raise ValueError("at least four recorded fit-window nodes required")
    baseline = _scalar(baseline_current, "baseline_current")
    limit = _scalar(relative_rmse_limit, "relative_rmse_limit", positive=True)
    with np.errstate(over='ignore', invalid='ignore'):
        target = _finite(i[ids]-baseline, "tail target")
    scale = float(max(abs(target)))
    if scale == 0 or not np.isfinite(scale):
        raise ValueError("zero/unrepresentable tail signal")
    progress = _progress(e, direction)
    def residual(z):
        return (z[0]*np.exp(-progress[ids]/z[1])-target)/scale
    opt = least_squares(residual, [float(ab[0]/2+ab[1]/2), float(np.sqrt(sb[0])*np.sqrt(sb[1]))],
                        bounds=(np.array([ab[0], sb[0]]), np.array([ab[1], sb[1]])),
                        x_scale='jac', ftol=1e-12, xtol=1e-12, gtol=1e-12, max_nfev=2000)
    model = exponential_tail(e, branch_direction=direction, amplitude=opt.x[0],
                             decay_scale_V=opt.x[1], current_unit=current_unit, model_source=model_source)
    residual_current = model['tail'][ids]-target
    nrmse = float(np.sqrt(np.mean((residual_current/scale)**2)))
    norms = np.linalg.norm(opt.jac, axis=0)
    condition = float(np.linalg.cond(opt.jac/norms)) if np.all(norms > 0) else float('inf')
    holds = []
    if not opt.success: holds.append('optimizer_failed')
    if nrmse > limit: holds.append('window_rmse_exceeds_declared_limit')
    if np.any(opt.active_mask): holds.append('parameter_at_bound')
    if not np.isfinite(condition) or condition > 1e8: holds.append('ill_conditioned_tail')
    model.update({"status": "HOLD_TAIL_MODEL" if holds else "CONDITIONAL_TAIL_FIT",
                  "hold_reasons": holds, "fit_indices": ids, "fit_window_V": w,
                  "raw_current": i, "baseline_current": baseline,
                  "fit_residual_current": residual_current, "relative_rmse": nrmse,
                  "relative_rmse_limit": limit,
                  "scaled_jacobian_condition": condition if np.isfinite(condition) else None,
                  "amplitude_bounds": ab, "decay_scale_bounds_V": sb,
                  "optimizer_success": bool(opt.success),
                  "model_extrapolated_nodes": len(e)-len(ids)})
    return model


def subtract_terms(current, *, tail, background, current_unit, correction_source):
    """Preserve I, separately supplied signed tail/background and I-tail-background."""
    i, t, b = _array(current, "current"), _array(tail, "tail"), _array(background, "background")
    _same(i, t, b)
    with np.errstate(over='ignore', invalid='ignore'):
        dr = _finite(i-t, "de-residual current")
        corrected = _finite(dr-b, "de-background current")
    return {"raw_current": i, "tail": t, "background": b,
            "de_residual_current": dr, "corrected_current": corrected,
            "current_unit": _unit(current_unit), "correction_source": _source(correction_source),
            "source_order_preserved": True, "status": "CONDITIONAL_TRANSFORM"}


def edlc_interval_current(time_s, corrected_potential_V, *, capacitance_F, control_source):
    """Constant-C interval average I=C*delta(E_corrected)/delta(t), signed A.

    Uses supplied physical time, never nominal scan rate. Q_interval=C*delta(E)
    closes exactly under piecewise-linear E(t). This is a control-based constant-C
    model, not proof that an electrode is purely double-layer capacitive.
    """
    t, e = _array(time_s, "time_s"), _array(corrected_potential_V, "corrected_potential_V")
    _same(t, e)
    c = _scalar(capacitance_F, "capacitance_F")
    dt = _difference(t, 'time intervals')
    de = _difference(e, 'potential intervals')
    if c < 0 or not np.all(dt > 0):
        raise ValueError("nonnegative constant C and increasing physical time required")
    with np.errstate(over='ignore', invalid='ignore', divide='ignore'):
        q = _finite(c*de, "EDLC interval charge")
        i = _finite(q/dt, "EDLC interval current")
    if np.any((de != 0) & (q == 0)) and c != 0:
        raise ValueError("nonzero EDLC interval charge underflows float representation")
    if np.any((q != 0) & (i == 0)):
        raise ValueError("nonzero EDLC interval current underflows float representation")
    return {"raw_time_s": t, "raw_corrected_potential_V": e,
            "interval_current_A": i, "interval_charge_C": q,
            "interval_dt_s": dt, "capacitance_F": c,
            "control_source": _source(control_source), "status": "CONDITIONAL_CONTROL_MODEL"}
