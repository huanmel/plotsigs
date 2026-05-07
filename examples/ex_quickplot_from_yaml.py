"""
examples/quickplot_from_yaml.py
================================
Demonstrate plot_signals_from_yaml() — load plot layout from YAML.

Two YAML formats are shown:

  1. Simple quickplot format  (groups: key, ref_lines inline)
  2. Catalog / preset format  (plot_presets: key, pick preset by name)

Run from repo root:
    python examples/quickplot_from_yaml.py
"""

import pandas as pd
from plotsigs import plot_signals, plot_signals_from_yaml

df = pd.read_csv("examples/compressor_sim_data.csv")


# ── Style 1: reference lines mixed into the signal list ───────────────────────
#
#   Numbers in the list are pulled out as dashed horizontal reference lines.
#   Handy for quick one-liners where you already know the setpoint bounds.

plot_signals(
    df,
    groups=[
        ["AC_Set_Speed", "Compressor_Running_Speed", 800, 8000],  # 800 / 8000 → ref lines
        ["AC_Enable", "DrvrOut_IsRunOk", "IsActVld"],
        ["Board_Temp", "DC_Bus_Voltage"],
    ],
    title="Compressor — inline reference lines",
    figsize=(14, 9),
    output="output/quickplot_ref_inline.png",
    show=False,
)


# ── Style 2: simple quickplot YAML ────────────────────────────────────────────
#
#   Load the full layout from quickplot_config.yaml.  The file controls titles,
#   figsize, signal groups, ref_lines with custom labels/colours, and mode.
#   Keyword arguments passed here override anything in the YAML.

plot_signals_from_yaml(
    df,
    "examples/quickplot_config.yaml",
    output="output/quickplot_from_yaml.png",
    show=False,
)


# ── Style 3: catalog / preset YAML ────────────────────────────────────────────
#
#   A catalog file can contain many named presets under plot_presets:.
#   Select the one you want with preset=.  Useful for a shared signal catalog
#   where different engineers define their own preset views.

CATALOG_YAML = """\
plot_presets:
  speed_overview:
    description: "Speed signals with operating limits"
    plot_groups:
      - name: "Speed [RPM]"
        signals: ["AC_Set_Speed", "Compressor_Running_Speed"]
        ref_lines: [800, 8000]
      - name: "Control flags"
        signals: ["AC_Enable", "DrvrOut_IsRunOk", "IsActVld"]
        mode: digital

  thermal_check:
    description: "Thermal and bus voltage"
    plot_groups:
      - name: "Board temp [°C]"
        signals: ["Board_Temp"]
        ref_lines:
          - value: 85
            label: "TRIP"
            color: "#e74c3c"
      - name: "DC bus [V]"
        signals: ["DC_Bus_Voltage"]
"""

import tempfile, pathlib

with tempfile.NamedTemporaryFile(
    mode="w", suffix=".yaml", delete=False, encoding="utf-8"
) as f:
    f.write(CATALOG_YAML)
    catalog_path = f.name

plot_signals_from_yaml(
    df,
    catalog_path,
    preset="speed_overview",
    figsize=(14, 7),
    output="output/quickplot_preset_speed.png",
    show=False,
)

plot_signals_from_yaml(
    df,
    catalog_path,
    preset="thermal_check",
    figsize=(14, 6),
    output="output/quickplot_preset_thermal.png",
    show=True,
)

pathlib.Path(catalog_path).unlink(missing_ok=True)
