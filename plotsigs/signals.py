"""
Signal definitions — data layer, no matplotlib here.

All signals resolve to (t, values) arrays via .evaluate(t).
"""

from __future__ import annotations
import operator as _op
import numpy as np
from typing import List, Tuple, Optional


Breakpoints = List[Tuple[float, float]]   # [(t0, v0), (t1, v1), ...]


def to_digital_bps(t_arr: np.ndarray, v_arr: np.ndarray) -> Breakpoints:
    """Convert dense (t, v) arrays to transition-only breakpoints.

    Useful for creating DigitalSignal or EnumeratedSignal inputs from a
    boolean/integer numpy array without manually locating edge indices.

    Example:
        flag = (T_MR > threshold).astype(float)
        bps = to_digital_bps(t, flag)
        g.add_digital("FLAG", bps, color="red")
    """
    t_arr = np.asarray(t_arr, dtype=float)
    v_arr = np.asarray(v_arr, dtype=float)
    bps: Breakpoints = [(float(t_arr[0]), float(v_arr[0]))]
    for i in range(1, len(v_arr)):
        if v_arr[i] != v_arr[i - 1]:
            bps.append((float(t_arr[i]), float(v_arr[i])))
    return bps


# ── Base ──────────────────────────────────────────────────────────────────────

class Signal:
    """Abstract base. Subclasses must implement evaluate(t)."""

    def __init__(self, name: str, color: str = "#333333", lw: float = 1.8,
                 label: Optional[str] = None, ls: str = "-"):
        self.name = name
        self.color = color
        self.lw = lw
        self.ls = ls
        self.label = label or name

    def evaluate(self, t: np.ndarray) -> np.ndarray:
        raise NotImplementedError


# ── Analog signals ────────────────────────────────────────────────────────────

class SteppedSignal(Signal):
    """
    Piecewise-constant signal defined by (time, value) breakpoints.
    Typical use: command / set-point signals.

    Example:
        SteppedSignal("Set Speed", [(0, 1000), (10, 8500), (22, 1000)], color="green")
    """

    def __init__(self, name: str, breakpoints: Breakpoints,
                 color: str = "#2ecc71", lw: float = 1.8, **kwargs):
        super().__init__(name, color, lw, **kwargs)
        self.breakpoints = breakpoints

    def evaluate(self, t: np.ndarray) -> np.ndarray:
        s = np.zeros_like(t)
        bp = self.breakpoints
        for i, (t0, v) in enumerate(bp):
            t1 = bp[i + 1][0] if i + 1 < len(bp) else t[-1] + 1
            s[(t >= t0) & (t < t1)] = v
        return s


class LaggedSignal(Signal):
    """
    First-order lag (low-pass) response to a source signal.
    Simulates physical actuator / sensor response.

    Example:
        LaggedSignal("Running Speed", source=cmd_signal, tau=1.8, color="red")
    """

    def __init__(self, name: str, source: Signal, tau: float = 1.5,
                 color: str = "#e74c3c", lw: float = 2.0, **kwargs):
        super().__init__(name, color, lw, **kwargs)
        self.source = source
        self.tau = tau

    def evaluate(self, t: np.ndarray) -> np.ndarray:
        dt = t[1] - t[0]
        alpha = dt / (self.tau + dt)
        target = self.source.evaluate(t)
        s = np.zeros_like(t)
        s[0] = target[0]
        for i in range(1, len(t)):
            s[i] = s[i - 1] + alpha * (target[i] - s[i - 1])
        return s


class RawSignal(Signal):
    """
    Signal from measured / simulated data arrays (e.g. from CSV, DataFrame, or .mat).

    Example:
        RawSignal("Measured Speed", t_data, v_data, color="orange")
    """

    def __init__(self, name: str, t_data: np.ndarray, v_data: np.ndarray,
                 color: str = "#e67e22", lw: float = 1.8, **kwargs):
        super().__init__(name, color, lw, **kwargs)
        self.t_data = np.asarray(t_data, dtype=float)
        self.v_data = np.asarray(v_data, dtype=float)

    def evaluate(self, t: np.ndarray) -> np.ndarray:
        return np.interp(t, self.t_data, self.v_data)

    @classmethod
    def from_dataframe(cls, df, time_col: str, value_col: str,
                       name: str, **kwargs) -> "RawSignal":
        """
        Create from two columns of a pandas DataFrame.

        Example:
            sig = RawSignal.from_dataframe(df, "time", "speed", "Speed")
        """
        t = np.asarray(df[time_col].values, dtype=float)
        v = np.asarray(df[value_col].values, dtype=float)
        return cls(name, t, v, **kwargs)

    @classmethod
    def from_series(cls, series, name: str, **kwargs) -> "RawSignal":
        """
        Create from a pandas Series whose index is the time axis.

        Example:
            sig = RawSignal.from_series(df.set_index("time")["speed"], "Speed")
        """
        t = np.asarray(series.index, dtype=float)
        v = np.asarray(series.values, dtype=float)
        return cls(name, t, v, **kwargs)


# ── Derived / computed signals ────────────────────────────────────────────────

class DerivedSignal(Signal):
    """
    A signal computed from two other signals via an arithmetic operator.

    Default operation is subtraction so the natural use is an error signal:

        err = DerivedSignal("Error", setpoint_sig, feedback_sig)

    Any binary numpy-compatible callable can be passed as ``op``.
    """

    def __init__(self, name: str, a: Signal, b: Signal,
                 op=None, color: str = "#95a5a6", lw: float = 1.5, **kwargs):
        super().__init__(name, color, lw, **kwargs)
        self.a  = a
        self.b  = b
        self._op = op if op is not None else _op.sub

    def evaluate(self, t: np.ndarray) -> np.ndarray:
        return self._op(self.a.evaluate(t), self.b.evaluate(t))


# ── Enumerated signals ────────────────────────────────────────────────────────

class EnumeratedSignal(Signal):
    """
    Stepped signal with named integer levels — state machines, mode selectors.

    Pass a dense (t, v) array; the constructor auto-computes breakpoints so
    evaluation is O(levels) not O(N).  The renderer uses ``labels`` to set
    y-axis tick labels and ``colors`` to shade each level's band.

    Example:
        mode_enum = 1 * heating + 2 * circulation + 3 * cooling
        EnumeratedSignal(
            "Mode", t, mode_enum,
            labels={1: "Heating", 2: "Circulation", 3: "Cooling"},
            colors={1: "#e74c3c", 2: "#9b59b6", 3: "#3498db"},
        )
    """

    def __init__(self, name: str, t_data: np.ndarray, v_data: np.ndarray,
                 labels: dict, colors: Optional[dict] = None,
                 color: str = "#2980b9", lw: float = 2.5, **kwargs):
        super().__init__(name, color, lw, **kwargs)
        self.labels = labels                       # {int_code: str_label}
        self.colors = colors or {}                 # {int_code: str_color}
        self.breakpoints = to_digital_bps(t_data, v_data)

    def evaluate(self, t: np.ndarray) -> np.ndarray:
        s = np.zeros_like(t)
        bp = self.breakpoints
        for i, (t0, v) in enumerate(bp):
            t1 = bp[i + 1][0] if i + 1 < len(bp) else t[-1] + 1
            s[(t >= t0) & (t < t1)] = v
        return s


# ── Digital signals ───────────────────────────────────────────────────────────

class DigitalSignal(Signal):
    """
    Binary (0/1) signal defined by (time, value) breakpoints.
    Rendered in stacked lanes in the digital panel.

    Example:
        DigitalSignal("AC_Enable", [(0, 1), (2, 0), (5, 1), (9, 0)], color="blue")
    """

    def __init__(self, name: str, breakpoints: Breakpoints,
                 color: str = "#2980b9", lw: float = 1.8, **kwargs):
        super().__init__(name, color, lw, **kwargs)
        self.breakpoints = breakpoints

    def evaluate(self, t: np.ndarray) -> np.ndarray:
        s = np.zeros_like(t)
        bp = self.breakpoints
        for i, (t0, v) in enumerate(bp):
            t1 = bp[i + 1][0] if i + 1 < len(bp) else t[-1] + 1
            s[(t >= t0) & (t < t1)] = v
        return s
