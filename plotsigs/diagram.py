"""
Diagram — the main user-facing class.

Single analog group (backward-compatible):
    d = Diagram("My Test", t_end=62)
    cmd = d.add_stepped("Set Speed", [...])
    d.add_lagged("Running Speed", source=cmd, tau=1.8)
    d.add_threshold(1500, label="MIN")
    d.render("output.svg")

Multiple groups with controlled order (analog / digital / analog / ...):
    d = Diagram("Test", t_end=62)

    g_speed = d.add_group("Speed [RPM]")
    g_speed.add_stepped("Set Speed", [...])
    g_speed.add_lagged("Running Speed", source=cmd, tau=1.8)

    g_flags = d.add_digital_group()          # digital panel here in the order
    g_flags.add_digital("Enable", [...])

    g_temp = d.add_group("Temp [°C]")        # another analog group below
    g_temp.add_measured("Board Temp", df)
"""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
from typing import List, Optional, Tuple, Union
from pathlib import Path

from .signals import Signal, SteppedSignal, LaggedSignal, RawSignal, DigitalSignal, DerivedSignal, EnumeratedSignal, Breakpoints
from .annotations import (
    Threshold, ToleranceBand, PctToleranceBand, ComparisonConfig,
    VLine, VSpan, PhaseLabel, Callout, EventDurationAnnotation,
)


# ── Signal group (one subplot) ────────────────────────────────────────────────

class SignalGroup:
    """
    A named group of signals sharing one subplot.

    Obtain via ``Diagram.add_group(ylabel)`` (analog) or
    ``Diagram.add_digital_group(ylabel)`` (digital stacked lanes).
    Don't instantiate directly.
    """

    def __init__(self, ylabel: str, signal_map: dict, mode: str = "analog"):
        self.ylabel = ylabel
        self.mode = mode                       # "analog" | "digital"
        self._signal_map = signal_map          # shared with parent Diagram
        self.signals: List[Signal] = []
        # analog-only annotations
        self.thresholds: List[Threshold] = []
        self.tolerance_bands: List[ToleranceBand] = []
        self.pct_tolerance_bands: List[PctToleranceBand] = []
        self.comparisons: List[ComparisonConfig] = []
        self.callouts: List[Callout] = []
        self.event_durations: List[EventDurationAnnotation] = []

    def _register(self, sig: Signal) -> Signal:
        self.signals.append(sig)
        self._signal_map[sig.name] = sig
        return sig

    # ── Analog signal builders ────────────────────────────────────────────────

    def add_stepped(self, name: str, breakpoints: Breakpoints,
                    color: str = "#2ecc71", lw: float = 1.8, **kwargs) -> SteppedSignal:
        return self._register(SteppedSignal(name, breakpoints, color=color, lw=lw, **kwargs))

    def add_lagged(self, name: str, source: Signal, tau: float = 1.5,
                   color: str = "#e74c3c", lw: float = 2.0, **kwargs) -> LaggedSignal:
        return self._register(LaggedSignal(name, source, tau=tau, color=color, lw=lw, **kwargs))

    def add_raw(self, name: str, t_data: np.ndarray, v_data: np.ndarray,
                color: str = "#e67e22", **kwargs) -> RawSignal:
        return self._register(RawSignal(name, t_data, v_data, color=color, **kwargs))

    def add_measured(self, name: str, df, time_col: str = "time",
                     value_col: Optional[str] = None,
                     color: str = "#e67e22", lw: float = 1.8, **kwargs) -> RawSignal:
        """Add a DataFrame column as an analog signal in this group."""
        sig = RawSignal.from_dataframe(
            df, time_col=time_col, value_col=value_col or name,
            name=name, color=color, lw=lw, **kwargs
        )
        return self._register(sig)

    # ── Digital signal builders ───────────────────────────────────────────────

    def add_digital(self, name: str, breakpoints: Breakpoints,
                    color: str = "#2980b9", **kwargs) -> DigitalSignal:
        """Add a binary (0/1) breakpoint signal as a lane in this group."""
        return self._register(DigitalSignal(name, breakpoints, color=color, **kwargs))

    def add_measured_digital(self, name: str, df, time_col: str = "time",
                             value_col: Optional[str] = None,
                             color: str = "#2980b9", lw: float = 1.8,
                             **kwargs) -> RawSignal:
        """Add a 0/1 measured DataFrame column as a lane in this group."""
        sig = RawSignal.from_dataframe(
            df, time_col=time_col, value_col=value_col or name,
            name=name, color=color, lw=lw, **kwargs
        )
        return self._register(sig)

    # ── Per-group annotations (analog only) ───────────────────────────────────

    def add_threshold(self, value: float, label: str = "", color: str = "#3498db",
                      ls: str = "--", **kwargs) -> "SignalGroup":
        self.thresholds.append(Threshold(value, label, color, ls, **kwargs))
        return self

    def add_tolerance(self, signal_name: str, tolerance: float,
                      color: str = "#9b59b6", **kwargs) -> "SignalGroup":
        self.tolerance_bands.append(ToleranceBand(signal_name, tolerance, color, **kwargs))
        return self

    def add_callout(self, signal_name: str, t: float, label: str = "",
                    offset: Tuple[float, float] = (-3.0, 500.0),
                    **kwargs) -> "SignalGroup":
        self.callouts.append(Callout(signal_name, t, label, offset, **kwargs))
        return self

    def add_pct_tolerance(self, signal_name: str, pct: float,
                          color: str = "#9b59b6", **kwargs) -> "SignalGroup":
        """Add a ±pct% shaded band that tracks the signal value."""
        self.pct_tolerance_bands.append(PctToleranceBand(signal_name, pct, color, **kwargs))
        return self

    def add_transient_analysis(self, reference: str, feedback: str,
                       tolerance_pct: float = 5.0,
                       tolerance_abs: Optional[float] = None,
                       show_settling: bool = True,
                       show_overshoot: bool = True,
                       show_rise_time: bool = True,
                       show_steady_state: bool = True,
                       show_crosshairs: bool = True,
                       phase: Optional[PhaseLabel] = None,
                       after_t:  Optional[float] = None,
                       before_t: Optional[float] = None,
                       **kwargs) -> "SignalGroup":
        """
        Overlay setpoint-vs-feedback analysis annotations.

        Draws a tolerance band around the reference signal, plus MATLAB-style
        cross-hair dashed lines and labels for each requested characteristic
        (overshoot, settling time, rise time, steady state).

        Parameters
        ----------
        reference        : signal name of the setpoint / reference
        feedback         : signal name of the feedback / response
        tolerance_pct    : half-width of the band in % of setpoint value (default 5%)
        tolerance_abs    : half-width of the band in absolute engineering units;
                           overrides tolerance_pct when set
        show_crosshairs  : draw dashed lines connecting characteristics to axes
        phase            : PhaseLabel returned by Diagram.add_phase() — sets
                           after_t and before_t from the phase's t0 / t1.
                           Explicit after_t / before_t override the phase values.
        after_t          : restrict analysis to t >= after_t (step start)
        before_t         : restrict analysis to t <= before_t (next step start)
        """
        if phase is not None:
            if after_t is None:
                after_t = phase.t0
            if before_t is None:
                before_t = phase.t1
        self.comparisons.append(ComparisonConfig(
            reference=reference, feedback=feedback,
            tolerance_pct=tolerance_pct,
            tolerance_abs=tolerance_abs,
            show_settling=show_settling,
            show_overshoot=show_overshoot,
            show_rise_time=show_rise_time,
            show_steady_state=show_steady_state,
            show_crosshairs=show_crosshairs,
            after_t=after_t, before_t=before_t,
            **kwargs,
        ))
        return self

    def add_event_duration(self, signal_a: str, threshold_a: float,
                           signal_b: str,
                           direction_a: str = "below",
                           edge_b: str = "rise",
                           phase: Optional[PhaseLabel] = None,
                           after_t: Optional[float] = None,
                           before_t: Optional[float] = None,
                           **kwargs) -> "SignalGroup":
        """
        Annotate the elapsed time between a threshold crossing and a signal edge.

        Draws a double-headed arrow in this group's subplot between the two
        detected event times.  Signals may live in any group — they are looked
        up by name from the shared diagram signal map.

        Parameters
        ----------
        signal_a    : signal whose threshold crossing starts the measurement
        threshold_a : threshold value for signal_a
        signal_b    : signal whose edge ends the measurement
        direction_a : "below" (drops under threshold) | "above" (rises above)
        edge_b      : "rise" (0→1) | "fall" (1→0)
        phase       : PhaseLabel — sets after_t / before_t from the phase window
        after_t     : restrict event search to t >= after_t (overrides phase.t0)
        before_t    : restrict event search to t <= before_t (overrides phase.t1)
        """
        if phase is not None:
            if after_t is None:
                after_t = phase.t0
            if before_t is None:
                before_t = phase.t1
        self.event_durations.append(EventDurationAnnotation(
            signal_a=signal_a, threshold_a=threshold_a,
            signal_b=signal_b,
            direction_a=direction_a, edge_b=edge_b,
            after_t=after_t, before_t=before_t,
            **kwargs,
        ))
        return self

    def add_derived(self, name: str,
                    a: Union[str, Signal], b: Union[str, Signal],
                    color: str = "#95a5a6", **kwargs) -> "DerivedSignal":
        """Add a computed signal (default: a − b). a/b can be names or Signal objects."""
        sig_a = self._signal_map[a] if isinstance(a, str) else a
        sig_b = self._signal_map[b] if isinstance(b, str) else b
        return self._register(DerivedSignal(name, sig_a, sig_b, color=color, **kwargs))

    def add_enum(self, name: str, t_data: np.ndarray, v_data: np.ndarray,
                 labels: dict, colors: Optional[dict] = None,
                 color: str = "#2980b9", lw: float = 2.5, **kwargs) -> EnumeratedSignal:
        """
        Add an enumerated (state-machine) signal with named integer levels.

        Parameters
        ----------
        t_data, v_data : dense time and integer-code arrays (e.g. from numpy)
        labels         : {int_code: str_label}, e.g. {1: "Heating", 2: "Circulation"}
        colors         : {int_code: str_color} — per-level band shading (optional)
        """
        return self._register(EnumeratedSignal(name, t_data, v_data, labels,
                                               colors=colors, color=color,
                                               lw=lw, **kwargs))


# ── Diagram ───────────────────────────────────────────────────────────────────

class Diagram:
    """
    Central builder for a control system timing diagram.

    Groups are rendered as subplots in the order they are added.
    Mix analog and digital groups freely:

        d = Diagram("Test", t_end=62)
        g0 = d.add_group("Speed [RPM]")
        g1 = d.add_digital_group()
        g2 = d.add_group("Temp [°C]")

    Parameters
    ----------
    title : str
        Plot title shown at the top.
    t_end : float
        End time of the time axis (seconds).
    t_start : float
        Start time (default 0).
    n_points : int
        Resolution of synthetic signals (default 2000).
    figsize : tuple
        Matplotlib figure size.
    ylabel_analog : str
        Y-axis label for the default (first) analog subplot.
    """

    def __init__(
        self,
        title: str = "Control Timing Diagram",
        t_end: float = 60.0,
        t_start: float = 0.0,
        n_points: int = 2000,
        figsize: Tuple[float, float] = (14, 7),
        analog_ratio: float = 3.0,
        digital_ratio: float = 1.4,
        ylabel_analog: str = "Value",
        xlabel: str = "Time [s]",
        caption: str = "",
        caption_fontsize: float = 14,
    ):
        self.title = title
        self.caption = caption
        self.caption_fontsize = caption_fontsize
        self.t = np.linspace(t_start, t_end, n_points)
        self.figsize = figsize
        self.analog_ratio = analog_ratio
        self.digital_ratio = digital_ratio
        self.xlabel = xlabel

        # signal lookup shared across all groups
        self._signal_map: dict[str, Signal] = {}

        # unified ordered list of groups (each becomes one subplot)
        self._groups: List[SignalGroup] = [
            SignalGroup(ylabel_analog, self._signal_map, mode="analog")
        ]

        # diagram-level annotations (drawn on every subplot)
        self._vlines: List[VLine] = []
        self._vspans: List[VSpan] = []
        self._phase_labels: List[PhaseLabel] = []

    # ── Group management ──────────────────────────────────────────────────────

    def add_group(self, ylabel: str = "Value") -> SignalGroup:
        """
        Append a new analog subplot and return its builder.

        Example:
            g = d.add_group("Speed [RPM]")
            g.add_stepped("Set Speed", [...])
        """
        g = SignalGroup(ylabel, self._signal_map, mode="analog")
        self._groups.append(g)
        return g

    def add_digital_group(self, ylabel: str = "") -> SignalGroup:
        """
        Append a new digital (stacked lanes) subplot and return its builder.

        Example:
            g = d.add_digital_group()
            g.add_digital("Enable", [(0, 0), (5, 1)])
            g.add_measured_digital("IsActVld", df)
        """
        g = SignalGroup(ylabel, self._signal_map, mode="digital")
        self._groups.append(g)
        return g

    def _implicit_digital_group(self) -> SignalGroup:
        """Return the last digital group; create one at the end if none exists."""
        for g in reversed(self._groups):
            if g.mode == "digital":
                return g
        g = SignalGroup("", self._signal_map, mode="digital")
        self._groups.append(g)
        return g

    # ── Signal builders — delegate to group 0 (backward-compatible) ───────────

    def add_stepped(self, name: str, breakpoints: Breakpoints,
                    color: str = "#2ecc71", lw: float = 1.8, **kwargs) -> SteppedSignal:
        """Add a piecewise-constant signal to the default (first) analog subplot."""
        return self._groups[0].add_stepped(name, breakpoints, color=color, lw=lw, **kwargs)

    def add_lagged(self, name: str, source: Signal, tau: float = 1.5,
                   color: str = "#e74c3c", lw: float = 2.0, **kwargs) -> LaggedSignal:
        """Add a first-order lag signal to the default analog subplot."""
        return self._groups[0].add_lagged(name, source, tau=tau, color=color, lw=lw, **kwargs)

    def add_raw(self, name: str, t_data: np.ndarray, v_data: np.ndarray,
                color: str = "#e67e22", **kwargs) -> RawSignal:
        """Add a measured/simulated data signal to the default analog subplot."""
        return self._groups[0].add_raw(name, t_data, v_data, color=color, **kwargs)

    def add_measured(self, name: str, df, time_col: str = "time",
                     value_col: Optional[str] = None,
                     color: str = "#e67e22", lw: float = 1.8, **kwargs) -> RawSignal:
        """
        Add a DataFrame column signal to the default analog subplot.

        Example:
            d.add_measured("Speed", df, time_col="t", value_col="speed_rpm")
        """
        return self._groups[0].add_measured(
            name, df, time_col=time_col, value_col=value_col,
            color=color, lw=lw, **kwargs
        )

    # ── Annotation builders — delegate to group 0 (backward-compatible) ───────

    def add_derived(self, name: str, a, b,
                    color: str = "#95a5a6", **kwargs) -> "DerivedSignal":
        """Add a computed signal to the default (first) analog subplot."""
        return self._groups[0].add_derived(name, a, b, color=color, **kwargs)

    def add_threshold(self, value: float, label: str = "", color: str = "#3498db",
                      ls: str = "--", **kwargs) -> "Diagram":
        self._groups[0].add_threshold(value, label, color, ls, **kwargs)
        return self

    def add_tolerance(self, signal_name: str, tolerance: float,
                      color: str = "#9b59b6", **kwargs) -> "Diagram":
        self._groups[0].add_tolerance(signal_name, tolerance, color, **kwargs)
        return self

    def add_callout(self, signal_name: str, t: float, label: str = "",
                    offset: Tuple[float, float] = (-3.0, 500.0), **kwargs) -> "Diagram":
        self._groups[0].add_callout(signal_name, t, label, offset, **kwargs)
        return self

    # ── Digital — backward-compatible (adds to implicit digital group) ─────────

    def add_digital(self, name: str, breakpoints: Breakpoints,
                    color: str = "#2980b9", **kwargs) -> DigitalSignal:
        """Add a binary signal to the implicit digital panel (always last)."""
        return self._implicit_digital_group().add_digital(name, breakpoints, color=color, **kwargs)

    def add_measured_digital(self, name: str, df, time_col: str = "time",
                             value_col: Optional[str] = None,
                             color: str = "#2980b9", lw: float = 1.8,
                             **kwargs) -> RawSignal:
        """Add a 0/1 DataFrame column to the implicit digital panel (always last)."""
        return self._implicit_digital_group().add_measured_digital(
            name, df, time_col=time_col, value_col=value_col,
            color=color, lw=lw, **kwargs
        )

    # ── Diagram-level annotations ─────────────────────────────────────────────

    def add_vline(self, t: float, label: str = "", color: str = "#c0392b",
                  **kwargs) -> "Diagram":
        """Add a vertical marker line across all subplots."""
        self._vlines.append(VLine(t, label, color, **kwargs))
        return self

    def add_vspan(self, t0: float, t1: float, label: str = "",
                  color: str = "#f39c12", **kwargs) -> "Diagram":
        """Add a shaded vertical span across all subplots."""
        self._vspans.append(VSpan(t0, t1, label, color, **kwargs))
        return self

    def add_phase(self, t0: float, t1: float, label: str,
                  color: str = "#555555",
                  show_vline: bool = True,
                  vline_label: bool = True,
                  status: Optional[str] = None) -> PhaseLabel:
        """
        Add a phase label and return the PhaseLabel object.

        Draws a double-headed arrow + label under the bottom axes.
        When ``show_vline=True`` (default) also draws a dashed vertical line at
        ``t0`` across every subplot; ``vline_label=True`` adds the phase name
        rotated 90° on the line (FMU / MATLAB step-marker style).

        ``status`` overrides ``color``:
            - ``"pass"`` → green vline and label
            - ``"fail"`` → red vline and label + × marker at top of each subplot
            - ``None``   → use ``color`` (default gray)

        The returned PhaseLabel can be passed directly to ``add_transient_analysis(phase=...)``
        to restrict the analysis window to this phase's time range.
        """
        ph = PhaseLabel(t0, t1, label, color, show_vline=show_vline,
                        vline_label=vline_label, status=status)
        self._phase_labels.append(ph)
        return ph

    # ── Backward-compat properties ────────────────────────────────────────────

    @property
    def _analog_groups(self) -> List[SignalGroup]:
        return [g for g in self._groups if g.mode == "analog"]

    @property
    def _digital_signals(self) -> List[Signal]:
        return [sig for g in self._groups if g.mode == "digital" for sig in g.signals]

    # ── Render ────────────────────────────────────────────────────────────────

    def render_plotly(self, output=None, show: bool = True):
        """
        Render to an interactive Plotly Figure.

        Parameters
        ----------
        output : str or Path, optional
            If provided, saves a standalone interactive HTML file.
        show : bool
            Open in the browser (default True).

        Returns
        -------
        plotly.graph_objects.Figure
        """
        from .renderer_plotly import render_plotly
        return render_plotly(self, output=output, show=show)

    def run_dash(self, port: int = 8050, debug: bool = False) -> None:
        """
        Launch a full Dash application for this Diagram.

        Opens a browser tab at http://localhost:<port>/.
        Blocks until the server is stopped (Ctrl-C).

        Parameters
        ----------
        port  : TCP port (default 8050)
        debug : Enable Dash hot-reload / debug panel
        """
        from .dash_app import run_dash
        run_dash(self, port=port, debug=debug)

    def render(self, output: Optional[Union[str, Path, List]] = None,
               show: bool = True, dpi: int = 150) -> plt.Figure:
        """
        Build and render the figure.

        Parameters
        ----------
        output : str, Path, or list thereof, optional
            File path(s) to save (PNG or SVG inferred from extension).
        show : bool
            Call plt.show() after rendering.
        dpi : int
            Resolution for raster output.

        Returns
        -------
        matplotlib.figure.Figure
        """
        if show:
            import os
            import matplotlib
            if ("MPLBACKEND" not in os.environ
                    and matplotlib.get_backend().lower()
                    in ("agg", "pdf", "ps", "svg", "cairo")):
                for _be in ("TkAgg", "Qt5Agg", "Qt6Agg", "wxAgg"):
                    try:
                        plt.switch_backend(_be)
                        break
                    except Exception:
                        continue

        from . import renderer
        fig = renderer.render(self)

        if output is not None:
            paths = [output] if isinstance(output, (str, Path)) else output
            for p in paths:
                p = Path(p)
                p.parent.mkdir(parents=True, exist_ok=True)
                fmt = p.suffix.lstrip(".") or "png"
                fig.savefig(p, format=fmt, bbox_inches="tight", dpi=dpi)

        if show:
            renderer.add_nav_buttons(fig, fig.get_axes(),
                                     float(self.t[0]), float(self.t[-1]))
            plt.show()

        return fig

    def export(self, path, dpi: int = 150) -> None:
        """
        Export to draw.io (.drawio) or Excalidraw (.excalidraw) based on extension.

        The diagram is rendered to a PNG background image; key annotations
        (phase labels, threshold labels, title, vline/vspan labels) are added
        as native editable shapes so collaborators can edit without Python.

        Parameters
        ----------
        path : str or Path — must end with .drawio or .excalidraw
        dpi  : resolution of the embedded background PNG

        Example
        -------
            d.export("output/analysis.drawio")
            d.export("output/analysis.excalidraw")
        """
        from . import export as _export
        from pathlib import Path as _Path
        p = _Path(path)
        if p.suffix == ".drawio":
            _export.export_drawio(self, p, dpi=dpi)
        elif p.suffix == ".excalidraw":
            _export.export_excalidraw(self, p, dpi=dpi)
        else:
            raise ValueError(
                f"Unsupported export format: {p.suffix!r}. Use .drawio or .excalidraw"
            )
