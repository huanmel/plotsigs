"""
examples/ex_render_spec.py
==========================
Demonstrate render_spec() — the universal dict-based API.

render_spec() accepts a plain PlotSpec dict so any application can assemble
a plot request without touching the Diagram / SignalGroup fluent API.
Two patterns are shown:

  Part 1 — Single DataFrame
      Equivalent to ex_plot_from_csv.py, written as a spec dict.

  Part 2 — Multiple named DataFrames
      Two real test-run logs compared side by side; each source has its own
      time column, and signals reference it via the "source" key.

Run from repo root:
    python examples/ex_render_spec.py
"""

import pandas as pd
import plotsigs

# ── Load data ──────────────────────────────────────────────────────────────────

sim  = pd.read_csv("examples/compressor_sim_data.csv")
log1 = pd.read_csv("examples/compressor_real_data_log_1.csv")
log2 = pd.read_csv("examples/compressor_real_data_log_2.csv")


# ══════════════════════════════════════════════════════════════════════════════
# Part 1 — Single DataFrame
# The same plot as ex_plot_from_csv.py, written as a spec dict.
# ══════════════════════════════════════════════════════════════════════════════

plotsigs.render_spec(
    {
        "meta": {
            "title":  "Compressor Speed Control — render_spec, single DataFrame",
            "xlabel": "Time [s]",
            "figsize": [14, 9],
        },
        "data": sim,          # single DataFrame; time_col defaults to "time"

        "groups": [
            {
                "ylabel": "Speed [RPM]",
                "signals": [
                    {"name": "AC_Set_Speed",             "column": "AC_Set_Speed",             "color": "#2ecc71"},
                    {"name": "Compressor_Running_Speed", "column": "Compressor_Running_Speed", "color": "#e74c3c"},
                ],
                "ref_lines": [
                    {"value": 800,  "label": "MIN 800",  "color": "#3498db"},
                    {"value": 8500, "label": "MAX 8500", "color": "#e74c3c"},
                ],
            },
            {
                "mode":   "digital",
                "signals": [
                    {"name": "AC_Enable",       "column": "AC_Enable",       "color": "#2980b9"},
                    {"name": "DrvrOut_IsRunOk", "column": "DrvrOut_IsRunOk", "color": "#27ae60"},
                    {"name": "DrvrOut_IsFault", "column": "DrvrOut_IsFault", "color": "#c0392b"},
                    {"name": "IsActVld",        "column": "IsActVld",        "color": "#8e44ad"},
                ],
            },
            {
                "ylabel": "Board [°C] / Bus [V]",
                "signals": [
                    {"name": "Board_Temp",     "column": "Board_Temp",     "color": "#e67e22"},
                    {"name": "DC_Bus_Voltage", "column": "DC_Bus_Voltage", "color": "#8e44ad"},
                ],
            },
        ],

        "annotations": [
            {"type": "phase", "t0": 0,  "t1": 10, "label": "IDLE"},
            {"type": "phase", "t0": 10, "t1": 22, "label": "RAMP"},
            {"type": "phase", "t0": 22, "t1": 47, "label": "STEADY"},
            {"type": "phase", "t0": 47, "t1": 61, "label": "SHUTDOWN"},
        ],
    },
    output="output/render_spec_single_df.png",
    show=True,
)


# ══════════════════════════════════════════════════════════════════════════════
# Part 2 — Multiple named DataFrames
# Two test-run logs compared in the same figure.  Each source has its own
# time column ("timestamps"); signals reference their source by name.
# t_start / t_end / n_points are auto-derived from the data.
# ══════════════════════════════════════════════════════════════════════════════

plotsigs.render_spec(
    {
        "meta": {
            "title":  "Compressor — two test runs compared",
            "xlabel": "Time [s]",
            "figsize": [14, 8],
            # t_end and n_points are omitted → auto-derived from log1 and log2
        },
        "data": {
            "log1": {"df": log1, "time_col": "timestamps"},
            "log2": {"df": log2, "time_col": "timestamps"},
        },

        "groups": [
            {
                "ylabel": "Set Speed [RPM]",
                "signals": [
                    {"name": "Set Speed — run 1", "source": "log1", "column": "AC_Set_Speed",                   "color": "#2ecc71"},
                    {"name": "Set Speed — run 2", "source": "log2", "column": "AC_Set_Speed",                   "color": "#27ae60", "ls": "--"},
                ],
                "ref_lines": [800, 8500],
            },
            {
                "ylabel": "Running Speed [RPM]",
                "signals": [
                    {"name": "Running Speed — run 1", "source": "log1", "column": "EC1_Compressor_Running_Speed", "color": "#e74c3c"},
                    {"name": "Running Speed — run 2", "source": "log2", "column": "EC1_Compressor_Running_Speed", "color": "#c0392b", "ls": "--"},
                ],
            },
            {
                "mode": "digital",
                "ylabel": "Enable (run 1 / run 2)",
                "signals": [
                    {"name": "Enable — run 1", "source": "log1", "column": "AC_Enable_Disable_Compressor", "color": "#2980b9"},
                    {"name": "Enable — run 2", "source": "log2", "column": "AC_Enable_Disable_Compressor", "color": "#8e44ad"},
                ],
            },
        ],
    },
    output="output/render_spec_multi_df.png",
    show=True,
)
