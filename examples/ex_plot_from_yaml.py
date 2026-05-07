"""
examples/ex_plot_from_yaml.py
==============================
Load diagrams from declarative YAML config files.

Two examples are shown:
  1. Synthetic signals (stepped + lagged) — compressor_plot_data.yaml
  2. Real CSV log data with transient analysis — ex_real_log_analysis.yaml

Run from repo root:
    python examples/ex_plot_from_yaml.py
"""

from plotsigs import load_yaml

# ── Example 1: synthetic signals ──────────────────────────────────────────────
d1 = load_yaml("examples/compressor_plot_data.yaml")
d1.render(output="output/plot_from_yaml.png", show=False)

# ── Example 2: real CSV log data + transient analysis ─────────────────────────
d2 = load_yaml("examples/ex_real_log_analysis.yaml")
d2.render(output="output/real_log_analysis_yaml.png", show=True)
