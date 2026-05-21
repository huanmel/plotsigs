"""
examples/quickplot.py
=====================
Demonstrate plot_signals() — the one-liner API for DataFrame-driven plots.

Three call styles are shown:
  1. List of lists  — minimal, auto-detects digital signals
  2. Mixed shorthand — single strings and lists
  3. Dict spec      — explicit ylabel, mode, per group

Run from repo root:
    python examples/quickplot.py
"""

import pandas as pd
from plotsigs import plot_signals

df = pd.read_csv("examples/compressor_sim_data.csv")

# ── Style 1: list of lists (mirrors can_log_utils / FMU plot_signals pattern) ─
#
#   Auto-detection:
#     • AC_Set_Speed, Compressor_Running_Speed → values span 0–8500 → analog
#     • AC_Enable, DrvrOut_IsRunOk, DrvrOut_IsFault, IsActVld → all 0/1 → digital
#     • Board_Temp, DC_Bus_Voltage → numeric → analog

plot_signals(
    df,
    groups=[
        ["AC_Set_Speed", "Compressor_Running_Speed"],
        ["AC_Enable", "DrvrOut_IsRunOk", "DrvrOut_IsFault", "IsActVld"],
        ["Board_Temp", "DC_Bus_Voltage"],
    ],
    title="Compressor — auto-detected groups",
    figsize=(14, 9),
    output="output/quickplot_auto.png",
    show=True,
)

# ── Style 2: mixed shorthand (single string = one signal per subplot) ──────────

plot_signals(
    df,
    groups=[
        "AC_Set_Speed",                                   # one signal, auto ylabel
        "Compressor_Running_Speed",
        ["AC_Enable", "DrvrOut_IsRunOk", "IsActVld"],    # digital group
    ],
    title="Compressor — single-signal subplots",
    figsize=(14, 9),
    output="output/quickplot_single.png",
    show=True,
)

# ── Style 3: dict spec — explicit labels and mode overrides ───────────────────

plot_signals(
    df,
    groups=[
        {
            "signals": ["AC_Set_Speed", "Compressor_Running_Speed"],
            "ylabel":  "Speed [RPM]",
        },
        {
            "signals": ["AC_Enable", "DrvrOut_IsRunOk", "DrvrOut_IsFault", "IsActVld"],
            "ylabel":  "Control flags",
            "mode":    "digital",           # explicit — skip auto-detection
        },
        {
            "signals": ["Board_Temp"],
            "ylabel":  "Board temp [°C]",
        },
        {
            "signals": ["DC_Bus_Voltage"],
            "ylabel":  "DC bus [V]",
        },
    ],
    title="Compressor — explicit group config",
    figsize=(14, 11),
    output="output/quickplot_explicit.png",
    show=True,
)
