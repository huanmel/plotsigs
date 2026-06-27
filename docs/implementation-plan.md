# Implementation Plan

Five items in dependency order. Complete each wave before starting the next —
ROAD-22 changes the trace layout that everything else builds on.

See [Test Strategy](test-strategy.md) for the full testing approach. Each step
below includes the tests to write alongside the production code.

---

## Step 0 — Test infrastructure (before touching production code)

**Goal:** Put the shared fixture and skeleton test files in place so every
subsequent step has a place to add tests immediately.

**Files:** `tests/conftest.py`, `tests/test_figure.py`,
`tests/test_callbacks.py`, `tests/test_smoke.py`, `pyproject.toml`

**Changes:**

1. Create `tests/conftest.py` with `minimal_diagram`, `active_groups`,
   `plotly_figure`, and `minimal_annotations` fixtures exactly as specified
   in the [Test Strategy — Shared fixture](test-strategy.md#shared-fixture-testsconftestpy).

2. Create skeleton files with one placeholder test each so pytest collects them
   without error:

   ```python
   # tests/test_figure.py
   def test_placeholder():
       pass   # replaced by ROAD-22 tests
   ```

3. Update `pyproject.toml` dev extras to include plotly and dash:

   ```toml
   dev = ["pytest", "ruff", "black", "pandas>=1.5", "plotly>=5.18", "dash>=2.14"]
   ```

4. Verify `pytest tests/` still passes (all existing `test_signals.py` tests green).

**Acceptance:** `pytest tests/ -v` passes with zero failures.

---

## Wave 1 — Foundation (performance + architecture)

### Step 1: ROAD-21 — Clientside visibility toggle

**Goal:** Remove the Python round-trip from signal visibility checkboxes.

**Files:** `plotsigs/dash_app.py`

**Changes:**

1. Add `dcc.Store(id="legend-store")` to the app layout.

2. Populate it from `_update_main` alongside the figure — one extra Output that
   writes `[{idx: i, name: sig_name}, ...]` for every signal trace in `trace_meta`.

3. Replace the existing `_toggle_visibility` Python `Patch()` callback with a
   clientside callback:

   ```javascript
   function(checked_vals, figure, legend) {
       if (!figure || !legend) return window.dash_clientside.no_update;
       var p = JSON.parse(JSON.stringify(figure));
       legend.forEach(function(e) {
           p.data[e.idx].visible = checked_vals.indexOf(String(e.idx)) !== -1;
       });
       return p;
   }
   ```

**Acceptance test:** Tick and untick a signal checkbox — trace appears/disappears
with no visible network delay and no spinner. Verify DevTools Network tab shows
no XHR on checkbox change.

**Tests to write (`tests/test_callbacks.py`):**

- `test_legend_store_maps_all_signal_traces` — assert `legend-store` contains one
  entry per signal trace with correct `idx` and `name` fields
- `test_legend_store_excludes_fill_traces` — fill traces must not appear in the store

**Risk:** Low. Visibility state is independent of annotation and click detection.

---

### Step 2: ROAD-22 — WebGL rendering + customdata click detection

**Goal:** Switch all signal traces to `go.Scattergl` (WebGL) and replace the
`bbox` + `mousedown` click detection with `customdata` identity lookup.

**Files:** `plotsigs/renderer_plotly.py`, `plotsigs/dash_app.py`

**Changes in `renderer_plotly.py`:**

1. Change every signal trace from `go.Scatter` to `go.Scattergl`.
   Fill traces (`fill="tonext"`, tolerance bands) stay as `go.Scatter` —
   WebGL does not support `fill="tonext"`.

2. Add `customdata=[[sig.name, group_idx]] * len(t)` to every signal trace.
   This is the identity that replaces `bbox`.

3. Remove the invisible marker block (the `marker=dict(size=8, opacity=0.01,
   maxdisplayed=500)` added for bbox capture). No longer needed.

4. Remove the `use_gl` parameter (or hardcode `use_gl=True`). The SVG fallback
   mode is retired.

**Changes in `dash_app.py`:**

1. Remove the `mousedown` JavaScript listener from the clientside setup callback.

2. Remove the clientside cursor-y callback (`_psig_mousedown_y` / bbox loop).
   The `cursor-y-store` input to `_set_cursor` / `_add_annotation` becomes unused.

3. Rewrite `_find_nearest_signal` to read identity from `customdata`:

   ```python
   def _find_nearest_signal(click_point, t, active):
       sig_name  = click_point["customdata"][0]
       group_idx = click_point["customdata"][1]
       grp  = active[group_idx]
       sig  = next(s for s in grp.signals if s.name == sig_name)
       pos  = int(np.argmin(np.abs(t - click_point["x"])))
       is_digital = grp.mode == "digital"
       if is_digital:
           from .style import DIGITAL_LANE_HEIGHT as _LH, DIGITAL_SIGNAL_SCALE as _SC
           lane_idx = grp.signals.index(sig)
           y_snap = float(sig.evaluate(t)[pos]) * _SC + lane_idx * _LH
       else:
           y_snap = float(sig.evaluate(t)[pos])
       return sig, y_snap, group_idx
   ```

   The function signature simplifies: no more `y_cursor` or `curve_number` args;
   takes the raw `clickData["points"][0]` dict instead.

4. Add hovermode switching: when tool changes, patch `layout.hovermode`:
   - View / zoom → `"x unified"`
   - Annotation / delta cursor / point note → `"closest"`

   This is a Python `Patch()` on tool selection (no figure rebuild needed).

5. Update `_classify_traces` / `trace_meta` — it can be simplified since
   curveNumber is no longer the primary identity mechanism. Keep it for the
   fill-trace skip logic; remove the `sig_name` field (now in customdata).

**Acceptance tests:**

- Click a signal in an analog subplot → correct signal selected, arrow on right trace
- Click upper / lower lane in digital subplot → correct lane selected (DASH-01 regression)
- Hover over main graph → unified tooltip visible across all subplots
- Switch to annotation tool → tooltip switches to nearest-point mode
- HTML export → annotations still at correct positions (DASH-02 regression)

**Tests to write (`tests/test_figure.py` and `tests/test_callbacks.py`):**

- `test_signal_traces_are_scattergl` — all signal traces must be `go.Scattergl`
- `test_fill_traces_are_scatter` — fill traces stay `go.Scatter`
- `test_signal_traces_have_customdata` — every signal trace has `customdata[0] == [name, group_idx]`
- `test_trace_count_matches_signals` — total signal traces equals sum of signals across groups
- `test_find_nearest_analog` — synthetic `customdata` click → correct signal, correct y-snap
- `test_find_nearest_digital_upper_lane` — clicking lane 2 returns lane 2 signal (DASH-01 regression)
- `test_find_nearest_digital_lower_lane` — clicking lane 0 returns lane 0 signal

**Risk:** Medium. The `_find_nearest_signal` signature changes propagate to
`_add_annotation` and `_set_cursor`. Both must be updated in the same commit.
Run the full acceptance test list before merging.

---

### Step 3: ROAD-20 — plotly-resampler

**Goal:** For signals with >50k points, send only ~2,000 display points to the
browser and fetch full-resolution slices on zoom.

**Files:** `plotsigs/dash_app.py`, `pyproject.toml`

**Changes:**

1. Add optional dependency:

   ```toml
   [project.optional-dependencies]
   dash = ["plotly>=5.18", "dash>=2.14", "plotly-resampler>=0.9"]
   ```

2. Wrap the figure in `_build_main_figure`:

   ```python
   from plotly_resampler import FigureResampler
   fig = FigureResampler(
       make_subplots(...),
       default_n_shown_samples=2_000,
   )
   # Add traces via fig.add_trace(..., hf_x=t, hf_y=values)
   # instead of go.Scattergl(x=t, y=values)
   ```

3. Register resampler callbacks after the app is created:

   ```python
   fig.register_update_graph_callback(app, "main-graph")
   ```

4. Add `prevent_initial_call=True` and `allow_duplicate=True` where needed on
   existing `relayoutData` callbacks (x-axis sync, zoom-linked annotations ROAD-07)
   to avoid conflicts with the resampler's own `relayoutData` consumer.

**Acceptance tests:**

- Load a 200k-point signal. Initial render is fast (2,000 points sent).
- Zoom into a 1-second window. Full-resolution data appears for that window.
- Place a point annotation during zoom. Arrow snaps to correct y-value.
- x-axis sync between main graph and analysis pane still works.

**Tests to write (`tests/test_figure.py`):**

- `test_resampler_wraps_figure` — `_build_main_figure` returns a `FigureResampler`
  instance (or a plain `go.Figure` when resampler not installed — optional dep)
- `test_signal_trace_count_unchanged_with_resampler` — wrapping in resampler does
  not add or remove traces; count matches pre-resampler baseline

**Risk:** Medium. The resampler intercepts `relayoutData` — must verify it
does not conflict with existing callbacks consuming the same event.
Implement after ROAD-22 so the resampler wraps the final `go.Scattergl` traces.

---

## Wave 2 — Usability (features on the stable foundation)

### Step 4: ROAD-01 — Delta cursor visual snap lines

**Goal:** Show dashed vertical lines at C1 and C2 cursor positions on the main
graph so the measurement bounds are visually obvious.

**Files:** `plotsigs/dash_app.py`

**Changes:**

1. Add `cursor-store` as a `State` input to `_update_main` (it is already
   available as a store; just wire it in).

2. In `_update_main`, after building the figure, when `tool == "delta"`:

   ```python
   c1 = cursor.get("C1")
   c2 = cursor.get("C2")
   if c1 is not None:
       fig.add_vline(x=c1, line=dict(color="#2196F3", dash="dash", width=1.5))
   if c2 is not None:
       fig.add_vline(x=c2, line=dict(color="#FF9800", dash="dash", width=1.5))
   ```

3. Lines disappear automatically when tool changes because `_update_main` rebuilds.

**Acceptance tests:**

- Set delta tool, click once → blue dashed line appears at C1.
- Click again → orange dashed line appears at C2, readout shows Δt/Δy.
- Switch to a different tool → both lines disappear.

**Risk:** Low. Additive change; does not touch click detection or annotations.

---

### Step 5: ROAD-02 — Annotation export / import

**Goal:** Save annotations to a JSON file and restore them into a new session.

**Files:** `plotsigs/dash_app.py`

**Changes:**

1. Add to sidebar layout:
   - "Export annotations" button + `dcc.Download(id="download-annotations")`
   - `dcc.Upload(id="import-annotations", children=html.Div("Import .json"))`

2. Export callback:

   ```python
   @app.callback(
       Output("download-annotations", "data"),
       Input("export-btn", "n_clicks"),
       State("annotations-store", "data"),
       prevent_initial_call=True,
   )
   def _export_annotations(_, annotations):
       import json, datetime
       stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
       return dcc.send_string(
           json.dumps(annotations or [], indent=2),
           f"annotations_{stamp}.json",
       )
   ```

3. Import callback:

   ```python
   @app.callback(
       Output("annotations-store", "data"),
       Input("import-annotations", "contents"),
       State("annotations-store", "data"),
       prevent_initial_call=True,
   )
   def _import_annotations(contents, existing):
       import json, base64
       if contents is None:
           return existing or []
       _, b64 = contents.split(",", 1)
       imported = json.loads(base64.b64decode(b64))
       merged = (existing or []) + imported   # merge, not replace
       return merged
   ```

   Import merges into the existing store so in-session annotations are not lost.

**Acceptance tests:**

- Place 3 annotations (mix of phase and point types).
- Click Export → `annotations_*.json` downloaded.
- Refresh the page (clears store).
- Import the JSON → all 3 annotations re-appear at correct positions.
- Import a second time → annotations are added (not replaced); no duplicates if
  the file is not imported twice.

**Risk:** Low. Annotations store is already the single source of truth.

---

## Dependency summary

```text
ROAD-21  (clientside visibility)
    │
    ▼
ROAD-22  (WebGL + customdata)   ← must complete before any new trace-adding feature
    │
    ▼
ROAD-20  (plotly-resampler)
    │
    ▼
ROAD-01  (delta cursor lines)   ─┐  independent of each other,
ROAD-02  (annotation export)    ─┘  can be done in parallel after ROAD-20
```

Features deferred until after this plan is complete: ROAD-13, ROAD-14, ROAD-15,
ROAD-16, ROAD-17, ROAD-18, ROAD-19. All depend on the trace layout and callback
architecture being stable after ROAD-22.
