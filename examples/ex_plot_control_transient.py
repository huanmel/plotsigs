"""
examples/comparison.py
=======================
Demonstrate setpoint-vs-feedback comparison annotations:

  - add_transient_analysis()  → ±5% tolerance band, cross-hair lines, overshoot, settling,
                        rise time, and steady-state annotations
  - add_derived()     → error subplot (setpoint − feedback)
  - before_t / after_t → isolate individual steps in a multi-step trace

Run from repo root:
    python examples/comparison.py
"""

import numpy as np
from plotsigs import Diagram


# ── Helpers ───────────────────────────────────────────────────────────────────

def second_order_step(t, t_step, from_val, to_val, wn=1.5, zeta=0.4):
    """Underdamped 2nd-order step response (natural overshoot ≈ 25% for zeta=0.4)."""
    wd  = wn * np.sqrt(1 - zeta**2)
    tau = np.clip(t - t_step, 0, None)
    step_size = to_val - from_val
    resp = from_val + step_size * np.where(
        t < t_step, 0,
        1 - np.exp(-zeta * wn * tau) * (
            np.cos(wd * tau) + zeta / np.sqrt(1 - zeta**2) * np.sin(wd * tau)
        ),
    )
    return resp


# ── Example 1: single step ────────────────────────────────────────────────────

T_END  = 40.0
T_STEP = 5.0
TARGET = 8500.0

t_arr = np.linspace(0, T_END, 4000)
fb_v  = second_order_step(t_arr, T_STEP, 0, TARGET)

d1 = Diagram("Speed control — single step", t_end=T_END, n_points=4000, figsize=(14, 8))

g_speed = d1.add_group("Speed [RPM]")
g_speed.add_stepped("Set Speed",     [(0, 0), (T_STEP, TARGET)], color="#2ecc71")
g_speed.add_raw(    "Running Speed", t_arr, fb_v,                color="#e74c3c")
g_speed.add_transient_analysis(
    "Set Speed", "Running Speed",
    tolerance_pct=5.0,
    after_t=T_STEP,
    show_crosshairs=True,
)

g_err = d1.add_group("Tracking error [RPM]")
g_err.add_derived("Error", "Set Speed", "Running Speed", color="#8e44ad")
g_err.add_threshold(0, label="zero", ls="-", lw=0.6, color="#aaaaaa")

d1.add_phase(0,      T_STEP, "PRE-STEP")
d1.add_phase(T_STEP, T_END,  "STEP RESPONSE")
d1.render(output="output/comparison_single.png", show=False)


# ── Example 2: multi-step trace — each step analysed independently ────────────
#
#   Setpoint ramps through three levels.  find_steps() locates the transitions
#   automatically; we then pass after_t / before_t to isolate each window.

STEPS = [(5.0, 0, 4000), (18.0, 4000, 7000), (32.0, 7000, 8500)]

t2 = np.linspace(0, 50, 5000)
# Build setpoint from steps
sp2 = np.zeros(len(t2))
for i, (ts, f, to) in enumerate(STEPS):
    sp2 = np.where(t2 < ts, sp2, to)

# Build feedback: chain of second-order responses
fb2 = np.zeros(len(t2))
for ts, f, to in STEPS:
    fb2 = np.where(t2 < ts, fb2, second_order_step(t2, ts, f, to))

# Detect step boundaries for windowing
raw_steps = [(ts, ts_next)
             for (ts, _, _), ts_next in zip(STEPS, [s[0] for s in STEPS[1:]] + [50.0])]

d2 = Diagram("Speed control — multi-step trace", t_end=50, n_points=5000, figsize=(14, 9))

g2 = d2.add_group("Speed [RPM]")
g2.add_raw("Set Speed",     t2, sp2, color="#2ecc71")
g2.add_raw("Running Speed", t2, fb2, color="#e74c3c")

for (ts, f, to), (t_after, t_before) in zip(STEPS, raw_steps):
    g2.add_transient_analysis(
        "Set Speed", "Running Speed",
        tolerance_pct=5.0,
        after_t=t_after,
        before_t=t_before,
        show_crosshairs=True,
    )

g2_err = d2.add_group("Tracking error [RPM]")
g2_err.add_derived("Error", "Set Speed", "Running Speed", color="#8e44ad")
g2_err.add_threshold(0, label="zero", ls="-", lw=0.6, color="#aaaaaa")

d2.render(output="output/comparison_multistep.png", show=True)
