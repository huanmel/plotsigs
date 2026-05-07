"""
examples/plot_from_script.py
======================
Compressor speed control diagram — demonstrates the grouped subplot API.

Layout:
    ┌─────────────────────────────┐
    │  Speed [RPM]  (analog)      │  ← g_speed: signals + threshold + tolerance + callout
    ├─────────────────────────────┤
    │  Control flags  (digital)   │  ← g_flags: digital lanes
    └─────────────────────────────┘

Run from repo root:
    python examples/plot_from_script.py
"""

from plotsigs import Diagram

d = Diagram(
    title="Compressor Speed Control — EC1",
    t_end=62,
    xlabel="Time [s]",
    figsize=(14, 7),
)

# ── Group 1: speed signals (analog subplot) ────────────────────────────────────
g_speed = d.add_group("Speed [RPM]")

cmd = g_speed.add_stepped("AC_Set_Speed", [
    (0, 1000), (3, 800), (5, 1000), (10, 2000),
    (12, 2500), (16, 8500), (22, 1000), (36, 4500),
    (47, 1000), (56, 200), (60, 0),
], color="#2ecc71")

g_speed.add_lagged("Compressor Running Speed", source=cmd, tau=1.8, color="#e74c3c")

# per-group annotations: thresholds, tolerance band, callout
g_speed.add_threshold(1500, label="MIN 1500", color="#3498db")
g_speed.add_threshold(8000, label="MAX 8000", color="#e74c3c", ls="--")
g_speed.add_tolerance("AC_Set_Speed", tolerance=400)
g_speed.add_callout("Compressor Running Speed", t=26, label="Peak speed", offset=(-4, 400))

# ── Group 2: control flags (digital subplot) ───────────────────────────────────
g_flags = d.add_digital_group("Control flags")

g_flags.add_digital("AC_Enable",       [(0,1),(2,0),(5,1),(9,0),(10,1),(21,0),(22,1),(47,0),(48,1),(59,0),(60,1)])
g_flags.add_digital("DrvrOut.IsRunOk", [(0,1),(2,0),(5,1),(9,0),(10,1),(21,0),(22,1),(47,0),(48,1),(59,0),(60,1)], color="#e67e22")
g_flags.add_digital("IsActVld",        [(0,0),(12,1),(21,0),(22,0),(30,1),(47,0),(48,0),(54,1),(59,0)],            color="#8e44ad")

# ── Diagram-level annotations (span all subplots) ─────────────────────────────
d.add_vspan(10, 12, label="STARTUP\nwindow", color="#f39c12")
d.add_vline(21, label="Fault detected", color="#c0392b", label_y=0.72)

# ── Phase labels (bottom subplot) ─────────────────────────────────────────────
d.add_phase(0,  10, "IDLE")
d.add_phase(10, 22, "ACTIVE / RAMP")
d.add_phase(22, 47, "ACTIVE / STEADY")
d.add_phase(47, 62, "SHUTDOWN")

# ── Render ─────────────────────────────────────────────────────────────────────
d.render(
    output=["output/plot_from_script.svg", "output/plot_from_script.png"],
    show=True,
)
