"""
examples/ex_export.py
======================
Export a diagram to draw.io and Excalidraw for collaborative annotation editing.

The full rendered diagram is embedded as a PNG background; phase labels,
threshold labels, vline/vspan labels, and the title are added as native
editable shapes so collaborators can rename or reposition them without Python.

Run from repo root:
    python examples/ex_export.py

Output:
    output/real_log_analysis.drawio      → open in draw.io (diagrams.net)
    output/real_log_analysis.excalidraw  → import at excalidraw.com
"""

import pandas as pd
from plotsigs import Diagram

df = pd.read_csv("examples/compressor_real_data_log_1.csv")
TC = "timestamps"

d = Diagram(
    title="Compressor real log — transient analysis",
    t_end=df[TC].max(),
    xlabel="Time [s]",
    figsize=(14, 10),
)

# ── Phases ─────────────────────────────────────────────────────────────────────
ph_idle      = d.add_phase(0,    14,   "IDLE")
ph_startup   = d.add_phase(14,   19,   "STARTUP")
ph_ramp_up   = d.add_phase(19,   38.2, "RAMP UP")
ph_max       = d.add_phase(38.2, 43,   "MAX SPEED")
ph_ramp_down = d.add_phase(43,   54.4, "RAMP DOWN")
ph_steady    = d.add_phase(54.4, 70,   "STEADY")

# ── Speed group ────────────────────────────────────────────────────────────────
g_speed = d.add_group("Speed [RPM]")
g_speed.add_measured("AC_Set_Speed",                 df, time_col=TC, color="#2ecc71")
g_speed.add_measured("EC1_Compressor_Running_Speed", df, time_col=TC, color="#e74c3c")
g_speed.add_threshold(8500, label="MAX 8500", color="#c0392b")
g_speed.add_transient_analysis(
    "AC_Set_Speed", "EC1_Compressor_Running_Speed",
    tolerance_pct=5.0,
    phase=ph_startup,
    show_crosshairs=True,
)

# ── Tracking error ─────────────────────────────────────────────────────────────
g_err = d.add_group("Tracking error [RPM]")
g_err.add_derived("Error", "AC_Set_Speed", "EC1_Compressor_Running_Speed",
                  color="#8e44ad")
g_err.add_threshold(0, label="zero", ls="-", lw=0.6, color="#aaaaaa")

# ── Digital flags ──────────────────────────────────────────────────────────────
g_flags = d.add_digital_group()
g_flags.add_measured_digital("AC_Enable_Disable_Compressor", df, time_col=TC,
                              color="#2980b9")
g_flags.add_measured_digital("AcDrvrIsRunOk", df, time_col=TC, color="#27ae60")

# ── Export ─────────────────────────────────────────────────────────────────────
d.export("output/real_log_analysis.drawio")
print("  -> output/real_log_analysis.drawio")

d.export("output/real_log_analysis.excalidraw")
print("  -> output/real_log_analysis.excalidraw")

print("Done.")
