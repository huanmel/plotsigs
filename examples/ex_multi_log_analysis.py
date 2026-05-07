"""
examples/ex_multi_log_analysis.py
===================================
Batch-process multiple compressor logs using a shared analysis template.

The template (compressor_analysis_template.yaml) defines what to plot and
how to analyse it.  Each run supplies only what varies:
  - data=   pre-loaded DataFrame (load from CSV, Parquet, HDF5, SQL, ...)
  - title   run identifier
  - phases  time boundaries for each named phase

Run from repo root:
    python examples/ex_multi_log_analysis.py
"""

import pandas as pd
from plotsigs import load_yaml

TEMPLATE = "examples/compressor_analysis_template.yaml"


def phases_to_annotations(phases: dict) -> list:
    """Convert {label: (t0, t1)} dict to diagram annotation list."""
    return [
        {"type": "phase", "t0": t0, "t1": t1, "label": label}
        for label, (t0, t1) in phases.items()
    ]


# ── Per-run config ─────────────────────────────────────────────────────────────
LOGS = [
    {
        "title":  "Compressor log — run 001 (startup at t=14 s)",
        "file":   "examples/compressor_real_data_log_1.csv",
        "phases": {
            "IDLE":      (0,    14),
            "STARTUP":   (14,   19),    # drives the transient_analysis window
            "RAMP UP":   (19,   38.2),
            "MAX SPEED": (38.2, 43),
            "RAMP DOWN": (43,   54.4),
            "STEADY":    (54.4, 70),
        },
        "output": "output/multi_log_001.png",
    },
    {
        "title":  "Compressor log — run 002 (oscillations at steady state)",
        "file":   "examples/compressor_real_data_log_2.csv",
        "phases": {
            "IDLE":      (0,    6.8),
            "STARTUP":   (6.8,  11.9),
            "RAMP UP":   (11.9, 23),
            "MAX SPEED": (23,   44),
            "RAMP DOWN": (44,   50),
            "STEADY":    (50,   80),
        },
        "output": "output/multi_log_002.png",
    },
]

# ── Batch render ───────────────────────────────────────────────────────────────
for log in LOGS:
    # Load data here — swap pd.read_csv for read_parquet, read_sql, etc.
    df = pd.read_csv(log["file"])

    d = load_yaml(
        TEMPLATE,
        data=df,                                        # DataFrame passed directly
        overrides={
            "title":       log["title"],
            "annotations": phases_to_annotations(log["phases"]),
        },
    )
    d.render(output=log["output"], show=False)
    print(f"  -> {log['output']}")

print("Done.")
