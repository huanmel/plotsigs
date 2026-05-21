"""
plotsigs.sim — Plant simulation helpers for control system timing diagrams.

Provides ready-to-use simulation functions for common plant models so that
diagram scripts focus on what to show, not on implementing integrators.

Supported models
----------------
first_order           : linear 1st-order system G(s)=1/(τs+1) via scipy.signal.lsim
second_order          : linear 2nd-order system via scipy.signal.lsim
second_order_saturated: 2nd-order with actuator rate saturation (nonlinear)
second_order_disturbed: 2nd-order with additive forcing disturbance (nonlinear)
transport_delay       : pure time delay (zero-order hold)

The underlying transfer function for all second-order variants is:

    G(s) = ωn² / (s² + 2ζωn·s + ωn²)

Linear cases use scipy.signal.lsim (matrix-exponential integrator — accurate
for any step size).  Nonlinear extensions fall back to Euler integration.
"""

from __future__ import annotations
import numpy as np
from scipy import signal


def first_order(
    t: np.ndarray,
    u: np.ndarray,
    tau: float,
    y0: float | None = None,
) -> np.ndarray:
    """Simulate a 1st-order plant G(s) = 1/(τs+1) via scipy.lsim.

    Parameters
    ----------
    t   : uniform time array [s]
    u   : plant input (e.g. setpoint), same length as t
    tau : time constant [s]
    y0  : initial output value; default u[0] (equilibrium start)
    """
    if y0 is None:
        y0 = float(u[0])
    sys = signal.TransferFunction([1.0], [tau, 1.0])
    _, y, _ = signal.lsim(sys, np.asarray(u, float) - y0, t)
    return y + y0


def second_order(
    t: np.ndarray,
    u: np.ndarray,
    omega_n: float,
    zeta: float,
    y0: float | None = None,
) -> np.ndarray:
    """Simulate a 2nd-order plant G(s) = ωn²/(s²+2ζωn·s+ωn²) via scipy.lsim.

    Parameters
    ----------
    t       : uniform time array [s]
    u       : plant input (e.g. setpoint), same length as t
    omega_n : natural frequency [rad/s]
    zeta    : damping ratio
    y0      : initial output value; default u[0] (equilibrium start)

    Returns
    -------
    y : output array
    """
    if y0 is None:
        y0 = float(u[0])
    sys = signal.TransferFunction(
        [omega_n**2],
        [1.0, 2.0 * zeta * omega_n, omega_n**2],
    )
    _, y, _ = signal.lsim(sys, np.asarray(u, float) - y0, t)
    return y + y0


def second_order_saturated(
    t: np.ndarray,
    u: np.ndarray,
    omega_n: float,
    zeta: float,
    max_rate: float,
    y0: float | None = None,
) -> np.ndarray:
    """2nd-order plant with output rate-of-change saturation.

    The saturation makes the plant nonlinear; Euler integration is used.

    Parameters
    ----------
    max_rate : maximum absolute rate of change of the output [units/s]
    """
    dt = float(t[1] - t[0])
    n = len(t)
    if y0 is None:
        y0 = float(u[0])
    y, v = np.zeros(n), np.zeros(n)
    y[0] = y0
    for i in range(1, n):
        acc  = omega_n**2 * (u[i] - y[i-1]) - 2.0 * zeta * omega_n * v[i-1]
        v[i] = float(np.clip(v[i-1] + acc * dt, -max_rate, max_rate))
        y[i] = y[i-1] + v[i] * dt
    return y


def second_order_disturbed(
    t: np.ndarray,
    u: np.ndarray,
    omega_n: float,
    zeta: float,
    disturbance: np.ndarray,
    y0: float | None = None,
) -> np.ndarray:
    """2nd-order plant with an additive forcing disturbance term.

    The disturbance enters as an extra acceleration [units/s], modelling
    external heat loads, friction forces, or any unmodelled input.
    Euler integration is used because the forcing is time-varying.

    Parameters
    ----------
    disturbance : additive forcing rate array, same length as t [units/s]
    """
    dt = float(t[1] - t[0])
    n = len(t)
    if y0 is None:
        y0 = float(u[0])
    y, v = np.zeros(n), np.zeros(n)
    y[0] = y0
    for i in range(1, n):
        acc  = omega_n**2 * (u[i] - y[i-1]) - 2.0 * zeta * omega_n * v[i-1] + disturbance[i]
        v[i] = v[i-1] + acc * dt
        y[i] = y[i-1] + v[i] * dt
    return y


def transport_delay(y: np.ndarray, t: np.ndarray, delay: float) -> np.ndarray:
    """Apply a pure time delay to signal y (zero-order hold padding).

    Parameters
    ----------
    delay : delay in seconds; values before the delay window are held at y[0]
    """
    steps = int(delay / (t[1] - t[0]))
    if steps <= 0:
        return y.copy()
    out = np.empty_like(y)
    out[:steps] = y[0]
    out[steps:] = y[:-steps]
    return out
