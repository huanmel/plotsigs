"""
render_spec — universal PlotSpec → Figure entry point.

A PlotSpec is a plain Python dict that any caller can assemble and hand to
``render_spec()`` without touching the Diagram / SignalGroup fluent API.

PlotSpec format
---------------

    spec = {
        "meta": {
            "title":    "Run #42",
            "caption":  "Cold start, -20 °C",
            # All time/size keys are optional — auto-derived from data when omitted.
            "t_start":  0.0,        # default: min of all time columns
            "t_end":    120.0,      # default: max of all time columns
            "n_points": 2000,       # default: max(len(df)) across sources
            "figsize":  [14, 8],
            "xlabel":   "Time [s]",
            # Any extra keys (run_id, date, …) are stored but not rendered.
        },

        # Named DataFrames — each may carry its own time column.
        "data": {
            "sim":  {"df": sim_df,  "time_col": "t"},
            "meas": {"df": meas_df, "time_col": "timestamp"},
        },
        # Shorthand when there is only one source (time_col defaults to "time"):
        # "data": my_df

        "groups": [
            {
                "ylabel": "Speed [RPM]",
                "mode":   "analog",     # or "digital"; default "analog"
                "signals": [
                    # Measured column from a named source:
                    {"name": "Set Speed",    "source": "sim",  "column": "speed_cmd"},
                    {"name": "Actual Speed", "source": "meas", "column": "motor_rpm"},
                    # Auto-detected as measured when source/column present (no type needed):
                    {"name": "Coolant T",    "source": "meas", "column": "coolant_t"},
                    # Synthetic types (same vocabulary as the YAML loader):
                    {"name": "Min Limit",    "type": "stepped",  "breakpoints": [[0, 800]]},
                    {"name": "Response Lag", "type": "lagged",   "source": "Set Speed", "tau": 2.0},
                    {"name": "Error",        "type": "derived",  "a": "Set Speed", "b": "Actual Speed"},
                    {"name": "Raw Sig",      "type": "raw",      "data": [[0, 0], [10, 1]]},
                ],
                # Horizontal reference lines (quickplot-style shorthand):
                "ref_lines": [800, 8500],
                # or with labels:  [{"value": 800, "label": "MIN", "color": "#3498db"}]
                # Explicit thresholds (same as YAML):
                "thresholds": [{"value": 9000, "label": "MAX"}],
                # Per-group annotations (tolerance, callout, transient_analysis):
                "annotations": [
                    {"type": "transient_analysis",
                     "reference": "Set Speed", "feedback": "Actual Speed",
                     "tolerance_pct": 5.0},
                ],
            },
            {
                "mode":   "digital",
                "ylabel": "Flags",
                "signals": [
                    # Measured 0/1 column — auto-detected as digital when mode=="digital":
                    {"name": "Fault Active", "source": "meas", "column": "fault_flag"},
                    # Explicit type also accepted:
                    {"name": "Pump On", "type": "measured_digital",
                     "source": "meas", "column": "pump_en"},
                    # Breakpoint-based digital lane:
                    {"name": "Enable", "type": "digital",
                     "breakpoints": [[0, 0], [5, 1], [50, 0]]},
                ],
            },
        ],

        # Diagram-level annotations (phase, vline, vspan) — same as YAML format:
        "annotations": [
            {"type": "phase",  "t0": 0,  "t1": 30, "label": "Startup", "status": "pass"},
            {"type": "vline",  "t": 15,  "label": "Step 1"},
            {"type": "vspan",  "t0": 5,  "t1": 10, "label": "Warm-up"},
        ],
    }

    fig = plotsigs.render_spec(spec)
    fig = plotsigs.render_spec(spec, output="run42.png", show=False)

Note on the ``source`` field
-----------------------------
- For ``type == "lagged"``, ``source`` is the **signal name** of the upstream signal.
- For measured signals (no type, or type ``"measured"`` / ``"measured_digital"``),
  ``source`` is the **DataFrame key** in ``spec["data"]``.
The ``type`` field disambiguates the two uses.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Union

import numpy as np


# ── Public API ────────────────────────────────────────────────────────────────

def render_spec(
    spec: dict,
    output: Union[str, Path, List, None] = None,
    show: bool = True,
    dpi: int = 150,
) -> object:
    """
    Render a PlotSpec dict to a matplotlib Figure.

    Parameters
    ----------
    spec : dict
        PlotSpec with optional keys: meta, data, groups, annotations.
        See module docstring for the full format.
    output : str, Path, or list, optional
        Save path(s). Format inferred from extension (.png, .svg).
    show : bool
        Call plt.show() after rendering (default True).
    dpi : int
        Resolution for raster output (default 150).

    Returns
    -------
    matplotlib.figure.Figure
    """
    from .diagram import Diagram
    from .loader import (
        _build_phase_map,
        _load_diagram_annotations,
        _load_group_annotations,
        _load_group_thresholds,
    )

    meta = spec.get("meta", {})

    data_map = _normalise_data(spec.get("data", {}))
    t_start, t_end, n_points = _resolve_time_params(meta, data_map)

    _DIAGRAM_KEYS = {
        "title", "analog_ratio", "digital_ratio", "ylabel_analog",
        "xlabel", "caption", "caption_fontsize",
    }
    d_kwargs = {k: v for k, v in meta.items() if k in _DIAGRAM_KEYS}
    d_kwargs.update(t_start=t_start, t_end=t_end, n_points=n_points)
    if "figsize" in meta:
        d_kwargs["figsize"] = tuple(meta["figsize"])

    d = Diagram(**d_kwargs)

    phase_map = _build_phase_map(spec.get("annotations", []))

    for grp_cfg in spec.get("groups", []):
        mode   = grp_cfg.get("mode", "analog").lower()
        ylabel = grp_cfg.get("ylabel", "")

        if mode == "digital":
            grp = d.add_digital_group(ylabel)
            for sig_cfg in grp_cfg.get("signals", []):
                _load_digital_signal(grp, sig_cfg, data_map)
        else:
            grp = d.add_group(ylabel or "Value")
            for sig_cfg in grp_cfg.get("signals", []):
                _load_analog_signal(grp, sig_cfg, d._signal_map, data_map)
            _load_group_thresholds(grp, grp_cfg.get("thresholds", []))
            _load_ref_lines(grp, grp_cfg.get("ref_lines", []))
            _load_group_annotations(grp, grp_cfg.get("annotations", []), phase_map)

    _load_diagram_annotations(d, spec.get("annotations", []))

    return d.render(output=output, show=show, dpi=dpi)


# ── Data normalisation ────────────────────────────────────────────────────────

def _normalise_data(raw: object) -> dict:
    """
    Return {source_name: {"df": DataFrame, "time_col": str}}.

    Accepted input:
    - bare DataFrame → {"_default": {"df": df, "time_col": "time"}}
    - dict of bare DataFrames → each wrapped with time_col="time"
    - dict of {"df": ..., "time_col": ...} → passed through
    - None or {} → {}
    """
    if raw is None or (isinstance(raw, dict) and not raw):
        return {}

    try:
        import pandas as pd
    except ImportError:
        pd = None  # type: ignore[assignment]

    if pd is not None and isinstance(raw, pd.DataFrame):
        return {"_default": {"df": raw, "time_col": "time"}}

    if not isinstance(raw, dict):
        raise TypeError(
            f"PlotSpec 'data' must be a DataFrame or dict, got {type(raw).__name__}"
        )

    result: dict = {}
    for key, value in raw.items():
        if pd is not None and isinstance(value, pd.DataFrame):
            result[key] = {"df": value, "time_col": "time"}
        elif isinstance(value, dict):
            if "df" not in value:
                raise ValueError(
                    f"PlotSpec data source '{key}' must have a 'df' key. "
                    "Use: {'df': my_df, 'time_col': 'time'}"
                )
            result[key] = {"df": value["df"], "time_col": value.get("time_col", "time")}
        else:
            raise TypeError(
                f"PlotSpec data source '{key}' must be a DataFrame or "
                "{'df': DataFrame, 'time_col': str}."
            )
    return result


def _resolve_time_params(meta: dict, data_map: dict):
    """Return (t_start, t_end, n_points), auto-deriving from data when absent from meta."""
    t_start  = float(meta["t_start"])  if "t_start"  in meta else None
    t_end    = float(meta["t_end"])    if "t_end"    in meta else None
    n_points = int(meta["n_points"])   if "n_points" in meta else None

    if data_map and (t_start is None or t_end is None or n_points is None):
        time_series = [
            src["df"][src["time_col"]]
            for src in data_map.values()
            if src["time_col"] in src["df"].columns
        ]
        if time_series:
            if t_start  is None: t_start  = float(min(s.min() for s in time_series))
            if t_end    is None: t_end    = float(max(s.max() for s in time_series))
            if n_points is None: n_points = max(len(s) for s in time_series)

    if t_start  is None: t_start  = 0.0
    if t_end    is None: t_end    = 60.0
    if n_points is None: n_points = 2000

    return t_start, t_end, n_points


# ── Signal building ───────────────────────────────────────────────────────────

_SKIP_SYNTHETIC = frozenset({"type", "name", "breakpoints", "source", "tau", "data"})
_SKIP_MEASURED  = frozenset({"type", "name", "source", "column"})
_SKIP_DERIVED   = frozenset({"type", "name", "a", "b"})


def _resolve_df(sig_cfg: dict, data_map: dict):
    """Return (df, time_col) for a measured signal spec."""
    source_key = sig_cfg.get("source", "_default")
    if source_key not in data_map:
        raise ValueError(
            f"Signal '{sig_cfg.get('name', '?')}' references unknown source '{source_key}'. "
            f"Known sources: {list(data_map)}"
        )
    entry = data_map[source_key]
    return entry["df"], entry["time_col"]


def _load_analog_signal(grp, sig_cfg: dict, signal_map: dict, data_map: dict) -> None:
    name     = sig_cfg["name"]
    sig_type = sig_cfg.get("type", "").lower()

    if not sig_type and ("source" in sig_cfg or "column" in sig_cfg):
        sig_type = "measured"

    if sig_type == "stepped":
        bp    = [tuple(p) for p in sig_cfg["breakpoints"]]
        extra = {k: v for k, v in sig_cfg.items() if k not in _SKIP_SYNTHETIC}
        grp.add_stepped(name, bp, **extra)

    elif sig_type == "lagged":
        source_name = sig_cfg["source"]
        if source_name not in signal_map:
            raise ValueError(
                f"Lagged signal '{name}' references unknown source signal '{source_name}'. "
                "Declare the source signal before the lagged one."
            )
        tau   = float(sig_cfg.get("tau", 1.5))
        extra = {k: v for k, v in sig_cfg.items() if k not in _SKIP_SYNTHETIC}
        grp.add_lagged(name, signal_map[source_name], tau=tau, **extra)

    elif sig_type == "raw":
        data  = np.array(sig_cfg["data"], dtype=float)
        extra = {k: v for k, v in sig_cfg.items() if k not in _SKIP_SYNTHETIC}
        grp.add_raw(name, data[:, 0], data[:, 1], **extra)

    elif sig_type == "derived":
        extra = {k: v for k, v in sig_cfg.items() if k not in _SKIP_DERIVED}
        grp.add_derived(name, sig_cfg["a"], sig_cfg["b"], **extra)

    elif sig_type in ("measured", ""):
        if not data_map:
            raise ValueError(
                f"Signal '{name}' has no type, source, or column. "
                "Add 'type' (stepped/lagged/etc.) or provide 'source'/'column' for measured data."
            )
        df, time_col = _resolve_df(sig_cfg, data_map)
        col   = sig_cfg.get("column")
        extra = {k: v for k, v in sig_cfg.items() if k not in _SKIP_MEASURED}
        grp.add_measured(name, df, time_col=time_col, value_col=col, **extra)

    else:
        raise ValueError(
            f"Unknown signal type '{sig_type}' for signal '{name}'. "
            "Supported: stepped, lagged, raw, measured, derived."
        )


def _load_digital_signal(grp, sig_cfg: dict, data_map: dict) -> None:
    name     = sig_cfg["name"]
    sig_type = sig_cfg.get("type", "").lower()

    if not sig_type and ("source" in sig_cfg or "column" in sig_cfg):
        sig_type = "measured_digital"
    if not sig_type:
        sig_type = "digital"

    if sig_type == "measured_digital":
        df, time_col = _resolve_df(sig_cfg, data_map)
        col   = sig_cfg.get("column")
        extra = {k: v for k, v in sig_cfg.items() if k not in _SKIP_MEASURED}
        grp.add_measured_digital(name, df, time_col=time_col, value_col=col, **extra)

    else:  # "digital" or unrecognised — breakpoint-based
        bp    = [tuple(p) for p in sig_cfg["breakpoints"]]
        extra = {k: v for k, v in sig_cfg.items() if k not in {"type", "name", "breakpoints"}}
        grp.add_digital(name, bp, **extra)


def _load_ref_lines(grp, ref_lines: list) -> None:
    """Convert quickplot-style ref_lines entries to group thresholds."""
    for entry in ref_lines:
        if isinstance(entry, (int, float)) and not isinstance(entry, bool):
            grp.add_threshold(float(entry))
        elif isinstance(entry, dict):
            value = float(entry["value"])
            extra = {k: v for k, v in entry.items() if k != "value"}
            grp.add_threshold(value, **extra)
