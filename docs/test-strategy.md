# Test Strategy

Automated test approach for plotsigs. The goal is to catch regressions introduced
during the implementation plan (ROAD-21 → 22 → 20 → 01 → 02) without requiring
manual browser interaction after every change.

---

## What already exists

`tests/test_signals.py` covers:

- All signal types (`SteppedSignal`, `LaggedSignal`, `DigitalSignal`, `RawSignal`, `DerivedSignal`)
- Analysis functions (settling time, overshoot, rise time, step detection)
- Matplotlib render smoke tests (full `Diagram.render()`)
- `plot_signals()` and `load_yaml()` entry points

These run in under 2 seconds with no external dependencies. Keep them passing at all times.

---

## What is missing

| Gap | Risk | Adds coverage for |
| --- | --- | --- |
| `_find_nearest_signal` unit tests | High — ROAD-22 rewrites this function | DASH-01 regression (digital lane), DASH-03 (wrong y) |
| Figure structure assertions | High — ROAD-22 changes trace types and adds `customdata` | Trace count, types, customdata shape |
| Callback unit tests (synthetic inputs) | Medium — ROAD-01/02 add new callback outputs | Annotation store, cursor store, export JSON |
| App startup smoke test | Low | Does the server start without crashing |

---

## Three test layers

### Layer 1 — Pure Python unit tests (no Dash, no browser)

Call the functions directly. No server, no browser, runs in milliseconds.
This is the most valuable layer.

**Target functions:**

- `_find_nearest_signal(click_point, t, active)` — signal identity from customdata
- `_classify_traces(fig, d)` — trace metadata mapping
- `_yaxis_ref(group_idx)` — axis reference string
- `_windowed_deriv(y, t, window)` — derivative calculation
- `minmax_decimate(t, y, n_out)` — preprocessing utility (future)

**Example — digital lane disambiguation (DASH-01 regression):**

```python
def test_find_nearest_digital_upper_lane(diagram_fixture, active_groups):
    t = np.linspace(0, 10, 1000)
    # Simulate what Plotly sends after ROAD-22: customdata carries identity
    click_point = {"x": 5.0, "customdata": ["IsActVld", 1]}
    sig, y_snap, group_idx = _find_nearest_signal(click_point, t, active_groups)
    assert sig.name == "IsActVld"
    assert group_idx == 1
```

**Example — analog signal y-snap:**

```python
def test_find_nearest_analog_y_value(diagram_fixture, active_groups):
    t = np.linspace(0, 10, 1000)
    click_point = {"x": 3.0, "customdata": ["SetSpeed", 0]}
    sig, y_snap, group_idx = _find_nearest_signal(click_point, t, active_groups)
    assert sig.name == "SetSpeed"
    assert y_snap == pytest.approx(1000.0, abs=1)  # stepped signal at t=3 → 1000
```

---

### Layer 2 — Figure structure tests (no browser)

Build a figure from the shared fixture and assert on `fig.data`. Catches trace layout
regressions without rendering anything in a browser.

**Write these as part of ROAD-22** — they lock in the expected post-ROAD-22 structure
and will fail immediately if a future change breaks the trace layout.

**Example — WebGL traces after ROAD-22:**

```python
def test_signal_traces_are_scattergl(plotly_figure):
    signal_traces = [t for t in plotly_figure.data if t.hoverinfo != "skip"]
    for tr in signal_traces:
        assert type(tr).__name__ == "Scattergl", f"Expected Scattergl, got {type(tr).__name__}"
```

**Example — customdata shape:**

```python
def test_signal_traces_have_customdata(plotly_figure, minimal_diagram):
    active = [g for g in minimal_diagram._groups if g.signals]
    signal_traces = [t for t in plotly_figure.data if getattr(t, "customdata", None) is not None]
    assert len(signal_traces) > 0
    for tr in signal_traces:
        # Each customdata entry must be [sig_name, group_idx]
        assert len(tr.customdata[0]) == 2
        sig_name, group_idx = tr.customdata[0]
        assert isinstance(sig_name, str)
        assert isinstance(group_idx, int)
```

**Example — trace count is stable:**

```python
def test_trace_count_matches_signals(plotly_figure, minimal_diagram):
    active = [g for g in minimal_diagram._groups if g.signals]
    expected_signal_traces = sum(len(g.signals) for g in active)
    signal_traces = [t for t in plotly_figure.data
                     if getattr(t, "customdata", None) is not None]
    assert len(signal_traces) == expected_signal_traces
```

---

### Layer 3 — Callback unit tests (synthetic inputs, no browser)

Dash callbacks are Python functions. Call them directly with fake inputs constructed
to match the shape Plotly/Dash would produce at runtime.

**Write these as part of ROAD-01 and ROAD-02.**

**Example — point annotation stores correct yaxis (DASH-03 regression):**

```python
def test_add_point_annotation_yaxis(minimal_diagram):
    fake_click = {
        "points": [{"x": 3.0, "customdata": ["SetSpeed", 0], "y": 1000.0}]
    }
    result = _add_annotation(
        n_clicks=1,
        click_data=fake_click,
        tool_state={"tool": "point", "color": "#e74c3c", "text": "peak"},
        existing_annotations=[],
        diagram=minimal_diagram,
    )
    assert len(result) == 1
    ann = result[0]
    assert ann["type"] == "point"
    assert ann["yaxis"] == "y"       # group 0 → "y"
    assert ann["y"] == pytest.approx(1000.0, abs=1)
```

**Example — annotation export round-trip (ROAD-02):**

```python
def test_annotation_export_import_roundtrip(minimal_annotations):
    # Export to JSON string
    export_result = _export_annotations(n_clicks=1, annotations=minimal_annotations)
    json_str = export_result["content"]

    # Import back — simulate base64 contents from dcc.Upload
    import base64, json
    b64 = base64.b64encode(json_str.encode()).decode()
    contents = f"data:application/json;base64,{b64}"

    restored = _import_annotations(contents=contents, existing=[])
    assert len(restored) == len(minimal_annotations)
    assert restored[0]["type"] == minimal_annotations[0]["type"]
    assert restored[0]["t"] == pytest.approx(minimal_annotations[0]["t"])
```

---

### Layer 4 — App startup smoke test (one test, optional CI)

Verifies the Dash server starts and serves the app without crashing. Does not
test any interaction — just the import and server init path.

```python
# tests/test_smoke.py
import pytest
from plotsigs.dash_app import run_dash

def test_app_builds_without_error(minimal_diagram):
    """_build_app() should return a Dash app without raising."""
    from plotsigs.dash_app import _build_app
    app = _build_app(minimal_diagram)
    assert app is not None
    assert app.layout is not None
```

This does not start the HTTP server — it only exercises the layout and callback
registration code. No `dash[testing]`, no browser, no Selenium.

---

## Shared fixture (`tests/conftest.py`)

One canonical `Diagram` used across all test files:

```python
import numpy as np
import pytest
from plotsigs import Diagram

@pytest.fixture
def minimal_diagram():
    """
    One analog group (2 signals) + one digital group (2 signals).
    Known stepped values for deterministic assertions.

    Analog group (idx 0):
      SetSpeed: 0 → 1000 at t=2 → 500 at t=6
      RunSpeed: 0 →  800 at t=2 → 450 at t=6  (slightly lower at all times)

    Digital group (idx 1):
      IsEnabled: 0→1 at t=2, 1→0 at t=8
      IsActVld:  0→1 at t=3
    """
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
    """Plotly figure built from the shared fixture — post-ROAD-22 structure."""
    from plotsigs.renderer_plotly import _build_main_figure
    return _build_main_figure(minimal_diagram)


@pytest.fixture
def minimal_annotations():
    return [
        {"type": "phase", "t0": 1.0, "t1": 3.0, "label": "RAMP", "color": "#3498db"},
        {"type": "point", "t": 5.0, "y": 1000.0, "yaxis": "y",
         "sig": "SetSpeed", "text": "peak", "color": "#e74c3c"},
        {"type": "bookmark", "t": 7.0, "label": "check here", "color": "#2ecc71"},
    ]
```

---

## What we explicitly don't do

| Approach | Why not |
| --- | --- |
| Selenium / `dash[testing]` for graph clicks | `clickData` is generated by Plotly's JS pipeline — cannot be triggered by a DOM click; catches nothing our callback tests don't |
| js2py for clientside callbacks | Unmaintained (no release since 2022); our JS callbacks are thin wrappers around figure data — testing the Python equivalent is more reliable |
| Snapshot / screenshot tests | Brittle across OS/font/GPU differences; figure structure assertions catch the same regressions |
| Testing the matplotlib backend via Dash | The matplotlib renderer has its own tests in `test_signals.py`; it is independent of Dash |

---

## Test file layout

```
tests/
├── conftest.py              ← shared fixtures (minimal_diagram, plotly_figure, ...)
├── test_signals.py          ← existing — signal types and analysis functions
├── test_figure.py           ← NEW (write with ROAD-22) — trace structure assertions
├── test_callbacks.py        ← NEW (write with ROAD-01/02) — callback unit tests
└── test_smoke.py            ← NEW (write once) — app builds without error
```

---

## Test coverage by implementation step

| Step | New tests to write |
| --- | --- |
| Step 0 (now) | `conftest.py`, skeleton `test_figure.py`, skeleton `test_callbacks.py` |
| ROAD-21 | `test_callbacks.py`: visibility store maps to correct trace indices |
| ROAD-22 | `test_figure.py`: Scattergl types, customdata shape, trace count; `test_callbacks.py`: `_find_nearest_signal` with synthetic `customdata` inputs |
| ROAD-20 | `test_figure.py`: resampler wraps figure without changing signal trace count |
| ROAD-01 | `test_callbacks.py`: delta cursor store → vlines present in figure shapes |
| ROAD-02 | `test_callbacks.py`: export JSON round-trip, import merges without duplication |

---

## Running the tests

```bash
# All tests
pytest tests/

# Signal/analysis only (fast, no Dash import)
pytest tests/test_signals.py

# Dash tests only
pytest tests/test_figure.py tests/test_callbacks.py tests/test_smoke.py

# With output
pytest tests/ -v
```

Add to `pyproject.toml` dev extras:

```toml
dev = ["pytest", "ruff", "black", "pandas>=1.5", "plotly>=5.18", "dash>=2.14"]
```
