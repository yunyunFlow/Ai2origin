"""Opt-in peak models and conditional GITT numerical methods.

Inputs are copied, never sorted or corrected implicitly. Peak areas mean the
integral of the normalized model over the whole real line, not a finite-window
integral. Fitting/conditional GITT diagnostics are not scientific acceptance.
Only NumPy and the already installed SciPy are used; no dependency is installed.
"""
from __future__ import annotations

import math
from numbers import Real

import numpy as np

_trapezoid = np.trapezoid if hasattr(np, "trapezoid") else np.trapz


def _number(value, name, *, positive=False, nonnegative=False):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(name + " must be an explicit finite number")
    result = float(value)
    if not math.isfinite(result) or positive and result <= 0 or nonnegative and result < 0:
        raise ValueError(name + " is outside its finite allowed range")
    return result


def _array(values, name, *, minimum=1):
    if isinstance(values, (list, tuple)) and any(isinstance(v, (bool, np.bool_)) or not isinstance(v, Real) for v in values):
        raise ValueError(name + " cannot coerce boolean/text observations")
    raw = np.asarray(values)
    if raw.ndim != 1 or raw.size < minimum or raw.dtype.kind not in "iuf":
        raise ValueError(name + " must be a one-dimensional numeric array")
    with np.errstate(over="ignore", under="ignore"):
        result = np.array(raw, dtype=float, copy=True)
    if not np.all(np.isfinite(result)):
        raise ValueError(name + " contains nonfinite data")
    if np.any((raw != 0) & (result == 0)):
        raise ValueError(name + " contains unrepresentable nonzero observations")
    return result


def _xy(x, y, reverse=False):
    if type(reverse) is not bool:
        raise ValueError("reverse_working_copy must be boolean")
    x0, y0 = _array(x, "x", minimum=4), _array(y, "y", minimum=4)
    if len(x0) != len(y0):
        raise ValueError("x and y lengths differ")
    with np.errstate(over="ignore"):
        steps = np.diff(x0)
    if not np.all(np.isfinite(steps)):
        raise ValueError("x steps are unrepresentable")
    reversed_copy = False
    if np.all(steps < 0) and reverse:
        xw, yw = x0[::-1].copy(), y0[::-1].copy()
        reversed_copy = True
    elif np.all(steps > 0):
        xw, yw = x0.copy(), y0.copy()
    else:
        raise ValueError("x must increase strictly; descending x needs explicit working-copy reversal")
    return x0, y0, xw, yw, reversed_copy


def _profile(x, center, fwhm, area, kind):
    center = _number(center, "center")
    fwhm = _number(fwhm, "fwhm", positive=True)
    area = _number(area, "area", nonnegative=True)
    factor = math.sqrt(4 * math.log(2) / math.pi) if kind == "gaussian" else 2 / math.pi
    if area == 0:
        return np.zeros_like(x)
    log_height = math.log(area) - math.log(fwhm) + math.log(factor)
    if log_height > math.log(np.finfo(float).max) or math.exp(log_height) == 0:
        raise ValueError("peak height overflow/underflow")
    # Evaluate the final intensity in log space. Squaring a large distance,
    # or multiplying an underflowed exponential by a large height, can erase
    # representable Lorentz/Gaussian tails even when the final value is finite.
    with np.errstate(over="ignore", under="ignore", invalid="ignore"):
        distance = np.abs(x - center)
    overflow = np.isinf(distance)
    scale = np.maximum(np.abs(x[overflow]), abs(center))
    with np.errstate(over="ignore", under="ignore", divide="ignore"):
        if kind == "gaussian":
            z = distance / fwhm
            z[overflow] = np.abs(x[overflow] / scale - center / scale) * (scale / fwhm)
            penalty = 4 * math.log(2) * z * z
        else:
            log_distance = np.log(distance)
            log_distance[overflow] = np.log(scale) + np.log(np.abs(x[overflow] / scale - center / scale))
            log_z = log_distance - math.log(fwhm)
            penalty = np.logaddexp(0., math.log(4.) + 2 * log_z)
        result = np.exp(log_height - penalty)
    if not np.all(np.isfinite(result)):
        raise ValueError("peak profile is unrepresentable")
    return result


def gaussian(x, center, fwhm, area):
    """Area-normalized Gaussian; fwhm uses the same physical unit as x."""
    return _profile(_array(x, "x"), center, fwhm, area, "gaussian")


def lorentzian(x, center, fwhm, area):
    """Area-normalized Lorentzian; its tails extend beyond the fitting window."""
    return _profile(_array(x, "x"), center, fwhm, area, "lorentzian")


def _bounds(value, name, *, positive=False):
    if not isinstance(value, (list, tuple, np.ndarray)) or len(value) != 2:
        raise ValueError(name + " must be an explicit [lower, upper] pair")
    low, high = (_number(v, name, positive=positive) for v in value)
    if high <= low or not math.isfinite(high - low):
        raise ValueError(name + " must have a representable increasing range")
    return low, high


def _baseline(spec, x):
    if not isinstance(spec, dict) or spec.get("kind") not in ("none", "linear_anchors", "joint_linear", "supplied"):
        raise ValueError("Declare none, linear_anchors, joint_linear or an explicit supplied baseline")
    kind = spec["kind"]
    if kind=='supplied':
        if set(spec)!={'kind','values','source'} or not isinstance(spec['source'],str) or not spec['source'].strip():
            raise ValueError('Supplied baseline needs its exact values and source')
        result=_array(spec['values'],'supplied baseline')
        if len(result)!=len(x):raise ValueError('Supplied baseline must match every working node')
        return result,False
    expected = {"kind", "anchors"} if kind == "linear_anchors" else {"kind"}
    if set(spec) != expected:
        raise ValueError("Unknown or missing baseline settings")
    if kind == "linear_anchors":
        anchors = spec["anchors"]
        if not isinstance(anchors, (list, tuple)) or len(anchors) != 2 or any(len(p) != 2 for p in anchors):
            raise ValueError("Exactly two declared linear baseline anchors are required")
        a, b = [[_number(v, "baseline anchor") for v in p] for p in anchors]
        if b[0] <= a[0] or not math.isfinite(b[0] - a[0]):
            raise ValueError("Baseline anchor coordinates must increase")
        if a[0] > x[0] or b[0] < x[-1]:
            raise ValueError("Baseline anchors must cover the fitting window; no implicit extrapolation")
        result = a[1] + (x - a[0]) / (b[0] - a[0]) * (b[1] - a[1])
    else:
        result = np.zeros_like(x)
    if not np.all(np.isfinite(result)):
        raise ValueError("Baseline overflow")
    return result, kind == "joint_linear"


def shirley_background(binding_energy_eV, intensity, *, endpoints, source,
                       reverse_working_copy=False, tolerance=1e-8, max_iterations=300,
                       damping=0.5):
    """Fixed-endpoint iterative Shirley in increasing binding-energy coordinates.

    B(E)=B_low+(B_high-B_low)*integral_low^E(Y-B)dE/integral_low^high(Y-B)dE.
    Trapezoids follow actual coordinates. No clipping, endpoint averaging,
    extrapolation, peak fitting or charge calibration. Damping is a disclosed
    numerical fixed-point step; it does not filter the input observations.
    """
    x0,y0,x,y,reversed_copy=_xy(binding_energy_eV,intensity,reverse_working_copy)
    if not isinstance(source,str) or not source.strip():raise ValueError('Shirley endpoint provenance required')
    ends=_array(endpoints,'Shirley endpoint intensities')
    if len(ends)!=2 or np.any(ends<0):raise ValueError('Declare nonnegative low/high-binding-energy endpoint intensities')
    tol=_number(tolerance,'Shirley tolerance',positive=True);mix=_number(damping,'Shirley damping',positive=True)
    if tol>=1 or mix>1 or type(max_iterations) is not int or not 1<=max_iterations<=2000:
        raise ValueError('Shirley tolerance in(0,1), damping in(0,1], iterations1..2000 required')
    scale=float(np.max(np.abs(y)))
    if scale<=0:raise ValueError('Shirley requires a nonzero intensity scale')
    yn=y/scale;lo,hi=ends/scale;bg=lo+(x-x[0])/(x[-1]-x[0])*(hi-lo)
    widths=np.diff(x);status='HOLD_SHIRLEY_NOT_CONVERGED';history=[]
    for iteration in range(max_iterations):
        net=yn-bg;terms=(net[:-1]/2+net[1:]/2)*widths
        area=math.fsum(terms)
        if not math.isfinite(area) or area<=0:raise ValueError('Shirley net area is nonpositive/unrepresentable; no zero baseline substituted')
        cumulative=np.r_[0.,np.cumsum(terms)];proposed=lo+(hi-lo)*cumulative/area
        if not np.all(np.isfinite(proposed)):raise ValueError('Shirley iteration overflow')
        error=float(np.max(np.abs(proposed-bg)));history.append(error)
        bg=(1-mix)*bg+mix*proposed;bg[0]=lo;bg[-1]=hi
        if error<=tol:status='CONDITIONAL_SHIRLEY';break
    background=bg*scale
    if not np.all(np.isfinite(background)):raise ValueError('Shirley background unrepresentable')
    original=background[::-1] if reversed_copy else background
    return {'status':status,'raw_energy_eV':x0.tolist(),'raw_intensity':y0.tolist(),
            'background_source_order':original.tolist(),'background_working':background.tolist(),
            'working_energy_eV':x.tolist(),'working_copy_reversed':reversed_copy,
            'endpoints_low_high_binding':ends.tolist(),'endpoint_source':source,
            'iterations':iteration+1,'tolerance_relative_to_max_intensity':tol,'damping':mix,
            'fixed_point_error_history':history,'raw_order_preserved':True,
            'negative_net_observation_count':int(np.count_nonzero(y-background<0)),
            'formula':'B_low+(B_high-B_low)*cumulative_integral(Y-B)/total_integral(Y-B)',
            'claim':'Conditional fixed-endpoint background only; not an inelastic-loss/depth/composition model or automatic endpoint selection.'}


def _widths(bounds, count):
    if isinstance(bounds, (list, tuple, np.ndarray)) and len(bounds) == 2 and all(isinstance(v, Real) for v in bounds):
        return [_bounds(bounds, "width_bounds", positive=True)] * count
    if not isinstance(bounds, (list, tuple)) or len(bounds) != count:
        raise ValueError("Declare one width-bound pair or one pair per peak")
    return [_bounds(v, "width_bounds", positive=True) for v in bounds]


def _fit_core(x, y, *, baseline, parameter_names, initial, lower, upper, area_indices,
              model, starts, weights):
    """Bounded multi-start least squares shared by the two declared peak models."""
    from scipy.optimize import least_squares

    if type(starts) is not int or not 3 <= starts <= 9:
        raise ValueError("starts must be an integer from 3 to 9")
    fixed, joint = _baseline(baseline, x)
    mid = x[0] / 2 + x[-1] / 2
    names, initial, lower, upper = list(parameter_names), list(initial), list(lower), list(upper)
    core_count = len(initial)
    if joint:
        slope0 = (y[-1] - y[0]) / (x[-1] - x[0])
        intercept0 = y[0] + slope0 * (mid - x[0])
        names += ["baseline_at_midpoint", "baseline_slope"]
        initial += [intercept0, slope0]
        lower += [-np.inf, -np.inf]; upper += [np.inf, np.inf]
    if len(x) <= len(initial):
        raise ValueError("More observations than fitted parameters are required")
    if weights is None:
        weights_array = np.ones_like(y)
    else:
        weights_array = _array(weights, "weights")
        if len(weights_array) != len(y) or np.any(weights_array <= 0):
            raise ValueError("weights must be positive and match every working observation")
    # Weights mean sum(weights * residual**2), not residual multipliers.
    sqrt_weights = np.sqrt(weights_array)
    initial, lower, upper = map(lambda a: np.array(a, dtype=float), (initial, lower, upper))
    if not np.all(np.isfinite(initial)):
        raise ValueError("Initial model parameters overflow")
    signal_scale = float(np.max(np.abs(y)))
    weight_scale = float(np.max(sqrt_weights))
    if signal_scale <= 0:
        raise ValueError("A nonzero fit intensity scale is required")
    parameter_scales = []
    for i in range(len(initial)):
        if i in area_indices:
            scale = abs(initial[i])
        elif np.isfinite(lower[i]) and np.isfinite(upper[i]):
            scale = upper[i] - lower[i]
        else:
            scale = signal_scale if names[i] == "baseline_at_midpoint" else signal_scale / (x[-1] - x[0])
        if not math.isfinite(scale) or scale <= 0:
            raise ValueError("Fit parameter scaling is unrepresentable")
        parameter_scales.append(scale)
    parameter_scales = np.array(parameter_scales)

    def evaluate(p):
        components = model(p[:core_count])
        bg = fixed + (p[-2] + p[-1] * (x - mid) if joint else 0)
        predicted = bg + np.sum(components, axis=0)
        if not np.all(np.isfinite(predicted)):
            raise ValueError("Predicted intensity overflow")
        return components, bg, predicted

    def objective(scaled_p):
        # Numerical parameter/intensity scaling only. Source units and the
        # declared weighted-SSE optimum remain unchanged, even at 1e-12 signal.
        residual = (evaluate(scaled_p * parameter_scales)[2] - y) / signal_scale * (sqrt_weights / weight_scale)
        if not np.all(np.isfinite(residual)):
            raise ValueError("Fit residual overflow")
        return residual

    trials, successes = [], []
    for start in range(starts):
        guess = initial.copy()
        fraction = (start + 1) / (starts + 1)
        for i in range(core_count):
            if i in area_indices:
                guess[i] *= 0.5 + fraction
            elif math.isfinite(lower[i]) and math.isfinite(upper[i]):
                guess[i] = lower[i] + fraction * (upper[i] - lower[i])
        try:
            fit = least_squares(objective, guess / parameter_scales,
                                bounds=(lower / parameter_scales, upper / parameter_scales), jac="3-point",
                                x_scale="jac", ftol=1e-11, xtol=1e-11, gtol=1e-11,
                                max_nfev=3000)
            successful = bool(fit.success and np.all(np.isfinite(fit.x)) and math.isfinite(fit.cost))
            trials.append({"start": start, "success": successful, "cost": float(fit.cost),
                           "nfev": int(fit.nfev), "parameters": (fit.x * parameter_scales).tolist()})
            if successful:
                successes.append((float(fit.cost), start, fit))
        except (ValueError, FloatingPointError, OverflowError) as exc:
            trials.append({"start": start, "success": False, "reason": str(exc)})
    if not successes:
        raise ValueError("All declared peak-model starts failed; no fit accepted")
    _, selected, fit = min(successes, key=lambda v: (v[0], v[1]))
    fitted_parameters = fit.x * parameter_scales
    components, bg, predicted = evaluate(fitted_parameters)
    jac = fit.jac
    norms = np.linalg.norm(jac, axis=0)
    scaled_jac = jac / np.where(norms > 0, norms, 1)
    singular = np.linalg.svd(scaled_jac, compute_uv=False)
    cutoff = max(scaled_jac.shape) * np.finfo(float).eps * singular[0]
    rank = int(np.count_nonzero(singular > cutoff))
    condition = float(singular[0] / singular[-1]) if singular[-1] > 0 else None
    if condition is not None and not math.isfinite(condition): condition = None
    shape_condition = condition
    # Column normalization alone hides a vanishing-amplitude component's
    # unconstrained width. Retain the dimensionless optimizer Jacobian too.
    optimizer_singular = np.linalg.svd(jac, compute_uv=False)
    optimizer_rank = int(np.count_nonzero(optimizer_singular > max(jac.shape) * np.finfo(float).eps * optimizer_singular[0]))
    optimizer_condition = float(optimizer_singular[0] / optimizer_singular[-1]) if optimizer_singular[-1] > 0 else None
    if optimizer_condition is not None and not math.isfinite(optimizer_condition): optimizer_condition = None
    rank = min(rank, optimizer_rank)
    condition = max(shape_condition, optimizer_condition) if shape_condition is not None and optimizer_condition is not None else None
    hits = []
    for i, name in enumerate(names):
        scale = upper[i] - lower[i] if np.isfinite(lower[i]) and np.isfinite(upper[i]) else abs(initial[i])
        tolerance = 1e-6 * max(scale, np.finfo(float).tiny)
        if np.isfinite(lower[i]) and fitted_parameters[i] - lower[i] <= tolerance:
            hits.append({"parameter": name, "bound": "lower"})
        if np.isfinite(upper[i]) and upper[i] - fitted_parameters[i] <= tolerance:
            hits.append({"parameter": name, "bound": "upper"})
    reasons = []
    if rank < len(fit.x): reasons.append("RANK_DEFICIENT")
    if condition is None or condition > 1e9: reasons.append("ILL_CONDITIONED")
    if hits: reasons.append("PARAMETER_BOUND_HIT")
    # No covariance/CI is advertised: a valid noise and weighting model is absent.
    normalized_sse = float(2 * fit.cost)
    log_sse = None if normalized_sse == 0 else math.log(normalized_sse) + 2 * math.log(signal_scale) + 2 * math.log(weight_scale)
    if log_sse is None:
        weighted_sse = 0.
    elif log_sse > math.log(np.finfo(float).max):
        weighted_sse = None
    else:
        weighted_sse = math.exp(log_sse)
        if weighted_sse == 0: weighted_sse = None  # Never claim a false exact zero.
    result = {"status": "MODEL_DIAGNOSTICS" if not reasons else "HOLD_MODEL",
              "accepted_numeric_fit": not reasons, "hold_reasons": reasons,
              "baseline_spec": baseline, "baseline_midpoint_x": float(mid),
              "baseline": bg.tolist(), "components": [c.tolist() for c in components],
              "fit": predicted.tolist(), "residual": (y - predicted).tolist(),
              "residual_definition": "observed minus fitted, working order",
              "parameters": dict(zip(names, fitted_parameters.tolist())), "parameter_names": names,
              "multistart": trials, "selected_start": selected,
              "weighted_sse": weighted_sse, "weighted_sse_log": log_sse,
              "normalized_sse": normalized_sse, "weight_definition": "sum(w * residual^2)",
              "optimizer_scaling": {"intensity": signal_scale, "sqrt_weight": weight_scale,
                                    "parameter_scales": dict(zip(names, parameter_scales.tolist()))},
              "weights": weights_array.tolist(), "jacobian_scaled_rank": rank,
              "parameter_count": len(fit.x), "jacobian_scaled_condition": condition,
              "jacobian_shape_condition": shape_condition, "jacobian_optimizer_scaled_condition": optimizer_condition,
              "bound_hits": hits, "uncertainty": "NOT_ESTIMATED",
              "claim": "Declared peak/linear-baseline model only; no chemical-state or population assignment."}
    return result, fitted_parameters[:core_count]


def _finish_peaks(result, x0, y0, xw, yw, reversed_copy, peak_parameters, kind):
    factor = math.sqrt(4 * math.log(2) / math.pi) if kind == "gaussian" else 2 / math.pi
    result.update(raw_x=x0.tolist(), raw_y=y0.tolist(), x_working=xw.tolist(), y_working=yw.tolist(),
                  working_copy_reversed=reversed_copy, raw_order_preserved=True,
                  source_transform="reverse paired working copy only" if reversed_copy else "none",
                  kind=kind)
    result["peaks"] = [{"center": float(center), "fwhm": float(width), "area": float(area),
                         "height": float(area / width * factor),
                         "area_definition": "whole-line integral of normalized model",
                         "area_in_window_trapezoid": float(_trapezoid(component, xw))}
                        for (center, width, area), component in zip(peak_parameters, result["components"])]
    return result


def fit_peaks(x, y, *, centers, width_bounds, baseline, kind="gaussian",
              center_bounds=None, starts=5, reverse_working_copy=False, weights=None):
    """Fit nonnegative normalized peaks with fixed declared centers by default.

    center_bounds enables explicit center fitting. weights are in source order
    and define weighted SSE; reversing a descending source reverses weights too.
    A successful optimizer with poor rank/conditioning or bound hits is HOLD.
    """
    if kind not in ("gaussian", "lorentzian"):
        raise ValueError("Only Gaussian/Lorentzian prototypes are implemented")
    x0, y0, xw, yw, reversed_copy = _xy(x, y, reverse_working_copy)
    centers = _array(centers, "centers")
    if np.any(centers < xw[0]) or np.any(centers > xw[-1]):
        raise ValueError("Every declared center must lie inside the fitting window")
    widths = _widths(width_bounds, len(centers))
    if center_bounds is not None:
        if not isinstance(center_bounds, (list, tuple)) or len(center_bounds) != len(centers):
            raise ValueError("Declare one center-bound pair per peak")
        center_bounds = [_bounds(p, "center_bounds") for p in center_bounds]
        if any(not xw[0] <= lo <= c <= hi <= xw[-1] for c, (lo, hi) in zip(centers, center_bounds)):
            raise ValueError("Center bounds must cover initial centers within the fitting window")
    bg, joint = _baseline(baseline, xw)
    if joint:
        bg = yw[0] + (xw - xw[0]) / (xw[-1] - xw[0]) * (yw[-1] - yw[0])
    # Positivity is used only to initialize areas; raw observations are not clipped.
    area_seed = float(_trapezoid(np.maximum(yw - bg, 0), xw)) / len(centers)
    if not math.isfinite(area_seed) or area_seed <= 0:
        raise ValueError("A positive representable peak-area initialization is required")
    names, initial, low, high, area_indices = [], [], [], [], []
    stride = 3 if center_bounds is not None else 2
    for i, (center, (wl, wh)) in enumerate(zip(centers, widths)):
        area_indices.append(len(initial)); names += [f"area{i + 1}", f"fwhm{i + 1}"]
        initial += [area_seed, wl / 2 + wh / 2]; low += [0, wl]; high += [np.inf, wh]
        if center_bounds is not None:
            names += [f"center{i + 1}"]; initial += [center]
            low += [center_bounds[i][0]]; high += [center_bounds[i][1]]

    def unpack(p):
        return [(p[stride * i + 2] if stride == 3 else center, p[stride * i + 1], p[stride * i])
                for i, center in enumerate(centers)]

    def model(p):
        return [_profile(xw, c, w, a, kind) for c, w, a in unpack(p)]

    if weights is not None and reversed_copy:
        weights = _array(weights, "weights")[::-1]
    result, p = _fit_core(xw, yw, baseline=baseline, parameter_names=names, initial=initial,
                         lower=low, upper=high, area_indices=area_indices, model=model,
                         starts=starts, weights=weights)
    return _finish_peaks(result, x0, y0, xw, yw, reversed_copy, unpack(p), kind)


def fit_doublet(x, y, *, center, split_eV, area_ratio, width_bounds, baseline,
                kind="gaussian", center_bounds=None, starts=5,
                reverse_working_copy=False, weights=None):
    """Constrained doublet: positive splitting, shared FWHM, fixed A_low/A_high.

    x is explicitly in eV. It is an assigned spectral model, not identification
    of spin-orbit states. Only explicit linear/no background is implemented.
    """
    if kind not in ("gaussian", "lorentzian"):
        raise ValueError("Only Gaussian/Lorentzian doublets are implemented")
    x0, y0, xw, yw, reversed_copy = _xy(x, y, reverse_working_copy)
    center = _number(center, "center")
    split = _number(split_eV, "split_eV", positive=True)
    ratio = _number(area_ratio, "area_ratio", positive=True)
    wl, wh = _bounds(width_bounds, "width_bounds", positive=True)
    if not xw[0] <= center < center + split <= xw[-1]:
        raise ValueError("Both doublet centers must lie in the fitting window")
    if ratio >= 1:
        fraction1, fraction2 = 1 / (1 + 1 / ratio), (1 / ratio) / (1 + 1 / ratio)
    else:
        fraction1, fraction2 = ratio / (1 + ratio), 1 / (1 + ratio)
    bg, joint = _baseline(baseline, xw)
    if joint: bg = yw[0] + (xw - xw[0]) / (xw[-1] - xw[0]) * (yw[-1] - yw[0])
    area_seed = float(_trapezoid(np.maximum(yw - bg, 0), xw))
    if not math.isfinite(area_seed) or area_seed <= 0:
        raise ValueError("Positive doublet-area initialization is required")
    names, initial, low, high = ["total_area", "shared_fwhm"], [area_seed, wl / 2 + wh / 2], [0, wl], [np.inf, wh]
    if center_bounds is not None:
        cl, ch = _bounds(center_bounds, "center_bounds")
        if not xw[0] <= cl <= center <= ch or ch + split > xw[-1]:
            raise ValueError("Doublet center bounds lie outside the fitting window")
        names.append("center"); initial.append(center); low.append(cl); high.append(ch)

    def unpack(p):
        c = p[2] if center_bounds is not None else center
        return [(c, p[1], p[0] * fraction1), (c + split, p[1], p[0] * fraction2)]

    def model(p):
        peaks = unpack(p)
        if p[0] and any(a == 0 for _, _, a in peaks):
            raise ValueError("Doublet component-area underflow")
        return [_profile(xw, c, w, a, kind) for c, w, a in peaks]

    if weights is not None and reversed_copy: weights = _array(weights, "weights")[::-1]
    result, p = _fit_core(xw, yw, baseline=baseline, parameter_names=names, initial=initial,
                         lower=low, upper=high, area_indices=[0], model=model,
                         starts=starts, weights=weights)
    result["constraints"] = {"split_eV": split, "area_ratio_low_over_high": ratio, "shared_fwhm": True}
    return _finish_peaks(result, x0, y0, xw, yw, reversed_copy, unpack(p), kind)


def percentT_to_A(percentT, *, allow_over_100=False):
    """A = log10(100) - log10(percentT); no clipping or discarded observations.

    Values above 100% require allow_over_100=True and produce negative A. This
    is a unit/observable conversion, not baseline, ATR or scattering correction.
    """
    if type(allow_over_100) is not bool:
        raise ValueError("allow_over_100 must be boolean")
    values = _array(percentT, "percentT")
    if np.any(values <= 0) or not allow_over_100 and np.any(values > 100):
        raise ValueError("Transmittance must be positive; >100% requires explicit allowance")
    return 2 - np.log10(values)


def xps_energy(energy, *, energy_type, photon_energy_eV=None,
               work_function_eV=None, assigned_shift_eV=None):
    """Explicit E_B=hnu-E_K-phi plus an independently assigned energy shift.

    A calibrated hnu-E_K convention is represented by an explicit phi=0.
    No C1s target, charge correction or instrument calibration is inferred.
    """
    raw = _array(energy, "energy_eV")
    shift = 0 if assigned_shift_eV is None else _number(assigned_shift_eV, "assigned_shift_eV")
    if energy_type == "kinetic":
        if np.any(raw < 0):
            raise ValueError("Kinetic energy must be nonnegative; negative binding energy is a separate convention")
        hnu = _number(photon_energy_eV, "photon_energy_eV", positive=True)
        phi = _number(work_function_eV, "work_function_eV", nonnegative=True)
        bound = hnu - raw - phi
        formula = "BE_eV = photon_energy_eV - KE_eV - declared_work_function_eV + assigned_shift_eV"
    elif energy_type == "binding":
        if photon_energy_eV is not None or work_function_eV is not None:
            raise ValueError("BE input needs no conversion photon/work-function arguments")
        hnu, phi, bound = None, None, raw.copy()
        formula = "BE_eV = supplied_BE_eV + assigned_shift_eV"
    else:
        raise ValueError("Declare binding or kinetic energy type")
    bound = bound + shift
    if not np.all(np.isfinite(bound)):
        raise ValueError("Energy conversion overflow")
    return {"raw_energy_eV": raw.tolist(), "binding_energy_eV": bound.tolist(),
            "energy_type": energy_type, "photon_energy_eV": hnu, "work_function_eV": phi,
            "assigned_shift_eV": shift, "shift_declared": assigned_shift_eV is not None,
            "formula": formula, "claim": "Explicit energy convention/assigned shift only; not an inferred charge calibration."}


def gitt_pulse(t, E, *, pulse_tau_s, pre_eq, post_eq, fit_window_s,
               equilibrium_confirmed, transient_excluded, length_m=None,
               short_time_limit=0.01, delta_es_min_V=1e-8, r2_min=0.99,
               known_iR_drop_V=None):
    """Conditional planar short-time GITT; input units s, V and m.

    length_m is an explicitly chosen V_active/A-effective characteristic length,
    not an inferred coating thickness or particle radius. delta_E_tau comes from
    the fitted E-vs-sqrt(t) slope, excluding the fitted intercept/instant jump.
    No rest-equilibrium, current constancy or geometry is inferred from a curve.
    """
    times, voltage = _array(t, "time_s", minimum=4), _array(E, "voltage_V", minimum=4)
    if len(times) != len(voltage) or np.any(np.diff(times) <= 0) or times[0] < 0:
        raise ValueError("Time/voltage must match in strictly increasing nonnegative time order")
    tau = _number(pulse_tau_s, "pulse_tau_s", positive=True)
    pre, post = _number(pre_eq, "pre_eq_V"), _number(post_eq, "post_eq_V")
    low, high = _bounds(fit_window_s, "fit_window_s", positive=True)
    limit = _number(short_time_limit, "short_time_limit", positive=True)
    minimum_delta = _number(delta_es_min_V, "delta_es_min_V", positive=True)
    r2_threshold = _number(r2_min, "r2_min")
    if not 0 <= r2_threshold <= 1 or not limit < 1:
        raise ValueError("R2 threshold must be [0,1] and short-time limit must be <1")
    if type(equilibrium_confirmed) is not bool or type(transient_excluded) is not bool:
        raise ValueError("Equilibrium/transient declarations must be booleans")
    if high > tau or low < times[0] or high > times[-1] or not np.any(times == tau):
        raise ValueError("Fit window must lie in the recorded pulse and the declared pulse endpoint must be recorded")
    length = None if length_m is None else _number(length_m, "length_m", positive=True)
    known_ir = None if known_iR_drop_V is None else _number(known_iR_drop_V, "known_iR_drop_V")
    chosen = np.flatnonzero((times >= low) & (times <= high))
    if len(chosen) < 3:
        raise ValueError("Fit window requires at least three actual source observations")
    x, y = np.sqrt(times[chosen]), voltage[chosen]
    # Centering keeps a constant iR offset out of the diffusion slope.
    xmean, ymean = float(np.mean(x)), float(np.mean(y))
    dx, dy = x - xmean, y - ymean
    denominator = float(np.dot(dx, dx))
    if not math.isfinite(denominator) or denominator <= 0:
        raise ValueError("Unresolvable sqrt(time) fit span")
    slope = float(np.dot(dx, dy) / denominator)
    intercept = ymean - slope * xmean
    predicted = intercept + slope * x
    residual = y - predicted
    delta_tau, delta_es = slope * math.sqrt(tau), post - pre
    if not all(math.isfinite(v) for v in (slope, intercept, delta_tau, delta_es)):
        raise ValueError("GITT fit/difference overflow")
    if slope != 0 and delta_tau == 0:
        raise ValueError("GITT response underflow")
    sse, sst = float(np.dot(residual, residual)), float(np.dot(dy, dy))
    if not math.isfinite(sse) or not math.isfinite(sst):
        raise ValueError("GITT residual scale overflow")
    r2 = None if sst == 0 else 1 - sse / sst
    reasons = []
    if not equilibrium_confirmed: reasons.append("EQUILIBRIUM_NOT_CONFIRMED")
    if not transient_excluded: reasons.append("IR_OR_EARLY_TRANSIENT_NOT_EXCLUDED")
    if length is None: reasons.append("MISSING_EFFECTIVE_GEOMETRY")
    if abs(delta_es) < minimum_delta: reasons.append("EQUILIBRIUM_CHANGE_TOO_SMALL")
    if delta_tau == 0: reasons.append("ZERO_DIFFUSION_RESPONSE")
    if delta_es and delta_tau and math.copysign(1., delta_es) != math.copysign(1., delta_tau):
        reasons.append("INCONSISTENT_PULSE_RESPONSE_DIRECTION")
    if r2 is None or r2 < r2_threshold: reasons.append("NONLINEAR_SQRT_TIME_WINDOW")
    candidate, dimensionless = None, None
    if delta_tau and abs(delta_es) >= minimum_delta:
        log_group = math.log(4 / math.pi) + 2 * (math.log(abs(delta_es)) - math.log(abs(delta_tau)))
        if log_group > math.log(np.finfo(float).max):
            raise ValueError("Short-time diagnostic overflow")
        dimensionless = math.exp(log_group)
        if dimensionless == 0: raise ValueError("Short-time diagnostic underflow")
        if dimensionless > limit: reasons.append("SHORT_TIME_APPROXIMATION_FAILED")
        if length is not None:
            log_d = log_group + 2 * math.log(length) - math.log(tau)
            if log_d > math.log(np.finfo(float).max): raise ValueError("Diffusivity overflow")
            candidate = math.exp(log_d)
            if candidate == 0: raise ValueError("Diffusivity underflow")
    accepted = not reasons and candidate is not None
    offset = intercept - pre
    return {"status": "CONDITIONAL_MODEL_RESULT" if accepted else "HOLD",
            "hold_reasons": reasons, "raw_t_s": times.tolist(), "raw_E_V": voltage.tolist(),
            "fit_source_indices_zero_based": chosen.tolist(), "fit_window_s": [low, high],
            "fit_sqrt_t_sqrt_s": x.tolist(), "fit_E_V": predicted.tolist(), "fit_residual_V": residual.tolist(),
            "slope_V_per_sqrt_s": slope, "intercept_V": intercept, "r2": r2,
            "delta_E_s_V": delta_es, "delta_E_tau_from_slope_V": delta_tau,
            "intercept_minus_pre_eq_V": offset, "known_iR_drop_V": known_ir,
            "intercept_minus_pre_minus_known_iR_V": None if known_ir is None else offset - known_ir,
            "offset_claim": "Intercept offset may include iR and fast kinetics; it is not an inferred Rs.",
            "pulse_tau_s": tau, "effective_length_m": length,
            "effective_length_definition": "declared active volume / effective interface area, in m",
            "equilibrium_confirmed": equilibrium_confirmed, "transient_excluded": transient_excluded,
            "short_time_tau_D_over_L_squared": dimensionless, "short_time_limit": limit,
            "delta_es_min_V": minimum_delta, "r2_min": r2_threshold,
            "D_candidate_m2_s": candidate, "D_conditional_m2_s": candidate if accepted else None,
            "formula": "D = 4/(pi*tau_s) * length_m^2 * (delta_E_s/delta_E_tau_from_slope)^2",
            "claim": "Planar short-time chemical diffusivity conditional on declared geometry, equilibrium, small perturbation and diffusion dominance; not tracer/self diffusivity or scientific acceptance."}
