"""
Figure structure tests — assert on fig.data without a browser.

Current state (pre-ROAD-22): all signal traces are go.Scatter.
Post-ROAD-22 tests (Scattergl, customdata) will be added here as part of that step.
"""

import plotly.graph_objects as go
import pytest


# ── Trace count and presence ──────────────────────────────────────────────────

def test_figure_has_traces(plotly_figure):
    assert len(plotly_figure.data) > 0


def test_trace_count_matches_signals(plotly_figure, minimal_diagram):
    """One trace per signal in the fixture — no fills in the minimal fixture."""
    active = [g for g in minimal_diagram._groups if g.signals]
    expected = sum(len(g.signals) for g in active)  # 2 analog + 2 digital = 4
    assert len(plotly_figure.data) == expected


# ── _classify_traces ──────────────────────────────────────────────────────────

def test_classify_traces_length_matches_data(plotly_figure, trace_meta):
    assert len(trace_meta) == len(plotly_figure.data)


def test_classify_traces_all_signals_found(trace_meta):
    """All 4 traces in the minimal fixture are signal traces (no fills)."""
    signal_entries = [m for m in trace_meta if m["is_signal"]]
    assert len(signal_entries) == 4


def test_classify_traces_group_assignment(trace_meta):
    """First two traces belong to group 0 (analog), last two to group 1 (digital)."""
    groups = [m["group_idx"] for m in trace_meta if m["is_signal"]]
    assert groups == [0, 0, 1, 1]


def test_classify_traces_signal_names(trace_meta):
    names = [m["sig_name"] for m in trace_meta if m["is_signal"]]
    assert names == ["SetSpeed", "RunSpeed", "IsEnabled", "IsActVld"]


# ── Subplot layout ────────────────────────────────────────────────────────────

def test_figure_has_two_subplots(plotly_figure):
    """Two active groups → two y-axes."""
    yaxes = [k for k in plotly_figure.layout.to_plotly_json()
             if k.startswith("yaxis")]
    assert len(yaxes) == 2


def test_analog_traces_on_first_axis(plotly_figure, trace_meta):
    """SetSpeed and RunSpeed should be bound to yaxis (row 1)."""
    analog_traces = [plotly_figure.data[i] for i, m in enumerate(trace_meta)
                     if m["is_signal"] and m["group_idx"] == 0]
    for tr in analog_traces:
        assert tr.yaxis == "y"


def test_digital_traces_on_second_axis(plotly_figure, trace_meta):
    """IsEnabled and IsActVld should be bound to yaxis2 (row 2)."""
    digital_traces = [plotly_figure.data[i] for i, m in enumerate(trace_meta)
                      if m["is_signal"] and m["group_idx"] == 1]
    for tr in digital_traces:
        assert tr.yaxis == "y2"


# ── ROAD-20: plotly-resampler integration ─────────────────────────────────────

def test_resampler_wraps_figure(minimal_diagram):
    """_build_figure(use_resampler=True) returns a FigureResampler instance."""
    pytest.importorskip("plotly_resampler")
    from plotly_resampler import FigureResampler
    from plotsigs.renderer_plotly import _build_figure
    fig = _build_figure(minimal_diagram, use_resampler=True)
    assert isinstance(fig, FigureResampler)


def test_signal_trace_count_unchanged_with_resampler(minimal_diagram, plotly_figure):
    """FigureResampler wrapper adds no extra traces vs plain go.Figure."""
    pytest.importorskip("plotly_resampler")
    from plotsigs.renderer_plotly import _build_figure
    fig_r = _build_figure(minimal_diagram, use_resampler=True)
    assert len(fig_r.data) == len(plotly_figure.data)
