"""
dash_app — full interactive Dash application for plotsigs Diagrams.

Three-pane layout (matching can_log_utils pattern):
  LEFT   — sticky sidebar: tool selector + tool controls + signal visibility + save
  CENTRE — scrollable signal subplots (height grows with subplot count)
  RIGHT  — sticky panel: analysis graph (diff/deriv) OR annotation manager

Entry point: run_dash(diagram, port=8050, debug=False)
"""

from __future__ import annotations

import logging
import pathlib
import numpy as np
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .diagram import Diagram

# Module-level logger — handlers are configured inside run_dash() so tests stay silent.
_log = logging.getLogger("plotsigs.dash")

try:
    from plotly_resampler import FigureResampler as _FigureResampler
    _RESAMPLER = True
except ImportError:
    _RESAMPLER = False

try:
    import dash_ag_grid as dag
    _AGGRID = True
except ImportError:
    dag = None  # type: ignore[assignment]
    _AGGRID = False

_RESAMPLE_THRESHOLD = 50_000  # points; above this, send only 2k samples to browser

# Mutable ref to the latest FigureResampler so the zoom callback always queries the
# most recently rebuilt figure without needing re-registration.
_fr_ref: list = [None]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _windowed_deriv(y: np.ndarray, t: np.ndarray, window: int) -> np.ndarray:
    """Centered finite-difference dy/dt over `window` samples; edges via np.gradient."""
    y = y.astype(float)
    t = t.astype(float)
    if window <= 1:
        return np.gradient(y, t)
    half = window // 2
    dy = np.empty_like(y)
    dy[half:-half] = (y[2 * half:] - y[:-2 * half]) / (t[2 * half:] - t[:-2 * half])
    dy[:half]  = np.gradient(y[:half * 2], t[:half * 2])[:half]
    dy[-half:] = np.gradient(y[-half * 2:], t[-half * 2:])[-half:]
    return dy


def _classify_traces(fig, d: "Diagram") -> list[dict]:
    """
    Map each trace in fig.data to its group and signal.
    Fills (hoverinfo='skip') → is_signal=False.
    Signal traces matched in add order: fills first per group, then signals.
    """
    active = [g for g in d._groups if g.signals]
    signal_order: list[tuple[int, object]] = []
    for gi, grp in enumerate(active):
        for sig in grp.signals:
            signal_order.append((gi, sig))

    meta = []
    sig_ptr = 0
    for tr in fig.data:
        is_fill = (
            getattr(tr, "hoverinfo", "") == "skip"
            or getattr(tr, "fill", "") in ("toself", "tonexty")
        )
        if is_fill:
            meta.append({"is_signal": False, "group_idx": None, "sig_name": None})
        elif sig_ptr < len(signal_order):
            gi, sig = signal_order[sig_ptr]
            meta.append({"is_signal": True, "group_idx": gi, "sig_name": sig.name})  # type: ignore[union-attr]
            sig_ptr += 1
        else:
            meta.append({"is_signal": False, "group_idx": None, "sig_name": None})
    return meta


def _find_nearest_signal(click_point, t, active, trace_meta=None):
    """
    Resolve clicked signal from clickData point.

    Primary path (ROAD-22): customdata=[[sig.name, group_idx], ...] per point.
    Fallback (ROAD-20 resampler): customdata absent → use curveNumber + trace_meta.

    Returns (signal_obj, y_at_x, group_idx).
    """
    cd = click_point.get("customdata") if isinstance(click_point, dict) else None
    if cd and len(cd) >= 2:
        sig_name = cd[0]
        group_idx = int(cd[1])
    elif trace_meta is not None:
        curve_num = int(click_point.get("curveNumber", 0))
        meta = trace_meta[curve_num] if 0 <= curve_num < len(trace_meta) else {}
        sig_name = meta.get("sig_name")
        group_idx = int(meta.get("group_idx") or 0)
    else:
        group_idx = 0
        sig_name = None

    if group_idx >= len(active):
        group_idx = len(active) - 1

    grp = active[group_idx]
    if not grp.signals:
        return None, 0.0, group_idx

    if sig_name:
        sig = next((s for s in grp.signals if s.name == sig_name), None)
    else:
        sig = None
    if sig is None:
        sig = grp.signals[0]

    x_click = float(click_point.get("x", 0.0))
    pos = int(np.argmin(np.abs(t - x_click)))

    is_digital = grp.mode == "digital"
    if is_digital:
        from .style import DIGITAL_LANE_HEIGHT as _LH, DIGITAL_SIGNAL_SCALE as _SC
        lane_idx = grp.signals.index(sig)
        y_at = float(sig.evaluate(t)[pos]) * _SC + lane_idx * _LH
    else:
        y_at = float(sig.evaluate(t)[pos])

    _log.debug("[find_nearest] customdata=%s group=%d → %s y=%.4g",
               cd, group_idx, sig.label or sig.name, y_at)
    return sig, y_at, group_idx


def _yaxis_ref(group_idx: int) -> str:
    """Plotly y-axis reference string for a given active-group index (0-based)."""
    return "y" if group_idx == 0 else f"y{group_idx + 1}"


def _overlay_annotations(fig, annotations, n_rows: int) -> None:
    """
    Replay stored user annotations onto fig in-place.

    Annotation dict format:
      Phase: {'type': 'phase', 'x': float, 'text': str, 'color': str}
      Point: {'type': 'point', 'x': float, 'y': float, 'yaxis': str,
               'signal': str, 'text': str, 'color': str}
    """
    _MAX_LABEL = 14
    for ann in (annotations or []):
        x     = ann["x"]
        text  = ann.get("text") or "★"
        color = ann.get("color", "#d62728")
        atype = ann.get("type", "phase")

        if atype == "phase":
            fig.add_vline(x=x, line_dash="dot", line_color=color, line_width=1.5)
            label = text[:_MAX_LABEL] + ("…" if len(text) > _MAX_LABEL else "")
            # Repeat label inside every subplot so it stays visible when scrolled
            for i in range(n_rows):
                yref = "y domain" if i == 0 else f"y{i + 1} domain"
                fig.add_annotation(
                    x=x, y=0.97,
                    xref="x", yref=yref,
                    text=label, showarrow=False,
                    textangle=-60, xanchor="left",
                    font=dict(size=9, color=color),
                    bgcolor="rgba(255,255,255,0.78)",
                    bordercolor=color, borderwidth=1, borderpad=2,
                )
        else:  # point note
            y    = ann.get("y", 0)
            yref = ann.get("yaxis", "y")    # actual y-axis ref stored at click time
            fig.add_annotation(
                x=x, y=y,
                xref="x", yref=yref,
                text=text, showarrow=True,
                arrowhead=2, arrowsize=1, arrowwidth=1.5, arrowcolor=color,
                ax=30, ay=-40,
                font=dict(size=10, color="#333"),
                bgcolor="rgba(255,255,255,0.92)",
                bordercolor=color, borderwidth=1.5, borderpad=4,
            )


def _groups_from_layout(layout_store, signal_map):
    """Build SimpleNamespace group objects from a layout-store list."""
    from types import SimpleNamespace
    groups = []
    for panel in (layout_store or []):
        sigs = [signal_map[n] for n in panel.get("signals", []) if n in signal_map]
        if sigs:
            groups.append(SimpleNamespace(
                ylabel=panel.get("ylabel", ""),
                mode=panel.get("mode", "analog"),
                signals=sigs,
                thresholds=[], tolerance_bands=[], pct_tolerance_bands=[],
                comparisons=[], callouts=[], event_durations=[],
            ))
    return groups


def _build_figure_from_layout(d, layout_store, use_gl=True, use_resampler=False):
    """Build a Plotly figure using layout-store panel assignments instead of d._groups."""
    import copy
    from .renderer_plotly import _build_figure
    d_tmp = copy.copy(d)
    d_tmp._groups = _groups_from_layout(layout_store, d._signal_map)
    return _build_figure(d_tmp, use_gl=use_gl, use_resampler=use_resampler)


def _legend_from_fig(fig, signal_map):
    """Extract legend entries [{idx, name, color}] from figure trace customdata."""
    entries = []
    for tidx, tr in enumerate(fig.data):
        cd = getattr(tr, "customdata", None)
        if cd is not None and len(cd) > 0:
            row0 = cd[0]
            if row0 is not None and len(row0) >= 2:
                sig_name = row0[0]
                sig_obj = signal_map.get(sig_name)
                if sig_obj:
                    entries.append({
                        "idx": tidx,
                        "name": sig_obj.label or sig_obj.name,
                        "color": sig_obj.color,
                    })
    return entries


def _build_main_figure(d, use_gl=True, tool=None, ann_type=None,
                       use_resampler=False, cursor_store=None,
                       sig_a_name=None, sig_b_name=None,
                       deriv_sig_name=None, deriv_window=11,
                       smooth_sig_name=None, smooth_window=11,
                       stored_annotations=None, visible_idxs=None,
                       layout_store=None):
    """
    Build the complete main figure, applying:
      - analysis overlay (customdata in hover tooltip for diff/deriv)
      - stored user annotations
      - trace visibility
    """
    from .renderer_plotly import _build_figure

    if layout_store:
        fig = _build_figure_from_layout(d, layout_store, use_gl=use_gl,
                                        use_resampler=use_resampler)
        active = _groups_from_layout(layout_store, d._signal_map)
    else:
        fig = _build_figure(d, use_gl=use_gl, use_resampler=use_resampler)
        active = [g for g in d._groups if g.signals]
    n_rows = len(active)
    t = d.t

    # Set figure height and hovermode based on tool
    heights = [260 if g.mode == "analog" else 100 for g in active]
    # "closest" only when a specific trace click is needed (delta, or point annotation).
    # Phase annotations (and all other tools) use "x unified" so any x-click fires clickData.
    hovermode = "closest" if (
        tool == "delta" or (tool == "annotate" and ann_type == "point")
    ) else "x unified"
    fig.update_layout(height=max(300, sum(heights) + 100), hovermode=hovermode)

    def _get_sig(name):
        for grp in active:
            for s in grp.signals:
                if (s.label or s.name) == name:
                    return s
        return None

    # ── Embed analysis values via update_traces(selector=) — no index loops ─
    if tool == "diff" and sig_a_name and sig_b_name:
        sa = _get_sig(sig_a_name)
        sb = _get_sig(sig_b_name)
        if sa and sb:
            diff_vals = (sa.evaluate(t) - sb.evaluate(t)).tolist()
            fig.update_traces(
                customdata=diff_vals,
                hovertemplate=(
                    "<b>%{fullData.name}</b><br>y=%{y:.4g}"
                    "<br><span style='color:#d62728'>Δ(A−B)=%{customdata:.4g}</span>"
                    "<extra></extra>"
                ),
                selector={"name": sa.label or sa.name},
            )
            fig.update_traces(
                customdata=[-v for v in diff_vals],
                hovertemplate=(
                    "<b>%{fullData.name}</b><br>y=%{y:.4g}"
                    "<br><span style='color:#d62728'>Δ(B−A)=%{customdata:.4g}</span>"
                    "<extra></extra>"
                ),
                selector={"name": sb.label or sb.name},
            )

    elif tool == "deriv" and deriv_sig_name:
        sa = _get_sig(deriv_sig_name)
        if sa:
            dy = _windowed_deriv(sa.evaluate(t), t, max(1, deriv_window or 11))
            fig.update_traces(
                customdata=dy.tolist(),
                hovertemplate=(
                    "<b>%{fullData.name}</b><br>y=%{y:.4g}"
                    "<br><span style='color:#ff7f0e'>dY/dt=%{customdata:.4g}</span>"
                    "<extra></extra>"
                ),
                selector={"name": sa.label or sa.name},
            )

    elif tool == "smooth" and smooth_sig_name:
        sa = _get_sig(smooth_sig_name)
        if sa:
            w = max(3, (smooth_window or 11) | 1)
            smoothed = np.convolve(sa.evaluate(t), np.ones(w) / w, mode="same")
            fig.update_traces(
                y=smoothed.tolist(),
                selector={"name": sa.label or sa.name},
            )

    # ── Overlay user annotations ───────────────────────────────────────────
    _overlay_annotations(fig, stored_annotations or [], n_rows)

    # ── Delta cursor snap lines ────────────────────────────────────────────
    if tool == "delta" and cursor_store:
        c1 = cursor_store.get("c1")
        c2 = cursor_store.get("c2")
        if c1 is not None:
            fig.add_vline(x=c1["x"],
                          line=dict(color="#2196F3", dash="dash", width=1.5))
        if c2 is not None:
            fig.add_vline(x=c2["x"],
                          line=dict(color="#FF9800", dash="dash", width=1.5))

    # ── Apply visibility ───────────────────────────────────────────────────
    if visible_idxs is not None:
        for i, tr in enumerate(fig.data):
            tr.update(visible=(i in visible_idxs))  # type: ignore[union-attr]

    return fig


# ── Main entry point ──────────────────────────────────────────────────────────

def run_dash(d: "Diagram", port: int = 8050, debug: bool = False) -> None:
    """
    Launch a full Dash application for an interactive Diagram session.

    Parameters
    ----------
    d : Diagram
        A fully configured plotsigs Diagram.
    port : int
        Port to run the Dash server on (default 8050).
    debug : bool
        Enable Dash debug mode.
    """
    try:
        import dash
        from dash import Dash, dcc, html, Input, Output, State, Patch, ctx, no_update, ALL
        import plotly.graph_objects as go
    except ImportError as exc:
        raise ImportError(
            "dash and plotly are required: pip install 'plotsigs[dash]'"
        ) from exc

    # ── Debug logging: terminal + file ────────────────────────────────────────
    _log_dir = pathlib.Path(__file__).parent.parent / "temp"
    _log_dir.mkdir(exist_ok=True)
    _log_path = _log_dir / "dash_debug.log"
    _fh = logging.FileHandler(_log_path, mode="w", encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%H:%M:%S"))
    _log.handlers.clear()
    _log.addHandler(_fh)
    _log.addHandler(logging.StreamHandler())
    _log.setLevel(logging.DEBUG)
    _log.info("plotsigs Dash debug log → %s", _log_path)

    from .renderer_plotly import _build_figure

    t = d.t
    active = [g for g in d._groups if g.signals]
    n_rows = len(active)

    # ── Resampler: use when dataset is large and library is available ─────────
    use_resampler = _RESAMPLER and len(t) > _RESAMPLE_THRESHOLD

    # ── Trace metadata & legend entries ───────────────────────────────────────
    # _base_fig is always built without resampler so _classify_traces sees
    # customdata (which resampler traces omit).
    _base_fig = _build_figure(d)
    trace_meta = _classify_traces(_base_fig, d)

    legend_entries: list[dict] = []
    for tidx, meta in enumerate(trace_meta):
        if meta["is_signal"]:
            grp = active[meta["group_idx"]]
            sig_obj = next((s for s in grp.signals if s.name == meta["sig_name"]), None)
            if sig_obj:
                legend_entries.append({
                    "idx": tidx,
                    "name": sig_obj.label or sig_obj.name,
                    "color": sig_obj.color,
                })

    all_sig_names = [e["name"] for e in legend_entries]
    default_a = all_sig_names[0] if all_sig_names else None
    default_b = all_sig_names[1] if len(all_sig_names) > 1 else default_a
    sig_options = [{"label": s, "value": s} for s in all_sig_names]

    # Layout-store: initial value mirrors d._groups
    initial_layout_store = [
        {"ylabel": grp.ylabel, "mode": grp.mode, "signals": [sig.name for sig in grp.signals]}
        for grp in active
    ]

    # Ordered list of all signals (spec order, deduped) — used for rowData
    _seen_sigs: set = set()
    all_signals_ordered = []
    for _grp in active:
        for _sig in _grp.signals:
            if _sig.name not in _seen_sigs:
                all_signals_ordered.append(_sig)
                _seen_sigs.add(_sig.name)

    # Map signal name → type label ("A" / "D") from original spec grouping
    _sig_type_map: dict = {}
    for _grp in active:
        _type_label = "D" if _grp.mode == "digital" else "A"
        for _sig in _grp.signals:
            _sig_type_map.setdefault(_sig.name, _type_label)

    # Precompute per-signal min/max once so _update_library_rows stays fast
    _sig_stats: dict[str, tuple[float, float]] = {}
    for _s in all_signals_ordered:
        _v = _s.evaluate(t)
        _sig_stats[_s.name] = (float(np.min(_v)), float(np.max(_v)))

    def _make_library_row(sig, layout_data):
        """Build one rowData dict for the AG Grid signal library."""
        panels_str = ", ".join(
            p["ylabel"] for p in (layout_data or []) if sig.name in p.get("signals", [])
        ) or "—"
        mn, mx = _sig_stats.get(sig.name, (0.0, 0.0))
        return {
            "name":     sig.name,
            "label":    sig.label or sig.name,
            "color":    sig.color,
            "panels":   panels_str,
            "type":     _sig_type_map.get(sig.name, "A"),
            "min_val":  mn,
            "max_val":  mx,
        }

    # Build initial figure
    initial_fig = _build_main_figure(d, use_resampler=use_resampler)
    if use_resampler:
        _fr_ref[0] = initial_fig

    # ── Shared styles ─────────────────────────────────────────────────────────
    _sticky_pane = {
        "position": "sticky", "top": "0",
        "height": "100vh", "overflowY": "auto",
    }
    sidebar_style = {
        **_sticky_pane,
        "width": "260px", "minWidth": "260px",
        "padding": "16px", "boxSizing": "border-box",
        "background": "#f8f9fa",
        "borderRight": "1px solid #dee2e6",
        "fontFamily": "Arial, sans-serif",
        "zIndex": "100",
    }
    analysis_pane_base = {
        **_sticky_pane,
        "borderLeft": "1px solid #dee2e6",
        "background": "#fff",
        "minWidth": "0",
    }
    lbl = {
        "display": "block", "marginTop": "12px",
        "marginBottom": "4px", "fontWeight": "bold", "fontSize": "12px",
    }
    _btn = {
        "marginTop": "8px", "fontSize": "11px", "padding": "4px 12px",
        "cursor": "pointer", "border": "none", "borderRadius": "3px",
        "width": "100%",
    }

    # ── App ───────────────────────────────────────────────────────────────────
    import flask as _flask

    app = Dash(__name__, suppress_callback_exceptions=True)

    @app.server.route("/_log", methods=["POST"])
    def _browser_log():
        msg = _flask.request.get_data(as_text=True)
        _log.info("[browser] %s", msg)
        return "", 204

    app.layout = html.Div([
        # Stores & download
        dcc.Store(id="cursor-store",      data={"c1": None, "c2": None}),
        dcc.Store(id="annotations-store", data=[]),
        dcc.Store(id="legend-store",      data=legend_entries),
        dcc.Store(id="layout-store",      data=initial_layout_store),
        dcc.Store(id="ag-sel-store",      data=[]),
        dcc.Download(id="download-html"),
        html.Div(id="_css-dummy", style={"display": "none"}),

        # ── LEFT: collapsible sticky sidebar ─────────────────────────────────
        # Collapse toggle tab — always visible
        html.Div(
            "◀",
            id="sidebar-toggle",
            n_clicks=0,
            title="Collapse/expand sidebar",
            style={
                "position": "sticky", "top": "0", "zIndex": "200",
                "writingMode": "vertical-lr", "cursor": "pointer",
                "background": "#dee2e6", "color": "#495057",
                "padding": "10px 4px", "fontSize": "13px",
                "userSelect": "none", "flexShrink": "0",
                "alignSelf": "flex-start",
                "borderRight": "1px solid #ced4da",
            },
        ),
        html.Div([
            html.H4("Analysis", style={"margin": "0 0 12px", "fontSize": "14px"}),
            html.Label("Tool:", style=lbl),
            dcc.Dropdown(
                id="tool-select",
                options=[
                    {"label": "Raw Signals",            "value": "raw"},
                    {"label": "Diff  A − B",            "value": "diff"},
                    {"label": "Rate of Change  dY/dt",  "value": "deriv"},
                    {"label": "Rolling Average",         "value": "smooth"},
                    {"label": "Δ Measurement",           "value": "delta"},
                    {"label": "Annotate",                "value": "annotate"},
                ],
                value="raw", clearable=False,
                style={"fontSize": "12px"},
            ),

            # Diff controls
            html.Div(id="diff-controls", style={"display": "none"}, children=[
                html.Label("Signal A:", style=lbl),
                dcc.Dropdown(id="sig-a", options=sig_options, value=default_a,
                             style={"fontSize": "12px"}),
                html.Label("Signal B:", style=lbl),
                dcc.Dropdown(id="sig-b", options=sig_options, value=default_b,
                             style={"fontSize": "12px"}),
            ]),

            # Deriv controls
            html.Div(id="deriv-controls", style={"display": "none"}, children=[
                html.Label("Signal:", style=lbl),
                dcc.Dropdown(id="deriv-sig", options=sig_options, value=default_a,
                             style={"fontSize": "12px"}),
                html.Label("Window (samples):", style={**lbl, "marginTop": "8px"}),
                dcc.Slider(id="deriv-window", min=1, max=100, step=1, value=11,
                           marks={1: "1", 25: "25", 50: "50", 100: "100"},
                           tooltip={"placement": "bottom", "always_visible": True}),
            ]),

            # Smooth controls
            html.Div(id="smooth-controls", style={"display": "none"}, children=[
                html.Label("Signal:", style=lbl),
                dcc.Dropdown(id="smooth-sig", options=sig_options, value=default_a,
                             style={"fontSize": "12px"}),
                html.Label("Window (samples):", style=lbl),
                dcc.Slider(id="smooth-window", min=2, max=100, step=1, value=11,
                           marks={2: "2", 25: "25", 50: "50", 100: "100"},
                           tooltip={"placement": "bottom", "always_visible": True}),
            ]),

            # Delta cursor controls
            html.Div(id="delta-controls", style={"display": "none"}, children=[
                html.Small(
                    "Click plot → C1.  Click again → C2.  3rd click resets.",
                    style={"color": "#888", "fontSize": "10px", "display": "block",
                           "marginTop": "8px", "marginBottom": "6px"},
                ),
                dcc.Checklist(
                    id="delta-auto",
                    options=[{"label": " Auto-detect signal on click", "value": "auto"}],
                    value=["auto"],
                    style={"fontSize": "11px", "marginBottom": "6px"},
                ),
                html.Label("Signal:", style=lbl),
                dcc.Dropdown(id="cursor-signal", options=sig_options, value=default_a,
                             clearable=False, style={"fontSize": "12px"}),
                html.Button("Reset cursors", id="cursor-reset", n_clicks=0, style={
                    **_btn, "background": "#6c757d", "color": "white",
                }),
                html.Div(id="cursor-readout", children="", style={
                    "fontSize": "11px", "fontFamily": "monospace",
                    "lineHeight": "1.8", "color": "#333", "marginTop": "8px",
                    "background": "#fff", "padding": "6px 8px",
                    "borderRadius": "4px", "border": "1px solid #dee2e6",
                    "minHeight": "3em",
                }),
            ]),

            # Annotate controls
            html.Div(id="annotate-controls", style={"display": "none"}, children=[
                html.Label("Type:", style={**lbl, "marginTop": "8px"}),
                dcc.RadioItems(
                    id="ann-type",
                    options=[
                        {"label": " Phase line", "value": "phase"},
                        {"label": " Point note", "value": "point"},
                    ],
                    value="phase",
                    labelStyle={"display": "block", "fontSize": "12px",
                                "marginBottom": "3px", "cursor": "pointer"},
                    style={"marginBottom": "8px"},
                ),
                html.Small(id="annotate-hint",
                           children="Type note, then click the plot.",
                           style={"color": "#888", "fontSize": "10px", "display": "block",
                                  "marginBottom": "6px"}),
                html.Label("Note:", style=lbl),
                dcc.Input(
                    id="ann-text", type="text", placeholder="Enter note…",
                    debounce=False,
                    style={"width": "100%", "fontSize": "12px", "padding": "4px",
                           "boxSizing": "border-box", "marginBottom": "6px"},
                ),
                html.Label("Color:", style=lbl),
                dcc.Dropdown(
                    id="ann-color",
                    options=[
                        {"label": "● Red",    "value": "#d62728"},
                        {"label": "● Blue",   "value": "#1f77b4"},
                        {"label": "● Green",  "value": "#2ca02c"},
                        {"label": "● Orange", "value": "#ff7f0e"},
                        {"label": "● Gray",   "value": "#7f7f7f"},
                    ],
                    value="#d62728", clearable=False,
                    style={"fontSize": "12px"},
                ),
                html.Button("Clear all", id="ann-clear", n_clicks=0, style={
                    **_btn, "background": "#dc3545", "color": "white", "marginTop": "10px",
                }),
            ]),

            # ── Panels section (collapsed by default) ────────────────────────
            html.Hr(style={"margin": "14px 0 6px"}),
            html.Div([
                html.Div([
                    html.Button(
                        ["Panels ", html.Span("▸", id="panels-arrow")],
                        id="panels-toggle",
                        n_clicks=1,   # start collapsed
                        style={
                            "background": "none", "border": "none", "padding": "0",
                            "cursor": "pointer", "fontWeight": "bold",
                            "fontSize": "12px", "color": "#212529", "flex": "1",
                            "textAlign": "left",
                        },
                    ),
                    html.Button(
                        "＋A", id="add-analog-btn", n_clicks=0,
                        title="Add analog panel",
                        style={
                            "fontSize": "10px", "padding": "1px 5px", "cursor": "pointer",
                            "background": "#2196F3", "color": "white",
                            "border": "none", "borderRadius": "3px",
                        },
                    ),
                    html.Button(
                        "＋D", id="add-digital-btn", n_clicks=0,
                        title="Add digital panel",
                        style={
                            "fontSize": "10px", "padding": "1px 5px", "cursor": "pointer",
                            "background": "#4CAF50", "color": "white",
                            "border": "none", "borderRadius": "3px",
                        },
                    ),
                ], style={"display": "flex", "alignItems": "center", "gap": "4px",
                          "marginBottom": "4px"}),
                html.Div(id="panels-list", children=[], style={"display": "none"}),
            ], id="panels-section"),

            html.Hr(style={"margin": "8px 0 6px", "borderColor": "#dee2e6"}),
            html.Button(
                "💾 Save as HTML", id="save-html-btn", n_clicks=0,
                style={**_btn, "background": "#495057", "color": "white",
                       "flexShrink": "0"},
            ),

            # ── Signal library (fills remaining height) ───────────────────────
            html.Hr(style={"margin": "8px 0 6px"}),
            html.Div([
                html.Span("Signals", style={
                    "fontWeight": "bold", "fontSize": "12px", "flex": "1",
                }),
                html.Span("Add to:",
                          style={"fontSize": "11px", "color": "#6c757d",
                                 "flexShrink": "0"}),
                dcc.Dropdown(
                    id="panel-target-dd",
                    options=[],
                    value=None,
                    placeholder="panel…",
                    clearable=False,
                    style={"minWidth": "90px", "fontSize": "11px"},
                ),
                html.Button(
                    "+", id="assign-sigs-btn", n_clicks=0,
                    title="Add selected signals to panel",
                    style={
                        "fontSize": "12px", "padding": "1px 7px",
                        "background": "#2196F3", "color": "white",
                        "border": "none", "borderRadius": "3px",
                        "cursor": "pointer", "flexShrink": "0",
                        "fontWeight": "bold",
                    },
                ),
            ], style={
                "display": "flex", "alignItems": "center", "gap": "5px",
                "marginBottom": "4px", "flexShrink": "0",
            }),
            dag.AgGrid(  # type: ignore[union-attr]
                id="signal-library",
                columnDefs=[
                    {
                        "field": "color", "headerName": "", "width": 18,
                        "cellStyle": {"function": "({'background': params.data.color})"},
                        "suppressHeaderMenuButton": True,
                        "suppressMovable": True,
                    },
                    {
                        "field": "label", "headerName": "Signal",
                        "flex": 2, "filter": True, "rowDrag": True,
                    },
                    {"field": "panels", "headerName": "Panels", "flex": 2},
                    {"field": "type", "headerName": "T", "width": 34},
                ],
                rowData=[_make_library_row(s, initial_layout_store)
                         for s in all_signals_ordered],
                defaultColDef={"resizable": True, "sortable": True},
                dashGridOptions={
                    "rowSelection": {
                        "mode": "multiRow",
                        "checkboxes": True,
                        "headerCheckbox": True,
                    },
                    "rowHeight": 26,
                    "headerHeight": 26,
                    "getRowId": {"function": "params.data.name"},
                },
                # eventListeners not used — events are handled directly in assets/logger.js
                # via dash_ag_grid.getApi().addEventListener() and dash_clientside.set_props
                style={"flex": "1", "minHeight": "0"},
            ) if _AGGRID else html.Div(
                "Install dash-ag-grid to enable the signal library.",
                style={"padding": "8px", "color": "#6c757d", "fontSize": "11px",
                       "flex": "1"},
            ),
        ], id="sidebar-body", style={**sidebar_style,
                                      "display": "flex", "flexDirection": "column"}),

        # ── Resize handle ─────────────────────────────────────────────────────
        html.Div(id="sidebar-resizer", style={
            "width": "6px", "minWidth": "6px", "flexShrink": "0",
            "cursor": "ew-resize",
            "background": "transparent",
            "position": "sticky", "top": "0", "height": "100vh",
            "zIndex": "150",
        }),

        # ── CENTRE: main figure ───────────────────────────────────────────────
        dcc.Graph(
            id="main-graph", figure=initial_fig,
            style={"flex": "2", "minWidth": "0"},
            config={
                "scrollZoom": True,
                "displayModeBar": True,
                "modeBarButtonsToRemove": ["lasso2d", "select2d"],
            },
        ),

        # ── RIGHT: analysis pane (diff / deriv) ───────────────────────────────
        html.Div(id="analysis-pane", children=[
            dcc.Graph(
                id="analysis-graph", figure=go.Figure(),
                style={"height": "100vh", "minHeight": "300px"},
                responsive=True,
                config={"scrollZoom": True, "displayModeBar": True,
                        "modeBarButtonsToRemove": ["lasso2d", "select2d"]},
            ),
        ], style={**analysis_pane_base, "flex": "1", "display": "none"}),

        # ── RIGHT: annotation manager (annotate tool only) ────────────────────
        html.Div(id="annotation-manager", children=[
            html.Div([
                html.Strong(id="ann-count", children="Annotations (0)",
                            style={"fontSize": "13px"}),
            ], style={
                "padding": "10px 12px 8px",
                "borderBottom": "1px solid #dee2e6",
                "background": "#f8f9fa",
                "flexShrink": "0",
            }),
            html.Div(id="annotation-manager-list", style={
                "overflowY": "auto", "flex": "1", "padding": "6px 8px",
            }),
        ], style={
            **_sticky_pane,
            "borderLeft": "1px solid #dee2e6",
            "background": "#fff",
            "width": "270px", "minWidth": "270px",
            "display": "none", "flexDirection": "column",
        }),

    ], style={"display": "flex", "flexDirection": "row", "alignItems": "flex-start"})

    # ══════════════════════════════════════════════════════════════════════════
    # CSS injection
    # ══════════════════════════════════════════════════════════════════════════
    app.clientside_callback(
        """
        function(id) {
            var s = document.createElement('style');
            s.textContent = [
                '#main-graph .modebar-container {',
                '  position: fixed !important;',
                '  right: 12px; top: 60px; z-index: 9999;',
                '  background: rgba(255,255,255,0.92);',
                '  box-shadow: 0 2px 6px rgba(0,0,0,0.18);',
                '  border-radius: 5px; padding: 2px 0;',
                '}',
                '#main-graph .modebar { flex-direction: column !important; }',
                '#main-graph .modebar-group { margin: 0 !important; }',
                '#sidebar-resizer:hover,#sidebar-resizer.resizing {',
                '  background: rgba(33,150,243,0.3) !important; }',
                '[data-layout-drop].ag-drag-active {',
                '  border-color: #2196F3 !important;',
                '  background: #e3f2fd !important; }',
            ].join(' ');
            document.head.appendChild(s);

            /* Console forwarding is handled by assets/logger.js (loaded earlier by Dash) */

            /* ── AG Grid row drag → panel zone hover tracking ── */
            window._agDragOverPanel = null;
            window._lastMX = 0;
            window._lastMY = 0;
            document.addEventListener('mousemove', function(e) {
                window._lastMX = e.clientX;
                window._lastMY = e.clientY;
                // Clean up highlight when not dragging
                if (!document.querySelector('.ag-dnd-ghost')) {
                    if (window._agDragOverPanel !== null) {
                        document.querySelectorAll('[data-layout-drop]')
                            .forEach(function(z) { z.classList.remove('ag-drag-active'); });
                        window._agDragOverPanel = null;
                    }
                    return;
                }
                // Use elementsFromPoint so we see through the ghost to the zone beneath
                var els = document.elementsFromPoint(e.clientX, e.clientY) || [];
                var zone = null;
                for (var _j = 0; _j < els.length; _j++) {
                    if (els[_j].dataset && els[_j].dataset.layoutDrop !== undefined) {
                        zone = els[_j]; break;
                    }
                }
                document.querySelectorAll('[data-layout-drop]')
                    .forEach(function(z) { z.classList.remove('ag-drag-active'); });
                if (zone) {
                    zone.classList.add('ag-drag-active');
                    window._agDragOverPanel = zone.dataset.layoutDrop;
                } else {
                    window._agDragOverPanel = null;
                }
            });

            /* ── Sidebar drag-resize ── */
            var startX, startW;
            document.addEventListener('mousedown', function(e) {
                if (e.target.id !== 'sidebar-resizer') return;
                e.preventDefault();
                var sb = document.getElementById('sidebar-body');
                if (!sb || sb.style.display === 'none') return;
                startX = e.clientX;
                startW = sb.getBoundingClientRect().width;
                e.target.classList.add('resizing');
                function onMove(ev) {
                    var w = Math.min(Math.max(startW + (ev.clientX - startX), 120), 700);
                    sb.style.width    = w + 'px';
                    sb.style.minWidth = w + 'px';
                }
                function onUp() {
                    e.target.classList.remove('resizing');
                    document.removeEventListener('mousemove', onMove);
                    document.removeEventListener('mouseup',   onUp);
                }
                document.addEventListener('mousemove', onMove);
                document.addEventListener('mouseup',   onUp);
            });

            return '';
        }
        """,
        Output("_css-dummy", "children"),
        Input("_css-dummy", "id"),
    )

    # Sidebar collapse/expand
    app.clientside_callback(
        """
        function(n) {
            var collapsed = n % 2 === 1;
            return [
                collapsed ? {display: 'none'} : {
                    width: '260px', minWidth: '260px',
                    padding: '16px', boxSizing: 'border-box',
                    background: '#f8f9fa', borderRight: '1px solid #dee2e6',
                    fontFamily: 'Arial, sans-serif', position: 'sticky',
                    top: '0', height: '100vh', overflowY: 'auto', zIndex: '100',
                    display: 'flex', flexDirection: 'column',
                },
                collapsed ? '▶' : '◀',
            ];
        }
        """,
        Output("sidebar-body",   "style"),
        Output("sidebar-toggle", "children"),
        Input("sidebar-toggle",  "n_clicks"),
    )

    # AG Grid row drag → panel drop zone → layout-store
    app.clientside_callback(
        """
        function(evData, layout) {
            var ev = evData && evData.data;
            console.log('[plotsigs drag] evData type:', ev && ev.type,
                        'hasNodes:', !!(ev && (ev.nodes || ev.node)));
            if (!ev || ev.type !== 'rowDragEnd')
                return window.dash_clientside.no_update;

            var nodes = ev.nodes || (ev.node ? [ev.node] : []);
            var nd = nodes.length ? nodes[0] : null;
            var sigName = nd && ((nd.data && nd.data.name) || nd.name);
            console.log('[plotsigs drag] sigName:', sigName,
                        'lastPos:', window._lastMX, window._lastMY);
            if (!sigName) return window.dash_clientside.no_update;

            var mx = window._lastMX || 0, my = window._lastMY || 0;
            var toPanel = null;

            if (mx || my) {
                var els = document.elementsFromPoint(mx, my) || [];

                /* ── Try 1: sidebar panel zone (data-layout-drop attribute) ── */
                for (var i = 0; i < els.length; i++) {
                    if (els[i].dataset && els[i].dataset.layoutDrop !== undefined) {
                        toPanel = els[i].dataset.layoutDrop;
                        break;
                    }
                }

                /* ── Try 2: Plotly chart subplot (.subplot SVG group ancestor) ── */
                if (!toPanel) {
                    for (var j = 0; j < els.length; j++) {
                        var spEl = els[j].closest && els[j].closest('.subplot');
                        if (spEl) {
                            /* class is e.g. "subplot xy", "subplot xy2", "subplot xy3" */
                            var spCls = Array.from(spEl.classList)
                                            .find(function(c) { return c !== 'subplot'; });
                            if (spCls) {
                                var ym = spCls.match(/y(\\d*)$/);
                                var gIdx = ym ? (ym[1] ? parseInt(ym[1]) - 1 : 0) : 0;
                                var actPanels = (layout || []).filter(function(p) {
                                    return (p.signals || []).length > 0;
                                });
                                if (gIdx >= 0 && gIdx < actPanels.length)
                                    toPanel = actPanels[gIdx].ylabel;
                            }
                            break;
                        }
                    }
                }
            }

            if (!toPanel) toPanel = window._agDragOverPanel;
            window._agDragOverPanel = null;
            document.querySelectorAll('[data-layout-drop]')
                .forEach(function(z) { z.classList.remove('ag-drag-active'); });
            console.log('[plotsigs drag] toPanel:', toPanel);
            if (!toPanel) return window.dash_clientside.no_update;

            var newLayout = (layout || []).map(function(p) {
                return Object.assign({}, p, {signals: p.signals.slice()});
            });
            var idx = newLayout.findIndex(function(p) { return p.ylabel === toPanel; });
            if (idx < 0) return window.dash_clientside.no_update;
            if (newLayout[idx].signals.indexOf(sigName) < 0) {
                newLayout[idx].signals = newLayout[idx].signals.concat([sigName]);
            }
            return newLayout;
        }
        """,
        Output("layout-store", "data", allow_duplicate=True),
        Input("signal-library", "eventData"),
        State("layout-store", "data"),
        prevent_initial_call=True,
    )

    # selectionChanged → ag-sel-store: read selected rows via grid API
    app.clientside_callback(
        """
        function(evData) {
            var ev = evData && evData.data;
            if (!ev || ev.type !== 'selectionChanged')
                return window.dash_clientside.no_update;
            try {
                var api = dash_ag_grid.getApi('signal-library');
                var rows = api ? api.getSelectedRows() : [];
                var names = rows.map(function(r) { return r.name; });
                console.log('[plotsigs sel] selected:', names);
                return names;
            } catch(e) {
                console.error('[plotsigs sel] error:', e);
                return [];
            }
        }
        """,
        Output("ag-sel-store", "data"),
        Input("signal-library", "eventData"),
        prevent_initial_call=True,
    )

    app.clientside_callback(
        """
        function(n) {
            var collapsed = n % 2 === 1;
            return [collapsed ? {display: 'none'} : {display: 'block'}, collapsed ? '▸' : '▾'];
        }
        """,
        Output("panels-list",  "style"),
        Output("panels-arrow", "children"),
        Input("panels-toggle", "n_clicks"),
    )

    # ══════════════════════════════════════════════════════════════════════════
    # Callback 1: tool selector → show/hide controls + annotation manager
    # ══════════════════════════════════════════════════════════════════════════
    @app.callback(
        Output("diff-controls",     "style"),
        Output("deriv-controls",    "style"),
        Output("smooth-controls",   "style"),
        Output("delta-controls",    "style"),
        Output("annotate-controls", "style"),
        Output("annotation-manager","style"),
        Input("tool-select", "value"),
    )
    def _toggle_controls(tool):
        show = {"display": "block"}
        hide = {"display": "none"}
        ann_mgr_show = {
            **_sticky_pane,
            "borderLeft": "1px solid #dee2e6",
            "background": "#fff",
            "width": "270px", "minWidth": "270px",
            "display": "flex", "flexDirection": "column",
        }
        ann_mgr_hide = {**ann_mgr_show, "display": "none"}
        return (
            show if tool == "diff"     else hide,
            show if tool == "deriv"    else hide,
            show if tool == "smooth"   else hide,
            show if tool == "delta"    else hide,
            show if tool == "annotate" else hide,
            ann_mgr_show if tool == "annotate" else ann_mgr_hide,
        )

    # ══════════════════════════════════════════════════════════════════════════
    # Callback 1b: annotate type → hint text
    # ══════════════════════════════════════════════════════════════════════════
    @app.callback(
        Output("annotate-hint", "children"),
        Input("ann-type", "value"),
    )
    def _update_hint(ann_type):
        if ann_type == "point":
            return "Type note, then click directly on a signal line."
        return "Type note, then click anywhere on the plot."

    # ══════════════════════════════════════════════════════════════════════════
    # Callback 1c: ann-type change → patch hovermode without full rebuild
    # ══════════════════════════════════════════════════════════════════════════
    @app.callback(
        Output("main-graph", "figure", allow_duplicate=True),
        Input("ann-type", "value"),
        State("tool-select", "value"),
        prevent_initial_call=True,
    )
    def _patch_ann_hovermode(ann_type, tool):
        if tool != "annotate":
            raise dash.exceptions.PreventUpdate
        p = Patch()
        p["layout"]["hovermode"] = "closest" if ann_type == "point" else "x unified"
        return p

    # ══════════════════════════════════════════════════════════════════════════
    # ROAD-13/14: render panel chips from layout-store
    # ══════════════════════════════════════════════════════════════════════════
    @app.callback(
        Output("panels-list", "children"),
        Input("layout-store", "data"),
    )
    def _render_panels_editor(layout):
        if not layout:
            return [html.Span("No panels", style={"color": "#aaa", "fontSize": "11px"})]

        children = []
        for i, panel in enumerate(layout):
            mode   = panel.get("mode", "analog")
            ylabel = panel.get("ylabel", "")
            sigs   = panel.get("signals", [])

            chips = []
            for sig_name in sigs:
                sig_obj = d._signal_map.get(sig_name)
                label   = (sig_obj.label or sig_obj.name) if sig_obj else sig_name
                color   = sig_obj.color if sig_obj else "#666"
                chips.append(html.Span(
                    [
                        html.Span(label, style={"verticalAlign": "middle"}),
                        html.Button(
                            "−",
                            id={"type": "sig-rem", "index": f"{i}:{sig_name}"},
                            n_clicks=0,
                            title=f"Remove {sig_name} from this panel",
                            style={
                                "marginLeft": "3px", "background": "rgba(0,0,0,0.25)",
                                "border": "none", "color": "white",
                                "cursor": "pointer", "fontSize": "10px",
                                "borderRadius": "2px", "padding": "0 3px",
                                "lineHeight": "1.2", "verticalAlign": "middle",
                            },
                        ),
                    ],
                    title=sig_name,
                    style={
                        "display": "inline-flex", "alignItems": "center",
                        "background": color, "color": "white",
                        "borderRadius": "3px", "padding": "1px 4px",
                        "margin": "2px 1px", "fontSize": "10px",
                    },
                ))

            children.append(html.Div([
                html.Div([
                    html.Span(
                        "A" if mode == "analog" else "D",
                        title=f"{mode} panel",
                        style={
                            "background": "#2196F3" if mode == "analog" else "#4CAF50",
                            "color": "white", "borderRadius": "3px",
                            "padding": "1px 5px", "fontSize": "10px",
                            "fontWeight": "bold", "flexShrink": "0",
                        },
                    ),
                    dcc.Input(
                        id={"type": "panel-ylabel", "index": i},
                        value=ylabel,
                        debounce=True,
                        placeholder="Y-axis label",
                        style={
                            "width": "90px", "fontSize": "10px",
                            "padding": "1px 3px",
                            "border": "1px solid #ced4da", "borderRadius": "3px",
                        },
                    ),
                    html.Button(
                        "×",
                        id={"type": "panel-remove", "index": i},
                        n_clicks=0,
                        title="Remove panel",
                        style={
                            "marginLeft": "auto", "background": "none",
                            "border": "none", "color": "#aaa",
                            "cursor": "pointer", "fontSize": "14px",
                            "padding": "0 2px", "lineHeight": "1",
                        },
                    ),
                ], style={"display": "flex", "alignItems": "center", "gap": "4px"}),
                html.Div(
                    chips if chips else [
                        html.Span("drag signal here or select + Add",
                                  style={"fontSize": "9px", "color": "#aaa"})
                    ],
                    **{"data-layout-drop": ylabel},
                    style={
                        "minHeight": "28px", "border": "1px dashed #ced4da",
                        "borderRadius": "3px", "padding": "3px",
                        "marginTop": "3px", "background": "#fafafa",
                        "flexWrap": "wrap", "display": "flex", "alignItems": "center",
                        "transition": "border-color 0.1s, background 0.1s",
                    },
                ),
            ], style={"marginBottom": "6px"}))

        return children

    # ══════════════════════════════════════════════════════════════════════════
    # ROAD-13/14: update layout-store (add panel, remove panel, ylabel edit)
    # ══════════════════════════════════════════════════════════════════════════
    @app.callback(
        Output("layout-store", "data"),
        Input({"type": "panel-remove", "index": ALL}, "n_clicks"),
        Input("add-analog-btn",                       "n_clicks"),
        Input("add-digital-btn",                      "n_clicks"),
        Input({"type": "panel-ylabel", "index": ALL}, "value"),
        State("layout-store",                         "data"),
        prevent_initial_call=True,
    )
    def _update_layout_store(_removes, _add_a, _add_d, _ylabels, layout):
        layout = [dict(p) for p in (layout or [])]
        triggered = ctx.triggered_id

        if isinstance(triggered, dict) and triggered.get("type") == "panel-remove":
            # Guard: newly-mounted buttons fire with n_clicks=0 — not a real click
            if ctx.triggered and ctx.triggered[0].get("value", 0) > 0:
                idx = int(triggered["index"])
                if 0 <= idx < len(layout):
                    layout.pop(idx)

        elif triggered == "add-analog-btn":
            layout.append({"ylabel": "New Panel", "mode": "analog", "signals": []})

        elif triggered == "add-digital-btn":
            layout.append({"ylabel": "New Panel", "mode": "digital", "signals": []})

        elif isinstance(triggered, dict) and triggered.get("type") == "panel-ylabel":
            idx = int(triggered["index"])
            if ctx.triggered and 0 <= idx < len(layout):
                new_val = ctx.triggered[0].get("value")
                if new_val is not None:
                    layout[idx] = {**layout[idx], "ylabel": new_val}

        return layout

    # ══════════════════════════════════════════════════════════════════════════
    # ROAD-13/14: assign selected grid rows to a panel
    # ══════════════════════════════════════════════════════════════════════════
    @app.callback(
        Output("layout-store", "data", allow_duplicate=True),
        Input("assign-sigs-btn",    "n_clicks"),
        State("ag-sel-store",       "data"),
        State("panel-target-dd",    "value"),
        State("layout-store",       "data"),
        prevent_initial_call=True,
    )
    def _assign_signals_to_panel(_, selected_names, target_ylabel, layout):
        _log.info("[assign] n_clicks=%s selected=%r target=%r", _, selected_names, target_ylabel)
        if not selected_names or not target_ylabel:
            raise dash.exceptions.PreventUpdate
        layout = [dict(p) for p in (layout or [])]
        target_idx = next(
            (i for i, p in enumerate(layout) if p["ylabel"] == target_ylabel), None
        )
        if target_idx is None:
            raise dash.exceptions.PreventUpdate
        for sig_name in selected_names:
            if sig_name and sig_name not in layout[target_idx]["signals"]:
                layout[target_idx] = {
                    **layout[target_idx],
                    "signals": layout[target_idx]["signals"] + [sig_name],
                }
        return layout

    @app.callback(
        Output("ag-sel-store", "data", allow_duplicate=True),
        Input("assign-sigs-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def _clear_selection_after_assign(_):
        return []

    # Cache layout-store into window._plotsigsLayout so assets/logger.js can
    # read the current layout when handling rowDragEnd via set_props.
    app.clientside_callback(
        """
        function(layout) {
            window._plotsigsLayout = layout;
            var pending = window._plotsigsPendingAdd;
            if (pending) {
                window._plotsigsPendingAdd = null;
                var sigName = pending.sigName, toPanel = pending.toPanel;
                var newLayout = (layout || []).map(function(p) {
                    if (p.ylabel !== toPanel) return p;
                    if ((p.signals || []).indexOf(sigName) >= 0) return p;
                    return Object.assign({}, p, { signals: p.signals.concat([sigName]) });
                });
                console.log('[plotsigs] pending add applied:', sigName, '->', toPanel);
                return newLayout;
            }
            return window.dash_clientside.no_update;
        }
        """,
        Output("layout-store", "data", allow_duplicate=True),
        Input("layout-store", "data"),
        prevent_initial_call="initial_duplicate",
    )

    # ══════════════════════════════════════════════════════════════════════════
    # ROAD-13/14: remove a signal from a panel via its [−] chip button
    # ══════════════════════════════════════════════════════════════════════════
    @app.callback(
        Output("layout-store", "data", allow_duplicate=True),
        Input({"type": "sig-rem", "index": ALL}, "n_clicks"),
        State("layout-store", "data"),
        prevent_initial_call=True,
    )
    def _remove_signal_from_panel(_clicks, layout):
        triggered = ctx.triggered_id
        if not isinstance(triggered, dict) or triggered.get("type") != "sig-rem":
            raise dash.exceptions.PreventUpdate
        # Guard: newly-mounted buttons fire with n_clicks=0 — not a real click
        if not ctx.triggered or (ctx.triggered[0].get("value") or 0) == 0:
            raise dash.exceptions.PreventUpdate
        index_str = triggered["index"]            # e.g. "2:SetSpeed"
        panel_idx_str, sig_name = index_str.split(":", 1)
        panel_idx = int(panel_idx_str)
        layout = [dict(p) for p in (layout or [])]
        if 0 <= panel_idx < len(layout):
            layout[panel_idx] = {
                **layout[panel_idx],
                "signals": [s for s in layout[panel_idx]["signals"] if s != sig_name],
            }
        return layout

    # ══════════════════════════════════════════════════════════════════════════
    # ROAD-13/14: update signal library grid rows when layout changes
    # ══════════════════════════════════════════════════════════════════════════
    @app.callback(
        Output("signal-library", "rowData"),
        Input("layout-store", "data"),
    )
    def _update_library_rows(layout_data):
        return [_make_library_row(s, layout_data) for s in all_signals_ordered]

    # ══════════════════════════════════════════════════════════════════════════
    # ROAD-13/14: keep panel-target dropdown in sync with layout
    # ══════════════════════════════════════════════════════════════════════════
    @app.callback(
        Output("panel-target-dd", "options"),
        Output("panel-target-dd", "value"),
        Input("layout-store", "data"),
        State("panel-target-dd", "value"),
    )
    def _update_panel_target_options(layout_data, current_value):
        panels = layout_data or []
        options = [{"label": p["ylabel"], "value": p["ylabel"]} for p in panels]
        valid_values = {p["ylabel"] for p in panels}
        new_value = current_value if current_value in valid_values else (
            panels[0]["ylabel"] if panels else None
        )
        return options, new_value

    # ══════════════════════════════════════════════════════════════════════════
    # Callback 2: update MAIN graph (tool + signals + window + annotations)
    # ══════════════════════════════════════════════════════════════════════════
    @app.callback(
        Output("main-graph",   "figure"),
        Output("legend-store", "data", allow_duplicate=True),
        Input("tool-select",         "value"),
        Input("sig-a",               "value"),
        Input("sig-b",               "value"),
        Input("deriv-sig",           "value"),
        Input("deriv-window",        "value"),
        Input("smooth-sig",          "value"),
        Input("smooth-window",       "value"),
        Input("annotations-store",   "data"),
        Input("cursor-store",        "data"),
        Input("layout-store",        "data"),
        State("ann-type",            "value"),
        prevent_initial_call=True,
    )
    def _update_main(tool, sig_a, sig_b, deriv_sig, deriv_win,
                     smooth_sig, smooth_win, stored_anns, cursor_data,
                     layout_data, ann_type_val):
        if ctx.triggered_id == "layout-store":
            _log.info("[update_main] layout-store → %d panels: %s",
                      len(layout_data or []),
                      [(p["ylabel"], len(p.get("signals", [])))
                       for p in (layout_data or [])])
        visible_idxs = None
        fig = _build_main_figure(
            d,
            tool=tool,
            ann_type=ann_type_val,
            use_resampler=use_resampler,
            cursor_store=cursor_data,
            sig_a_name=sig_a,
            sig_b_name=sig_b,
            deriv_sig_name=deriv_sig,
            deriv_window=deriv_win or 11,
            smooth_sig_name=smooth_sig,
            smooth_window=smooth_win or 11,
            stored_annotations=stored_anns,
            visible_idxs=visible_idxs,
            layout_store=layout_data,
        )
        if use_resampler:
            _fr_ref[0] = fig

        if ctx.triggered_id != "layout-store":
            return fig, no_update

        # Rebuild legend entries from the new figure (customdata-based)
        new_legend = _legend_from_fig(fig, d._signal_map)
        if not new_legend and layout_data:
            # Resampler omits customdata — build a cheap non-resampler figure
            fig_for_legend = _build_figure_from_layout(
                d, layout_data, use_gl=False, use_resampler=False
            )
            new_legend = _legend_from_fig(fig_for_legend, d._signal_map)
        return fig, new_legend

    # ══════════════════════════════════════════════════════════════════════════
    # Callback 3: update ANALYSIS pane (right-side graph)
    # ══════════════════════════════════════════════════════════════════════════
    @app.callback(
        Output("analysis-graph", "figure"),
        Output("analysis-pane",  "style"),
        Input("tool-select",  "value"),
        Input("sig-a",        "value"),
        Input("sig-b",        "value"),
        Input("deriv-sig",    "value"),
        Input("deriv-window", "value"),
    )
    def _update_analysis(tool, sig_a, sig_b, deriv_sig, deriv_win):
        show = {**analysis_pane_base, "flex": "1", "display": "block"}
        hide = {**analysis_pane_base, "flex": "1", "display": "none"}

        def _get_sig(name):
            for grp in active:
                for s in grp.signals:
                    if (s.label or s.name) == name:
                        return s
            return None

        if tool == "diff" and sig_a and sig_b:
            sa = _get_sig(sig_a)
            sb = _get_sig(sig_b)
            if sa and sb:
                diff_vals = sa.evaluate(t) - sb.evaluate(t)
                afig = go.Figure()
                afig.add_trace(go.Scatter(
                    x=t, y=diff_vals, mode="lines",
                    name=f"{sig_a} − {sig_b}",
                    line=dict(color="#d62728", width=1.5),
                ))
                afig.add_hline(y=0, line_dash="dash", line_color="gray", line_width=1)
                afig.update_layout(
                    title=dict(text=f"{sig_a}<br>− {sig_b}", font=dict(size=12)),
                    xaxis_title=d.xlabel, yaxis_title="Δ",
                    hovermode="x unified",
                    margin=dict(t=60, b=50, l=60, r=20),
                )
                return afig, show

        if tool == "deriv" and deriv_sig:
            sa = _get_sig(deriv_sig)
            if sa:
                dy = _windowed_deriv(sa.evaluate(t), t, max(1, deriv_win or 11))
                afig = go.Figure()
                afig.add_trace(go.Scatter(
                    x=t, y=dy, mode="lines",
                    name=f"d({deriv_sig})/dt",
                    line=dict(color="#ff7f0e", width=1.5),
                ))
                afig.add_hline(y=0, line_dash="dash", line_color="gray", line_width=1)
                afig.update_layout(
                    title=dict(text=f"dY/dt<br>{deriv_sig}", font=dict(size=12)),
                    xaxis_title=d.xlabel, yaxis_title="Rate (1/s)",
                    hovermode="x unified",
                    margin=dict(t=60, b=50, l=60, r=20),
                )
                return afig, show

        return go.Figure(), hide

    # ══════════════════════════════════════════════════════════════════════════
    # Callback 5: add annotation / clear all → update store only
    # (main graph is rebuilt by _update_main triggered by store change)
    # ══════════════════════════════════════════════════════════════════════════
    @app.callback(
        Output("annotations-store", "data"),
        Input("main-graph",      "clickData"),
        Input("ann-clear",       "n_clicks"),
        State("tool-select",     "value"),
        State("ann-type",        "value"),
        State("ann-text",        "value"),
        State("ann-color",       "value"),
        State("annotations-store", "data"),
        prevent_initial_call=True,
    )
    def _add_annotation(click_data, _clear, tool, ann_type, ann_text, ann_color, store):
        if ctx.triggered_id == "ann-clear":
            return []
        if tool != "annotate":
            raise dash.exceptions.PreventUpdate
        if not click_data or not click_data.get("points"):
            raise dash.exceptions.PreventUpdate

        pt = click_data["points"][0]
        x_clicked = pt["x"]
        text = ann_text or "★"
        color = ann_color or "#d62728"

        if ann_type == "point":
            sig_obj, y_snapped, group_idx = _find_nearest_signal(pt, t, active, trace_meta)
            yaxis = _yaxis_ref(group_idx)
            sig_name = (sig_obj.label or sig_obj.name) if sig_obj else ""
            _log.debug("[annotate] point sig=%s x=%.4f y_snap=%.4g group=%d yaxis=%s",
                       sig_name, x_clicked, y_snapped, group_idx, yaxis)
            entry = {
                "type": "point",
                "x": x_clicked,
                "y": y_snapped,
                "yaxis": yaxis,
                "signal": sig_name,
                "text": text,
                "color": color,
            }
        else:
            _log.debug("[annotate] phase x=%.4f text=%r", x_clicked, text)
            entry = {"type": "phase", "x": x_clicked, "text": text, "color": color}

        return (store or []) + [entry]

    # ══════════════════════════════════════════════════════════════════════════
    # Callback 6: delta cursor — C1 / C2 / reset
    # ══════════════════════════════════════════════════════════════════════════
    @app.callback(
        Output("cursor-store",  "data"),
        Output("cursor-signal", "value"),
        Input("main-graph",     "clickData"),
        Input("cursor-reset",   "n_clicks"),
        State("tool-select",    "value"),
        State("delta-auto",     "value"),
        State("cursor-signal",  "value"),
        State("cursor-store",   "data"),
        State("layout-store",   "data"),
        prevent_initial_call=True,
    )
    def _set_cursor(click_data, _rst, tool, auto_mode, cursor_sig, store, layout_data):
        if ctx.triggered_id == "cursor-reset":
            return {"c1": None, "c2": None}, no_update
        if tool != "delta":
            raise dash.exceptions.PreventUpdate
        if not click_data or not click_data.get("points"):
            raise dash.exceptions.PreventUpdate

        pt = click_data["points"][0]
        x_clicked = pt["x"]
        _log.debug("[cursor] triggered=%s x=%.4f auto=%s",
                   ctx.triggered_id, x_clicked, auto_mode)

        # Use current layout groups so group_idx from customdata stays in sync
        curr_active = _groups_from_layout(layout_data, d._signal_map) if layout_data else active

        use_auto = "auto" in (auto_mode or [])
        if use_auto:
            sig_obj, y_val, _ = _find_nearest_signal(pt, t, curr_active, trace_meta)
            if sig_obj is None:
                raise dash.exceptions.PreventUpdate
            sig_name = sig_obj.label or sig_obj.name
        else:
            sig_name = cursor_sig
            if not sig_name:
                raise dash.exceptions.PreventUpdate
            sig_obj = None
            for grp in curr_active:
                for s in grp.signals:
                    if (s.label or s.name) == sig_name:
                        sig_obj = s
                        break
            if sig_obj is None:
                raise dash.exceptions.PreventUpdate
            pos = int(np.argmin(np.abs(t - x_clicked)))
            y_val = float(sig_obj.evaluate(t)[pos])

        pos = int(np.argmin(np.abs(t - x_clicked)))
        x_val = float(t[pos])
        cursor = {"x": x_val, "y": y_val, "name": sig_name}
        _log.debug("[cursor] resolved sig=%s x=%.4f y=%.4g", sig_name, x_val, y_val)
        data = dict(store or {})
        data.setdefault("c1", None)
        data.setdefault("c2", None)
        if data["c1"] is None:
            data["c1"] = cursor
        elif data["c2"] is None:
            data["c2"] = cursor
        else:
            data = {"c1": cursor, "c2": None}
        return data, sig_name if use_auto else no_update

    # ══════════════════════════════════════════════════════════════════════════
    # Callback 7: render delta readout
    # ══════════════════════════════════════════════════════════════════════════
    @app.callback(
        Output("cursor-readout", "children"),
        Input("cursor-store", "data"),
    )
    def _update_readout(store):
        c1 = (store or {}).get("c1")
        c2 = (store or {}).get("c2")
        if not c1 and not c2:
            return ""
        parts = []
        if c1:
            parts += [
                html.Span(f"● C1  t={c1['x']:.4f}s  y={c1['y']:.5g}",
                          style={"color": "#1f77b4", "display": "block"}),
                html.Span(f"      [{c1.get('name', '')}]",
                          style={"color": "#666", "display": "block", "fontSize": "10px"}),
            ]
        if c2:
            parts += [
                html.Span(f"○ C2  t={c2['x']:.4f}s  y={c2['y']:.5g}",
                          style={"color": "#ff7f0e", "display": "block"}),
                html.Span(f"      [{c2.get('name', '')}]",
                          style={"color": "#666", "display": "block", "fontSize": "10px"}),
            ]
        if c1 and c2:
            dt = c2["x"] - c1["x"]
            dy = c2["y"] - c1["y"]
            dydt_str = f"{dy / dt:.5g}" if dt != 0 else "∞"
            parts += [
                html.Hr(style={"margin": "4px 0", "borderColor": "#ccc"}),
                html.Span(f"Δt    = {dt:.4f} s",  style={"display": "block", "fontWeight": "bold"}),
                html.Span(f"Δy    = {dy:.5g}",     style={"display": "block", "fontWeight": "bold"}),
                html.Span(f"dY/dt = {dydt_str}",   style={"display": "block", "fontWeight": "bold"}),
            ]
        return parts

    # ══════════════════════════════════════════════════════════════════════════
    # Callback 8: annotation manager list + count
    # ══════════════════════════════════════════════════════════════════════════
    @app.callback(
        Output("annotation-manager-list", "children"),
        Output("ann-count", "children"),
        Input("annotations-store", "data"),
    )
    def _render_ann_list(store):
        rows = []
        for i, ann in enumerate(store or []):
            atype  = ann.get("type", "phase")
            x      = ann["x"]
            text   = ann.get("text", "")
            color  = ann.get("color", "#d62728")
            icon   = "⁞" if atype == "phase" else "↗"
            y_str  = (
                f"  y={ann['y']:.3g}"
                + (f"  [{ann['signal']}]" if ann.get("signal") else "")
            ) if atype == "point" else ""

            rows.append(html.Div([
                html.Span(icon, title=atype, style={
                    "color": color, "fontSize": "16px",
                    "minWidth": "18px", "marginRight": "6px",
                }),
                html.Div([
                    html.Div([
                        html.Span("t=", style={"fontSize": "10px", "color": "#aaa",
                                               "marginRight": "2px"}),
                        dcc.Input(
                            id={"type": "ann-x-edit", "index": i},
                            value=round(x, 3), type="number", debounce=True,
                            style={
                                "width": "80px", "fontSize": "10px",
                                "padding": "1px 4px", "boxSizing": "border-box",
                                "border": "1px solid #dee2e6", "borderRadius": "3px",
                            },
                        ),
                        html.Span("s" + y_str, style={"fontSize": "9px", "color": "#bbb",
                                                       "marginLeft": "2px"}),
                    ], style={"display": "flex", "alignItems": "center", "marginBottom": "3px"}),
                    dcc.Input(
                        id={"type": "ann-text-edit", "index": i},
                        value=text, type="text", debounce=True,
                        style={
                            "width": "100%", "fontSize": "11px",
                            "padding": "2px 5px", "boxSizing": "border-box",
                            "border": "1px solid #dee2e6", "borderRadius": "3px",
                        },
                    ),
                ], style={"flex": "1", "minWidth": "0", "marginRight": "6px"}),
                html.Span("●", style={"color": color, "fontSize": "13px", "marginRight": "4px"}),
                html.Button("×",
                            id={"type": "ann-del", "index": i}, n_clicks=0,
                            title="Delete", style={
                                "border": "none", "background": "none",
                                "color": "#bbb", "fontSize": "16px",
                                "cursor": "pointer", "padding": "0 3px",
                                "lineHeight": "1",
                            }),
            ], style={
                "display": "flex", "alignItems": "center",
                "padding": "5px 2px",
                "borderBottom": "1px solid #f2f2f2",
            }))

        count = f"Annotations ({len(store or [])})"
        return rows, count

    # ══════════════════════════════════════════════════════════════════════════
    # Callback 9: delete annotation → store only (graph rebuilt by _update_main)
    # ══════════════════════════════════════════════════════════════════════════
    @app.callback(
        Output("annotations-store", "data", allow_duplicate=True),
        Input({"type": "ann-del", "index": ALL}, "n_clicks"),
        State("annotations-store", "data"),
        prevent_initial_call=True,
    )
    def _delete_annotation(del_clicks, store):
        if not ctx.triggered_id or not isinstance(ctx.triggered_id, dict):
            raise dash.exceptions.PreventUpdate
        idx = ctx.triggered_id["index"]
        if not del_clicks or not del_clicks[idx]:
            raise dash.exceptions.PreventUpdate
        store = list(store or [])
        if 0 <= idx < len(store):
            store.pop(idx)
        return store

    # ══════════════════════════════════════════════════════════════════════════
    # Callback 10: edit annotation text (inline)
    # ══════════════════════════════════════════════════════════════════════════
    @app.callback(
        Output("annotations-store", "data", allow_duplicate=True),
        Input({"type": "ann-text-edit", "index": ALL}, "value"),
        State("annotations-store", "data"),
        prevent_initial_call=True,
    )
    def _edit_annotation_text(texts, store):
        if not ctx.triggered_id or not isinstance(ctx.triggered_id, dict):
            raise dash.exceptions.PreventUpdate
        idx = ctx.triggered_id["index"]
        store = [dict(a) for a in (store or [])]
        if 0 <= idx < len(store) and idx < len(texts):
            store[idx]["text"] = texts[idx] or ""
        return store

    # ══════════════════════════════════════════════════════════════════════════
    # Callback 11: edit annotation x position (inline)
    # ══════════════════════════════════════════════════════════════════════════
    @app.callback(
        Output("annotations-store", "data", allow_duplicate=True),
        Input({"type": "ann-x-edit", "index": ALL}, "value"),
        State("annotations-store", "data"),
        prevent_initial_call=True,
    )
    def _edit_annotation_x(xs, store):
        if not ctx.triggered_id or not isinstance(ctx.triggered_id, dict):
            raise dash.exceptions.PreventUpdate
        idx = ctx.triggered_id["index"]
        store = [dict(a) for a in (store or [])]
        if 0 <= idx < len(store) and idx < len(xs) and xs[idx] is not None:
            store[idx]["x"] = float(xs[idx])
        return store

    # ══════════════════════════════════════════════════════════════════════════
    # Callback 12: x-axis sync main → analysis pane
    # ══════════════════════════════════════════════════════════════════════════
    @app.callback(
        Output("analysis-graph", "figure", allow_duplicate=True),
        Input("main-graph",      "relayoutData"),
        State("analysis-pane",   "style"),
        prevent_initial_call=True,
    )
    def _sync_to_analysis(relayout, pane_style):
        if not relayout or (pane_style or {}).get("display") == "none":
            raise dash.exceptions.PreventUpdate
        p = Patch()
        if "xaxis.range[0]" in relayout:
            p["layout"]["xaxis"]["range"] = [relayout["xaxis.range[0]"], relayout["xaxis.range[1]"]]
            p["layout"]["xaxis"]["autorange"] = False
        elif "xaxis.autorange" in relayout:
            p["layout"]["xaxis"]["autorange"] = relayout["xaxis.autorange"]
        else:
            raise dash.exceptions.PreventUpdate
        return p

    # ══════════════════════════════════════════════════════════════════════════
    # Callback 13: x-axis sync analysis → main
    # ══════════════════════════════════════════════════════════════════════════
    @app.callback(
        Output("main-graph",    "figure", allow_duplicate=True),
        Input("analysis-graph", "relayoutData"),
        State("analysis-pane",  "style"),
        prevent_initial_call=True,
    )
    def _sync_to_main(relayout, pane_style):
        if not relayout or (pane_style or {}).get("display") == "none":
            raise dash.exceptions.PreventUpdate
        p = Patch()
        if "xaxis.range[0]" in relayout:
            p["layout"]["xaxis"]["range"] = [relayout["xaxis.range[0]"], relayout["xaxis.range[1]"]]
            p["layout"]["xaxis"]["autorange"] = False
        elif "xaxis.autorange" in relayout:
            p["layout"]["xaxis"]["autorange"] = relayout["xaxis.autorange"]
        else:
            raise dash.exceptions.PreventUpdate
        return p

    # ══════════════════════════════════════════════════════════════════════════
    # Callback 14 (optional): plotly-resampler dynamic zoom — only registered
    # when dataset exceeds RESAMPLE_THRESHOLD and library is installed.
    # ══════════════════════════════════════════════════════════════════════════
    if use_resampler:
        @app.callback(
            Output("main-graph", "figure", allow_duplicate=True),
            Input("main-graph",  "relayoutData"),
            State("main-graph",  "figure"),
            prevent_initial_call=True,
        )
        def _resample_on_zoom(relayout_data, current_fig):
            fr = _fr_ref[0]
            if fr is None or not relayout_data:
                raise dash.exceptions.PreventUpdate
            try:
                patch = fr.construct_update_data_patch(relayout_data, current_fig)
            except Exception:
                raise dash.exceptions.PreventUpdate
            if patch is None:
                raise dash.exceptions.PreventUpdate
            return patch

    # ══════════════════════════════════════════════════════════════════════════
    # Callback 15: download HTML
    # ══════════════════════════════════════════════════════════════════════════
    @app.callback(
        Output("download-html", "data"),
        Input("save-html-btn", "n_clicks"),
        State("main-graph", "figure"),
        State("annotations-store", "data"),
        prevent_initial_call=True,
    )
    def _download_html(_, fig_dict, _stored_annotations):
        import datetime
        # fig_dict["layout"] already contains annotations from the last _update_main
        # render; calling _overlay_annotations again would duplicate every annotation.
        fig = go.Figure(
            data=fig_dict.get("data", []),
            layout=fig_dict.get("layout", {}),
        )
        from .renderer_plotly import _PLOTLY_EXTRAS_JS
        html_str = fig.to_html(include_plotlyjs="cdn", full_html=True,
                               post_script=_PLOTLY_EXTRAS_JS)
        fname = f"plotsigs_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        return dcc.send_string(html_str, filename=fname)

    # ── Launch ────────────────────────────────────────────────────────────────
    import threading, webbrowser
    url = f"http://localhost:{port}/"
    print(f"Dash app running at {url}  (Ctrl+C to stop)")
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    app.run(debug=debug, port=port)
