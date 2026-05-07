"""
examples/ex_plot_csv_analysis_sim.py
======================================
Transient analysis on simulated compressor CSV data using phase-first workflow.

Phases defined upfront; transient analyses reference phase objects directly:

  IDLE            t=0..10    step 0 -> 1075 RPM  (after_t=1 — setpoint settled)
  COOLING MIN 1   t=10..22   ramp to low-speed cooling
  COOLING ACTIVE 1 t=22..37  high-speed active cooling
  COOLING MIN 2   t=37..47   step -> 4750 RPM  (second analysis window)
  SHUTDOWN        t=47..61   speed ramps down

Annotations:
  - ±5% tolerance band around the setpoint in each analysis window
  - Settling time, rise time, overshoot crosshairs
  - Tracking error subplot

Run from repo root:
    python examples/ex_plot_csv_analysis_sim.py
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

# ── Phase labels (defined first so analyses can reference them) ────────────────
ph_idle         = d.add_phase(0,  1, "IDLE")
ph_cool_min1    = d.add_phase(1, 11, "COOLING MIN 1")
ph_cool_active1 = d.add_phase(11, 47, "COOLING ACTIVE 1")
ph_cool_min2    = d.add_phase(47, 56, "COOLING MIN 2")
ph_shutdown     = d.add_phase(56, 61, "SHUTDOWN")

# ── Group 0: speed signals + transient analysis overlays ──────────────────────
g_speed = d.add_group("Speed [RPM]")
g_speed.add_measured("AC_Set_Speed",             df, color="#2ecc71")
g_speed.add_measured("Compressor_Running_Speed", df, color="#e74c3c")
g_speed.add_threshold(100,  label="RUN DETECT THD 100",  color="#3498db")
g_speed.add_threshold(800,  label="MIN 800",  color="#3498db")
g_speed.add_threshold(8500, label="MAX 8500", color="#e74c3c")

# IDLE: step 0 -> 1075 RPM; setpoint rate-limited, flat from t=1
g_speed.add_transient_analysis(
    "AC_Set_Speed", "Compressor_Running_Speed",
    tolerance_pct=5.0,
    phase=ph_cool_min1,
    after_t=1.0,        # setpoint has settled by t=1 within the IDLE phase
    show_crosshairs=True,
)

# COOLING MIN 2: step -> 4750 RPM at phase start (t=37)
g_speed.add_transient_analysis(
    "AC_Set_Speed", "Compressor_Running_Speed",
    tolerance_pct=5.0,
    phase=ph_cool_min2,
    show_crosshairs=True,
    settling_color="#1abc9c",
    overshoot_color="#e67e22",
    rise_time_color="#2980b9",
)

# ── Group 1: tracking error ────────────────────────────────────────────────────
g_err = d.add_group("Tracking error [RPM]")
g_err.add_derived("Error", "AC_Set_Speed", "Compressor_Running_Speed", color="#8e44ad")
g_err.add_threshold(0, label="zero", ls="-", lw=0.6, color="#aaaaaa")
g_err.add_threshold(100, label="RUN THRESHOLD 100", ls="-", lw=0.6, color="#e71b1b")
g_err.add_threshold(-100, label="RUN THRESHOLD -100", ls="-", lw=0.6, color="#e71b1b")

# ── Group 2: digital flags ─────────────────────────────────────────────────────
g_flags = d.add_digital_group()
g_flags.add_measured_digital("AC_Enable",       df, color="#2980b9")
g_flags.add_measured_digital("DrvrOut_IsRunOk", df, color="#27ae60")

# Duration: error < 100 RPM  →  DrvrOut_IsRunOk rising edge  (COOLING MIN 1 only)
g_flags.add_event_duration(
    "Error",    100,           # event A: tracking error drops below 100 RPM
    "DrvrOut_IsRunOk",         # event B: run-OK flag goes HIGH
    direction_a="below",
    edge_b="rise",
    phase=ph_cool_min1,
    color="#e74c3c",
    y_pos=0.65,
)

g_flags.add_event_duration(
    "Compressor_Running_Speed",    100,           # event A: tracking error drops below 100 RPM
    "DrvrOut_IsRunOk",         # event B: run-OK flag goes HIGH
    direction_a="below",
    edge_b="fall",
    phase=ph_shutdown,
    color="#e74c3c",
    y_pos=0.65,
)

# ── Render ─────────────────────────────────────────────────────────────────────
d.render(
    output="output/plot_csv_analysis_sim.png",
    show=True,
)
