"""
examples/ex_template_function.py
=================================
Demonstrate the reusable diagram template function pattern.

Key patterns shown:
  • Define add_tms_groups() once — builds the standard 3-panel layout
    (Temperature + Error + Mode) on any Diagram.
  • Two independent scenarios call the same helper, avoiding copy-paste.
  • plotsigs.sim — physics-based 2nd-order plant simulation.
  • to_digital_bps() — convert a numpy 0/1 array to a DigitalSignal.
  • add_tolerance() — shaded deadband band tracking the setpoint.
  • add_enum() — state-machine mode panel with zoom-reactive labels.

Run from repo root:
    python examples/ex_template_function.py
"""

import numpy as np
from plotsigs import Diagram, to_digital_bps
from plotsigs.sim import second_order, second_order_disturbed

# ── Shared constants ──────────────────────────────────────────────────────────
DEAD        = 4.0   # °C  half-width of mode deadband
OMEGA_N     = 0.25  # rad/s  natural frequency
ZETA_DAMP   = 0.40  # –     well-damped (clean settling)
ZETA_OSC    = 0.10  # –     underdamped (oscillating)

MODE_LABELS = {1: "Heating", 2: "Circulation", 3: "Cooling"}
MODE_COLORS = {1: "#e74c3c", 2: "#9b59b6", 3: "#3498db"}


# ── Simple stateless mode logic ───────────────────────────────────────────────

def tms_mode(T_MR: np.ndarray, T_SP: np.ndarray, dead: float) -> np.ndarray:
    mode = np.full(len(T_MR), 2.0)            # default: Circulation
    mode[T_MR < T_SP - dead] = 1.0            # too cold  → Heating
    mode[T_MR > T_SP + dead] = 3.0            # too warm  → Cooling
    return mode


# ── Template function ─────────────────────────────────────────────────────────

def add_tms_groups(d: Diagram, t, T_MR, T_SP, mode, dead=DEAD):
    """
    Add the standard TMS 3-panel layout to *d* and return the three groups.

    Panels
    ------
    Temperature [°C]   — setpoint, measured, ±dead °C tolerance band
    T_ERR [°C]         — T_MR − T_SP with ±dead threshold lines
    TMS Mode           — enumerated state panel (Heating / Circulation / Cooling)

    The returned groups can be further customised by the caller
    (add_transient_analysis, add_callout, extra thresholds, …).
    """
    g_temp = d.add_group("Temperature [°C]")
    g_temp.add_raw("T_SP", t, T_SP, color="#2ecc71", lw=2.0)
    g_temp.add_raw("T_MR", t, T_MR, color="#e74c3c", lw=1.8)
    g_temp.add_tolerance("T_SP", dead,
                         color="#9b59b6", label=f"+-{dead:.0f} degC mode band")

    g_err = d.add_group("T_ERR [°C]")
    g_err.add_derived("T_err", "T_MR", "T_SP", color="#8e44ad", lw=1.5)
    g_err.add_threshold( dead, label=f"+{dead:.0f} -> Cooling",
                        color="#3498db", ls="--")
    g_err.add_threshold(-dead, label=f"-{dead:.0f} -> Heating",
                        color="#e74c3c", ls="--")
    g_err.add_threshold(0, label="zero", ls="-", lw=0.6, color="#aaaaaa")

    g_mode = d.add_group("TMS Mode")
    g_mode.add_enum("Mode", t, mode,
                    labels=MODE_LABELS, colors=MODE_COLORS)

    return g_temp, g_err, g_mode


# ── Shared time vector & setpoint ─────────────────────────────────────────────
T_END  = 120.0
N_PTS  = 5000
t      = np.linspace(0, T_END, N_PTS)

# Setpoint: held at 20 °C, then steps to 27 °C at t = 10 s
T_SP   = np.where(t < 10, 20.0, 27.0)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Scenario A — clean step response (well-damped, no disturbance)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
T_MR_a = second_order(t, T_SP, omega_n=OMEGA_N, zeta=ZETA_DAMP, y0=20.0)
mode_a  = tms_mode(T_MR_a, T_SP, DEAD)

# to_digital_bps: convert computed 0/1 array -> DigitalSignal breakpoints
heater_on_a = (mode_a == 1).astype(float)
cooler_on_a = (mode_a == 3).astype(float)

d_a = Diagram(
    title="TMS Scenario A — Clean Step Response (well-damped)",
    t_end=T_END, n_points=N_PTS,
    figsize=(14, 10), xlabel="Time [s]",
)

ph_pre  = d_a.add_phase(0,   10,  "HOLD 20 degC",     status=None)
ph_step = d_a.add_phase(10,  60,  "STEP to 27 degC",  status="pass")
ph_ss   = d_a.add_phase(60,  T_END, "STEADY STATE",   status="pass")

g_temp_a, g_err_a, _ = add_tms_groups(d_a, t, T_MR_a, T_SP, mode_a)

# Add transient analysis on top of the template-generated groups
g_temp_a.add_transient_analysis(
    "T_SP", "T_MR",
    tolerance_pct=5.0,
    phase=ph_step,
    show_crosshairs=True,
)

# Digital panel: actuator states derived from the mode array
g_act_a = d_a.add_digital_group("Actuators")
g_act_a.add_digital("Heater ON",  to_digital_bps(t, heater_on_a), color="#e74c3c")
g_act_a.add_digital("Cooler ON",  to_digital_bps(t, cooler_on_a), color="#3498db")

d_a.render(output="output/tms_template_a.png", show=False)
print("Saved -> output/tms_template_a.png")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Scenario B — underdamped + external heat load after settling
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DIST_START = 70.0   # s    heat load begins (e.g. compressor starts)
DIST_RATE  = 0.28   # °C/s additive heating rate

dist_b = np.where(t >= DIST_START, DIST_RATE, 0.0)
T_MR_b = second_order_disturbed(
    t, T_SP, omega_n=OMEGA_N, zeta=ZETA_OSC, disturbance=dist_b, y0=20.0
)
mode_b      = tms_mode(T_MR_b, T_SP, DEAD)
heater_on_b = (mode_b == 1).astype(float)
cooler_on_b = (mode_b == 3).astype(float)

n_transitions = int(np.sum(np.diff(mode_b) != 0))

d_b = Diagram(
    title=f"TMS Scenario B — Underdamped + External Heat Load ({n_transitions} mode transitions)",
    t_end=T_END, n_points=N_PTS,
    figsize=(14, 10), xlabel="Time [s]",
    caption=(
        f"External heat load begins at t={DIST_START:.0f} s ({DIST_RATE} degC/s). "
        f"Underdamped oscillations (zeta={ZETA_OSC}) cross the Cooling boundary "
        f"repeatedly, causing {n_transitions} mode transitions."
    ),
)

d_b.add_phase(0,           10,         "HOLD 20 degC",       status=None)
d_b.add_phase(10,          DIST_START, "STEP — settling",    status="pass")
d_b.add_phase(DIST_START,  T_END,      "DISTURBED",          status="fail")
d_b.add_vspan(DIST_START, T_END,
              label="External heat load", color="#e74c3c", alpha=0.07)

g_temp_b, g_err_b, g_mode_b = add_tms_groups(d_b, t, T_MR_b, T_SP, mode_b)

g_temp_b.add_callout("T_MR", DIST_START + 15,
                     label=f"T_MR drifts above\nCooling boundary",
                     offset=(3, 1.5))

g_act_b = d_b.add_digital_group("Actuators")
g_act_b.add_digital("Heater ON", to_digital_bps(t, heater_on_b), color="#e74c3c")
g_act_b.add_digital("Cooler ON", to_digital_bps(t, cooler_on_b), color="#3498db")

d_b.render(output="output/tms_template_b.png", show=False)
print("Saved -> output/tms_template_b.png")
print(f"Scenario B: {n_transitions} mode transitions after disturbance onset.")
