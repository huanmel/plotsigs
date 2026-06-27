"""
renderer_plotly — Plotly/WebGL rendering backend for plotsigs.

Parallel to renderer.py (matplotlib). Takes a built Diagram and returns
a go.Figure with interactive subplots, shared x-axis, and all plotsigs
annotations mapped to their Plotly equivalents.

This is the only module that imports plotly.
"""

from __future__ import annotations

import numpy as np
from typing import TYPE_CHECKING

from . import style, analysis
from .signals import SteppedSignal, EnumeratedSignal

if TYPE_CHECKING:
    import plotly.graph_objects as go
    from .diagram import Diagram, SignalGroup

_PASS_COLOR = "#27ae60"
_FAIL_COLOR = "#e74c3c"

# Matplotlib ls → Plotly dash mapping
_LS_MAP = {"-": "solid", "--": "dash", ":": "dot", "-.": "dashdot"}


# ── Custom JS injected into standalone HTML exports ───────────────────────────

_PLOTLY_EXTRAS_JS = r"""
(function() {
  var gd = document.querySelector('.js-plotly-plot');
  if (!gd) return;

  // ------- delta cursor -------
  var _dpts = [];
  var _rdiv = document.createElement('div');
  _rdiv.style.cssText = [
    'position:fixed', 'top:60px', 'right:16px',
    'background:rgba(10,10,10,0.82)', 'color:#eee',
    'border-radius:5px', 'padding:7px 12px',
    'font-size:11px', 'font-family:monospace',
    'z-index:9999', 'display:none', 'white-space:pre',
    'line-height:1.5', 'pointer-events:none',
  ].join(';');
  document.body.appendChild(_rdiv);

  gd.on('plotly_click', function(ev) {
    if (!ev || !ev.points || !ev.points.length) return;
    var p = ev.points[0];
    _dpts.push({x: p.x, y: p.y, name: (p.data && p.data.name) || ''});
    if (_dpts.length > 2) _dpts = _dpts.slice(-2);
    if (_dpts.length === 1) {
      _rdiv.textContent = 'P1: x=' + (+_dpts[0].x).toFixed(4)
                        + '  y=' + (+_dpts[0].y).toFixed(4)
                        + '\n(click 2nd point — right-click to clear)';
      _rdiv.style.display = 'block';
    } else {
      var dx = _dpts[1].x - _dpts[0].x;
      var dy = _dpts[1].y - _dpts[0].y;
      var sl = (Math.abs(dx) > 1e-12) ? (dy / dx).toFixed(5) : 'inf';
      _rdiv.textContent = [
        'P1: x=' + (+_dpts[0].x).toFixed(4) + '  y=' + (+_dpts[0].y).toFixed(4),
        'P2: x=' + (+_dpts[1].x).toFixed(4) + '  y=' + (+_dpts[1].y).toFixed(4),
        'Δx=' + (+dx).toFixed(4) + '  Δy=' + (+dy).toFixed(4) + '  slope=' + sl,
      ].join('\n');
    }
  });

  gd.addEventListener('contextmenu', function(e) {
    if (_dpts.length) { e.preventDefault(); _dpts = []; _rdiv.style.display = 'none'; }
  });

  // ------- CSV export button -------
  var _cbtn = document.createElement('button');
  _cbtn.textContent = '↓ CSV';
  _cbtn.title = 'Export all signal traces as CSV';
  _cbtn.style.cssText = [
    'position:fixed', 'bottom:14px', 'left:14px',
    'background:#3d7ebf', 'color:#fff', 'border:none',
    'border-radius:4px', 'padding:5px 12px',
    'font-size:11px', 'cursor:pointer', 'z-index:9999',
  ].join(';');
  _cbtn.addEventListener('click', function() {
    var rows = ['"signal","x","y"'];
    gd.data.forEach(function(tr) {
      if (!tr.x || !tr.y || tr.fill) return;
      var nm = (tr.name || '').replace(/"/g, '""');
      for (var i = 0; i < tr.x.length; i++) {
        rows.push('"' + nm + '",' + tr.x[i] + ',' + tr.y[i]);
      }
    });
    var blob = new Blob([rows.join('\n')], {type: 'text/csv'});
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'plotsigs_data.csv';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  });
  document.body.appendChild(_cbtn);
})();
"""


# ── Public entry point ────────────────────────────────────────────────────────

def render_plotly(
    d: "Diagram",
    output=None,
    show: bool = True,
) -> "go.Figure":
    """
    Render a Diagram to a Plotly Figure.

    Parameters
    ----------
    d : Diagram
        A fully configured plotsigs Diagram object.
    output : str or Path, optional
        If provided, saves a standalone interactive HTML file.
    show : bool
        Open the figure in the browser (default True).

    Returns
    -------
    plotly.graph_objects.Figure
    """
    try:
        import plotly.graph_objects as go  # noqa: F401
    except ImportError as e:
        raise ImportError(
            "plotly is required for the Plotly backend: pip install plotly"
        ) from e

    fig = _build_figure(d)

    if output is not None:
        from pathlib import Path
        p = Path(output)
        p.parent.mkdir(parents=True, exist_ok=True)
        fig.write_html(
            str(p),
            include_plotlyjs="cdn",
            post_script=_PLOTLY_EXTRAS_JS,
        )

    if show:
        fig.show()

    return fig


# ── Figure builder ────────────────────────────────────────────────────────────

def _build_figure(d: "Diagram", use_gl: bool = True) -> "go.Figure":
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    active = [g for g in d._groups if g.signals]
    if not active:
        raise ValueError("Diagram has no signals — add at least one signal before rendering.")

    has_phases = bool(d._phase_labels)
    n_rows = len(active)

    # ── Height ratios ─────────────────────────────────────────────────────────
    raw = [d.analog_ratio if g.mode == "analog" else d.digital_ratio for g in active]
    total = sum(raw)
    row_heights = [r / total for r in raw]

    fig = make_subplots(
        rows=n_rows, cols=1,
        shared_xaxes=True,
        row_heights=row_heights,
        vertical_spacing=0.03,
    )

    t = d.t
    t_max = float(t[-1])

    # ── Draw each group ───────────────────────────────────────────────────────
    for row_idx, grp in enumerate(active, start=1):
        if grp.mode == "analog":
            _draw_analog(grp, fig, t, t_max, row_idx, d._signal_map, use_gl=use_gl)
        else:
            _draw_digital(grp, fig, t, t_max, row_idx, d._signal_map, use_gl=use_gl)

    # ── Diagram-level VSpans ──────────────────────────────────────────────────
    for vs in d._vspans:
        for row_idx, grp in enumerate(active, start=1):
            if vs.panel == "analog" and grp.mode != "analog":
                continue
            if vs.panel == "digital" and grp.mode != "digital":
                continue
            fig.add_vrect(
                x0=vs.t0, x1=vs.t1,
                fillcolor=vs.color, opacity=vs.alpha,
                layer="below", line_width=0,
                row=row_idx, col=1,
            )
        if vs.label:
            fig.add_annotation(
                x=(vs.t0 + vs.t1) / 2, y=vs.label_y,
                xref="x", yref="y domain",
                text=vs.label,
                showarrow=False,
                font=dict(size=style.FONT_SIZE_ANNOT, color=vs.color, weight="bold"),
                bgcolor="white",
                bordercolor=vs.color,
                borderwidth=1,
                xanchor="center",
            )

    # ── Diagram-level VLines ──────────────────────────────────────────────────
    for vl in d._vlines:
        for row_idx, grp in enumerate(active, start=1):
            if vl.panel == "analog" and grp.mode != "analog":
                continue
            if vl.panel == "digital" and grp.mode != "digital":
                continue
            fig.add_vline(
                x=vl.t,
                line_color=vl.color,
                line_width=vl.lw,
                line_dash=_LS_MAP.get(vl.ls, "dot"),
                opacity=0.7,
                row=row_idx, col=1,
            )
        if vl.label:
            fig.add_annotation(
                x=vl.t, y=vl.label_y,
                xref="x", yref="y domain",
                text=vl.label,
                showarrow=True,
                arrowhead=2,
                ax=20, ay=0,
                axref="pixel", ayref="pixel",
                font=dict(size=style.FONT_SIZE_ANNOT, color=vl.color, weight="bold"),
                bgcolor="white",
                bordercolor=vl.color,
                borderwidth=1,
            )

    # ── Phase labels ──────────────────────────────────────────────────────────
    if has_phases:
        for ph in d._phase_labels:
            clr = _phase_color(ph)
            mid = (ph.t0 + ph.t1) / 2

            if ph.show_vline:
                fig.add_vline(
                    x=ph.t0,
                    line_color=clr, line_dash="dash",
                    line_width=0.8, opacity=0.55,
                )
                if ph.vline_label and ph.label:
                    fig.add_annotation(
                        x=ph.t0, y=1.0,
                        xref="x", yref="y domain",
                        text=ph.label,
                        textangle=-90,
                        showarrow=False,
                        xanchor="right",
                        yanchor="top",
                        font=dict(size=style.FONT_SIZE_ANNOT - 0.5, color=clr),
                        opacity=0.85,
                    )

                if ph.status == "fail":
                    for row_idx in range(1, n_rows + 1):
                        ya = _ya(row_idx)
                        fig.add_annotation(
                            x=ph.t0, y=1.0,
                            xref="x", yref=f"{ya} domain",
                            text="✕",
                            showarrow=False,
                            font=dict(size=8, color=_FAIL_COLOR),
                            xanchor="center", yanchor="top",
                        )

            # Double-headed arrow + label below the last subplot.
            # ayref='paper' is not supported; use axref='x', ayref='pixel', ay=0
            # so both ends share the same paper y=-0.04.
            fig.add_annotation(
                x=ph.t1, y=-0.04,
                ax=ph.t0, ay=0,
                xref="x", yref="paper",
                axref="x", ayref="pixel",
                arrowhead=2,
                arrowside="start+end",
                arrowwidth=1.5,
                arrowcolor=clr,
                text="",
                showarrow=True,
            )
            fig.add_annotation(
                x=mid, y=-0.07,
                xref="x", yref="paper",
                text=ph.label,
                showarrow=False,
                xanchor="center",
                font=dict(size=style.FONT_SIZE_PHASE, color=clr),
            )

    # ── Layout ────────────────────────────────────────────────────────────────
    bottom_margin = 80 if has_phases else 40
    fig.update_layout(
        title=dict(
            text=d.title,
            font=dict(size=style.FONT_SIZE_TITLE, weight="bold"),
            x=0.5,
        ),
        plot_bgcolor=style.AXES_BG,
        paper_bgcolor=style.FIG_BG,
        hovermode="x unified",
        hoverlabel=dict(bgcolor="white", bordercolor="#cccccc", font_size=11),
        legend=dict(
            x=1.02, y=1,
            xanchor="left", yanchor="top",
            bgcolor="rgba(255,255,255,0.9)",
            bordercolor="#cccccc", borderwidth=1,
            font=dict(size=style.FONT_SIZE_ANNOT),
        ),
        margin=dict(l=60, r=160, t=60, b=bottom_margin),
    )
    fig.update_xaxes(
        matches="x",
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        spikecolor="#888888",
        spikethickness=1,
        showgrid=True,
        gridcolor="#e0e0e0",
        gridwidth=0.5,
        showline=True,
        linecolor="#cccccc",
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor="#e0e0e0",
        gridwidth=0.5,
    )
    fig.update_xaxes(title_text=d.xlabel, row=n_rows, col=1)

    return fig


# ── Per-group drawing helpers ─────────────────────────────────────────────────

def _draw_analog(grp: "SignalGroup", fig, t: np.ndarray, t_max: float,
                 row: int, signal_map: dict, use_gl: bool = True) -> None:
    import plotly.graph_objects as go

    vals = {sig.name: sig.evaluate(t) for sig in grp.signals}
    ya = _ya(row)

    # ── Absolute tolerance bands ──────────────────────────────────────────────
    for tb in grp.tolerance_bands:
        if tb.signal_name not in vals:
            continue
        ref = vals[tb.signal_name]
        lbl = tb.label or f"±{tb.tolerance} tolerance"
        _add_fill_band(fig, t, ref + tb.tolerance, ref - tb.tolerance,
                       tb.color, tb.alpha, lbl, row)

    # ── Percentage tolerance bands ────────────────────────────────────────────
    for ptb in grp.pct_tolerance_bands:
        if ptb.signal_name not in vals:
            continue
        ref = vals[ptb.signal_name]
        tol = np.abs(ref) * ptb.pct / 100.0
        lbl = ptb.label or f"±{ptb.pct}% tolerance"
        _add_fill_band(fig, t, ref + tol, ref - tol,
                       ptb.color, ptb.alpha, lbl, row)

    # ── Comparison overlays (transient analysis) ──────────────────────────────
    for cmp in grp.comparisons:
        ref_v = vals.get(cmp.reference) or (
            signal_map[cmp.reference].evaluate(t) if cmp.reference in signal_map else None
        )
        fb_v = vals.get(cmp.feedback) or (
            signal_map[cmp.feedback].evaluate(t) if cmp.feedback in signal_map else None
        )
        if ref_v is None or fb_v is None:
            continue

        # Tolerance band
        if cmp.tolerance_abs is not None:
            tol = np.full_like(ref_v, cmp.tolerance_abs)
            tol_label = f"±{cmp.tolerance_abs}"
        else:
            tol = np.abs(ref_v) * cmp.tolerance_pct / 100.0
            tol_label = f"±{cmp.tolerance_pct}%"
        _add_fill_band(fig, t, ref_v + tol, ref_v - tol,
                       cmp.settling_color, 0.15, tol_label, row)

        # Window baseline values
        win_mask = np.ones(len(t), dtype=bool)
        if cmp.after_t  is not None: win_mask &= t >= cmp.after_t
        if cmp.before_t is not None: win_mask &= t <= cmp.before_t
        fb_win   = fb_v[win_mask]
        t_win    = t[win_mask]
        fb_base  = float(fb_win[0])  if len(fb_win) else 0.0
        t_base   = float(t_win[0])   if len(t_win)  else float(t[0])
        step_end = float(ref_v[win_mask][-1]) if len(ref_v[win_mask]) else 0.0

        if cmp.show_steady_state:
            fig.add_hline(y=step_end, row=row, col=1,
                          line_color="#888888", line_dash="dot",
                          line_width=0.8, opacity=0.5)

        if cmp.show_overshoot:
            os_info = analysis.overshoot(t, ref_v, fb_v, cmp.after_t, cmp.before_t)
            if os_info:
                tp, vp = os_info["t_peak"], os_info["value"]
                if cmp.show_crosshairs:
                    fig.add_shape(type="line", x0=tp, x1=tp, y0=fb_base, y1=vp,
                                  row=row, col=1,
                                  line=dict(color=cmp.overshoot_color, dash="dash", width=0.8),
                                  opacity=0.7)
                    fig.add_shape(type="line", x0=t_base, x1=tp, y0=vp, y1=vp,
                                  row=row, col=1,
                                  line=dict(color=cmp.overshoot_color, dash="dash", width=0.8),
                                  opacity=0.7)
                dv = abs(step_end) * 0.12 if step_end != 0 else abs(vp) * 0.1
                fig.add_annotation(
                    x=tp, y=vp + dv,
                    xref="x", yref=ya,
                    text=f"OS: {os_info['pct']:.1f}%",
                    showarrow=True, arrowhead=2,
                    ax=0, ay=-20, axref="pixel", ayref="pixel",
                    font=dict(size=style.FONT_SIZE_ANNOT, color=cmp.overshoot_color),
                    bgcolor="white", bordercolor=cmp.overshoot_color,
                )

        if cmp.show_settling:
            ts = analysis.settling_time(t, ref_v, fb_v, cmp.tolerance_pct,
                                        cmp.after_t, cmp.before_t,
                                        threshold_abs=cmp.tolerance_abs)
            if ts is not None:
                if cmp.show_crosshairs:
                    fig.add_shape(type="line", x0=ts, x1=ts, y0=fb_base, y1=step_end,
                                  row=row, col=1,
                                  line=dict(color=cmp.settling_color, dash="dash", width=0.8),
                                  opacity=0.7)
                t_origin = cmp.after_t if cmp.after_t is not None else float(t[0])
                fig.add_annotation(
                    x=ts, y=step_end,
                    xref="x", yref=ya,
                    text=f"Ts: {ts - t_origin:.1f}s",
                    showarrow=True, arrowhead=2,
                    ax=30, ay=0, axref="pixel", ayref="pixel",
                    font=dict(size=style.FONT_SIZE_ANNOT, color=cmp.settling_color),
                    bgcolor="white", bordercolor=cmp.settling_color,
                )

        if cmp.show_rise_time:
            rt = analysis.rise_time(t, ref_v, fb_v,
                                    after_t=cmp.after_t, before_t=cmp.before_t)
            if rt:
                if cmp.show_crosshairs:
                    for tx, vy in [(rt["t_lo"], rt["v_lo"]), (rt["t_hi"], rt["v_hi"])]:
                        fig.add_shape(type="line", x0=tx, x1=tx, y0=fb_base, y1=vy,
                                      row=row, col=1,
                                      line=dict(color=cmp.rise_time_color, dash="dot", width=0.8),
                                      opacity=0.7)
                        fig.add_shape(type="line", x0=t_base, x1=tx, y0=vy, y1=vy,
                                      row=row, col=1,
                                      line=dict(color=cmp.rise_time_color, dash="dot", width=0.8),
                                      opacity=0.7)
                fig.add_annotation(
                    x=rt["t_hi"], y=rt["v_hi"],
                    xref="x", yref=ya,
                    text=f"Tr: {rt['duration']:.2f}s",
                    showarrow=True, arrowhead=2,
                    ax=30, ay=0, axref="pixel", ayref="pixel",
                    font=dict(size=style.FONT_SIZE_ANNOT, color=cmp.rise_time_color),
                    bgcolor="white", bordercolor=cmp.rise_time_color,
                )

    # ── Threshold lines ───────────────────────────────────────────────────────
    for th in grp.thresholds:
        fig.add_hline(
            y=th.value, row=row, col=1,
            line_color=th.color,
            line_width=th.lw,
            line_dash=_LS_MAP.get(th.ls, "dash"),
            opacity=0.8,
        )
        if th.label:
            x_pos = 1.0 if getattr(th, "side", "right") == "right" else 0.0
            xanchor = "left" if getattr(th, "side", "right") == "right" else "right"
            fig.add_annotation(
                x=x_pos, y=th.value,
                xref="x domain", yref=ya,
                text=f"  {th.label}",
                showarrow=False,
                xanchor=xanchor,
                font=dict(size=style.FONT_SIZE_ANNOT, color=th.color, weight="bold"),
            )

    # ── Signals ───────────────────────────────────────────────────────────────
    import plotly.graph_objects as go

    group_idx = row - 1

    enum_sig = None
    for sig in grp.signals:
        v = vals[sig.name]
        _cd = [[sig.name, group_idx]] * len(t)

        if isinstance(sig, EnumeratedSignal):
            enum_sig = sig
            for code, clr in sig.colors.items():
                fig.add_hrect(
                    y0=code - 0.45, y1=code + 0.45,
                    fillcolor=clr, opacity=0.08,
                    layer="below", line_width=0,
                    row=row, col=1,
                )
            for code in sorted(sig.labels.keys()):
                fig.add_hline(y=code, row=row, col=1,
                              line_color="lightgray", line_width=0.5, opacity=0.8)
            fig.add_trace(go.Scatter(
                x=t, y=v,
                mode="lines",
                line=dict(color=sig.color, width=sig.lw, shape="hv"),
                name=sig.label,
                legendgroup=sig.name,
                customdata=_cd,
            ), row=row, col=1)

        elif isinstance(sig, SteppedSignal):
            fig.add_trace(go.Scatter(
                x=t, y=v,
                mode="lines",
                line=dict(color=sig.color, width=sig.lw, shape="hv"),
                name=sig.label,
                customdata=_cd,
            ), row=row, col=1)

        else:
            TraceClass = go.Scattergl if (use_gl and len(t) > 500) else go.Scatter
            line_kw: dict = dict(color=sig.color, width=sig.lw)
            ls = getattr(sig, "ls", "-")
            if ls and ls != "-":
                line_kw["dash"] = _LS_MAP.get(ls, "solid")
            fig.add_trace(TraceClass(
                x=t, y=v,
                mode="lines",
                line=line_kw,
                name=sig.label,
                customdata=_cd,
            ), row=row, col=1)

    if enum_sig is not None:
        codes = sorted(enum_sig.labels.keys())
        fig.update_yaxes(
            tickvals=codes,
            ticktext=[enum_sig.labels[c] for c in codes],
            tickfont=dict(size=style.FONT_SIZE_LABEL),
            range=[min(codes) - 0.6, max(codes) + 0.6],
            row=row, col=1,
        )

    # ── Callouts ─────────────────────────────────────────────────────────────
    for co in grp.callouts:
        if co.signal_name not in vals:
            continue
        idx   = int(np.argmin(np.abs(t - co.t)))
        v_pt  = float(vals[co.signal_name][idx])
        color = co.color or signal_map[co.signal_name].color
        label = co.label or f"{v_pt:.0f}"
        fig.add_annotation(
            x=float(t[idx]), y=v_pt,
            xref="x", yref=ya,
            text=label,
            showarrow=True, arrowhead=2,
            ax=co.offset[0] * 6, ay=-abs(co.offset[1]) * 0.04,
            axref="pixel", ayref="pixel",
            font=dict(size=style.FONT_SIZE_ANNOT, color=color),
            bgcolor="white", bordercolor=color,
        )

    fig.update_yaxes(title_text=grp.ylabel, row=row, col=1)


def _draw_digital(grp: "SignalGroup", fig, t: np.ndarray, t_max: float,
                  row: int, signal_map: dict, use_gl: bool = True) -> None:
    import plotly.graph_objects as go

    lane_h = style.DIGITAL_LANE_HEIGHT
    scale  = style.DIGITAL_SIGNAL_SCALE
    ya = _ya(row)

    group_idx = row - 1

    for i, sig in enumerate(grp.signals):
        offset = i * lane_h
        v = sig.evaluate(t)
        fig.add_trace(go.Scatter(
            x=t, y=v * scale + offset,
            mode="lines",
            line=dict(color=sig.color, width=sig.lw, shape="hv"),
            name=sig.label,
            customdata=[[sig.name, group_idx]] * len(t),
        ), row=row, col=1)
        # lane separator
        fig.add_hline(y=offset, row=row, col=1,
                      line_color="#cccccc", line_width=0.5, opacity=1.0)
        # signal label on the right
        fig.add_annotation(
            x=1.0, y=offset + scale / 2,
            xref="x domain", yref=ya,
            text=sig.label,
            showarrow=False,
            xanchor="left",
            font=dict(size=style.FONT_SIZE_ANNOT - 0.5, color=sig.color, weight="bold"),
        )

    n = len(grp.signals)

    # ── Event-duration annotations ────────────────────────────────────────────
    for ed in grp.event_durations:
        sig_a = signal_map.get(ed.signal_a)
        sig_b = signal_map.get(ed.signal_b)
        if sig_a is None or sig_b is None:
            continue
        ya_ev = sig_a.evaluate(t)
        yb_ev = sig_b.evaluate(t)
        t_a = analysis.find_crossing(t, ya_ev, ed.threshold_a, ed.direction_a,
                                     ed.after_t, ed.before_t)
        if t_a is None:
            continue
        t_b = analysis.find_edge(t, yb_ev, ed.edge_b, t_a, ed.before_t)
        if t_b is None:
            continue
        mid   = (t_a + t_b) / 2
        label = ed.label_fmt.format(t_b - t_a)
        yf    = ed.y_pos

        fig.add_annotation(
            x=t_b, y=yf,
            ax=t_a, ay=yf,
            xref="x", yref=f"{ya} domain",
            axref="x", ayref=f"{ya} domain",
            arrowhead=2,
            arrowside="start+end",
            arrowwidth=1.5,
            arrowcolor=ed.color,
            text="", showarrow=True,
        )
        fig.add_annotation(
            x=mid, y=yf + 0.05,
            xref="x", yref=f"{ya} domain",
            text=label,
            showarrow=False,
            xanchor="center",
            font=dict(size=style.FONT_SIZE_ANNOT, color=ed.color),
            bgcolor="white", bordercolor=ed.color,
        )

    fig.update_yaxes(
        range=[-0.2, n * lane_h],
        showticklabels=False,
        row=row, col=1,
    )
    ylabel = grp.ylabel or "Digital\nsignals"
    fig.update_yaxes(title_text=ylabel, row=row, col=1)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ya(row: int) -> str:
    """Plotly y-axis reference name for a given subplot row (1-based)."""
    return "y" if row == 1 else f"y{row}"


def _phase_color(ph) -> str:
    if ph.status == "pass":
        return _PASS_COLOR
    if ph.status == "fail":
        return _FAIL_COLOR
    return ph.color


def _add_fill_band(fig, t: np.ndarray, upper: np.ndarray, lower: np.ndarray,
                   color: str, alpha: float, name: str, row: int) -> None:
    """Add a shaded band between upper and lower as a filled polygon trace."""
    import plotly.graph_objects as go

    x_fill = np.concatenate([t, t[::-1]])
    y_fill = np.concatenate([upper, lower[::-1]])
    fc = _hex_to_rgba(color, alpha)
    fig.add_trace(go.Scatter(
        x=x_fill, y=y_fill,
        fill="toself",
        fillcolor=fc,
        line=dict(width=0),
        name=name,
        legendgroup=name,
        hoverinfo="skip",
        showlegend=True,
    ), row=row, col=1)


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    """Convert '#rrggbb' to 'rgba(r,g,b,a)' string for Plotly."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"
