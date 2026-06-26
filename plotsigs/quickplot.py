"""
quickplot — high-level convenience API for DataFrame-driven plots.

Designed for quick exploration: pass a DataFrame + a list of signal groups,
get a fully formatted figure back.

    from plotsigs import plot_signals, plot_signals_from_yaml

    # From Python
    plot_signals(df, [
        ["AC_Set_Speed", "Compressor_Running_Speed", 800, 8500],  # numbers → ref lines
        ["AC_Enable", "DrvrOut_IsRunOk", "IsActVld"],
    ])

    # From a quickplot YAML
    plot_signals_from_yaml(df, "analysis.yaml")

    # From a signal catalog YAML (preset-based)
    plot_signals_from_yaml(df, "catalog.yaml", preset="thermal_control_sequence")
"""

from __future__ import annotations

from os.path import commonprefix
from pathlib import Path
from typing import List, Union, Optional, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    import pandas as pd
    import matplotlib.pyplot as plt

# Colour palette — cycles within each analog group
_COLORS = [
    "#2ecc71", "#e74c3c", "#3498db", "#e67e22", "#9b59b6",
    "#1abc9c", "#f39c12", "#2980b9", "#c0392b", "#8e44ad",
]

# Reference line colours — cycles across ref lines within a group
_REF_COLORS = ["#3498db", "#e74c3c", "#2ecc71", "#e67e22", "#9b59b6"]


def plot_signals(
    df: "pd.DataFrame",
    groups: List[Union[str, List, dict]],
    *,
    time_col: str = "time",
    title: str = "",
    figsize: Optional[tuple] = None,
    output: Union[str, Path, List, None] = None,
    show: bool = True,
    auto_digital: bool = True,
) -> "plt.Figure":
    """
    Build and render a multi-group signal plot from a DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Data with a time column and one column per signal.
    groups : list
        Ordered list of subplot specifications. Each element is one of:

        ``["col1", "col2"]``
            Column names; mode auto-detected from values.

        ``["col1", 800, 8500]``
            Mix of column names (str) and numbers. Numbers become dashed
            horizontal reference lines drawn on that subplot.

        ``"col1"``
            Single-column shorthand.

        ``{"signals": ["col1", "col2"],
           "ylabel":  "Speed [RPM]",
           "mode":    "analog" | "digital",
           "ref_lines": [800, 8500]}``
            Explicit config. ``ref_lines`` may be a list of plain values *or*
            dicts ``{"value": 800, "label": "MIN", "color": "#3498db"}``.

    time_col : str
        Name of the time column in *df* (default ``"time"``).
    title : str
        Figure title.
    figsize : tuple, optional
        ``(width, height)`` in inches. Defaults to ``(14, 3 × n_groups)``.
    output : str, Path, or list thereof, optional
        Save path(s) — PNG or SVG inferred from extension.
    show : bool
        Call ``plt.show()`` after rendering (default ``True``).
    auto_digital : bool
        When ``True`` (default), groups whose every signal contains only
        0 and 1 are rendered as digital stacked lanes.

    Returns
    -------
    matplotlib.figure.Figure
    """
    from .spec import render_spec

    specs = _normalise(groups)
    plot_groups: list = []

    for spec in specs:
        sig_names = spec["signals"]
        ylabel    = spec.get("ylabel", "")
        mode      = spec.get("mode", None)
        ref_lines = spec.get("ref_lines", [])

        # Warn and skip missing columns
        missing = [s for s in sig_names if s not in df.columns]
        if missing:
            print(f"plot_signals: signals not in DataFrame, skipping: {missing}")
        sig_names = [s for s in sig_names if s in df.columns]
        if not sig_names and not ref_lines:
            continue

        # Auto-detect mode from values
        if mode is None:
            mode = "digital" if (auto_digital and _all_digital(df, sig_names)) else "analog"

        signal_specs = [
            {"name": name, "column": name, "color": _COLORS[i % len(_COLORS)]}
            for i, name in enumerate(sig_names)
        ]

        enriched_refs = [
            {
                "value": rl["value"],
                "label": rl.get("label", ""),
                "color": rl.get("color", _REF_COLORS[i % len(_REF_COLORS)]),
                "ls":    rl.get("ls", "--"),
                "lw":    rl.get("lw", 0.9),
            }
            for i, rl in enumerate(_normalise_ref_lines(ref_lines))
        ]

        plot_groups.append({
            "ylabel":    ylabel or (_auto_ylabel(sig_names) if mode != "digital" else ""),
            "mode":      mode,
            "signals":   signal_specs,
            "ref_lines": enriched_refs,
        })

    return render_spec(
        {
            "meta": {
                "title":    title,
                "figsize":  list(figsize or (14, max(5, 3 * len(plot_groups)))),
                "t_start":  float(df[time_col].min()),
                "t_end":    float(df[time_col].max()),
                "n_points": 2000,
            },
            "data": {"_default": {"df": df, "time_col": time_col}},
            "groups": plot_groups,
        },
        output=output,
        show=show,
    )


def plot_signals_from_yaml(
    df: "pd.DataFrame",
    path: Union[str, Path],
    preset: Optional[str] = None,
    **kwargs,
) -> "plt.Figure":
    """
    Load a quickplot configuration from YAML and render.

    Two YAML formats are supported:

    **Simple quickplot format** (``groups:`` key at top level)::

        title: My Analysis
        figsize: [14, 9]

        groups:
          - signals: ["AC_Set_Speed", "Compressor_Running_Speed"]
            ylabel: "Speed [RPM]"
            ref_lines: [800, 8500]
          - signals: ["AC_Enable", "IsActVld"]
            mode: digital

    **Signal catalog format** (``plot_presets:`` key, use *preset=* to pick one)::

        plot_presets:
          my_preset:
            description: "..."
            plot_groups:
              - name: "Speed signals"
                signals: ["AC_Set_Speed", "Compressor_Running_Speed"]
                ref_lines: [800, 8500]
              - name: "Control flags"
                signals: ["AC_Enable", "IsActVld"]

    Parameters
    ----------
    df : pd.DataFrame
        Measured data.
    path : str or Path
        Path to the YAML file.
    preset : str, optional
        Preset name — required when the YAML uses ``plot_presets:`` format.
    **kwargs
        Any ``plot_signals()`` keyword argument (``title``, ``figsize``,
        ``time_col``, ``output``, ``show``, ``auto_digital``).
        Caller values override values read from the YAML file.

    Returns
    -------
    matplotlib.figure.Figure
    """
    try:
        import yaml
    except ImportError as e:
        raise ImportError("PyYAML is required: pip install PyYAML") from e

    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # Build kwargs from YAML (caller kwargs take precedence)
    yaml_kw: dict = {}
    if "title"    in cfg: yaml_kw["title"]    = cfg["title"]
    if "figsize"  in cfg: yaml_kw["figsize"]  = tuple(cfg["figsize"])
    if "time_col" in cfg: yaml_kw["time_col"] = cfg["time_col"]
    yaml_kw.update(kwargs)

    # ── Simple quickplot format ────────────────────────────────────────────────
    if "groups" in cfg:
        groups = _groups_from_quickplot_yaml(cfg["groups"])
        return plot_signals(df, groups, **yaml_kw)

    # ── Catalog / preset format ────────────────────────────────────────────────
    if "plot_presets" in cfg:
        if preset is None:
            available = list(cfg["plot_presets"].keys())
            raise ValueError(
                f"YAML has plot_presets — specify preset=<name>. "
                f"Available: {available}"
            )
        preset_cfg = cfg["plot_presets"].get(preset)
        if preset_cfg is None:
            raise KeyError(f"Preset '{preset}' not found. "
                           f"Available: {list(cfg['plot_presets'].keys())}")

        if "title" not in yaml_kw:
            desc = preset_cfg.get("description", "")
            yaml_kw["title"] = f"{preset}" + (f" — {desc}" if desc else "")

        groups = _groups_from_preset_yaml(preset_cfg["plot_groups"])
        return plot_signals(df, groups, **yaml_kw)

    raise ValueError(
        "YAML must contain either a 'groups:' key (quickplot format) "
        "or a 'plot_presets:' key (catalog format)."
    )


# ── Normalisation helpers ─────────────────────────────────────────────────────

def _normalise(groups: list) -> list[dict]:
    """Convert any group spec to a uniform list of dicts with signals + ref_lines."""
    out = []
    for g in groups:
        if isinstance(g, str):
            out.append({"signals": [g], "ref_lines": []})

        elif isinstance(g, (list, tuple)):
            signals   = [x for x in g if isinstance(x, str)]
            ref_lines = [x for x in g if isinstance(x, (int, float))
                         and not isinstance(x, bool)]
            out.append({"signals": signals, "ref_lines": ref_lines})

        elif isinstance(g, dict):
            if "signals" not in g:
                raise ValueError(f"Group dict missing 'signals' key: {g!r}")
            # ref_lines may already be in the dict
            out.append({**g, "ref_lines": g.get("ref_lines", [])})

        else:
            raise TypeError(f"Invalid group spec: {g!r}")
    return out


def _normalise_ref_lines(ref_lines: list) -> list[dict]:
    """Convert plain values or dicts to uniform ref-line dicts."""
    out = []
    for rl in ref_lines:
        if isinstance(rl, (int, float)):
            out.append({"value": float(rl)})
        elif isinstance(rl, dict):
            out.append(rl)
        else:
            raise TypeError(f"Invalid ref_line spec: {rl!r}")
    return out


def _groups_from_quickplot_yaml(yaml_groups: list) -> list[dict]:
    """Parse the ``groups:`` list from a simple quickplot YAML."""
    out = []
    for g in yaml_groups:
        signals   = []
        ref_lines = []
        for item in g.get("signals", []):
            if isinstance(item, str):
                signals.append(item)
            elif isinstance(item, (int, float)):
                ref_lines.append(item)
        ref_lines.extend(g.get("ref_lines", []))   # also accept separate key
        out.append({
            "signals":   signals,
            "ref_lines": ref_lines,
            "ylabel":    g.get("ylabel", g.get("name", "")),
            "mode":      g.get("mode", None),
        })
    return out


def _groups_from_preset_yaml(plot_groups: list) -> list[dict]:
    """Parse the ``plot_groups:`` list from a catalog preset."""
    out = []
    for g in plot_groups:
        signals   = []
        ref_lines = []
        for item in g.get("signals", []):
            if isinstance(item, str):
                signals.append(item)
            elif isinstance(item, (int, float)):
                ref_lines.append(item)
        ref_lines.extend(g.get("ref_lines", []))
        out.append({
            "signals":   signals,
            "ref_lines": ref_lines,
            "ylabel":    g.get("name", g.get("ylabel", "")),
            "mode":      g.get("mode", None),
        })
    return out


# ── Detection helpers ─────────────────────────────────────────────────────────

def _all_digital(df: "pd.DataFrame", col_names: list) -> bool:
    """True if every listed column contains only 0 and 1 values."""
    for name in col_names:
        vals = df[name].dropna()
        if len(vals) == 0:
            continue
        unique = np.unique(vals.values.astype(float))
        if not np.all(np.isin(unique, [0.0, 1.0])):
            return False
    return True


def _auto_ylabel(signals: list) -> str:
    """Derive a y-axis label from signal names via common prefix."""
    if len(signals) == 1:
        return signals[0]
    prefix = commonprefix(signals).rstrip("_.")
    return prefix if len(prefix) >= 3 else ""
