"""
examples/ex_enum_phases.py
==========================
Demonstrate:
  • EnumeratedSignal  — state-machine panel with horizontal guides and
                        zoom-reactive midpoint labels (pan/zoom to see them)
  • Phase pass/fail   — status="pass" → green, status="fail" → red + × marker
  • Nav buttons       — ◄ Prev / Next ► appear at the bottom in interactive mode

Run from repo root:
    python examples/ex_enum_phases.py
"""

import numpy as np
from plotsigs import Diagram

# ── Synthetic timeline ─────────────────────────────────────────────────────────
t    = np.linspace(0, 400, 8001)
dt   = t[1] - t[0]

# Thermal mode enum (integer codes 0–6)
MODE_OFF        = 0
MODE_INIT       = 1
MODE_HEAT       = 2
MODE_CIRC       = 3
MODE_COOL_MIN   = 4
MODE_COOL_ACT   = 5
MODE_COOL_SETUP = 6

mode_labels = {
    MODE_OFF:        "OFF",
    MODE_INIT:       "INIT",
    MODE_HEAT:       "HEAT",
    MODE_CIRC:       "CIRC_ON",
    MODE_COOL_MIN:   "COOLING_MIN",
    MODE_COOL_ACT:   "COOLING_ON",
    MODE_COOL_SETUP: "HEAT_LOCK_SETUP",
}
mode_colors = {
    MODE_OFF:        "#95a5a6",
    MODE_INIT:       "#f39c12",
    MODE_HEAT:       "#e74c3c",
    MODE_CIRC:       "#3498db",
    MODE_COOL_MIN:   "#1abc9c",
    MODE_COOL_ACT:   "#2ecc71",
    MODE_COOL_SETUP: "#9b59b6",
}

# Build mode sequence matching phases below
mode_v = np.zeros(len(t), dtype=int)
mode_v[t < 5]               = MODE_INIT
mode_v[(t >= 5)  & (t < 30)] = MODE_HEAT
mode_v[(t >= 30) & (t < 60)] = MODE_CIRC
mode_v[(t >= 60) & (t < 110)]= MODE_COOL_MIN
mode_v[(t >= 110)& (t < 170)]= MODE_COOL_ACT
mode_v[(t >= 170)& (t < 210)]= MODE_COOL_MIN
mode_v[(t >= 210)& (t < 290)]= MODE_CIRC
mode_v[(t >= 290)& (t < 300)]= MODE_COOL_SETUP
mode_v[(t >= 300)& (t < 355)]= MODE_COOL_MIN
mode_v[(t >= 355)& (t < 400)]= MODE_CIRC
mode_v[t >= 400]             = MODE_OFF

# Temperature signal — rises during HEAT, falls during cooling
temp = 20 + 5 * np.cumsum(
    np.where((mode_v == MODE_HEAT), 0.05,
    np.where((mode_v == MODE_COOL_ACT), -0.03, 0.0))
) * dt
temp_sp = np.where(mode_v == MODE_HEAT, 35.0, 22.0)

# Digital flag: compressor active
comp_active = (mode_v == MODE_COOL_ACT).astype(float)

# ── Diagram ───────────────────────────────────────────────────────────────────
d = Diagram(
    title="Thermal Management — State Machine Overview",
    t_end=400,
    figsize=(16, 10),
)

# ── Mode enum panel ────────────────────────────────────────────────────────────
g_mode = d.add_group("Thermal Mode")
g_mode.add_enum("ThermalMode", t, mode_v,
                labels=mode_labels, colors=mode_colors,
                color="#2c3e50", lw=2.0)

# ── Temperature panel ──────────────────────────────────────────────────────────
g_temp = d.add_group("Temperature [°C]")
g_temp.add_raw("Btms_T_Meas",   t, temp,    color="#e74c3c", lw=1.8)
g_temp.add_raw("Btms_T_SP",     t, temp_sp, color="#2ecc71", lw=1.5, ls="--")
g_temp.add_threshold(35, label="MAX 35°C", color="#c0392b")
g_temp.add_threshold(22, label="SP 22°C",  color="#27ae60", ls=":")

# ── Digital flags ──────────────────────────────────────────────────────────────
g_flags = d.add_digital_group()
g_flags.add_raw("CompressorActive", t, comp_active, color="#2980b9")

# ── Phases (with pass/fail status) ────────────────────────────────────────────
d.add_phase(0,   5,   "INIT",           status=None)    # neutral gray
d.add_phase(5,   30,  "HEAT",           status="fail")  # red + × (over-temperature)
d.add_phase(30,  60,  "CIRC",           status="pass")
d.add_phase(60,  110, "COOL MIN 1",     status="pass")
d.add_phase(110, 170, "COOL ACTIVE 1",  status="pass")
d.add_phase(170, 210, "COOL MIN 2",     status="pass")
d.add_phase(210, 290, "CIRC 2",         status="pass")
d.add_phase(290, 300, "HEAT LOCK",      status="fail")  # fault
d.add_phase(300, 355, "COOL MIN 3",     status="pass")
d.add_phase(355, 400, "CIRC 3",         status="pass")

# ── Render ─────────────────────────────────────────────────────────────────────
d.render(
    output="output/enum_phases.png",
    show=True,
)
print("Saved -> output/enum_phases.png")
print("Tip: zoom into the mode panel to see state labels appear on each segment.")
