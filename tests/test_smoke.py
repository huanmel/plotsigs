"""
Smoke tests — verify the Dash pipeline initialises without crashing.
No HTTP server is started; no browser required.
"""

import pytest


def test_build_main_figure_does_not_crash(minimal_diagram):
    """_build_main_figure must return a non-empty figure for a valid Diagram."""
    from plotsigs.dash_app import _build_main_figure
    fig = _build_main_figure(minimal_diagram)
    assert fig is not None
    assert len(fig.data) > 0


def test_build_main_figure_with_tool_state(minimal_diagram):
    """_build_main_figure should not raise for any standard tool value."""
    from plotsigs.dash_app import _build_main_figure
    for tool in ("view", "delta", "point", "phase", "diff", "deriv", "rolling"):
        fig = _build_main_figure(minimal_diagram, tool=tool)
        assert fig is not None, f"Crashed for tool={tool!r}"


def test_build_main_figure_with_annotations(minimal_diagram, minimal_annotations):
    """Stored annotations must not prevent figure from building."""
    from plotsigs.dash_app import _build_main_figure
    fig = _build_main_figure(minimal_diagram, stored_annotations=minimal_annotations)
    assert fig is not None
    assert len(fig.data) > 0


def test_renderer_plotly_build_figure(minimal_diagram):
    """_build_figure from renderer_plotly must work for both use_gl modes."""
    from plotsigs.renderer_plotly import _build_figure
    for use_gl in (True, False):
        fig = _build_figure(minimal_diagram, use_gl=use_gl)
        assert fig is not None
        assert len(fig.data) > 0, f"No traces for use_gl={use_gl}"
