"""
temp/temp_ex_render_spec_plotly.py
====================================
HVAC / TMS compressor control — interactive Dash example.

Dataset:  C:/Users/ivanm/Downloads/plot_data.csv
Time:     0 – 1920 s, Δt = 0.1 s  (19 200 points)
Backend:  Dash (interactive) or Plotly (static HTML)

Run from repo root:
    python temp/temp_ex_render_spec_plotly.py
"""

import pandas as pd
import plotsigs

df = pd.read_csv(r"C:\Users\ivanm\Downloads\plot_data.csv")

spec = {
    "meta": {
        "title":  "HVAC TMS — Compressor & Thermal Loop",
        "xlabel": "Time [s]",
    },
    "data": df,                    # time_col defaults to "time"

    "groups": [

        # ── 1 · Control flags (digital) ──────────────────────────────────────
        {
            "mode": "digital",
            "ylabel": "Flags",
            "signals": [
                {"name": "AC Ena",         "column": "TmsCtrl_CmdAcEna",          "color": "#2980b9"},
                {"name": "AC Req (HMI)",   "column": "HMIDrvr_ClimAcReq",         "color": "#27ae60"},
                {"name": "PID Sat↑",       "column": "TmsCtrl_CmprCmdSatUpPID",   "color": "#e74c3c"},
                {"name": "Evap PID Sat↑",  "column": "TmsCtrl_CmprTEvapPIDSatUp", "color": "#e67e22"},
            ],
        },

        # ── 2 · Compressor speed [RPM] ───────────────────────────────────────
        {
            "ylabel": "Cmpr Speed [RPM]",
            "signals": [
                {"name": "Spd SP",       "column": "AC_Set_Speed",       "color": "#2ecc71", "ls": "--"},
                {"name": "Cmpr Cmd Spd", "column": "TmsCtrl_CmdAcSpd",   "color": "#3498db"},
            ],
            "ref_lines": [
                {"value": 800,  "label": "Min 800",  "color": "#95a5a6"},
                {"value": 8500, "label": "Max 8500", "color": "#e74c3c"},
            ],
        },

        # ── 3 · Evaporator temperature [°C] ─────────────────────────────────
        {
            "ylabel": "T Evap [°C]",
            "signals": [
                {"name": "T Evap SP",   "column": "Clim_T_Evap_SP",        "color": "#2980b9", "ls": "--"},
                {"name": "T Evap Meas", "column": "HMIDrvr_TempEvap",       "color": "#2ecc71"},
                {"name": "Evap PID SP", "column": "TmsCtrl_CmprTEvapPIDSp", "color": "#8e44ad", "ls": ":"},
            ],
        },

        # ── 4 · Cabin / mix-air temperatures [°C] ───────────────────────────
        {
            "ylabel": "T Cabin / Air [°C]",
            "signals": [
                {"name": "T Cabin SP",  "column": "Clim_T_Cabin_SP",    "color": "#c0392b", "ls": "--"},
                {"name": "T Cabin",     "column": "HMIDrvr_TempInCab",  "color": "#e74c3c"},
                {"name": "T MixAir SP", "column": "Clim_T_MixAir_SP",   "color": "#8e44ad", "ls": "--"},
                {"name": "T MixAir",    "column": "HMIDrvr_TempMixAir", "color": "#9b59b6"},
                {"name": "T Ambient",   "column": "HMIDrvr_TempExAm",   "color": "#95a5a6"},
            ],
        },

        # ── 5 · Refrigerant pressures [bar] ─────────────────────────────────
        {
            "ylabel": "Pressure [bar]",
            "signals": [
                {"name": "LoP Meas", "column": "SnsrPres_LoP_OutMeasd", "color": "#3498db"},
                {"name": "HiP Meas", "column": "SnsrPres_HiP_OutMeasd", "color": "#e74c3c"},
            ],
        },

        # ── 6 · Pressure-side temperatures [°C] ─────────────────────────────
        {
            "ylabel": "T Pres Side [°C]",
            "signals": [
                {"name": "LoP T SP",   "column": "TmsCtrl_LoP_TSp_degC", "color": "#2980b9", "ls": "--"},
                {"name": "LoP T Meas", "column": "TmsCtrl_LoP_T_degC",   "color": "#3498db"},
                {"name": "HiP T SP",   "column": "TmsCtrl_HiP_TSp_degC", "color": "#c0392b", "ls": "--"},
                {"name": "HiP T Meas", "column": "TmsCtrl_HiP_T_degC",   "color": "#e74c3c"},
            ],
        },

    ],

    # Phase annotations — adjust t0/t1 to match your test sequence
    # "annotations": [
    #     {"type": "phase", "t0":    0, "t1":  120, "label": "Init"},
    #     {"type": "phase", "t0":  120, "t1":  600, "label": "Cool-down 1"},
    #     {"type": "phase", "t0":  600, "t1": 1500, "label": "Steady"},
    #     {"type": "phase", "t0": 1500, "t1": 1920, "label": "Shutdown"},
    # ],
}

# ── Launch ────────────────────────────────────────────────────────────────────
plotsigs.render_spec(spec, backend="dash")

# Static HTML export instead:
# fig = plotsigs.render_spec(spec, backend="plotly",
#                            output="output/hvac_tms.html", show=False)
# print(f"Saved — {len(fig.data)} traces")
