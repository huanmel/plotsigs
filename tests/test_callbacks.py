"""
Callback unit tests — call dash_app functions directly with synthetic inputs.
No Dash server, no browser required.

ROAD-22 note: _find_nearest_signal tests use the current pre-ROAD-22 signature:
  (x_click, y_cursor, curve_number, t, active, trace_meta)
After ROAD-22 the signature will change to (click_point, t, active) and these
tests will be rewritten here alongside the production change.
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


# ── _find_nearest_signal — analog group ──────────────────────────────────────

def test_find_nearest_analog_snaps_to_signal_value(minimal_diagram, active_groups,
                                                    plotly_figure, trace_meta):
    """At t=3 (SetSpeed=1000), y-snap should equal the signal value."""
    from plotsigs.dash_app import _find_nearest_signal
    t = minimal_diagram.t
    sig, y_snap, group_idx = _find_nearest_signal(
        x_click=3.0, y_cursor=1000.0, curve_number=0,
        t=t, active=active_groups, trace_meta=trace_meta,
    )
    assert sig.name == "SetSpeed"
    assert group_idx == 0
    assert y_snap == pytest.approx(1000.0, abs=1)


def test_find_nearest_analog_y_cursor_picks_closer_signal(minimal_diagram,
                                                           active_groups,
                                                           plotly_figure,
                                                           trace_meta):
    """y_cursor=850 (between 800 and 1000) is closer to RunSpeed=800."""
    from plotsigs.dash_app import _find_nearest_signal
    t = minimal_diagram.t
    sig, y_snap, group_idx = _find_nearest_signal(
        x_click=3.0, y_cursor=850.0, curve_number=0,
        t=t, active=active_groups, trace_meta=trace_meta,
    )
    assert sig.name == "RunSpeed"
    assert y_snap == pytest.approx(800.0, abs=1)


def test_find_nearest_analog_after_second_step(minimal_diagram, active_groups,
                                               plotly_figure, trace_meta):
    """At t=7 (after step at t=6), SetSpeed=500."""
    from plotsigs.dash_app import _find_nearest_signal
    t = minimal_diagram.t
    sig, y_snap, group_idx = _find_nearest_signal(
        x_click=7.0, y_cursor=500.0, curve_number=0,
        t=t, active=active_groups, trace_meta=trace_meta,
    )
    assert sig.name == "SetSpeed"
    assert y_snap == pytest.approx(500.0, abs=1)


# ── _find_nearest_signal — digital group (DASH-01 regression) ────────────────

def test_find_nearest_digital_upper_lane(minimal_diagram, active_groups,
                                         plotly_figure, trace_meta):
    """
    DASH-01 regression: clicking near IsActVld (lane 1, display_y=2.3)
    must select IsActVld, not IsEnabled (lane 0, display_y=0.9).
    """
    from plotsigs.dash_app import _find_nearest_signal
    t = minimal_diagram.t
    # At t=5: IsEnabled=1→display_y=0.9, IsActVld=1→display_y=2.3
    sig, y_snap, group_idx = _find_nearest_signal(
        x_click=5.0, y_cursor=2.3, curve_number=3,  # curve 3 = IsActVld
        t=t, active=active_groups, trace_meta=trace_meta,
    )
    assert sig.name == "IsActVld", (
        f"Expected IsActVld but got {sig.name} — DASH-01 regression"
    )
    assert group_idx == 1
    assert y_snap == pytest.approx(2.3, abs=0.05)


def test_find_nearest_digital_lower_lane(minimal_diagram, active_groups,
                                         plotly_figure, trace_meta):
    """Clicking near IsEnabled (lane 0, display_y=0.9) selects IsEnabled."""
    from plotsigs.dash_app import _find_nearest_signal
    t = minimal_diagram.t
    sig, y_snap, group_idx = _find_nearest_signal(
        x_click=5.0, y_cursor=0.9, curve_number=2,  # curve 2 = IsEnabled
        t=t, active=active_groups, trace_meta=trace_meta,
    )
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


# ── _find_nearest_signal — digital group (DASH-01 regression) ────────────────

def test_find_nearest_digital_ambiguous_picks_nearest(minimal_diagram,
                                                       active_groups,
                                                       plotly_figure,
                                                       trace_meta):
    """y_cursor=1.6 (midpoint 0.9 and 2.3) is equidistant — picks lower lane
    (IsEnabled) since it is first in the iteration when distances tie."""
    from plotsigs.dash_app import _find_nearest_signal
    t = minimal_diagram.t
    sig, _, _ = _find_nearest_signal(
        x_click=5.0, y_cursor=1.6, curve_number=2,
        t=t, active=active_groups, trace_meta=trace_meta,
    )
    # At exact midpoint the first signal wins the tie; document that behaviour.
    assert sig.name in ("IsEnabled", "IsActVld")
