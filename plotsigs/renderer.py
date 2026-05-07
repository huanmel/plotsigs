"""
Renderer — all matplotlib drawing logic lives here.

This is the only module that imports matplotlib.
Everything else is pure data / config.
"""

from __future__ import annotations
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.transforms as mtransforms
from typing import TYPE_CHECKING

from . import style, analysis
from .signals import SteppedSignal

if TYPE_CHECKING:
    from .diagram import Diagram, SignalGroup


def render(d: "Diagram") -> plt.Figure:
    style.apply()

    active = [g for g in d._groups if g.signals]
    has_phases = bool(d._phase_labels)

    if not active:
        raise ValueError("Diagram has no signals — add at least one signal before rendering.")

    # ── Figure layout: height ratio per group ─────────────────────────────────
    ratios = [d.analog_ratio if g.mode == "analog" else d.digital_ratio
              for g in active]

    fig, axes = plt.subplots(
        len(active), 1,
        figsize=d.figsize,
        gridspec_kw={"height_ratios": ratios},
        sharex=True,
    )
    if len(active) == 1:
        axes = [axes]

    fig.patch.set_facecolor(style.FIG_BG)
    for ax in axes:
        ax.set_facecolor(style.AXES_BG)

    t     = d.t
    t_max = t[-1]

    # ── Draw each group in its subplot ────────────────────────────────────────
    for grp, ax in zip(active, axes):
        if grp.mode == "analog":
            _draw_analog(grp, ax, t, t_max, d._signal_map)
        else:
            _draw_digital(grp, ax, t, t_max, d._signal_map)

    # ── Title on the topmost subplot ──────────────────────────────────────────
    axes[0].set_title(d.title, fontsize=style.FONT_SIZE_TITLE,
                      fontweight="bold", pad=10)

    # ── Diagram-level VSpans (all groups) ─────────────────────────────────────
    for vs in d._vspans:
        for grp, ax in zip(active, axes):
            if vs.panel == "analog" and grp.mode != "analog":
                continue
            if vs.panel == "digital" and grp.mode != "digital":
                continue
            ax.axvspan(vs.t0, vs.t1, alpha=vs.alpha, color=vs.color, zorder=1)
        if vs.label:
            mid = (vs.t0 + vs.t1) / 2
            axes[0].annotate(
                vs.label,
                xy=(mid, vs.label_y), xycoords=("data", "axes fraction"),
                fontsize=style.FONT_SIZE_ANNOT, ha="center", color=vs.color,
                fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=vs.color, alpha=0.85),
            )

    # ── Diagram-level VLines (all groups) ─────────────────────────────────────
    for vl in d._vlines:
        for grp, ax in zip(active, axes):
            if vl.panel == "analog" and grp.mode != "analog":
                continue
            if vl.panel == "digital" and grp.mode != "digital":
                continue
            ax.axvline(vl.t, color=vl.color, lw=vl.lw, ls=vl.ls, alpha=0.7, zorder=4)
        if vl.label:
            axes[0].annotate(
                vl.label,
                xy=(vl.t, vl.label_y), xycoords=("data", "axes fraction"),
                xytext=(vl.t + 1.5, vl.label_y),
                textcoords=("data", "axes fraction"),
                fontsize=style.FONT_SIZE_ANNOT, color=vl.color, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=vl.color, lw=1.2),
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=vl.color, alpha=0.85),
            )

    # ── Phase vertical lines across all subplots ──────────────────────────────
    if has_phases:
        for ph in d._phase_labels:
            if not ph.show_vline:
                continue
            for ax in axes:
                ax.axvline(ph.t0, color=ph.color, ls="--", lw=0.8, alpha=0.55, zorder=2)
                if ph.vline_label and ph.label:
                    trans = mtransforms.blended_transform_factory(
                        ax.transData, ax.transAxes
                    )
                    ax.text(
                        ph.t0, 0.97, ph.label,
                        transform=trans,
                        fontsize=style.FONT_SIZE_ANNOT - 0.5,
                        rotation=90, va="top", ha="right",
                        color=ph.color, alpha=0.85,
                    )

    # ── Phase arrows + labels on the bottom subplot ───────────────────────────
    bottom_ax = axes[-1]
    if has_phases:
        for ph in d._phase_labels:
            mid = (ph.t0 + ph.t1) / 2
            bottom_ax.annotate(
                "", xy=(ph.t1, -0.15), xytext=(ph.t0, -0.15),
                xycoords=("data", "axes fraction"),
                textcoords=("data", "axes fraction"),
                arrowprops=dict(arrowstyle="<->", color=ph.color, lw=0.8),
            )
            bottom_ax.text(
                mid, -0.22, ph.label,
                ha="center", va="top",
                fontsize=style.FONT_SIZE_PHASE, color=ph.color,
                transform=bottom_ax.get_xaxis_transform(),
            )

    bottom_ax.set_xlabel(d.xlabel)

    has_threshold_labels = any(grp.thresholds for grp in active if grp.mode == "analog")
    right      = style.RIGHT_MARGIN if has_threshold_labels else 1.0
    bottom_pad = 0.04 if has_phases else 0.02
    plt.tight_layout(rect=[0, bottom_pad, right, 1.0])
    return fig


# ── Per-group drawing helpers ─────────────────────────────────────────────────

def _draw_analog(grp: "SignalGroup", ax, t: np.ndarray, t_max: float, signal_map: dict):
    vals = {sig.name: sig.evaluate(t) for sig in grp.signals}

    # absolute tolerance bands (behind signals)
    for tb in grp.tolerance_bands:
        if tb.signal_name in vals:
            ref = vals[tb.signal_name]
            lbl = tb.label or f"±{tb.tolerance} tolerance"
            ax.fill_between(t, ref - tb.tolerance, ref + tb.tolerance,
                            alpha=tb.alpha, color=tb.color, label=lbl, zorder=2)

    # percentage tolerance bands (width tracks the signal value)
    for ptb in grp.pct_tolerance_bands:
        if ptb.signal_name in vals:
            ref = vals[ptb.signal_name]
            tol = np.abs(ref) * ptb.pct / 100.0
            lbl = ptb.label or f"±{ptb.pct}% tolerance"
            ax.fill_between(t, ref - tol, ref + tol,
                            alpha=ptb.alpha, color=ptb.color, label=lbl, zorder=2)

    # comparison overlays: band + cross-hair lines + characteristic annotations
    for cmp in grp.comparisons:
        ref_v = vals.get(cmp.reference)
        fb_v  = vals.get(cmp.feedback)
        if ref_v is None and cmp.reference in signal_map:
            ref_v = signal_map[cmp.reference].evaluate(t)
        if fb_v is None and cmp.feedback in signal_map:
            fb_v = signal_map[cmp.feedback].evaluate(t)
        if ref_v is None or fb_v is None:
            continue

        # Tolerance band
        tol = np.abs(ref_v) * cmp.tolerance_pct / 100.0
        ax.fill_between(t, ref_v - tol, ref_v + tol,
                        alpha=0.15, color=cmp.settling_color,
                        label=f"±{cmp.tolerance_pct}%", zorder=2)

        # Compute baseline values for cross-hair anchors
        win_mask = np.ones(len(t), dtype=bool)
        if cmp.after_t  is not None: win_mask &= t >= cmp.after_t
        if cmp.before_t is not None: win_mask &= t <= cmp.before_t
        fb_win  = fb_v[win_mask]
        t_win   = t[win_mask]
        fb_base = float(fb_win[0])  if len(fb_win) > 0 else 0.0
        t_base  = float(t_win[0])   if len(t_win)  > 0 else float(t[0])
        ref_win = ref_v[win_mask]
        step_end = float(ref_win[-1]) if len(ref_win) > 0 else 0.0

        # Steady-state line
        if cmp.show_steady_state:
            ax.axhline(step_end, color="#888888", ls=":", lw=0.8, alpha=0.5, zorder=2)

        # Overshoot
        if cmp.show_overshoot:
            os_info = analysis.overshoot(t, ref_v, fb_v, cmp.after_t, cmp.before_t)
            if os_info:
                tp, vp = os_info["t_peak"], os_info["value"]
                if cmp.show_crosshairs:
                    ax.vlines(tp, fb_base, vp,
                              colors=cmp.overshoot_color, linestyles="--", lw=0.8,
                              alpha=0.7, zorder=3)
                    ax.hlines(vp, t_base, tp,
                              colors=cmp.overshoot_color, linestyles="--", lw=0.8,
                              alpha=0.7, zorder=3)
                dv = abs(step_end) * 0.12 if step_end != 0 else abs(vp) * 0.1
                ax.annotate(
                    f"OS: {os_info['pct']:.1f}%",
                    xy=(tp, vp), xytext=(tp, vp + dv),
                    fontsize=style.FONT_SIZE_ANNOT, color=cmp.overshoot_color,
                    fontweight="bold", ha="center",
                    arrowprops=dict(arrowstyle="->", color=cmp.overshoot_color, lw=1.0),
                    bbox=dict(boxstyle="round,pad=0.2", fc="white",
                              ec=cmp.overshoot_color, alpha=0.85),
                )

        # Settling time
        if cmp.show_settling:
            ts = analysis.settling_time(t, ref_v, fb_v, cmp.tolerance_pct,
                                        cmp.after_t, cmp.before_t)
            if ts is not None:
                if cmp.show_crosshairs:
                    ax.vlines(ts, fb_base, step_end,
                              colors=cmp.settling_color, linestyles="--", lw=0.8,
                              alpha=0.7, zorder=3)
                t_origin = cmp.after_t if cmp.after_t is not None else float(t[0])
                idx_ts   = int(np.argmin(np.abs(t - ts)))
                tol_at_ts = float(np.abs(ref_v[idx_ts])) * cmp.tolerance_pct / 100.0
                pos = cmp.ts_label_pos
                if pos == "above_band":
                    text_y = step_end + tol_at_ts * 1.15 + abs(step_end) * 0.04
                    kw = dict(xytext=(ts + 0.4, text_y), ha="left", va="bottom",
                              arrowprops=dict(arrowstyle="->", color=cmp.settling_color, lw=1.0))
                elif pos == "below_band":
                    text_y = step_end - tol_at_ts * 1.15 - abs(step_end) * 0.04
                    kw = dict(xytext=(ts + 0.4, text_y), ha="left", va="top",
                              arrowprops=dict(arrowstyle="->", color=cmp.settling_color, lw=1.0))
                elif pos == "top":
                    kw = dict(xytext=(ts + 0.4, 0.97),
                              textcoords=("data", "axes fraction"),
                              ha="left", va="top",
                              arrowprops=dict(arrowstyle="->", color=cmp.settling_color, lw=1.0))
                else:  # "signal"
                    kw = dict(xytext=(ts + 0.4, step_end), ha="left", va="center",
                              arrowprops=dict(arrowstyle="->", color=cmp.settling_color, lw=1.0))
                ax.annotate(
                    f"Ts: {ts - t_origin:.1f}s",
                    xy=(ts, step_end),
                    fontsize=style.FONT_SIZE_ANNOT, color=cmp.settling_color,
                    fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.2", fc="white",
                              ec=cmp.settling_color, alpha=0.85),
                    **kw,
                )

        # Rise time
        if cmp.show_rise_time:
            rt = analysis.rise_time(t, ref_v, fb_v,
                                    after_t=cmp.after_t, before_t=cmp.before_t)
            if rt:
                if cmp.show_crosshairs:
                    ax.vlines([rt["t_lo"], rt["t_hi"]], fb_base,
                              [rt["v_lo"], rt["v_hi"]],
                              colors=cmp.rise_time_color, linestyles=":", lw=0.8,
                              alpha=0.7, zorder=3)
                    ax.hlines([rt["v_lo"], rt["v_hi"]], t_base,
                              [rt["t_lo"], rt["t_hi"]],
                              colors=cmp.rise_time_color, linestyles=":", lw=0.8,
                              alpha=0.7, zorder=3)
                ax.annotate(
                    f"Tr: {rt['duration']:.2f}s",
                    xy=(rt["t_hi"], rt["v_hi"]),
                    xytext=(rt["t_hi"] + 0.4, rt["v_hi"]),
                    fontsize=style.FONT_SIZE_ANNOT, color=cmp.rise_time_color,
                    fontweight="bold", ha="left", va="center",
                    arrowprops=dict(arrowstyle="->", color=cmp.rise_time_color, lw=1.0),
                    bbox=dict(boxstyle="round,pad=0.2", fc="white",
                              ec=cmp.rise_time_color, alpha=0.85),
                )

    # threshold lines
    for th in grp.thresholds:
        ax.axhline(th.value, color=th.color, lw=th.lw, ls=th.ls, alpha=0.8, zorder=2)
        if th.label:
            ax.text(t_max + 0.3, th.value, th.label,
                    va="center", ha="left", fontsize=style.FONT_SIZE_ANNOT,
                    color=th.color, fontweight="bold")

    # signals
    for sig in grp.signals:
        v = vals[sig.name]
        if isinstance(sig, SteppedSignal):
            ax.step(t, v, where="post", color=sig.color, lw=sig.lw,
                    label=sig.label, zorder=3)
        else:
            ax.plot(t, v, color=sig.color, lw=sig.lw, label=sig.label, zorder=3)

    # callouts
    for co in grp.callouts:
        if co.signal_name not in vals:
            continue
        idx   = np.argmin(np.abs(t - co.t))
        v     = vals[co.signal_name][idx]
        color = co.color or signal_map[co.signal_name].color
        label = co.label or f"{v:.0f}"
        ax.annotate(
            label,
            xy=(t[idx], v),
            xytext=(t[idx] + co.offset[0], v + co.offset[1]),
            fontsize=style.FONT_SIZE_ANNOT, color=color,
            arrowprops=dict(arrowstyle="->", color=color, lw=1.0),
            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec=color, alpha=0.85),
        )

    ax.set_ylabel(grp.ylabel, fontsize=style.FONT_SIZE_LABEL)
    ax.legend(loc="upper right", fontsize=style.FONT_SIZE_ANNOT, framealpha=0.9)


def _draw_digital(grp: "SignalGroup", ax, t: np.ndarray, t_max: float,
                  signal_map: dict):
    lane_h = style.DIGITAL_LANE_HEIGHT
    scale  = style.DIGITAL_SIGNAL_SCALE

    for i, sig in enumerate(grp.signals):
        offset = i * lane_h
        v = sig.evaluate(t)
        ax.step(t, v * scale + offset, where="post",
                color=sig.color, lw=sig.lw)
        ax.text(t_max + 0.3, offset + scale / 2, sig.label,
                va="center", ha="left",
                fontsize=style.FONT_SIZE_ANNOT - 0.5,
                color=sig.color, fontweight="bold")
        ax.axhline(offset, color="#cccccc", lw=0.5)

    n = len(grp.signals)

    # event-duration annotations
    for ed in grp.event_durations:
        sig_a = signal_map.get(ed.signal_a)
        sig_b = signal_map.get(ed.signal_b)
        if sig_a is None or sig_b is None:
            continue
        ya = sig_a.evaluate(t)
        yb = sig_b.evaluate(t)
        t_a = analysis.find_crossing(t, ya, ed.threshold_a, ed.direction_a,
                                     ed.after_t, ed.before_t)
        if t_a is None:
            continue
        t_b = analysis.find_edge(t, yb, ed.edge_b, t_a, ed.before_t)
        if t_b is None:
            continue
        duration = t_b - t_a
        label = ed.label_fmt.format(duration)
        mid = (t_a + t_b) / 2
        yf  = ed.y_pos
        # double-headed arrow
        ax.annotate("",
                    xy=(t_b, yf), xytext=(t_a, yf),
                    xycoords=("data", "axes fraction"),
                    textcoords=("data", "axes fraction"),
                    arrowprops=dict(arrowstyle="<->", color=ed.color, lw=1.5),
                    zorder=5)
        # centred label above the arrow
        ax.annotate(label,
                    xy=(mid, yf), xycoords=("data", "axes fraction"),
                    fontsize=style.FONT_SIZE_ANNOT, color=ed.color,
                    fontweight="bold", ha="center", va="bottom",
                    bbox=dict(boxstyle="round,pad=0.25", fc="white",
                              ec=ed.color, alpha=0.9),
                    zorder=6)

    ax.set_ylim(-0.2, n * lane_h)
    ax.set_yticks([])
    if grp.ylabel:
        ax.set_ylabel(grp.ylabel, fontsize=style.FONT_SIZE_LABEL)
    else:
        ax.set_ylabel("Digital\nsignals", fontsize=style.FONT_SIZE_LABEL)
