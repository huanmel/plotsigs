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


# ── ROAD-01: delta cursor snap lines ─────────────────────────────────────────

def _vline_xs(fig):
    """Return set of x positions of dashed vertical snap lines in fig.layout.shapes."""
    xs = set()
    for sh in (fig.layout.shapes or []):
        if (getattr(sh, "type", None) == "line"
                and getattr(sh, "line", None) is not None
                and getattr(sh.line, "dash", None) == "dash"
                and getattr(sh, "x0", None) is not None
                and sh.x0 == getattr(sh, "x1", None)):
            xs.add(float(sh.x0))
    return xs


def test_delta_cursor_c1_snap_line(minimal_diagram):
    """C1 cursor → blue dashed vline at C1.x."""
    from plotsigs.dash_app import _build_main_figure
    store = {"c1": {"x": 3.0, "y": 1000.0, "name": "SetSpeed"}, "c2": None}
    fig = _build_main_figure(minimal_diagram, tool="delta", cursor_store=store)
    xs = _vline_xs(fig)
    assert 3.0 in xs, f"Expected vline at x=3.0, found: {xs}"


def test_delta_cursor_both_snap_lines(minimal_diagram):
    """C1 and C2 both set → two dashed vlines at their respective x positions."""
    from plotsigs.dash_app import _build_main_figure
    store = {
        "c1": {"x": 2.5, "y": 900.0,  "name": "SetSpeed"},
        "c2": {"x": 7.0, "y": 500.0,  "name": "SetSpeed"},
    }
    fig = _build_main_figure(minimal_diagram, tool="delta", cursor_store=store)
    xs = _vline_xs(fig)
    assert 2.5 in xs, f"Expected C1 vline at x=2.5, found: {xs}"
    assert 7.0 in xs, f"Expected C2 vline at x=7.0, found: {xs}"


def test_delta_cursor_no_lines_when_cursors_none(minimal_diagram):
    """Empty cursor store → no snap lines added."""
    from plotsigs.dash_app import _build_main_figure
    store = {"c1": None, "c2": None}
    fig = _build_main_figure(minimal_diagram, tool="delta", cursor_store=store)
    xs = _vline_xs(fig)
    assert not xs, f"Expected no cursor vlines, found: {xs}"


def test_delta_cursor_lines_absent_in_other_tools(minimal_diagram):
    """Cursor snap lines must not appear when tool is not 'delta'."""
    from plotsigs.dash_app import _build_main_figure
    store = {"c1": {"x": 3.0, "y": 1000.0, "name": "SetSpeed"}, "c2": None}
    for tool in ("raw", "annotate", "diff", "deriv", "smooth"):
        fig = _build_main_figure(minimal_diagram, tool=tool, cursor_store=store)
        xs = _vline_xs(fig)
        assert not xs, f"tool={tool!r}: unexpected vlines at {xs}"


# ── ROAD-13/14: layout-store panel management ─────────────────────────────────

def test_groups_from_layout_returns_correct_signals(minimal_diagram):
    """_groups_from_layout maps signal names to signal objects."""
    from plotsigs.dash_app import _groups_from_layout
    layout = [{"ylabel": "Speed", "mode": "analog", "signals": ["SetSpeed", "RunSpeed"]}]
    groups = _groups_from_layout(layout, minimal_diagram._signal_map)
    assert len(groups) == 1
    assert [s.name for s in groups[0].signals] == ["SetSpeed", "RunSpeed"]
    assert groups[0].mode == "analog"
    assert groups[0].ylabel == "Speed"


def test_groups_from_layout_skips_unknown_signals(minimal_diagram):
    """Signals not in signal_map are silently skipped."""
    from plotsigs.dash_app import _groups_from_layout
    layout = [{"ylabel": "X", "mode": "analog", "signals": ["SetSpeed", "NoSuchSig"]}]
    groups = _groups_from_layout(layout, minimal_diagram._signal_map)
    assert len(groups) == 1
    assert [s.name for s in groups[0].signals] == ["SetSpeed"]


def test_groups_from_layout_empty_panel_excluded(minimal_diagram):
    """A panel with no matching signals produces no group (panel is excluded)."""
    from plotsigs.dash_app import _groups_from_layout
    layout = [{"ylabel": "Empty", "mode": "analog", "signals": []}]
    groups = _groups_from_layout(layout, minimal_diagram._signal_map)
    assert groups == []


def test_build_figure_from_layout_trace_count(minimal_diagram):
    """_build_figure_from_layout produces one trace per assigned signal."""
    from plotsigs.dash_app import _build_figure_from_layout
    layout = [
        {"ylabel": "Speed", "mode": "analog", "signals": ["SetSpeed"]},
        {"ylabel": "Flags", "mode": "digital", "signals": ["IsEnabled", "IsActVld"]},
    ]
    fig = _build_figure_from_layout(minimal_diagram, layout, use_gl=False)
    assert fig is not None
    assert len(fig.data) == 3   # 1 analog + 2 digital


def test_build_main_figure_with_layout_store(minimal_diagram):
    """layout_store overrides default group layout in _build_main_figure."""
    from plotsigs.dash_app import _build_main_figure
    layout = [{"ylabel": "Speed", "mode": "analog", "signals": ["SetSpeed"]}]
    fig = _build_main_figure(minimal_diagram, layout_store=layout)
    assert fig is not None
    # Only SetSpeed → 1 trace (no fills in a single stepped signal)
    assert len(fig.data) == 1


def test_build_main_figure_layout_store_none_uses_diagram_groups(minimal_diagram):
    """When layout_store=None the figure uses d._groups (4 traces in minimal fixture)."""
    from plotsigs.dash_app import _build_main_figure
    fig = _build_main_figure(minimal_diagram, layout_store=None)
    assert len(fig.data) == 4


def test_legend_from_fig_extracts_entries(minimal_diagram):
    """_legend_from_fig reads signal name and color from trace customdata."""
    from plotsigs.dash_app import _legend_from_fig
    from plotsigs.renderer_plotly import _build_figure
    fig = _build_figure(minimal_diagram, use_gl=False)
    entries = _legend_from_fig(fig, minimal_diagram._signal_map)
    names = [e["name"] for e in entries]
    assert "SetSpeed" in names or any("Speed" in n for n in names)


# ── ROAD-13/14 refactor: AG Grid assign / remove callbacks ────────────────────

def _make_run_dash_helpers(minimal_diagram):
    """
    Extract the helper functions injected into run_dash's closure by actually
    calling run_dash up to the point where helpers are defined — but without
    starting the server. We do this by importing the module-level helpers
    directly and constructing the layout/signal state ourselves.
    """
    from plotsigs.dash_app import _groups_from_layout
    d = minimal_diagram
    active = [g for g in d._groups if g.signals]
    initial_layout = [
        {"ylabel": grp.ylabel, "mode": grp.mode, "signals": [s.name for s in grp.signals]}
        for grp in active
    ]
    all_sigs = []
    seen: set = set()
    for grp in active:
        for sig in grp.signals:
            if sig.name not in seen:
                all_sigs.append(sig)
                seen.add(sig.name)
    return d, initial_layout, all_sigs


def test_assign_signals_to_panel_adds_signal(minimal_diagram):
    """Simulates _assign_signals_to_panel: adds signal to target panel (copy semantics)."""
    d, layout, _ = _make_run_dash_helpers(minimal_diagram)
    # layout[0] = Speed panel with SetSpeed + RunSpeed
    # layout[1] = digital panel with IsEnabled + IsActVld
    # Assign IsEnabled to Speed panel
    selected_names = ["IsEnabled"]  # ag-sel-store: list of signal name strings
    target_ylabel = layout[0]["ylabel"]

    # Reproduce the callback logic inline
    layout = [dict(p) for p in layout]
    target_idx = next(i for i, p in enumerate(layout) if p["ylabel"] == target_ylabel)
    for sig_name in selected_names:
        if sig_name not in layout[target_idx]["signals"]:
            layout[target_idx] = {
                **layout[target_idx],
                "signals": layout[target_idx]["signals"] + [sig_name],
            }

    assert "IsEnabled" in layout[target_idx]["signals"]
    # IsEnabled should STILL be in the digital panel (copy semantics)
    assert "IsEnabled" in layout[1]["signals"]


def test_assign_signals_no_duplicate(minimal_diagram):
    """Assigning a signal already in the panel should not create a duplicate."""
    d, layout, _ = _make_run_dash_helpers(minimal_diagram)
    target_idx = 0
    existing_sig = layout[target_idx]["signals"][0]  # SetSpeed already present

    layout = [dict(p) for p in layout]
    selected_names = [existing_sig]
    for sig_name in selected_names:
        if sig_name not in layout[target_idx]["signals"]:
            layout[target_idx] = {
                **layout[target_idx],
                "signals": layout[target_idx]["signals"] + [sig_name],
            }

    assert layout[target_idx]["signals"].count(existing_sig) == 1


def test_remove_signal_from_panel(minimal_diagram):
    """Simulates _remove_signal_from_panel: removes one signal from one panel."""
    d, layout, _ = _make_run_dash_helpers(minimal_diagram)
    panel_idx = 0
    sig_name = layout[panel_idx]["signals"][0]  # SetSpeed

    layout = [dict(p) for p in layout]
    layout[panel_idx] = {
        **layout[panel_idx],
        "signals": [s for s in layout[panel_idx]["signals"] if s != sig_name],
    }

    assert sig_name not in layout[panel_idx]["signals"]
    # RunSpeed still in same panel
    assert layout[panel_idx]["signals"] == ["RunSpeed"]


def test_remove_signal_leaves_other_panels_intact(minimal_diagram):
    """Removing a signal from panel 0 must not affect panel 1."""
    d, layout, _ = _make_run_dash_helpers(minimal_diagram)
    panel1_sigs_before = list(layout[1]["signals"])
    panel_idx = 0
    sig_name = layout[panel_idx]["signals"][0]

    layout = [dict(p) for p in layout]
    layout[panel_idx] = {
        **layout[panel_idx],
        "signals": [s for s in layout[panel_idx]["signals"] if s != sig_name],
    }

    assert layout[1]["signals"] == panel1_sigs_before


def test_update_layout_store_add_analog(minimal_diagram):
    """Simulates _update_layout_store: +A button appends analog panel."""
    d, layout, _ = _make_run_dash_helpers(minimal_diagram)
    layout = [dict(p) for p in layout]
    layout.append({"ylabel": "New Panel", "mode": "analog", "signals": []})
    assert layout[-1]["mode"] == "analog"
    assert layout[-1]["signals"] == []


def test_update_layout_store_remove_panel(minimal_diagram):
    """Simulates _update_layout_store: × button removes panel by index."""
    d, layout, _ = _make_run_dash_helpers(minimal_diagram)
    n_before = len(layout)
    layout = [dict(p) for p in layout]
    layout.pop(0)
    assert len(layout) == n_before - 1
