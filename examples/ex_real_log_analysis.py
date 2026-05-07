"""
examples/ex_real_log_analysis.py
==================================
Transient analysis of a real compressor log.

CSV columns
-----------
  timestamps                      time axis
  EC1_Compressor_Running_Speed    measured speed feedback [RPM]
  AC_Set_Speed                    speed setpoint [RPM]
  AC_Enable_Disable_Compressor    digital — compressor enable command
  AcDrvrIsRunOk                   digital — drive OK status

Sequence in the log
-------------------
  IDLE (0..14 s)      : compressor off, all signals at 0
  STARTUP (14..19 s)  : step command to 1075 RPM — real startup transient
                        (overshoot ~60%, settling ~3.4 s)
  RAMP UP (19..38 s)  : rate-limited ramp to 8500 RPM
  MAX SPEED (38..43 s): steady run at 8500 RPM
  RAMP DOWN (43..52 s): rate-limited ramp down through a deceleration reversal
  RAMP TO 3550 (52..54 s): step-ramp to 3550 RPM target
  STEADY (54..70 s)   : steady run at 3550 RPM

Run from repo root:
    python examples/ex_real_log_analysis.py
"""

import pandas as pd
from plotsigs import Diagram

df = pd.read_csv("examples/compressor_real_data_log_1.csv")

TC = "timestamps"          # time column name in this CSV

d = Diagram(
    title="Compressor real log — transient analysis",
    t_end=df[TC].max(),
    xlabel="Time [s]",
    figsize=(14, 10),
)

# ── Phase labels — define first so analysis can reference them ─────────────────
ph_idle      = d.add_phase(0,    14,   "IDLE")
ph_startup   = d.add_phase(14,   19,   "STARTUP")
ph_ramp_up   = d.add_phase(19,   38.2, "RAMP UP")
ph_max       = d.add_phase(38.2, 43,   "MAX SPEED")
ph_ramp_down = d.add_phase(43,   54.4, "RAMP DOWN")
ph_steady    = d.add_phase(54.4, 70,   "STEADY")

# ── Group 0: speed signals + startup comparison ────────────────────────────────
g_speed = d.add_group("Speed [RPM]")
g_speed.add_measured("AC_Set_Speed",                df, time_col=TC, color="#2ecc71")
g_speed.add_measured("EC1_Compressor_Running_Speed", df, time_col=TC, color="#e74c3c")
g_speed.add_threshold(8500, label="MAX 8500", color="#c0392b")

# Startup step analysis: setpoint is flat at 1075 RPM during STARTUP phase.
# Real hardware shows ~60% overshoot and ~3.4 s settling (5% band).
g_speed.add_transient_analysis(
    "AC_Set_Speed", "EC1_Compressor_Running_Speed",
    tolerance_pct=5.0,
    phase=ph_startup,        # time window taken from the STARTUP phase
    show_crosshairs=True,
)

# ── Group 1: tracking error ────────────────────────────────────────────────────
g_err = d.add_group("Tracking error [RPM]")
g_err.add_derived(
    "Error",
    "AC_Set_Speed",
    "EC1_Compressor_Running_Speed",
    color="#8e44ad",
)
g_err.add_threshold(0, label="zero", ls="-", lw=0.6, color="#aaaaaa")

# ── Group 2: digital flags ─────────────────────────────────────────────────────
g_flags = d.add_digital_group()
g_flags.add_measured_digital("AC_Enable_Disable_Compressor", df, time_col=TC, color="#2980b9")
g_flags.add_measured_digital("AcDrvrIsRunOk",                df, time_col=TC, color="#27ae60")

# ── Render ─────────────────────────────────────────────────────────────────────
d.render(
    output="output/real_log_analysis.png",
    show=True,
)
