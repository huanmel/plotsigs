"""
Shared pytest fixtures for plotsigs tests.

minimal_diagram — one analog group (2 stepped signals) + one digital group
(2 digital signals) with known breakpoints for deterministic assertions.

Signal values at key times:
  t=3.0: SetSpeed=1000, RunSpeed=800, IsEnabled=1, IsActVld=1
  t=7.0: SetSpeed=500,  RunSpeed=450, IsEnabled=1, IsActVld=1
  t=9.0: SetSpeed=500,  RunSpeed=450, IsEnabled=0, IsActVld=1

Digital display coordinates (DIGITAL_LANE_HEIGHT=1.4, DIGITAL_SIGNAL_SCALE=0.9):
  IsEnabled lane 0: value=1 → display_y = 1*0.9 + 0*1.4 = 0.9
  IsActVld  lane 1: value=1 → display_y = 1*0.9 + 1*1.4 = 2.3
"""

import numpy as np
import pytest

from plotsigs import Diagram


@pytest.fixture
def minimal_diagram():
    d = Diagram("fixture", t_end=10, n_points=1000)

    g_a = d.add_group("Speed [RPM]")
    g_a.add_stepped("SetSpeed", [(0, 0),   (2, 1000), (6, 500)])
    g_a.add_stepped("RunSpeed", [(0, 0),   (2,  800), (6, 450)])

    g_d = d.add_digital_group()
    g_d.add_digital("IsEnabled", [(0, 0), (2, 1), (8, 0)])
    g_d.add_digital("IsActVld",  [(0, 0), (3, 1)])

    return d


@pytest.fixture
def active_groups(minimal_diagram):
    return [g for g in minimal_diagram._groups if g.signals]


@pytest.fixture
def plotly_figure(minimal_diagram):
    """Base Plotly figure built in Dash mode (use_gl=False)."""
    from plotsigs.renderer_plotly import _build_figure
    return _build_figure(minimal_diagram, use_gl=False)


@pytest.fixture
def trace_meta(plotly_figure, minimal_diagram):
    """Trace metadata produced by _classify_traces for the minimal fixture."""
    from plotsigs.dash_app import _classify_traces
    return _classify_traces(plotly_figure, minimal_diagram)


@pytest.fixture
def minimal_annotations():
    # Keys match the format _overlay_annotations reads:
    #   phase: x, text, color
    #   point: x, y, yaxis, signal, text, color
    return [
        {"type": "phase", "x": 1.0, "text": "RAMP", "color": "#3498db"},
        {"type": "point", "x": 5.0, "y": 1000.0, "yaxis": "y",
         "signal": "SetSpeed", "text": "peak", "color": "#e74c3c"},
    ]
