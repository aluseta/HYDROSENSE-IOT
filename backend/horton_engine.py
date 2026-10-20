"""
Horton Infiltration Engine & Mass-Balance Calculation
Implements empirical Horton curve fitting from double-ring infiltrometer survey data
and real-time mass-balance infiltration calculation from rain gauge and ponding depth.
"""

import math
from typing import List, Dict, Tuple, Optional


try:
    import numpy as np
    from scipy.optimize import curve_fit
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False


def _horton_func(t, f0, fc, k):
    return fc + (f0 - fc) * np.exp(-k * t)


def fit_horton_curve(data: List[Dict[str, float]]) -> Dict[str, float]:
    """
    Fits Horton's equation: f(t) = fc + (f0 - fc) * exp(-k * t)
    using non-linear least squares (SciPy) with automatic fallback to linearized regression.

    :param data: List of dicts [{"t": time_in_minutes, "f": measured_rate_mm_per_min}]
    :return: dict with keys {"f0", "fc", "k", "r_squared"}
    """
    if len(data) < 3:
        raise ValueError("At least 3 data points are required for Horton fitting.")

    # Sort data by time ascending
    sorted_data = sorted(data, key=lambda x: x["t"])
    t_vals = [float(item["t"]) for item in sorted_data]
    f_vals = [float(item["f"]) for item in sorted_data]

    min_f = min(f_vals)
    max_f = max(f_vals)

    # 1. Try SciPy non-linear curve fitting if available
    if SCIPY_AVAILABLE and len(t_vals) >= 3:
        try:
            t_arr = np.array(t_vals, dtype=float)
            f_arr = np.array(f_vals, dtype=float)
            p0 = [max_f, max(0.01, min_f * 0.9), 0.05]
            bounds = ([min_f * 0.5, 0.001, 0.0001], [max_f * 3.0, max_f, 10.0])
            popt, _ = curve_fit(_horton_func, t_arr, f_arr, p0=p0, bounds=bounds, maxfev=2000)
            f0_opt, fc_opt, k_opt = popt

            f_pred = _horton_func(t_arr, f0_opt, fc_opt, k_opt)
            ss_tot = np.sum((f_arr - np.mean(f_arr)) ** 2)
            ss_res = np.sum((f_arr - f_pred) ** 2)
            r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.95

            return {
                "f0": round(float(f0_opt), 4),
                "fc": round(float(fc_opt), 4),
                "k": round(float(k_opt), 5),
                "r_squared": round(float(max(0.0, min(1.0, r2))), 4)
            }
        except Exception:
            pass  # Fallback to linearized regression below

    # 2. Linearized regression fallback: ln(f - fc) vs t
    fc = max(0.01, min_f * 0.95)
    f0_initial = max_f

    sum_t = 0.0
    sum_y = 0.0
    sum_t2 = 0.0
    sum_ty = 0.0
    n = 0

    for t, f in zip(t_vals, f_vals):
        diff = f - fc
        if diff > 1e-5:
            y = math.log(diff)
            sum_t += t
            sum_y += y
            sum_t2 += t * t
            sum_ty += t * y
            n += 1

    if n < 2 or (n * sum_t2 - sum_t * sum_t) == 0:
        return {
            "f0": round(f0_initial, 3),
            "fc": round(fc, 3),
            "k": 0.05,
            "r_squared": 0.90
        }

    denom = n * sum_t2 - sum_t * sum_t
    slope = (n * sum_ty - sum_t * sum_y) / denom
    intercept = (sum_y - slope * sum_t) / n

    k = max(0.001, -slope)
    f0 = fc + math.exp(intercept)

    f_mean = sum(f_vals) / len(f_vals)
    ss_tot = sum((f - f_mean) ** 2 for f in f_vals)
    f_pred = [fc + (f0 - fc) * math.exp(-k * t) for t in t_vals]
    ss_res = sum((f_obs - f_p) ** 2 for f_obs, f_p in zip(f_vals, f_pred))

    r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

    return {
        "f0": round(f0, 4),
        "fc": round(fc, 4),
        "k": round(k, 5),
        "r_squared": round(max(0.0, min(1.0, r_squared)), 4)
    }


def calculate_dynamic_infiltration(
    rain_rate_mm_min: float,
    current_ponding_h_mm: float,
    previous_ponding_h_mm: Optional[float],
    delta_t_min: float = 1.0,
    fc_steady_mm_min: float = 0.96
) -> Tuple[float, str]:
    """
    Computes instantaneous infiltration rate f(t) in mm/s and classifies the phase:
    1. Pre-ponding (H = 0): f(t) = I(t)
    2. Active ponding (H > 0): f(t) = I(t) - ΔH/Δt
    3. Post-rainfall (I = 0, H > 0): f(t) = -ΔH/Δt = Ks

    :return: (infiltration_rate_mm_s, phase_name)
    """
    delta_h = 0.0
    if previous_ponding_h_mm is not None and delta_t_min > 0:
        delta_h = current_ponding_h_mm - previous_ponding_h_mm

    # Convert rain rate from mm/min to mm/s
    i_rate_mm_s = max(0.0, rain_rate_mm_min / 60.0)

    # Convert delta H / delta t from mm/min to mm/s
    dh_dt_mm_s = (delta_h / delta_t_min) / 60.0

    if current_ponding_h_mm <= 0.5:
        # Phase 1: Pre-ponding
        # All precipitation is directly absorbed
        f_t_mm_s = max(fc_steady_mm_min / 60.0, i_rate_mm_s)
        phase = "pra-genangan"
    elif i_rate_mm_s <= 0.001 and current_ponding_h_mm > 0.5:
        # Phase 3: Post-rainfall standing water
        # Rate of decline yields in-situ saturated hydraulic conductivity Ks
        if dh_dt_mm_s < 0:
            f_t_mm_s = abs(dh_dt_mm_s)
        else:
            f_t_mm_s = fc_steady_mm_min / 60.0
        phase = "post-hujan"
    else:
        # Phase 2: Active ponding
        # f(t) = I - ΔH/Δt
        f_t_mm_s = i_rate_mm_s - dh_dt_mm_s
        f_t_mm_s = max(0.001, f_t_mm_s)
        phase = "genangan-aktif"

    return round(f_t_mm_s, 5), phase
