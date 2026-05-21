"""
examples/ex_compare_naive_correct.py
=====================================
Demonstrate the "naive vs. correct" dual-panel comparison pattern.

Scenario — Hysteresis fix for mode chattering:
  A sustained external heat load holds T_MR just above the Cooling boundary.
  Underdamped oscillations cross the boundary repeatedly.

  Naive (standard deadband): mode chatters with every crossing.
  Correct (hysteresis):      enters Cooling at ±4 °C, exits only at ±3 °C.
                             One transition; stays stable despite oscillations.

Key patterns shown:
  • Two enum mode panels on one diagram (naive vs. correct) side-by-side
  • phase status="fail" / "pass" for chattering vs. stable windows
  • add_vspan() for the chattering time window
  • add_callout() for peak annotation
  • to_digital_bps() converting a mode-derived array to a DigitalSignal

Run from repo root:
    python examples/ex_compare_naive_correct.py
"""

import numpy as np
from plotsigs import Diagram, to_digital_bps
from plotsigs.sim import second_order_disturbed

# ── Constants ─────────────────────────────────────────────────────────────────
T_END    = 150.0
N_PTS    = 6000
OMEGA_N  = 0.25   # rad/s  natural frequency
ZETA     = 0.10   # –     underdamped (oscillating)
DEAD     = 4.0    # °C    deadband half-width
HYST     = 1.0    # °C    hysteresis margin (exit threshold = DEAD - HYST)
SP_VAL   = 27.0   # °C    fixed setpoint

MODE_LABELS = {1: "Heating", 2: "Circulation", 3: "Cooling"}
MODE_COLORS = {1: "#e74c3c", 2: "#9b59b6", 3: "#3498db"}

DIST_START = 5.0    # s    disturbance begins
DIST_RATE  = 0.28   # °C/s additive heat rate (pushes SS to SP+4.5 °C)


# ── Mode logic ─────────────────────────────────────────────────────────────────

def standard_mode(T_MR, T_SP, dead):
    """Stateless deadband: enter and exit at same threshold."""
    mode = np.full(len(T_MR), 2.0)
    mode[T_MR < T_SP - dead] = 1.0
    mode[T_MR > T_SP + dead] = 3.0
    return mode


def hysteresis_mode(T_MR, T_SP, dead, hyst):
    """
    Stateful hysteresis:
      Enter Heating/Cooling at ± dead
      Exit  Heating/Cooling at ± (dead - hyst)
    """
    mode    = np.full(len(T_MR), 2.0)
    current = 2
    for i in range(len(T_MR)):
        err = T_MR[i] - T_SP[i]
        if current == 2:               # Circulation
            if err < -dead:    current = 1   # enter Heating
            elif err > dead:   current = 3   # enter Cooling
        elif current == 1:             # Heating
            if err >= -(dead - hyst):  current = 2   # exit Heating
        elif current == 3:             # Cooling
            if err <= (dead - hyst):   current = 2   # exit Cooling
        mode[i] = float(current)
    return mode


# ── Simulation ────────────────────────────────────────────────────────────────
t     = np.linspace(0, T_END, N_PTS)
T_SP  = np.full(N_PTS, SP_VAL)

dist  = np.where(t >= DIST_START, DIST_RATE, 0.0)
T_MR  = second_order_disturbed(
    t, T_SP, omega_n=OMEGA_N, zeta=ZETA, disturbance=dist, y0=SP_VAL
)

mode_std  = standard_mode(T_MR, T_SP, DEAD)
mode_hyst = hysteresis_mode(T_MR, T_SP, DEAD, HYST)

n_std  = int(np.sum(np.diff(mode_std)  != 0))
n_hyst = int(np.sum(np.diff(mode_hyst) != 0))
print(f"Standard:   {n_std} mode transitions")
print(f"Hysteresis: {n_hyst} mode transitions  "
      f"(enter +-{DEAD:.0f} degC, exit +-{DEAD-HYST:.0f} degC)")

# ── Diagram ───────────────────────────────────────────────────────────────────
d = Diagram(
    title=(f"Hysteresis Fix — Standard ({n_std} transitions) vs. "
           f"Hysteresis ({n_hyst} transitions)"),
    t_end=T_END, n_points=N_PTS,
    figsize=(14, 13), xlabel="Time [s]",
    caption=(
        f"Sustained heat load ({DIST_RATE} degC/s) holds T_MR_ss at SP+4.5 degC. "
        f"Underdamped oscillations (zeta={ZETA}) repeatedly cross the SP+{DEAD:.0f} "
        f"degC boundary. Standard mode chatters ({n_std} transitions). "
        f"Hysteresis (enter +-{DEAD:.0f}, exit +-{DEAD-HYST:.0f} degC) "
        f"stays in Cooling after first entry ({n_hyst} transitions)."
    ),
)

# ── Phases ─────────────────────────────────────────────────────────────────────
d.add_phase(0,   DIST_START, "IDLE",               status=None)
d.add_phase(DIST_START, 40,  "RISE + OVERSHOOT",   status=None)
d.add_phase(40,  T_END,      "CHATTERING (std) / STABLE (hyst)", status="fail")

d.add_vspan(40, T_END,
            label=f"Chattering window — std: {n_std} transitions", color="#e67e22")

# ── Temperature panel (shared) ─────────────────────────────────────────────────
g_temp = d.add_group("Temperature [°C]")
g_temp.add_raw("T_SP",    t, T_SP, color="#2ecc71", lw=2.0)
g_temp.add_raw("T_MR",   t, T_MR, color="#e74c3c", lw=1.8)
g_temp.add_tolerance("T_SP", DEAD, color="#9b59b6",
                     label=f"+-{DEAD:.0f} degC deadband")
g_temp.add_threshold(SP_VAL + DEAD,
                     label=f"Enter Cooling = {SP_VAL+DEAD:.0f} degC",
                     color="#3498db", ls=":")
g_temp.add_threshold(SP_VAL + DEAD - HYST,
                     label=f"Exit Cooling  = {SP_VAL+DEAD-HYST:.0f} degC",
                     color="#9b59b6", ls=":")
g_temp.add_callout("T_MR", 75.0,
                   label=f"T_MR oscillates\nacross {SP_VAL+DEAD:.0f} degC boundary",
                   offset=(4, 1.5))

# ── Mode panel — Standard (naive) ──────────────────────────────────────────────
g_std = d.add_group(f"Mode — Standard deadband  ({n_std} transitions — chattering)")
g_std.add_enum("Mode_std",  t, mode_std,  labels=MODE_LABELS, colors=MODE_COLORS)

# ── Mode panel — Hysteresis (correct) ─────────────────────────────────────────
g_hyst = d.add_group(
    f"Mode — Hysteresis +-{HYST:.0f} degC  ({n_hyst} transitions — stable)"
)
g_hyst.add_enum("Mode_hyst", t, mode_hyst, labels=MODE_LABELS, colors=MODE_COLORS)

# ── Digital panel: cooler active comparison ────────────────────────────────────
g_flags = d.add_digital_group("Cooler active")
g_flags.add_digital("Cooler (std)",  to_digital_bps(t, (mode_std  == 3).astype(float)),
                    color="#c0392b")
g_flags.add_digital("Cooler (hyst)", to_digital_bps(t, (mode_hyst == 3).astype(float)),
                    color="#2980b9")

d.render(output="output/compare_naive_correct.png", show=False)
print("Saved -> output/compare_naive_correct.png")
