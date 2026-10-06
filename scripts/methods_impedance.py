"""Opt-in impedance methods with explicit models, weights and diagnostics.

Mathematical Z = Z' + j Z'', frequency in Hz, impedance in ohm, tau in
seconds and inductance in H. No sign correction, sorting, point exclusion,
KK certification or chemical assignment is performed. SciPy is an optional analysis dependency; plotting does not import this module.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import least_squares, lsq_linear


def _real_vector(value, name):
    if isinstance(value, (list, tuple)) and any(isinstance(v, (bool, np.bool_)) for v in value):
        raise ValueError(f"{name} cannot coerce boolean observations")
    raw = np.asarray(value)
    if raw.ndim != 1 or raw.size == 0 or raw.dtype.kind not in "iuf":
        raise ValueError(f"{name} must be a nonempty real numeric vector")
    with np.errstate(over="ignore", under="ignore"):
        result = raw.astype(float)
    if not np.all(np.isfinite(result)) or np.any((raw != 0) & (result == 0)):
        raise ValueError(f"{name} must be finite")
    return result


def _scalar(value, name, positive=False):
    raw = np.asarray(value)
    if raw.ndim or raw.dtype.kind not in "iuf" or not np.isfinite(raw):
        raise ValueError(f"{name} must be a finite real scalar")
    result = float(raw)
    if not np.isfinite(result) or raw != 0 and result == 0:
        raise ValueError(f"{name} is unrepresentable")
    if result < 0 or (positive and result == 0):
        raise ValueError(f"{name} must be {'positive' if positive else 'nonnegative'}")
    return result


def _frequency(f):
    f = _real_vector(f, "frequency_Hz")
    delta = np.diff(f)
    if np.any(f <= 0) or (f.size > 1 and not (np.all(delta > 0) or np.all(delta < 0))):
        raise ValueError("frequency must be positive and strictly monotonic; no duplicate/silent sort")
    if not np.all(np.isfinite(2 * np.pi * f)):
        raise ValueError("angular frequency is unrepresentable")
    return f


def _observations(Z, n):
    if isinstance(Z, (list, tuple)) and any(isinstance(v, (bool, np.bool_)) for v in Z):
        raise ValueError("Z cannot coerce boolean observations")
    raw = np.asarray(Z)
    if raw.shape != (n,) or raw.dtype.kind not in "iufc":
        raise ValueError("Z must be a matching real/complex numeric vector")
    with np.errstate(over="ignore", under="ignore"):
        Z = raw.astype(complex)
    if (not np.all(np.isfinite(Z)) or np.any((raw.real != 0) & (Z.real == 0))
            or np.any((raw.imag != 0) & (Z.imag == 0))):
        raise ValueError("Z must be finite; the mathematical imaginary sign is explicit")
    return Z


def _weights(Z, weighting):
    scale = float(np.median(np.abs(Z)))
    if scale <= 0 or not np.isfinite(scale):
        raise ValueError("positive representable impedance scale required")
    if isinstance(weighting, str):
        if weighting == "unit":
            weight = np.ones(len(Z))
        elif weighting == "modulus":
            if np.any(np.abs(Z) == 0):
                raise ValueError("modulus weighting is undefined at zero impedance")
            weight = scale / np.abs(Z)
        else:
            raise ValueError("weighting must be unit, modulus or explicit positive residual multipliers")
    else:
        weight = _real_vector(weighting, "residual weights")
        if weight.shape != Z.shape or np.any(weight <= 0):
            raise ValueError("positive residual weights must match Z")
    if not np.all(np.isfinite(weight)) or np.any(weight <= 0):
        raise ValueError("residual weights are unrepresentable")
    return scale, weight


def _relative_rmse(predicted, observed):
    # Normalize before squaring: norm(Z) itself can overflow or underflow
    # even when every observation and the dimensionless ratio is finite.
    scale = float(max(np.max(np.abs(observed.real)), np.max(np.abs(observed.imag))))
    with np.errstate(over="ignore", under="ignore", invalid="ignore"):
        reference = np.r_[observed.real / scale, observed.imag / scale]
        residual = np.r_[predicted.real / scale - reference[:len(observed)],
                         predicted.imag / scale - reference[len(observed):]]
        ratio = float(np.linalg.norm(residual) / np.linalg.norm(reference))
    if not np.isfinite(ratio):
        raise ValueError("relative residual is unrepresentable")
    return ratio


def rc_impedance(f, Rs, R_list, tau_list, L=0):
    """Forward series Rs, parallel Debye RC branches and optional series L."""
    f = _frequency(f)
    Rs, L = _scalar(Rs, "Rs"), _scalar(L, "L")
    R = _real_vector(R_list, "R_ohm")
    tau = _real_vector(tau_list, "tau_s")
    if len(R) != len(tau) or np.any(R < 0) or np.any(tau <= 0):
        raise ValueError("matching nonnegative resistances and positive time constants required")
    omega = 2 * np.pi * f
    with np.errstate(over="ignore", invalid="ignore"):
        omega_tau = omega[:, None] * tau
        if not np.all(np.isfinite(omega_tau)):
            raise ValueError("omega*tau is unrepresentable")
        result = Rs + 1j * omega * L + np.sum(R / (1 + 1j * omega_tau), axis=1)
    if not np.all(np.isfinite(result)):
        raise ValueError("forward impedance is unrepresentable")
    return result


def fit_rc(f, Z, n_rc=2, *, initial_guesses, bounds, weighting,
           fit_inductance=False, max_nfev=5000):
    """Fit the author-specified model; parameters Rs,R1,tau1,...[,L].

    Each start/bound is in physical units. Rs/R/tau lower bounds must be
    strictly positive; optional L lower bound may be zero. The first model
    parameters are optimized in log units and L as omega_max*L/|Z|scale.
    Returned covariance is conditional local least-squares uncertainty,
    never an independent-cell interval or proof of model identifiability.
    """
    f = _frequency(f)
    Z = _observations(Z, len(f))
    if isinstance(n_rc, bool) or not isinstance(n_rc, (int, np.integer)) or n_rc < 1:
        raise ValueError("n_rc must be a positive integer")
    if not isinstance(fit_inductance, bool):
        raise ValueError("fit_inductance must be boolean")
    size = 1 + 2 * n_rc + int(fit_inductance)
    if 2 * len(f) <= size:
        raise ValueError("insufficient observations for conditional parameter diagnostics")
    lo, hi = (_real_vector(v, "parameter bounds") for v in bounds)
    if lo.shape != (size,) or hi.shape != (size,) or np.any(lo >= hi):
        raise ValueError("finite ordered physical bounds must match the model")
    positive_count = 1 + 2 * n_rc
    if np.any(lo[:positive_count] <= 0) or (fit_inductance and lo[-1] < 0):
        raise ValueError("Rs/R/tau positive bounds and L nonnegative bounds required")
    scale, weight = _weights(Z, weighting)
    omega_max = 2 * np.pi * f.max()
    L_scale = scale / omega_max

    def encode(p):
        out = p.copy()
        out[:positive_count] = np.log(p[:positive_count])
        if fit_inductance:
            out[-1] /= L_scale
        return out

    def decode(p):
        out = p.copy()
        out[:positive_count] = np.exp(p[:positive_count])
        if fit_inductance:
            out[-1] *= L_scale
        return out

    def predict(p):
        return rc_impedance(f, p[0], p[1:positive_count:2], p[2:positive_count:2],
                            p[-1] if fit_inductance else 0)

    def residual(p):
        value = (predict(decode(p)) - Z) * weight / scale
        return np.r_[value.real, value.imag]

    def jacobian(p):
        physical = decode(p)
        omega_tau = 2j * np.pi * f[:, None] * physical[2:positive_count:2]
        response = 1 + omega_tau
        jac = np.empty((len(f), size), dtype=complex)
        jac[:, 0] = physical[0]
        jac[:, 1:positive_count:2] = physical[1:positive_count:2] / response
        jac[:, 2:positive_count:2] = -(physical[1:positive_count:2] / response) * (omega_tau / response)
        if fit_inductance:
            jac[:, -1] = 2j * np.pi * f * L_scale
        jac *= weight[:, None] / scale
        return np.vstack([jac.real, jac.imag])

    starts = list(initial_guesses)
    if not starts:
        raise ValueError("at least one explicit initialization required")
    transformed_lo, transformed_hi = encode(lo), encode(hi)
    results = []
    for start in starts:
        start = _real_vector(start, "initial guess")
        if start.shape != (size,) or np.any(start < lo) or np.any(start > hi):
            raise ValueError("initial guess lies outside physical bounds")
        result = least_squares(residual, encode(start), bounds=(transformed_lo, transformed_hi),
                               jac=jacobian, x_scale="jac", max_nfev=max_nfev,
                               ftol=1e-11, xtol=1e-11, gtol=1e-11)
        results.append((result, decode(result.x)))
    valid = [item for item in results if item[0].success]
    if not valid:
        raise ValueError("all explicitly initialized fits failed to converge")
    best, physical = min(valid, key=lambda item: item[0].cost)
    _, singular, right = np.linalg.svd(best.jac, full_matrices=False)
    rank = int(np.sum(singular > singular[0] * max(best.jac.shape) * np.finfo(float).eps))
    condition = float(singular[0] / singular[-1]) if rank == size else float("inf")
    covariance = None
    identifiability = "CONDITIONAL_LOCAL_DIAGNOSTIC"
    covariance_status = "CONDITIONAL_LOCAL_DIAGNOSTIC"
    # A full machine-precision rank alone is inadequate for a nearly
    # unidentifiable model. Never report tiny pseudo-inverse uncertainties
    # after silently truncating the weak parameter modes.
    if rank != size or condition > 1e8:
        identifiability = "HOLD_ILL_CONDITIONED"
        covariance_status = identifiability
    else:
        derivative = physical.copy()
        if fit_inductance:
            derivative[-1] = L_scale
        # Form physical standard-deviation factors before their Gram matrix;
        # never multiply a huge parameter outer product by a tiny variance.
        with np.errstate(over="ignore", under="ignore", invalid="ignore"):
            factors = (right.T / singular) * np.sqrt(2 * best.cost / (2 * len(f) - size))
            factors *= derivative[:, None]
            covariance = factors @ factors.T
        if not np.all(np.isfinite(covariance)) or best.cost > 0 and np.any(np.diag(covariance) == 0):
            covariance = None
            covariance_status = "HOLD_UNREPRESENTABLE_PHYSICAL_UNCERTAINTY"
    names = ["Rs_ohm"] + [name for k in range(1, n_rc + 1)
                          for name in (f"modelR{k}_ohm", f"tau{k}_s")]
    if fit_inductance:
        names.append("L_H")
    Z_fit = predict(physical)
    bound_hit = np.isclose(best.x, transformed_lo, rtol=0, atol=1e-5) | np.isclose(
        best.x, transformed_hi, rtol=0, atol=1e-5)
    if bound_hit.any():
        covariance = None
        covariance_status = "HOLD_BOUND_HIT"
        if identifiability != "HOLD_ILL_CONDITIONED":
            identifiability = "HOLD_BOUND_HIT"
    return {"parameter_names": names, "parameters": physical, "Rs_ohm": physical[0],
            "R_ohm": physical[1:positive_count:2], "tau_s": physical[2:positive_count:2],
            "L_H": physical[-1] if fit_inductance else 0.0, "Z_fit": Z_fit,
            "residual_ohm": Z_fit - Z, "relative_complex_rmse": _relative_rmse(Z_fit, Z),
            "jacobian_rank": rank, "jacobian_condition_log_scaled": condition,
            "identifiability": identifiability, "condition_hold_threshold": 1e8,
            "covariance_physical": covariance, "covariance_status": covariance_status, "bound_hit": bound_hit,
            "starts": [{"success": r.success, "cost": r.cost, "parameters": p,
                        "message": r.message} for r, p in results],
            "weighting": weighting, "impedance_scale_ohm": scale,
            "KK_status": "HOLD_NOT_PERFORMED", "physical_assignment": "MODEL_ELEMENTS_ONLY"}


def ln_trapezoid_weights(tau):
    """Quadrature for gamma defined per natural-log time, not per log10."""
    tau = _real_vector(tau, "tau_s")
    if len(tau) < 2 or np.any(tau <= 0) or np.any(np.diff(tau) <= 0):
        raise ValueError("tau requires at least two positive strictly increasing nodes")
    gap = np.diff(np.log(tau))
    if not np.all(np.isfinite(gap)) or np.any(gap <= 0):
        raise ValueError("distinct positive ln tau spacing must be representable")
    return np.r_[gap[0] / 2, (gap[:-1] + gap[1:]) / 2, gap[-1] / 2]


def drt_forward(f, tau, gamma, *, Rinf=0.0, L=0.0):
    """Z=Rinf+j*omega*L+integral gamma(ln tau)/(1+j*omega*tau) dln tau."""
    f = _frequency(f)
    tau, gamma = _real_vector(tau, "tau_s"), _real_vector(gamma, "gamma_ohm")
    weights = ln_trapezoid_weights(tau)
    if gamma.shape != tau.shape or np.any(gamma < 0):
        raise ValueError("this RC-only kernel requires matching nonnegative gamma")
    Rinf, L = _scalar(Rinf, "Rinf"), _scalar(L, "L")
    with np.errstate(over="ignore", invalid="ignore"):
        omega = 2 * np.pi * f
        omega_tau = omega[:, None] * tau
        if not np.all(np.isfinite(omega_tau)):
            raise ValueError("omega*tau is unrepresentable")
        result = Rinf + 1j * omega * L + (1 / (1 + 1j * omega_tau)) @ (gamma * weights)
    if not np.all(np.isfinite(result)):
        raise ValueError("DRT forward response is unrepresentable")
    return result


def drt_tikhonov(f, Z, tau, lambdas, order=2, *, weighting="modulus", fit_inductance=False):
    """Nonnegative RC diagnostic; returns every explicit lambda, selects none.

    Objective: ||W*(Zfit-Z)/Zscale||^2/(2*N) + lambda*||D*g||^2,
    g=gamma/Zscale. D=diff(order)/h**(order-0.5), h=delta ln(tau),
    approximates the derivative's squared natural-log integral on a uniform
    ln grid. Rinf and optional L are unpenalized. Lambda is dimensionless
    under this declared normalization, not interchangeable with another tool.
    """
    f = _frequency(f)
    Z = _observations(Z, len(f))
    tau = _real_vector(tau, "tau_s")
    quadrature = ln_trapezoid_weights(tau)
    if isinstance(order, bool) or not isinstance(order, (int, np.integer)) or order not in (1, 2) or len(tau) <= order:
        raise ValueError("first/second derivative and sufficient tau nodes required")
    gap = np.diff(np.log(tau))
    if not np.allclose(gap, gap[0], rtol=1e-9, atol=1e-12):
        raise ValueError("this derivative discretization requires a uniform ln tau grid")
    lambdas = _real_vector(lambdas, "lambdas")
    if np.any(lambdas <= 0) or len(np.unique(lambdas)) != len(lambdas):
        raise ValueError("explicit unique positive lambdas required")
    if not isinstance(fit_inductance, bool):
        raise ValueError("fit_inductance must be boolean")
    scale, weight = _weights(Z, weighting)
    omega = 2 * np.pi * f
    with np.errstate(over="ignore", invalid="ignore"):
        omega_tau = omega[:, None] * tau
        if not np.all(np.isfinite(omega_tau)):
            raise ValueError("omega*tau is unrepresentable")
        kernel = (1 / (1 + 1j * omega_tau)) * quadrature
    columns = [np.ones((len(f), 1)), kernel]
    if fit_inductance:
        columns.append((1j * omega / omega.max())[:, None])
    design = np.hstack(columns)
    weighted = design * weight[:, None] / np.sqrt(2 * len(f))
    A = np.vstack([weighted.real, weighted.imag])
    target = Z * weight / scale / np.sqrt(2 * len(f))
    b = np.r_[target.real, target.imag]
    derivative = np.diff(np.eye(len(tau)), n=order, axis=0) / gap[0] ** (order - 0.5)
    penalty = np.zeros((len(derivative), design.shape[1]))
    penalty[:, 1:1 + len(tau)] = derivative
    sampled_tau = [1 / omega.max(), 1 / omega.min()]
    outside = (tau < sampled_tau[0]) | (tau > sampled_tau[1])
    solutions = []
    for lam in lambdas:
        AA = np.vstack([A, np.sqrt(lam) * penalty])
        bb = np.r_[b, np.zeros(len(penalty))]
        result = lsq_linear(AA, bb, bounds=(0, np.inf), tol=1e-10, max_iter=2000)
        if not result.success:
            raise ValueError(f"DRT numerical solver failed at lambda={lam}")
        gamma = result.x[1:1 + len(tau)] * scale
        Rinf = float(result.x[0] * scale)
        L = float(result.x[-1] * scale / omega.max()) if fit_inductance else 0.0
        predicted = drt_forward(f, tau, gamma, Rinf=Rinf, L=L)
        integral = float(quadrature @ gamma)
        data_term = float(np.sum((A @ result.x - b) ** 2))
        roughness = float(np.sum((penalty @ result.x) ** 2))
        solutions.append({"lambda": float(lam), "gamma_ohm": gamma, "Rinf_ohm": Rinf,
                          "L_H": L, "Z_fit": predicted, "residual_ohm": predicted - Z,
                          "relative_complex_rmse": _relative_rmse(predicted, Z),
                          "gamma_integral_ohm": integral, "formal_dc_resistance_ohm": Rinf + integral,
                          "outside_sampled_tau_fraction": float(quadrature[outside] @ gamma[outside] / integral)
                          if integral > 0 else 0.0, "data_term": data_term,
                          "roughness": roughness, "objective": data_term + lam * roughness,
                          "solver_success": True, "iterations": result.nit})
    return {"tau_s": tau, "ln_quadrature_weights": quadrature, "solutions": solutions,
            "regularization_order": order, "ln_grid_spacing": float(gap[0]),
            "impedance_scale_ohm": scale, "weighting": weighting,
            "sampled_tau_interval_s": sampled_tau, "outside_sampled_tau_nodes": int(outside.sum()),
            "selection": "NOT_SELECTED_SENSITIVITY_ONLY", "KK_status": "HOLD_NOT_PERFORMED",
            "scientific_resolution": "NOT_CERTIFIED", "physical_assignment": "UNASSIGNED_RELAXATION"}
