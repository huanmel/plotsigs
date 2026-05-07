"""
examples/ex_plot_csv_analysis.py
=================================
Extends ex_plot_from_csv.py with control-system transient analysis.

The setpoint (AC_Set_Speed) is rate-limited, so analysis is applied only
to windows where the setpoint has reached its flat target value:

  Window A  t=1..10   step 0 -> 1075 RPM  (IDLE phase)
  Window B  t=37..46  step -> 4750 RPM    (STEADY phase, second step)

Annotations added:
  - ±5% tolerance band around the setpoint in each window
  - Settling time, rise time, overshoot (if any)
  - MATLAB-style cross-hair dashed lines for each characteristic
  - Tracking error subplot (AC_Set_Speed - Compressor_Running_Speed)

Run from repo root:
    python examples/ex_plot_csv_analysis.py
"""

import pandas as pd
from plotsigs import Diagram

df = pd.read_csv("examples/compressor_sim_data.csv")

d = Diagram(
    title="Compressor Speed Control — transient analysis",
    t_end=df["time"].max(),
    xlabel="Time [s]",
    figsize=(14, 10),
)

# ── Group 0: speed signals + comparison overlays ───────────────────────────────
g_speed = d.add_group("Speed [RPM]")
g_speed.add_measured("AC_Set_Speed",             df, color="#2ecc71")
g_speed.add_measured("Compressor_Running_Speed", df, color="#e74c3c")
g_speed.add_threshold(800, label="MIN 800", color="#3498db")
g_speed.add_threshold(8500, label="MAX 8500", color="#e74c3c")

# Window A: initial step up to 1075 RPM — flat setpoint t=1..10
g_speed.add_transient_analysis(
    "AC_Set_Speed", "Compressor_Running_Speed",
    tolerance_pct=5.0,
    after_t=1.0,
    before_t=10.0,
    show_crosshairs=True,
)

# Window B: step up to 4750 RPM — flat setpoint t=37..46
g_speed.add_transient_analysis(
    "AC_Set_Speed", "Compressor_Running_Speed",
    tolerance_pct=5.0,
    after_t=37.0,
    before_t=46.0,
    show_crosshairs=True,
    settling_color="#1abc9c",
    overshoot_color="#e67e22",
    rise_time_color="#2980b9",
)

# ── Group 1: tracking error ────────────────────────────────────────────────────
g_err = d.add_group("Tracking error [RPM]")
g_err.add_derived("Error", "AC_Set_Speed", "Compressor_Running_Speed", color="#8e44ad")
g_err.add_threshold(0, label="zero", ls="-", lw=0.6, color="#aaaaaa")

# ── Group 2: digital flags ─────────────────────────────────────────────────────
g_flags = d.add_digital_group()
g_flags.add_measured_digital("AC_Enable",       df, color="#2980b9")
g_flags.add_measured_digital("DrvrOut_IsRunOk", df, color="#27ae60")
g_flags.add_measured_digital("DrvrOut_IsFault", df, color="#c0392b")

# ── Phase labels ───────────────────────────────────────────────────────────────
d.add_phase(0,  10, "IDLE")
d.add_phase(10, 22, "RAMP")
d.add_phase(22, 47, "STEADY")
d.add_phase(47, 61, "SHUTDOWN")

# ── Render ─────────────────────────────────────────────────────────────────────
d.render(
    output="output/plot_csv_analysis.png",
    show=True,
)
