"""
examples/ex_render_spec_plotly.py
==================================
Demonstrate the Plotly backend via render_spec(backend="plotly").

Produces:
  output/render_spec_plotly.html   — standalone interactive HTML (open in browser)

To launch the full Dash application instead, change the last call to backend="dash".

Run from repo root:
    python examples/ex_render_spec_plotly.py
"""

import pandas as pd
import plotsigs

sim_data = pd.read_csv("examples/compressor_sim_data.csv")
spec = {
        "meta": {
            "title":  "Compressor Speed Control — Plotly interactive",
            "xlabel": "Time [s]",
            "figsize": [14, 9],        # ignored by plotly backend; kept for compat
        },
        "data": sim_data,

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
    }
fig = plotsigs.render_spec(
    spec,
    # backend="plotly",
    backend="dash",   # uncomment to launch the full Dash app instead of static HTML
    output="output/render_spec_plotly.html",
    show=True,   # set True to open in browser automatically
)

print(f"Plotly OK — {len(fig.data)} traces")
print("Saved: output/render_spec_plotly.html")
print()
print("To open the full Dash app, run:")
print("  plotsigs.render_spec({...}, backend='dash')")
