"""
examples/from_csv.py
====================
Plot signals loaded from a measured-data CSV file using multiple subplots.

Run from repo root:
    python examples/from_csv.py
"""

import pandas as pd
from plotsigs import Diagram

df = pd.read_csv("examples/compressor_sim_data.csv")

d = Diagram(
    title="Compressor Speed Control — measured data",
    t_end=df["time"].max(),
    xlabel="Time [s]",
    figsize=(14, 9),
)

# ── Group 0: speed signals ─────────────────────────────────────────────────────
g_speed = d.add_group("Speed [RPM]")
g_speed.add_measured("AC_Set_Speed",             df, color="#2ecc71")
g_speed.add_measured("Compressor_Running_Speed", df, color="#e74c3c")
g_speed.add_threshold(800, label="MIN 800", color="#3498db")
g_speed.add_threshold(8500, label="MAX 8500", color="#e74c3c")

# ── Group 1: digital flags (interleaved between analog groups) ─────────────────
g_flags = d.add_digital_group()
g_flags.add_measured_digital("AC_Enable",       df, color="#2980b9")
g_flags.add_measured_digital("DrvrOut_IsRunOk", df, color="#27ae60")
g_flags.add_measured_digital("DrvrOut_IsFault", df, color="#c0392b")
g_flags.add_measured_digital("IsActVld",        df, color="#8e44ad")

# ── Group 2: temperature & voltage ────────────────────────────────────────────
g_env = d.add_group("Board [°C] / Bus [V]")
g_env.add_measured("Board_Temp",     df, color="#e67e22")
g_env.add_measured("DC_Bus_Voltage", df, color="#8e44ad")

# ── Phase labels ───────────────────────────────────────────────────────────────
d.add_phase(0,  10, "IDLE")
d.add_phase(10, 22, "RAMP")
d.add_phase(22, 47, "STEADY")
d.add_phase(47, 61, "SHUTDOWN")

# ── Render ─────────────────────────────────────────────────────────────────────
d.render(
    output="output/plot_from_csv.png",
    show=True,
)
