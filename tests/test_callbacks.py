"""
Callback unit tests — call dash_app functions directly with synthetic inputs.
No Dash server, no browser required.

_find_nearest_signal uses the ROAD-22 customdata signature:
  (click_point, t, active)
where click_point is a dict with 'x', optional 'y', and 'customdata': [sig_name, group_idx].
"""

import numpy as np
import pytest


# ── _yaxis_ref ────────────────────────────────────────────────────────────────

def test_yaxis_ref_group_0():
    from plotsigs.dash_app import _yaxis_ref
    assert _yaxis_ref(0) == "y"


def test_yaxis_ref_group_1():
    from plotsigs.dash_app import _yaxis_ref
    assert _yaxis_ref(1) == "y2"


def test_yaxis_ref_group_3():
    from plotsigs.dash_app import _yaxis_ref
    assert _yaxis_ref(3) == "y4"


# ── _find_nearest_signal — ROAD-22 customdata routing ────────────────────────

def test_find_nearest_analog_routes_via_customdata(minimal_diagram, active_groups):
    """customdata [sig_name, group_idx] routes directly to the correct signal."""
    from plotsigs.dash_app import _find_nearest_signal
    t = minimal_diagram.t
    click_point = {"x": 3.0, "customdata": ["SetSpeed", 0]}
    sig, y_snap, group_idx = _find_nearest_signal(click_point, t, active_groups)
    assert sig.name == "SetSpeed"
    assert group_idx == 0
    assert y_snap == pytest.approx(1000.0, abs=1)  # SetSpeed=1000 at t=3


def test_find_nearest_analog_routes_second_signal(minimal_diagram, active_groups):
    """customdata routes to RunSpeed regardless of which signal has closer y."""
    from plotsigs.dash_app import _find_nearest_signal
    t = minimal_diagram.t
    click_point = {"x": 3.0, "customdata": ["RunSpeed", 0]}
    sig, y_snap, group_idx = _find_nearest_signal(click_point, t, active_groups)
    assert sig.name == "RunSpeed"
    assert y_snap == pytest.approx(800.0, abs=1)  # RunSpeed=800 at t=3


def test_find_nearest_analog_after_step(minimal_diagram, active_groups):
    """At t=7, SetSpeed=500 after the step at t=6."""
    from plotsigs.dash_app import _find_nearest_signal
    t = minimal_diagram.t
    click_point = {"x": 7.0, "customdata": ["SetSpeed", 0]}
    sig, y_snap, _ = _find_nearest_signal(click_point, t, active_groups)
    assert sig.name == "SetSpeed"
    assert y_snap == pytest.approx(500.0, abs=1)


# ── _find_nearest_signal — digital group (DASH-01 regression) ────────────────

def test_find_nearest_digital_upper_lane(minimal_diagram, active_groups):
    """
    DASH-01 regression: customdata ["IsActVld", 1] must select IsActVld at
    display_y = 1*0.9 + 1*1.4 = 2.3, not IsEnabled at 0.9.
    """
    from plotsigs.dash_app import _find_nearest_signal
    t = minimal_diagram.t
    click_point = {"x": 5.0, "customdata": ["IsActVld", 1]}
    sig, y_snap, group_idx = _find_nearest_signal(click_point, t, active_groups)
    assert sig.name == "IsActVld", (
        f"Expected IsActVld but got {sig.name} — DASH-01 regression"
    )
    assert group_idx == 1
    assert y_snap == pytest.approx(2.3, abs=0.05)


def test_find_nearest_digital_lower_lane(minimal_diagram, active_groups):
    """customdata ["IsEnabled", 1] selects IsEnabled at display_y=0.9."""
    from plotsigs.dash_app import _find_nearest_signal
    t = minimal_diagram.t
    click_point = {"x": 5.0, "customdata": ["IsEnabled", 1]}
    sig, y_snap, group_idx = _find_nearest_signal(click_point, t, active_groups)
    assert sig.name == "IsEnabled"
    assert y_snap == pytest.approx(0.9, abs=0.05)


# ── ROAD-21: legend-store entries (basis for clientside visibility callback) ──

def test_legend_entries_cover_all_signals(trace_meta, minimal_diagram):
    """legend_entries must have one entry per signal trace with correct idx."""
    active = [g for g in minimal_diagram._groups if g.signals]
    entries = []
    for tidx, meta in enumerate(trace_meta):
        if meta["is_signal"]:
            grp = active[meta["group_idx"]]
            sig_obj = next((s for s in grp.signals if s.name == meta["sig_name"]), None)
            if sig_obj:
                entries.append({"idx": tidx, "name": sig_obj.label or sig_obj.name})

    assert len(entries) == 4
    assert [e["idx"] for e in entries] == [0, 1, 2, 3]
    assert [e["name"] for e in entries] == [
        "SetSpeed", "RunSpeed", "IsEnabled", "IsActVld"
    ]


def test_legend_entries_exclude_fill_traces(trace_meta, minimal_diagram):
    """Fill traces (is_signal=False) must not appear in legend entries."""
    active = [g for g in minimal_diagram._groups if g.signals]
    entries = []
    for tidx, meta in enumerate(trace_meta):
        if meta["is_signal"]:
            grp = active[meta["group_idx"]]
            sig_obj = next((s for s in grp.signals if s.name == meta["sig_name"]), None)
            if sig_obj:
                entries.append(tidx)

    fill_idxs = [i for i, m in enumerate(trace_meta) if not m["is_signal"]]
    for fidx in fill_idxs:
        assert fidx not in entries, f"Fill trace {fidx} should not be in legend entries"


def test_find_nearest_fallback_no_customdata(minimal_diagram, active_groups):
    """When customdata is absent, falls back to first signal in group 0."""
    from plotsigs.dash_app import _find_nearest_signal
    t = minimal_diagram.t
    click_point = {"x": 3.0}  # no customdata key
    sig, y_snap, group_idx = _find_nearest_signal(click_point, t, active_groups)
    assert sig is not None
    assert group_idx == 0
    assert sig.name == active_groups[0].signals[0].name
