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
            meta.append({"is_signal": True, "group_idx": gi, "sig_name": sig.name})
            sig_ptr += 1
        else:
            meta.append({"is_signal": False, "group_idx": None, "sig_name": None})
    return meta


def _find_nearest_signal(click_point, t, active):
    """
    Resolve clicked signal from clickData point using customdata.

    Each signal trace carries customdata=[[sig.name, group_idx], ...] per point,
    set by renderer_plotly._draw_analog / _draw_digital (ROAD-22).

    Returns (signal_obj, y_at_x, group_idx).
    """
    cd = click_point.get("customdata") if isinstance(click_point, dict) else None
    if cd and len(cd) >= 2:
        sig_name = cd[0]
        group_idx = int(cd[1])
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


def _build_main_figure(d, use_gl=True, tool=None, ann_type=None,
                       sig_a_name=None, sig_b_name=None,
                       deriv_sig_name=None, deriv_window=11,
                       smooth_sig_name=None, smooth_window=11,
                       stored_annotations=None, visible_idxs=None):
    """
    Build the complete main figure, applying:
      - analysis overlay (customdata in hover tooltip for diff/deriv)
      - stored user annotations
      - trace visibility
    """
    from .renderer_plotly import _build_figure

    fig = _build_figure(d, use_gl=use_gl)
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
    _log_path = pathlib.Path(__file__).parent / "dash_debug.log"
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

    # ── Trace metadata & legend entries ───────────────────────────────────────
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

    # Build initial figure
    initial_fig = _build_main_figure(d)

    # ── Shared styles ─────────────────────────────────────────────────────────
    _sticky_pane = {
        "position": "sticky", "top": "0",
        "height": "100vh", "overflowY": "auto",
    }
    sidebar_style = {
        **_sticky_pane,
        "width": "220px", "minWidth": "220px",
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
    app = Dash(__name__, suppress_callback_exceptions=True)

    app.layout = html.Div([
        # Stores & download
        dcc.Store(id="cursor-store",      data={"c1": None, "c2": None}),
        dcc.Store(id="annotations-store", data=[]),
        dcc.Store(id="legend-store",      data=legend_entries),
        dcc.Download(id="download-html"),
        html.Div(id="_css-dummy", style={"display": "none"}),

        # ── LEFT: sticky sidebar ──────────────────────────────────────────────
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

            # Signal visibility (collapsible)
            html.Hr(style={"margin": "14px 0 8px"}),
            html.Button(
                id="signals-toggle", n_clicks=0,
                children=["Signals ", html.Span("▾", id="signals-arrow")],
                style={
                    "width": "100%", "textAlign": "left", "background": "none",
                    "border": "none", "padding": "0 0 6px", "cursor": "pointer",
                    "fontWeight": "bold", "fontSize": "12px", "color": "#212529",
                },
            ),
            html.Div(id="signals-list", children=[
                dcc.Checklist(
                    id="signal-visibility",
                    options=[
                        {
                            "label": html.Span([
                                html.Span(style={
                                    "display": "inline-block",
                                    "width": "18px", "height": "3px",
                                    "background": e["color"],
                                    "borderRadius": "2px",
                                    "marginRight": "5px",
                                    "verticalAlign": "middle",
                                }),
                                html.Span(e["name"], style={
                                    "fontSize": "11px",
                                    "fontFamily": "monospace",
                                    "verticalAlign": "middle",
                                }),
                            ]),
                            "value": str(e["idx"]),
                        }
                        for e in legend_entries
                    ],
                    value=[str(e["idx"]) for e in legend_entries],
                    labelStyle={"display": "flex", "alignItems": "center", "marginBottom": "3px"},
                ),
            ]),

            html.Hr(style={"margin": "12px 0", "borderColor": "#dee2e6"}),
            html.Button(
                "💾 Save as HTML", id="save-html-btn", n_clicks=0,
                style={**_btn, "background": "#495057", "color": "white"},
            ),
        ], style=sidebar_style),

        # ── CENTRE: scrollable signal subplots ────────────────────────────────
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
            ].join(' ');
            document.head.appendChild(s);
            return '';
        }
        """,
        Output("_css-dummy", "children"),
        Input("_css-dummy", "id"),
    )

    # ══════════════════════════════════════════════════════════════════════════
    # Clientside: collapse/expand signal visibility list
    # ══════════════════════════════════════════════════════════════════════════
    app.clientside_callback(
        """
        function(n) {
            var collapsed = n % 2 === 1;
            return [collapsed ? {display: 'none'} : {display: 'block'}, collapsed ? '▸' : '▾'];
        }
        """,
        Output("signals-list",  "style"),
        Output("signals-arrow", "children"),
        Input("signals-toggle", "n_clicks"),
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
    # Callback 2: update MAIN graph (tool + signals + window + annotations)
    # ══════════════════════════════════════════════════════════════════════════
    @app.callback(
        Output("main-graph", "figure"),
        Input("tool-select",         "value"),
        Input("sig-a",               "value"),
        Input("sig-b",               "value"),
        Input("deriv-sig",           "value"),
        Input("deriv-window",        "value"),
        Input("smooth-sig",          "value"),
        Input("smooth-window",       "value"),
        Input("annotations-store",   "data"),
        State("signal-visibility",   "value"),
        State("ann-type",            "value"),
        prevent_initial_call=True,
    )
    def _update_main(tool, sig_a, sig_b, deriv_sig, deriv_win,
                     smooth_sig, smooth_win, stored_anns, visible_vals, ann_type_val):
        visible_idxs = {int(v) for v in (visible_vals or [])}
        return _build_main_figure(
            d,
            tool=tool,
            ann_type=ann_type_val,
            sig_a_name=sig_a,
            sig_b_name=sig_b,
            deriv_sig_name=deriv_sig,
            deriv_window=deriv_win or 11,
            smooth_sig_name=smooth_sig,
            smooth_window=smooth_win or 11,
            stored_annotations=stored_anns,
            visible_idxs=visible_idxs,
        )

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
    # Callback 4: signal visibility toggle (Patch — no full rebuild needed)
    # ══════════════════════════════════════════════════════════════════════════
    app.clientside_callback(
        """
        function(checked_vals, figure, legend) {
            if (!figure || !legend) return window.dash_clientside.no_update;
            var p = JSON.parse(JSON.stringify(figure));
            legend.forEach(function(e) {
                p.data[e.idx].visible = checked_vals.indexOf(String(e.idx)) !== -1;
            });
            return p;
        }
        """,
        Output("main-graph", "figure", allow_duplicate=True),
        Input("signal-visibility", "value"),
        State("main-graph", "figure"),
        State("legend-store", "data"),
        prevent_initial_call=True,
    )

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
            sig_obj, y_snapped, group_idx = _find_nearest_signal(pt, t, active)
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
        prevent_initial_call=True,
    )
    def _set_cursor(click_data, _rst, tool, auto_mode, cursor_sig, store):
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

        use_auto = "auto" in (auto_mode or [])
        if use_auto:
            sig_obj, y_val, _ = _find_nearest_signal(pt, t, active)
            if sig_obj is None:
                raise dash.exceptions.PreventUpdate
            sig_name = sig_obj.label or sig_obj.name
        else:
            sig_name = cursor_sig
            if not sig_name:
                raise dash.exceptions.PreventUpdate
            sig_obj = None
            for grp in active:
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
    # Callback 14: download HTML
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
