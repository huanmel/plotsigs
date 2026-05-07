"""
Annotation definitions — data layer, no matplotlib here.

Each annotation knows what it represents; the renderer decides how to draw it.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Tuple


# ── Horizontal markers ────────────────────────────────────────────────────────

@dataclass
class Threshold:
    """
    Horizontal threshold line across the analog panel.

    Example:
        Threshold(value=1500, label="MIN speed", color="#3498db")
        Threshold(value=8000, label="MAX speed", color="#e74c3c")
    """
    value: float
    label: str = ""
    color: str = "#3498db"
    ls: str = "--"
    lw: float = 1.0
    side: str = "right"          # where to print the label: "right" | "left"


@dataclass
class ToleranceBand:
    """
    Shaded ± corridor around a named signal.

    Example:
        ToleranceBand(signal_name="Set Speed", tolerance=400, color="#9b59b6")
    """
    signal_name: str
    tolerance: float
    color: str = "#9b59b6"
    alpha: float = 0.13
    label: Optional[str] = None


# ── Vertical markers ──────────────────────────────────────────────────────────

@dataclass
class VLine:
    """
    Vertical dashed line with an optional callout label (arrow annotation).

    Example:
        VLine(t=21.0, label="Fault detected", color="#c0392b")
    """
    t: float
    label: str = ""
    color: str = "#c0392b"
    ls: str = ":"
    lw: float = 1.2
    label_y: float = 0.75        # fractional height in axes for label placement
    panel: str = "both"          # "analog" | "digital" | "both"


@dataclass
class VSpan:
    """
    Shaded vertical region (e.g. startup window, fault window).

    Example:
        VSpan(t0=10, t1=12, label="STARTUP window", color="#f39c12")
    """
    t0: float
    t1: float
    label: str = ""
    color: str = "#f39c12"
    alpha: float = 0.12
    label_y: float = 0.75        # fractional height in analog axes
    panel: str = "both"


# ── X-axis phase labels ───────────────────────────────────────────────────────

@dataclass
class PhaseLabel:
    """
    Phase annotation: double-headed arrow under the bottom axes **and**
    optional vertical dashed line at ``t0`` across all subplots.

    Example:
        PhaseLabel(t0=0,  t1=10, label="IDLE")
        PhaseLabel(t0=10, t1=22, label="RAMP UP",  show_vline=True)
        PhaseLabel(t0=22, t1=47, label="STEADY",   vline_label=False)
    """
    t0: float
    t1: float
    label: str
    color: str = "#555555"
    show_vline:  bool = True    # draw a dashed vertical line at t0 across all subplots
    vline_label: bool = True    # show the phase name rotated on the vertical line


# ── Percentage tolerance band ─────────────────────────────────────────────────

@dataclass
class PctToleranceBand:
    """
    Shaded ± corridor whose width tracks the reference signal (proportional).

    Unlike ``ToleranceBand`` (fixed absolute width), the band here is
    ``±pct%`` of the signal value at every point in time — it widens when
    the setpoint is high and narrows when it is low.

    Example:
        PctToleranceBand(signal_name="Set Speed", pct=5.0, color="#9b59b6")
    """
    signal_name: str
    pct: float                  # half-width as % of signal value
    color: str = "#9b59b6"
    alpha: float = 0.15
    label: Optional[str] = None


# ── Setpoint / feedback comparison config ─────────────────────────────────────

@dataclass
class ComparisonConfig:
    """
    Configuration for a setpoint-vs-feedback comparison overlay.

    Stored on a ``SignalGroup``; the renderer evaluates the signals and draws:
    - ``±tolerance_pct%`` shaded band around the reference signal
    - Vertical settling-time marker (when feedback first stays inside the band)
    - Callout annotation at peak overshoot

    Created via ``SignalGroup.add_transient_analysis()``.
    """
    reference: str              # signal name of the setpoint / reference
    feedback: str               # signal name of the feedback / response
    tolerance_pct: float = 5.0
    show_settling:    bool = True
    show_overshoot:   bool = True
    show_rise_time:   bool = True
    show_steady_state: bool = True
    show_crosshairs:  bool = True   # MATLAB-style dashed lines to each characteristic
    after_t:  Optional[float] = None   # restrict analysis to t >= after_t
    before_t: Optional[float] = None   # restrict analysis to t <= before_t (multi-step)
    settling_color:   str = "#27ae60"
    overshoot_color:  str = "#e74c3c"
    rise_time_color:  str = "#3498db"
    # Where to place the Ts label relative to the tolerance band:
    #   "above_band"  — just above the ±tol% band upper edge (default, avoids overlap)
    #   "below_band"  — just below the band lower edge
    #   "signal"      — beside the settling point at step_end height
    #   "top"         — top of the axes (original behaviour)
    ts_label_pos: str = "above_band"


# ── Event-to-event duration span ─────────────────────────────────────────────

@dataclass
class EventDurationAnnotation:
    """
    Measure and annotate the elapsed time between two signal events.

    Event A — signal_a crosses threshold_a in direction_a ("below" | "above").
    Event B — signal_b has an edge in direction edge_b ("rise" | "fall").

    A double-headed horizontal arrow is drawn between t_A and t_B in the
    group's subplot, with the measured duration as a centred label.

    Created via ``SignalGroup.add_event_duration()``.
    """
    signal_a:    str          # name of the signal for event A
    threshold_a: float        # threshold value for event A
    signal_b:    str          # name of the signal for event B
    direction_a: str = "below"   # "below" | "above"
    edge_b:      str = "rise"    # "rise"  | "fall"
    after_t:  Optional[float] = None
    before_t: Optional[float] = None
    label_fmt: str = "{:.1f}s"
    color:   str   = "#e74c3c"
    y_pos:   float = 0.6     # arrow height as axes fraction (0 = bottom, 1 = top)


# ── Point callouts ────────────────────────────────────────────────────────────

@dataclass
class Callout:
    """
    Arrow annotation pointing to a specific (t, value) on a named signal.
    Useful for labelling peak values, detection moments, etc.

    Example:
        Callout(signal_name="Running Speed", t=26.0, label="Peak", offset=(-3, 500))
    """
    signal_name: str
    t: float
    label: str = ""
    offset: Tuple[float, float] = (-3.0, 500.0)   # (dt, dv) from point
    color: Optional[str] = None                    # defaults to signal color
