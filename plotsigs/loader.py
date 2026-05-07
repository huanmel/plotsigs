"""
YAML loader — create a Diagram from a declarative config file.

Two supported formats:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NEW FORMAT  (groups:)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Synthetic signals only:

    title: My Diagram
    time_end: 62

    groups:
      - ylabel: "Speed [RPM]"
        mode: analog            # optional, default "analog"
        signals:
          - name: Set Speed
            type: stepped
            breakpoints: [[0, 1000], [10, 8500], [22, 1000]]
            color: "#2ecc71"
          - name: Running Speed
            type: lagged
            source: Set Speed
            tau: 1.8
            color: "#e74c3c"
          - name: Error
            type: derived       # a − b (default op)
            a: Set Speed
            b: Running Speed
            color: "#8e44ad"
        thresholds:
          - value: 1500
            label: MIN
            color: "#3498db"
        annotations:            # group-level: tolerance, callout, transient_analysis
          - type: tolerance
            signal: Set Speed
            tolerance: 400
          - type: callout
            signal: Running Speed
            t: 26
            label: Peak speed
            offset: [-4, 400]
          - type: transient_analysis   # by time window
            reference: Set Speed
            feedback: Running Speed
            tolerance_pct: 5.0
            after_t: 10.0
            before_t: 22.0
          - type: transient_analysis   # or by phase label (defined in annotations:)
            reference: Set Speed
            feedback: Running Speed
            tolerance_pct: 5.0
            phase: ACTIVE / RAMP

      - ylabel: "Control flags"
        mode: digital
        signals:
          - name: AC_Enable
            breakpoints: [[0, 1], [2, 0], [5, 1]]
          - name: IsActVld
            breakpoints: [[0, 0], [12, 1], [21, 0]]
            color: "#8e44ad"

    annotations:                # diagram-level: vspan, vline, phase
      - type: vspan
        t0: 10
        t1: 12
        label: STARTUP window
        color: "#f39c12"
      - type: vline
        t: 21
        label: Fault detected
        color: "#c0392b"
      - type: phase
        t0: 0
        t1: 10
        label: IDLE

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXTERNAL DATA  (csv:)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    title: Compressor log
    # time_end is optional — auto-derived from CSV max time when omitted

    csv:
      file: examples/compressor_real_data_log_1.csv
      time_col: timestamps      # default: "time"

    groups:
      - ylabel: "Speed [RPM]"
        signals:
          - name: AC_Set_Speed
            type: measured      # → add_measured(); column defaults to signal name
            color: "#2ecc71"
          - name: Running Speed
            type: measured
            column: EC1_Compressor_Running_Speed   # explicit column override
            color: "#e74c3c"
          - name: Error
            type: derived
            a: AC_Set_Speed
            b: Running Speed
            color: "#8e44ad"
        annotations:
          - type: transient_analysis
            reference: AC_Set_Speed
            feedback: Running Speed
            tolerance_pct: 5.0
            phase: STARTUP

      - ylabel: "Digital flags"
        mode: digital
        signals:
          - name: AC_Enable_Disable_Compressor
            type: measured_digital    # → add_measured_digital()
            color: "#2980b9"
          - name: AcDrvrIsRunOk
            type: measured_digital
            color: "#27ae60"

    annotations:
      - type: phase
        t0: 0
        t1: 14
        label: IDLE
      - type: phase
        t0: 14
        t1: 19
        label: STARTUP

    # Per-signal file override (when mixing multiple CSV files):
    #   - name: Sensor B
    #     type: measured
    #     file: other_log.csv   # overrides top-level csv.file
    #     time_col: ts          # overrides top-level csv.time_col
    #     column: sensor_b

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LEGACY FORMAT  (analog: / digital:)   — still fully supported
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    title: My Diagram
    time_end: 62

    analog:
      - name: Set Speed
        type: stepped
        breakpoints: [[0, 1000], [10, 8500], [22, 1000]]

    digital:
      - name: AC_Enable
        breakpoints: [[0, 1], [2, 0], [5, 1]]

    thresholds:
      - value: 1500
        label: MIN

    annotations:
      - type: vspan
        t0: 10
        t1: 12
        label: STARTUP window
      - type: vline
        t: 21
        label: Fault detected
"""

from __future__ import annotations

from pathlib import Path
from typing import Union, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from .diagram import Diagram, SignalGroup


def load_yaml(path: Union[str, Path],
              overrides: Union[dict, None] = None,
              data=None) -> "Diagram":
    """
    Load a Diagram from a YAML config file.

    Supports both the new ``groups:`` format and the legacy
    ``analog:`` / ``digital:`` flat format.  External data can be
    loaded via a top-level ``csv:`` block or passed directly via
    the ``data=`` parameter.

    Parameters
    ----------
    path : str or Path
        Path to the .yaml file.  Relative paths inside the YAML (e.g.
        ``csv.file``) are resolved relative to this file's directory.
    overrides : dict, optional
        Top-level keys that replace the corresponding keys in the YAML
        before processing.  Useful for batch workflows where a shared
        template defines signal layout and analysis config, while each
        run supplies the title and phase annotations::

            d = load_yaml("template.yaml", data=df, overrides={
                "title": "Run 001",
                "annotations": [
                    {"type": "phase", "t0": 0,  "t1": 12, "label": "IDLE"},
                    {"type": "phase", "t0": 12, "t1": 18, "label": "STARTUP"},
                ],
            })

    data : DataFrame, optional
        Pre-loaded DataFrame to use as the default signal source.  Takes
        precedence over any ``csv.file`` in the YAML or overrides.  The
        template still reads ``csv.time_col`` to know which column is the
        time axis.  This lets you load from any source (Parquet, HDF5,
        SQL, simulation output, …) before calling ``load_yaml``::

            df = pd.read_parquet("run_001.parquet")
            d  = load_yaml("template.yaml", data=df, overrides={...})

    Returns
    -------
    Diagram
        Ready to call .render() on.
    """
    try:
        import yaml
    except ImportError as e:
        raise ImportError("PyYAML is required for load_yaml: pip install PyYAML") from e

    from .diagram import Diagram

    path = Path(path)
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    if overrides:
        cfg.update(overrides)

    # ── CSV context (may be empty) ────────────────────────────────────────────
    csv_ctx = _build_csv_ctx(cfg.get("csv", {}), base_dir=path.parent,
                             injected_df=data)

    # ── Diagram metadata ──────────────────────────────────────────────────────
    d_kwargs: dict = {}
    if "title"      in cfg: d_kwargs["title"]    = cfg["title"]
    if "time_start" in cfg: d_kwargs["t_start"]  = float(cfg["time_start"])
    if "n_points"   in cfg: d_kwargs["n_points"] = int(cfg["n_points"])
    if "figsize"    in cfg: d_kwargs["figsize"]  = tuple(cfg["figsize"])
    if "xlabel"     in cfg: d_kwargs["xlabel"]   = cfg["xlabel"]

    if "time_end" in cfg:
        d_kwargs["t_end"] = float(cfg["time_end"])
    elif csv_ctx["default_df"] is not None:
        # Auto-derive t_end from the CSV time column when not specified
        d_kwargs["t_end"] = float(csv_ctx["default_df"][csv_ctx["time_col"]].max())

    d = Diagram(**d_kwargs)

    # Pre-pass: build {phase_label -> (t0, t1)} so group annotations can
    # reference phases by name before the diagram annotations are applied.
    phase_map = _build_phase_map(cfg.get("annotations", []))

    # ── Dispatch: grouped vs. legacy format ───────────────────────────────────
    if "groups" in cfg:
        _load_groups(d, cfg, phase_map, csv_ctx)
    else:
        _load_legacy(d, cfg, csv_ctx)

    # ── Diagram-level annotations (both formats share this) ───────────────────
    _load_diagram_annotations(d, cfg.get("annotations", []))

    return d


# ── CSV helpers ───────────────────────────────────────────────────────────────

def _build_csv_ctx(csv_cfg: dict, base_dir: Path, injected_df=None) -> dict:
    """
    Build the CSV context dict from the top-level ``csv:`` block.

    Returns a dict with keys:
        default_df   — pre-loaded default DataFrame (or None)
        time_col     — default time column name
        base_dir     — directory for resolving relative paths
        df_cache     — {abs_path_str: DataFrame} for per-signal overrides
    """
    ctx: dict = {
        "default_df": None,
        "time_col":   csv_cfg.get("time_col", "time"),
        "base_dir":   base_dir,
        "df_cache":   {},
    }
    if injected_df is not None:
        # Caller-supplied DataFrame takes precedence over any csv.file entry
        ctx["default_df"] = injected_df
    elif "file" in csv_cfg:
        p = (base_dir / csv_cfg["file"]).resolve()
        df = _read_csv(p)
        ctx["df_cache"][str(p)] = df
        ctx["default_df"] = df
    return ctx


def _read_csv(path: Path):
    try:
        import pandas as pd
    except ImportError as e:
        raise ImportError("pandas is required for CSV signal loading: pip install pandas") from e
    return pd.read_csv(path)


def _resolve_df(sig_cfg: dict, csv_ctx: dict):
    """
    Return (DataFrame, time_col) for a signal.

    Uses per-signal ``file`` / ``time_col`` overrides when present,
    otherwise falls back to the top-level CSV context.
    """
    time_col = sig_cfg.get("time_col", csv_ctx["time_col"])

    if "file" in sig_cfg:
        p = (csv_ctx["base_dir"] / sig_cfg["file"]).resolve()
        key = str(p)
        if key not in csv_ctx["df_cache"]:
            csv_ctx["df_cache"][key] = _read_csv(p)
        return csv_ctx["df_cache"][key], time_col

    if csv_ctx["default_df"] is not None:
        return csv_ctx["default_df"], time_col

    raise ValueError(
        "Signal type 'measured' / 'measured_digital' requires a CSV source. "
        "Add a top-level 'csv: file: ...' block or a per-signal 'file:' key."
    )


# ── Groups format ─────────────────────────────────────────────────────────────

def _build_phase_map(annotations: list) -> dict:
    """Return {label: (t0, t1)} for all phase entries in diagram-level annotations."""
    result: dict = {}
    for ann in annotations:
        if ann.get("type", "").lower() == "phase" and "label" in ann:
            result[ann["label"]] = (float(ann["t0"]), float(ann["t1"]))
    return result


def _load_groups(d: "Diagram", cfg: dict, phase_map: dict, csv_ctx: dict) -> None:
    for grp_cfg in cfg.get("groups", []):
        mode   = grp_cfg.get("mode", "analog").lower()
        ylabel = grp_cfg.get("ylabel", "")

        if mode == "digital":
            grp = d.add_digital_group(ylabel)
            _load_digital_signals(grp, grp_cfg.get("signals", []), csv_ctx)
        else:
            grp = d.add_group(ylabel or "Value")
            _load_analog_signals(grp, grp_cfg.get("signals", []), d._signal_map, csv_ctx)
            _load_group_thresholds(grp, grp_cfg.get("thresholds", []))
            _load_group_annotations(grp, grp_cfg.get("annotations", []), phase_map)


# ── Legacy format ─────────────────────────────────────────────────────────────

def _load_legacy(d: "Diagram", cfg: dict, csv_ctx: dict) -> None:
    grp = d._groups[0]   # default group 0

    _load_analog_signals(grp, cfg.get("analog", []), d._signal_map, csv_ctx)
    _load_group_thresholds(grp, cfg.get("thresholds", []))

    # legacy digital goes to implicit digital group at the end
    dig_grp = None
    for sig_cfg in cfg.get("digital", []):
        if dig_grp is None:
            dig_grp = d._implicit_digital_group()
        sig_type = sig_cfg.get("type", "digital").lower()
        name = sig_cfg["name"]
        if sig_type == "measured_digital":
            df, time_col = _resolve_df(sig_cfg, csv_ctx)
            col   = sig_cfg.get("column")
            extra = {k: v for k, v in sig_cfg.items()
                     if k not in ("type", "name", "file", "time_col", "column")}
            dig_grp.add_measured_digital(name, df, time_col=time_col,
                                         value_col=col, **extra)
        else:
            bp    = [tuple(p) for p in sig_cfg["breakpoints"]]
            extra = {k: v for k, v in sig_cfg.items() if k not in ("name", "breakpoints")}
            dig_grp.add_digital(name, bp, **extra)


# ── Signal loaders ────────────────────────────────────────────────────────────

_SKIP_SYNTHETIC = {"type", "name", "breakpoints", "source", "tau", "data"}
_SKIP_MEASURED  = {"type", "name", "file", "time_col", "column"}
_SKIP_DERIVED   = {"type", "name", "a", "b"}


def _load_analog_signals(grp: "SignalGroup", signals: list,
                         signal_map: dict, csv_ctx: dict) -> None:
    for sig_cfg in signals:
        sig_type = sig_cfg.get("type", "stepped").lower()
        name     = sig_cfg["name"]

        if sig_type == "stepped":
            bp    = [tuple(p) for p in sig_cfg["breakpoints"]]
            extra = {k: v for k, v in sig_cfg.items() if k not in _SKIP_SYNTHETIC}
            grp.add_stepped(name, bp, **extra)

        elif sig_type == "lagged":
            source_name = sig_cfg["source"]
            if source_name not in signal_map:
                raise ValueError(
                    f"Lagged signal '{name}' references unknown source '{source_name}'. "
                    "Declare the source signal before the lagged one."
                )
            tau   = float(sig_cfg.get("tau", 1.5))
            extra = {k: v for k, v in sig_cfg.items() if k not in _SKIP_SYNTHETIC}
            grp.add_lagged(name, signal_map[source_name], tau=tau, **extra)

        elif sig_type == "raw":
            data  = np.array(sig_cfg["data"], dtype=float)
            extra = {k: v for k, v in sig_cfg.items() if k not in _SKIP_SYNTHETIC}
            grp.add_raw(name, data[:, 0], data[:, 1], **extra)

        elif sig_type == "measured":
            df, time_col = _resolve_df(sig_cfg, csv_ctx)
            col   = sig_cfg.get("column")
            extra = {k: v for k, v in sig_cfg.items() if k not in _SKIP_MEASURED}
            grp.add_measured(name, df, time_col=time_col, value_col=col, **extra)

        elif sig_type == "derived":
            extra = {k: v for k, v in sig_cfg.items() if k not in _SKIP_DERIVED}
            grp.add_derived(name, sig_cfg["a"], sig_cfg["b"], **extra)

        else:
            raise ValueError(
                f"Unknown signal type '{sig_type}' for signal '{name}'. "
                "Supported: stepped, lagged, raw, measured, derived."
            )


def _load_digital_signals(grp: "SignalGroup", signals: list, csv_ctx: dict) -> None:
    for sig_cfg in signals:
        sig_type = sig_cfg.get("type", "digital").lower()
        name     = sig_cfg["name"]

        if sig_type == "measured_digital":
            df, time_col = _resolve_df(sig_cfg, csv_ctx)
            col   = sig_cfg.get("column")
            extra = {k: v for k, v in sig_cfg.items() if k not in _SKIP_MEASURED}
            grp.add_measured_digital(name, df, time_col=time_col, value_col=col, **extra)

        else:  # "digital" or unspecified — breakpoint-based
            bp    = [tuple(p) for p in sig_cfg["breakpoints"]]
            extra = {k: v for k, v in sig_cfg.items() if k not in ("type", "name", "breakpoints")}
            grp.add_digital(name, bp, **extra)


# ── Annotation loaders ────────────────────────────────────────────────────────

def _load_group_thresholds(grp: "SignalGroup", thresholds: list) -> None:
    for th in thresholds:
        extra = {k: v for k, v in th.items() if k not in ("value", "label")}
        grp.add_threshold(float(th["value"]), label=th.get("label", ""), **extra)


def _load_group_annotations(grp: "SignalGroup", annotations: list, phase_map: dict) -> None:
    """Load per-group annotations: tolerance, callout, transient_analysis."""
    for ann in annotations:
        ann_type = ann.get("type", "").lower()

        if ann_type == "tolerance":
            extra = {k: v for k, v in ann.items() if k not in ("type", "signal", "tolerance")}
            grp.add_tolerance(ann["signal"], float(ann["tolerance"]), **extra)

        elif ann_type == "callout":
            offset = tuple(ann["offset"]) if "offset" in ann else (-3.0, 500.0)
            extra  = {k: v for k, v in ann.items()
                      if k not in ("type", "signal", "t", "label", "offset")}
            grp.add_callout(ann["signal"], float(ann["t"]),
                            label=ann.get("label", ""), offset=offset, **extra)

        elif ann_type == "transient_analysis":
            _SKIP = {"type", "reference", "feedback", "phase", "after_t", "before_t"}
            after_t  = float(ann["after_t"])  if "after_t"  in ann else None
            before_t = float(ann["before_t"]) if "before_t" in ann else None
            if "phase" in ann:
                label = ann["phase"]
                if label not in phase_map:
                    raise ValueError(
                        f"transient_analysis references unknown phase '{label}'. "
                        f"Known phases: {list(phase_map)}"
                    )
                t0, t1 = phase_map[label]
                if after_t  is None: after_t  = t0
                if before_t is None: before_t = t1
            extra = {k: v for k, v in ann.items() if k not in _SKIP}
            grp.add_transient_analysis(
                ann["reference"], ann["feedback"],
                after_t=after_t, before_t=before_t,
                **extra,
            )

        else:
            raise ValueError(
                f"Unknown group-level annotation type '{ann_type}'. "
                "Group annotations support: tolerance, callout, transient_analysis. "
                "Use diagram-level annotations for: vspan, vline, phase."
            )


def _load_diagram_annotations(d: "Diagram", annotations: list) -> None:
    """Load diagram-level annotations: vspan, vline, phase."""
    for ann in annotations:
        ann_type = ann.get("type", "").lower()

        if ann_type == "vspan":
            extra = {k: v for k, v in ann.items() if k not in ("type", "t0", "t1", "label")}
            d.add_vspan(float(ann["t0"]), float(ann["t1"]),
                        label=ann.get("label", ""), **extra)

        elif ann_type == "vline":
            extra = {k: v for k, v in ann.items() if k not in ("type", "t", "label")}
            d.add_vline(float(ann["t"]), label=ann.get("label", ""), **extra)

        elif ann_type == "phase":
            extra = {k: v for k, v in ann.items() if k not in ("type", "t0", "t1", "label")}
            d.add_phase(float(ann["t0"]), float(ann["t1"]), ann.get("label", ""), **extra)

        else:
            raise ValueError(
                f"Unknown diagram-level annotation type '{ann_type}'. "
                "Supported: vspan, vline, phase."
            )
