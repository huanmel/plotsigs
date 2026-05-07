"""
Basic tests — run with: pytest tests/
"""

import numpy as np
import pytest
from plotsigs.signals import SteppedSignal, LaggedSignal, DigitalSignal, RawSignal, DerivedSignal


T = np.linspace(0, 60, 1000)


def test_stepped_basic():
    sig = SteppedSignal("cmd", [(0, 0), (10, 100), (30, 50)])
    v = sig.evaluate(T)
    assert v[0] == 0
    assert v[np.argmin(np.abs(T - 15))] == 100  # in [10,30) segment
    assert v[np.argmin(np.abs(T - 45))] == 50   # in [30,inf) segment
    assert v[-1] == 50


def test_stepped_single_segment():
    sig = SteppedSignal("cmd", [(0, 42)])
    v = sig.evaluate(T)
    assert np.all(v == 42)


def test_lagged_reaches_target():
    cmd = SteppedSignal("cmd", [(0, 0), (0.001, 1000)])
    lag = LaggedSignal("resp", source=cmd, tau=0.5)
    v = lag.evaluate(T)
    # after 5 tau the response should be > 99% of target
    assert v[-1] > 990


def test_lagged_starts_at_source():
    cmd = SteppedSignal("cmd", [(0, 500)])
    lag = LaggedSignal("resp", source=cmd, tau=2.0)
    v = lag.evaluate(T)
    assert v[0] == pytest.approx(500, abs=1)


def test_digital_binary():
    sig = DigitalSignal("flag", [(0, 0), (10, 1), (20, 0)])
    v = sig.evaluate(T)
    assert set(np.unique(v)).issubset({0.0, 1.0})


def test_raw_interpolation():
    t_data = np.array([0, 10, 20, 30])
    v_data = np.array([0, 100, 50, 200])
    sig = RawSignal("meas", t_data, v_data)
    v = sig.evaluate(T)
    assert v[0] == pytest.approx(0)
    # at t=10 should be 100
    idx = np.argmin(np.abs(T - 10))
    assert v[idx] == pytest.approx(100, abs=1)


def test_raw_from_dataframe():
    import pandas as pd
    df = pd.DataFrame({"time": [0, 10, 20, 30], "speed": [0, 100, 50, 200]})
    sig = RawSignal.from_dataframe(df, time_col="time", value_col="speed", name="meas")
    v = sig.evaluate(T)
    assert v[0] == pytest.approx(0)
    idx = np.argmin(np.abs(T - 10))
    assert v[idx] == pytest.approx(100, abs=1)


def test_raw_from_series():
    import pandas as pd
    s = pd.Series([0, 100, 50, 200], index=[0.0, 10.0, 20.0, 30.0], name="speed")
    sig = RawSignal.from_series(s, name="meas")
    v = sig.evaluate(T)
    assert v[0] == pytest.approx(0)
    idx = np.argmin(np.abs(T - 10))
    assert v[idx] == pytest.approx(100, abs=1)


def test_diagram_smoke():
    """Full render should not raise."""
    import matplotlib
    matplotlib.use("Agg")   # no display needed
    from plotsigs import Diagram
    d = Diagram("Test", t_end=30)
    cmd = d.add_stepped("cmd", [(0, 0), (10, 100)])
    d.add_lagged("resp", source=cmd, tau=1.0)
    d.add_digital("flag", [(0, 0), (5, 1)])
    d.add_threshold(80, label="MAX")
    d.add_vspan(10, 15, label="window")
    d.add_vline(12, label="event")
    d.add_phase(0, 10, "IDLE")
    fig = d.render(show=False)
    assert fig is not None


def test_multi_group_render():
    """Multiple analog subplots should render without error."""
    import matplotlib
    matplotlib.use("Agg")
    from plotsigs import Diagram

    d = Diagram("Multi-group test", t_end=30)

    g0 = d.add_group("Speed [RPM]")
    cmd = g0.add_stepped("cmd", [(0, 0), (10, 100)])
    g0.add_lagged("resp", source=cmd, tau=1.0)
    g0.add_threshold(80, label="MAX")

    g1 = d.add_group("Temp [°C]")
    g1.add_stepped("temp", [(0, 20), (10, 45)])

    d.add_digital("flag", [(0, 0), (5, 1)])
    d.add_vspan(10, 15, label="window")
    d.add_vline(12, label="event")
    d.add_phase(0, 10, "IDLE")

    fig = d.render(show=False)
    assert fig is not None
    assert len(fig.axes) == 3   # 2 analog groups + 1 implicit digital


def test_interleaved_groups():
    """Analog / digital / analog order should be preserved in subplot layout."""
    import matplotlib
    matplotlib.use("Agg")
    from plotsigs import Diagram

    d = Diagram("Interleaved", t_end=30)

    g_a1 = d.add_group("Speed")
    g_a1.add_stepped("cmd", [(0, 0), (10, 100)])

    g_d = d.add_digital_group()
    g_d.add_digital("flag", [(0, 0), (5, 1)])

    g_a2 = d.add_group("Temp")
    g_a2.add_stepped("temp", [(0, 20), (10, 45)])

    fig = d.render(show=False)
    assert fig is not None
    assert len(fig.axes) == 3   # analog, digital, analog


def test_plot_signals_quickplot():
    """plot_signals() should auto-detect digital groups and render without error."""
    import matplotlib
    matplotlib.use("Agg")
    import pandas as pd
    from plotsigs import plot_signals

    t = pd.Series(range(100), dtype=float)
    df = pd.DataFrame({
        "time":  t,
        "speed": t * 50,
        "temp":  20 + t * 0.3,
        "enable": (t > 30).astype(int),
        "fault":  (t > 80).astype(int),
    })

    fig = plot_signals(
        df,
        groups=[
            ["speed", "temp"],              # analog (mixed values)
            ["enable", "fault"],            # auto-detected as digital
        ],
        title="Quick plot test",
        show=False,
    )
    assert fig is not None
    assert len(fig.axes) == 2   # one analog + one digital


def test_plot_signals_explicit_mode():
    """plot_signals() should respect explicit mode in dict spec."""
    import matplotlib
    matplotlib.use("Agg")
    import pandas as pd
    from plotsigs import plot_signals

    t = pd.Series(range(50), dtype=float)
    df = pd.DataFrame({"time": t, "sig": t, "flag": (t > 25).astype(int)})

    fig = plot_signals(
        df,
        groups=[
            {"signals": ["sig"],  "ylabel": "Value",  "mode": "analog"},
            {"signals": ["flag"], "ylabel": "Flags",   "mode": "digital"},
        ],
        show=False,
    )
    assert len(fig.axes) == 2


def test_yaml_loader(tmp_path):
    """YAML loader should produce a renderable Diagram."""
    import matplotlib
    matplotlib.use("Agg")
    from plotsigs import load_yaml

    yaml_content = """
title: Test Diagram
time_end: 30

analog:
  - name: Set Speed
    type: stepped
    breakpoints: [[0, 1000], [10, 2500]]
  - name: Running Speed
    type: lagged
    source: Set Speed
    tau: 1.5

digital:
  - name: Enable
    breakpoints: [[0, 0], [5, 1]]

thresholds:
  - value: 1500
    label: MIN

annotations:
  - type: vspan
    t0: 5
    t1: 10
    label: window
"""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text(yaml_content)

    d = load_yaml(str(yaml_file))
    fig = d.render(show=False)
    assert fig is not None


# ── Analysis tests ────────────────────────────────────────────────────────────

def test_analysis_settling():
    from plotsigs import analysis
    t   = np.linspace(0, 30, 3000)
    cmd = SteppedSignal("cmd", [(0, 0), (5, 1000)])
    lag = LaggedSignal("fb", cmd, tau=2.0)
    sp  = cmd.evaluate(t)
    fb  = lag.evaluate(t)
    ts  = analysis.settling_time(t, sp, fb, threshold_pct=5.0, after_t=5.0)
    assert ts is not None
    assert ts > 5.0


def test_analysis_settling_never():
    from plotsigs import analysis
    t  = np.linspace(0, 10, 1000)
    sp = np.ones_like(t) * 1000.0
    fb = np.zeros_like(t)          # never reaches setpoint
    ts = analysis.settling_time(t, sp, fb, threshold_pct=5.0)
    assert ts is None


def test_analysis_overshoot_detected():
    from plotsigs import analysis
    t     = np.linspace(0, 20, 2000)
    wn, zeta = 2.0, 0.4
    wd    = wn * np.sqrt(1 - zeta**2)
    tau_c = np.clip(t - 5.0, 0, None)
    fb = 1000 * np.where(
        t < 5, 0,
        1 - np.exp(-zeta*wn*tau_c) * (
            np.cos(wd*tau_c) + zeta / np.sqrt(1 - zeta**2) * np.sin(wd*tau_c)
        ),
    )
    sp     = np.where(t < 5, 0.0, 1000.0)
    result = analysis.overshoot(t, sp, fb, after_t=5.0)
    assert result is not None
    assert result["pct"] > 0
    assert result["value"] > 1000.0


def test_analysis_no_overshoot():
    from plotsigs import analysis
    t   = np.linspace(0, 30, 3000)
    cmd = SteppedSignal("cmd", [(0, 0), (5, 1000)])
    lag = LaggedSignal("fb", cmd, tau=2.0)
    sp  = cmd.evaluate(t)
    fb  = lag.evaluate(t)
    assert analysis.overshoot(t, sp, fb, after_t=5.0) is None


def test_derived_signal():
    cmd = SteppedSignal("cmd", [(0, 0), (10, 1000)])
    lag = LaggedSignal("resp", cmd, tau=2.0)
    err = DerivedSignal("err", cmd, lag)
    v   = err.evaluate(T)
    assert v[0] == pytest.approx(0, abs=1)
    idx = np.argmin(np.abs(T - 15))
    assert v[idx] > 0     # cmd ahead of lag → positive error


def test_analysis_rise_time():
    from plotsigs import analysis
    t   = np.linspace(0, 20, 2000)
    wn, zeta = 2.0, 0.4
    wd    = wn * np.sqrt(1 - zeta**2)
    tau_c = np.clip(t - 5.0, 0, None)
    fb = 1000 * np.where(
        t < 5, 0,
        1 - np.exp(-zeta*wn*tau_c) * (
            np.cos(wd*tau_c) + zeta / np.sqrt(1 - zeta**2) * np.sin(wd*tau_c)
        ),
    )
    sp = np.where(t < 5, 0.0, 1000.0)
    rt = analysis.rise_time(t, sp, fb, after_t=5.0)
    assert rt is not None
    assert rt["duration"] > 0
    assert rt["t_lo"] < rt["t_hi"]
    assert abs(rt["v_lo"] - 100.0) < 5   # 10% of 1000
    assert abs(rt["v_hi"] - 900.0) < 5   # 90% of 1000


def test_analysis_find_steps():
    from plotsigs import analysis
    t  = np.linspace(0, 30, 3000)
    sp = np.where(t < 10, 0.0, np.where(t < 20, 1000.0, 500.0))
    steps = analysis.find_steps(t, sp)
    assert len(steps) == 2
    assert abs(steps[0]["t"] - 10.0) < 0.1
    assert abs(steps[1]["t"] - 20.0) < 0.1
    assert steps[0]["to_val"] == pytest.approx(1000.0, abs=1)


def test_analysis_before_t():
    from plotsigs import analysis
    t  = np.linspace(0, 40, 4000)
    sp = np.where(t < 10, 0.0, np.where(t < 25, 1000.0, 2000.0))
    cmd = SteppedSignal("cmd", [(0, 0), (10, 1000), (25, 2000)])
    lag = LaggedSignal("fb", cmd, tau=2.0)
    fb  = lag.evaluate(t)
    # Isolate first step only
    ts1 = analysis.settling_time(t, sp, fb, threshold_pct=5.0, after_t=10.0, before_t=25.0)
    assert ts1 is not None
    assert ts1 < 25.0


def test_comparison_render():
    import matplotlib
    matplotlib.use("Agg")
    from plotsigs import Diagram
    t_arr = np.linspace(0, 20, 2000)
    wn, zeta = 2.0, 0.4
    wd    = wn * np.sqrt(1 - zeta**2)
    tau_c = np.clip(t_arr - 5.0, 0, None)
    fb_v  = 1000 * np.where(
        t_arr < 5, 0,
        1 - np.exp(-zeta*wn*tau_c) * (
            np.cos(wd*tau_c) + zeta / np.sqrt(1 - zeta**2) * np.sin(wd*tau_c)
        ),
    )
    d = Diagram("Comparison smoke", t_end=20, n_points=2000)
    g = d.add_group("Speed")
    g.add_stepped("cmd", [(0, 0), (5, 1000)])
    g.add_raw("resp", t_arr, fb_v, color="#e74c3c")
    g.add_transient_analysis("cmd", "resp", tolerance_pct=5.0, after_t=5.0)
    g_err = d.add_group("Error")
    g_err.add_derived("error", "cmd", "resp", color="#8e44ad")
    fig = d.render(show=False)
    assert fig is not None
    assert len(fig.axes) == 2
