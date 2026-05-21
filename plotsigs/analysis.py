"""
Signal analysis utilities — pure numpy, no matplotlib.

All functions operate on evaluated arrays (not Signal objects) so they can be
called from tests or notebooks without a Diagram or renderer.
"""
from __future__ import annotations

import numpy as np
from typing import Optional, List


# ── Internal helpers ──────────────────────────────────────────────────────────

def _window(t: np.ndarray,
            after_t: Optional[float],
            before_t: Optional[float]) -> np.ndarray:
    """Boolean mask selecting t in [after_t, before_t]."""
    mask = np.ones(len(t), dtype=bool)
    if after_t  is not None: mask &= t >= after_t
    if before_t is not None: mask &= t <= before_t
    return mask


# ── Step characteristic functions ─────────────────────────────────────────────

def settling_time(
    t: np.ndarray,
    setpoint: np.ndarray,
    feedback: np.ndarray,
    threshold_pct: float = 2.0,
    after_t:  Optional[float] = None,
    before_t: Optional[float] = None,
    threshold_abs: Optional[float] = None,
) -> Optional[float]:
    """
    First time feedback enters and stays within the tolerance band of the final
    setpoint value.  Default 2% matches MATLAB stepinfo() SettlingTimeThreshold.

    'Stays within' means it never leaves the band again inside the window.
    Returns None if settling never occurs.

    Parameters
    ----------
    threshold_pct
        Half-width of the band as % of final setpoint (used when threshold_abs is None).
    threshold_abs
        Half-width of the band in absolute engineering units.  Takes precedence
        over threshold_pct when set.
    after_t / before_t
        Analysis window — useful for isolating one step in multi-step data.
    """
    mask = _window(t, after_t, before_t)
    sp, fb, tm = setpoint[mask], feedback[mask], t[mask]
    if len(sp) == 0:
        return None

    ss = float(sp[-1])   # steady-state (final setpoint value), matches MATLAB
    if threshold_abs is not None:
        out_idx = np.where(np.abs(fb - ss) > threshold_abs)[0]
    else:
        with np.errstate(divide="ignore", invalid="ignore"):
            err_pct = np.where(ss != 0, np.abs((fb - ss) / ss) * 100.0, 0.0)
        out_idx = np.where(err_pct > threshold_pct)[0]
    if len(out_idx) == 0:
        return float(tm[0])       # always in band from the start
    last_out = out_idx[-1]
    if last_out + 1 >= len(tm):
        return None               # never settles
    return float(tm[last_out + 1])


def overshoot(
    t: np.ndarray,
    setpoint: np.ndarray,
    feedback: np.ndarray,
    after_t:  Optional[float] = None,
    before_t: Optional[float] = None,
) -> Optional[dict]:
    """
    Peak overshoot of feedback relative to a stepped setpoint.

    Uses ``fb[0]`` (feedback at window start) as the step baseline so the
    function works correctly when ``after_t`` is placed at or after the step
    moment (where the setpoint is already at its final value).

    Returns
    -------
    None if no overshoot, otherwise::

        {"t_peak": float, "value": float, "pct": float, "step_end": float}

    where ``pct = |peak − step_end| / |step_size| * 100``.
    """
    mask = _window(t, after_t, before_t)
    sp, fb, tm = setpoint[mask], feedback[mask], t[mask]
    if len(sp) == 0:
        return None

    step_end   = float(sp[-1])
    step_start = float(fb[0])   # feedback baseline at window start
    step_size  = step_end - step_start
    if abs(step_size) < 1e-9:
        return None

    if step_size > 0:
        idx_peak = int(np.argmax(fb))
        if fb[idx_peak] <= step_end:
            return None
    else:
        idx_peak = int(np.argmin(fb))
        if fb[idx_peak] >= step_end:
            return None

    pct = abs(fb[idx_peak] - step_end) / abs(step_size) * 100.0
    return {
        "t_peak":     float(tm[idx_peak]),
        "value":      float(fb[idx_peak]),
        "pct":        float(pct),
        "step_end":   step_end,
        "step_start": step_start,
    }


def rise_time(
    t: np.ndarray,
    setpoint: np.ndarray,
    feedback: np.ndarray,
    low_pct:  float = 10.0,
    high_pct: float = 90.0,
    after_t:  Optional[float] = None,
    before_t: Optional[float] = None,
) -> Optional[dict]:
    """
    Rise time: elapsed time for feedback to go from ``low_pct%`` to ``high_pct%``
    of the step height (measured from ``fb[0]`` to ``setpoint[-1]``).

    Returns
    -------
    None if either crossing is not found, otherwise::

        {"t_lo": float, "t_hi": float, "duration": float,
         "v_lo": float, "v_hi": float}
    """
    mask = _window(t, after_t, before_t)
    sp, fb, tm = setpoint[mask], feedback[mask], t[mask]
    if len(sp) == 0:
        return None

    step_end   = float(sp[-1])
    step_start = float(fb[0])
    step_size  = step_end - step_start
    if abs(step_size) < 1e-9:
        return None

    v_lo = step_start + step_size * low_pct  / 100.0
    v_hi = step_start + step_size * high_pct / 100.0

    if step_size > 0:
        cross_lo = np.where(fb >= v_lo)[0]
        cross_hi = np.where(fb >= v_hi)[0]
    else:
        cross_lo = np.where(fb <= v_lo)[0]
        cross_hi = np.where(fb <= v_hi)[0]

    if len(cross_lo) == 0 or len(cross_hi) == 0:
        return None

    idx_lo = int(cross_lo[0])
    idx_hi = int(cross_hi[0])
    if idx_lo >= idx_hi:
        return None

    return {
        "t_lo":     float(tm[idx_lo]),
        "t_hi":     float(tm[idx_hi]),
        "duration": float(tm[idx_hi] - tm[idx_lo]),
        "v_lo":     float(v_lo),
        "v_hi":     float(v_hi),
    }


def stepinfo(
    t: np.ndarray,
    setpoint: np.ndarray,
    feedback: np.ndarray,
    settling_threshold_pct: float = 2.0,
    rise_time_limits: tuple = (10.0, 90.0),
    after_t:  Optional[float] = None,
    before_t: Optional[float] = None,
) -> dict:
    """
    Compute step-response characteristics in one call, matching MATLAB stepinfo().

    Parameters
    ----------
    settling_threshold_pct
        Band for settling time (default 2%, same as MATLAB SettlingTimeThreshold=0.02).
    rise_time_limits
        (low%, high%) for rise time (default (10, 90), same as MATLAB RiseTimeLimits=[0.1 0.9]).

    Returns
    -------
    dict with keys (None when not applicable):

        RiseTime        — time for fb to go from low% to high% of step height
        SettlingTime    — duration until fb stays within ±threshold% of final value
        SettlingMin     — min fb after it first crosses the upper rise threshold
        SettlingMax     — max fb after it first crosses the upper rise threshold
        Overshoot       — peak exceedance above final value as % of step size
        Undershoot      — peak exceedance below initial value as % of step size (step-down)
        Peak            — absolute peak fb value
        PeakTime        — time of peak fb value
        SteadyStateValue — final setpoint value (sp[-1] in window)
    """
    mask = _window(t, after_t, before_t)
    sp, fb, tm = setpoint[mask], feedback[mask], t[mask]
    t_origin = float(tm[0])

    ss         = float(sp[-1])
    step_start = float(fb[0])
    step_size  = ss - step_start

    result: dict = {
        "RiseTime":        None,
        "SettlingTime":    None,
        "SettlingMin":     None,
        "SettlingMax":     None,
        "Overshoot":       None,
        "Undershoot":      None,
        "Peak":            None,
        "PeakTime":        None,
        "SteadyStateValue": ss,
    }

    if len(tm) == 0 or abs(step_size) < 1e-9:
        return result

    # Rise time
    rt = rise_time(t, setpoint, feedback,
                   low_pct=rise_time_limits[0], high_pct=rise_time_limits[1],
                   after_t=after_t, before_t=before_t)
    if rt is not None:
        result["RiseTime"] = rt["duration"]
        # SettlingMin/Max: extremes of fb after it crosses the upper rise threshold
        upper_v = step_start + step_size * rise_time_limits[1] / 100.0
        if step_size > 0:
            post_idx = np.where(fb >= upper_v)[0]
        else:
            post_idx = np.where(fb <= upper_v)[0]
        if len(post_idx):
            post_fb = fb[post_idx[0]:]
            result["SettlingMin"] = float(post_fb.min())
            result["SettlingMax"] = float(post_fb.max())

    # Settling time (returned as duration from after_t / window start)
    ts = settling_time(t, setpoint, feedback,
                       threshold_pct=settling_threshold_pct,
                       after_t=after_t, before_t=before_t)
    if ts is not None:
        result["SettlingTime"] = ts - t_origin

    # Peak and overshoot
    if step_size > 0:
        idx_peak = int(np.argmax(fb))
    else:
        idx_peak = int(np.argmin(fb))
    result["Peak"]     = float(fb[idx_peak])
    result["PeakTime"] = float(tm[idx_peak]) - t_origin

    if step_size > 0 and fb[idx_peak] > ss:
        result["Overshoot"] = abs(fb[idx_peak] - ss) / abs(step_size) * 100.0
    elif step_size < 0 and fb[idx_peak] < ss:
        result["Overshoot"] = abs(fb[idx_peak] - ss) / abs(step_size) * 100.0

    # Undershoot: exceedance below the initial value (opposite direction of step)
    if step_size > 0:
        undershoot_idx = np.where(fb < step_start)[0]
        if len(undershoot_idx):
            result["Undershoot"] = abs(fb[undershoot_idx].min() - step_start) / abs(step_size) * 100.0
    else:
        undershoot_idx = np.where(fb > step_start)[0]
        if len(undershoot_idx):
            result["Undershoot"] = abs(fb[undershoot_idx].max() - step_start) / abs(step_size) * 100.0

    return result


def find_steps(
    t: np.ndarray,
    setpoint: np.ndarray,
    min_step_pct: float = 5.0,
) -> List[dict]:
    """
    Detect step changes in a setpoint signal.

    Useful for multi-step traces: call ``add_transient_analysis()`` once per returned
    step using ``after_t`` / ``before_t`` to isolate each window.

    Parameters
    ----------
    min_step_pct
        Minimum step size as % of the signal's peak-to-peak range.

    Returns
    -------
    List of dicts sorted by time::

        [{"t": float, "from_val": float, "to_val": float, "size": float}, ...]
    """
    sp    = np.asarray(setpoint, dtype=float)
    diffs = np.diff(sp)
    ptp   = float(np.ptp(sp))
    if ptp < 1e-9:
        return []

    threshold = ptp * min_step_pct / 100.0
    step_idx  = np.where(np.abs(diffs) >= threshold)[0]
    if len(step_idx) == 0:
        return []

    # Merge consecutive indices belonging to the same transition
    groups: list = [[step_idx[0]]]
    for i in step_idx[1:]:
        if i == groups[-1][-1] + 1:
            groups[-1].append(i)
        else:
            groups.append([i])

    steps = []
    for grp in groups:
        i0 = grp[0]
        i1 = grp[-1] + 1
        if i1 >= len(sp):
            continue
        steps.append({
            "t":        float(t[i1]),
            "from_val": float(sp[i0]),
            "to_val":   float(sp[i1]),
            "size":     float(sp[i1] - sp[i0]),
        })
    return steps


# ── Event detection ───────────────────────────────────────────────────────────

def find_crossing(
    t: np.ndarray,
    y: np.ndarray,
    threshold: float,
    direction: str = "below",
    after_t:  Optional[float] = None,
    before_t: Optional[float] = None,
) -> Optional[float]:
    """
    First time y crosses threshold in the given direction.

    Parameters
    ----------
    direction : "below" — y drops at or below threshold;
                "above" — y rises at or above threshold
    """
    mask = _window(t, after_t, before_t)
    tm, ym = t[mask], y[mask]
    if len(tm) == 0:
        return None
    idx = np.where(ym <= threshold)[0] if direction == "below" \
          else np.where(ym >= threshold)[0]
    return float(tm[idx[0]]) if len(idx) > 0 else None


def find_edge(
    t: np.ndarray,
    y: np.ndarray,
    edge: str = "rise",
    after_t:  Optional[float] = None,
    before_t: Optional[float] = None,
) -> Optional[float]:
    """
    First rising or falling edge of a binary (0/1) signal.

    Parameters
    ----------
    edge : "rise" — 0→1 transition; "fall" — 1→0 transition
    """
    mask = _window(t, after_t, before_t)
    tm, ym = t[mask], y[mask]
    if len(tm) < 2:
        return None
    diffs = np.diff(ym.astype(float))
    idx = np.where(diffs > 0.5)[0] if edge == "rise" \
          else np.where(diffs < -0.5)[0]
    return float(tm[idx[0] + 1]) if len(idx) > 0 else None


# ── Scalar utilities ──────────────────────────────────────────────────────────

def error_signal(setpoint: np.ndarray, feedback: np.ndarray) -> np.ndarray:
    """Element-wise error: setpoint − feedback."""
    return setpoint - feedback


def error_pct(setpoint: np.ndarray, feedback: np.ndarray) -> np.ndarray:
    """Element-wise relative error in percent: (setpoint − feedback) / |setpoint| × 100."""
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(setpoint != 0,
                        (setpoint - feedback) / np.abs(setpoint) * 100.0,
                        0.0)
