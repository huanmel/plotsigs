# Known Issues

Bug log for the plotsigs Dash backend and Plotly renderer.
Status: **Fixed** = resolved in current codebase. **Open** = not yet resolved.

---

## Fixed

### DASH-01 — Digital signal click always selects first signal in lane
**Status:** Fixed  
**File:** `dash_app.py` → `_find_nearest_signal()`

**Symptom:** When clicking on a digital signal subplot, the annotation or delta cursor
always snapped to the first signal in the group (e.g. `AC_Enable`) regardless of which
lane the user actually clicked.

**Root cause:** Digital signals are rendered at display y-coordinates:
```
y_plot = raw_value * DIGITAL_SIGNAL_SCALE + lane_index * DIGITAL_LANE_HEIGHT
```
`_find_nearest_signal` was comparing the click y-coordinate (in display units, e.g. 5.1)
against raw signal values (0 or 1). All signals return the same distance from y_cursor,
so the first signal always won the tie.

**Fix:** For digital groups, compute `display_y = raw * scale + lane_idx * lane_h` before
comparing. The snapped `y` stored in the annotation is also the display y, so the arrow
points to the correct lane in the subplot.

**Debug evidence (dash_debug.log before fix):**
```
[find_nearest] curve=5 y_cursor=5.1 group=1 → AC_Enable y=1
```
After fix, `IsActVld` (lane 3, display_y = 1*0.9 + 3*1.4 = 5.1) is selected with dist=0.

---

### DASH-02 — Double annotations in saved HTML
**Status:** Fixed  
**File:** `dash_app.py` → `_download_html()`

**Symptom:** Every phase line and point note appeared twice in the HTML file downloaded
via the "Save as HTML" button.

**Root cause:** `_build_main_figure` calls `_overlay_annotations(fig, ...)` which writes
vlines and annotation objects into `fig.layout.shapes` / `fig.layout.annotations`.
Dash serialises this full layout into `main-graph.figure`. `_download_html` then
reconstructed a `go.Figure` from that dict (already containing the annotations)
and called `_overlay_annotations` again — duplicating everything.

**Fix:** Removed the redundant `_overlay_annotations` call from `_download_html`.
The layout already contains all annotations from the most recent `_update_main` render.

---

### DASH-03 — Point note arrow pointing to wrong position
**Status:** Fixed  
**File:** `dash_app.py` → `_add_annotation()`, `_overlay_annotations()`

**Symptom:** Point note annotations appeared at the top of the figure or at the wrong
subplot, not at the signal the user clicked.

**Root cause:** The annotation was storing `y_frac=0.5, yref="paper"` (fractional paper
coordinates) instead of the actual signal value in axis coordinates.

**Fix:**
1. `_add_annotation` calls `_find_nearest_signal` to get `y_snapped` (signal value at
   click x) and `group_idx`.
2. `_yaxis_ref(group_idx)` computes the correct Plotly y-axis reference string
   (`"y"` for group 0, `"y2"` for group 1, etc.).
3. Both are stored in the annotation dict: `{"y": y_snapped, "yaxis": "y2", ...}`.
4. `_overlay_annotations` uses `yref=ann["yaxis"]` so the arrow anchors to the
   correct subplot axis.

---

### DASH-04 — `DuplicateCallback` on startup
**Status:** Fixed  
**File:** `dash_app.py` — clientside callback registration

**Symptom:** App crashed at import time with `dash.exceptions.DuplicateCallback`.

**Root cause:** Dash forbids `allow_duplicate=True` together with
`prevent_initial_call=False` on the same output. The combined CSS-injection +
mousedown clientside callback was incorrectly registered.

**Fix:** Added a dedicated `dcc.Store(id="_css-dummy")` as the output for the combined
CSS + mousedown setup callback. This avoids any duplicate output conflict.

---

### DASH-05 — Wrong signal selected on click (z-order / SVG stacking)
**Status:** Fixed by design  
**File:** `renderer_plotly.py` — `_draw_analog()`, `_draw_digital()`

**Symptom** (in reference implementation): The last trace drawn in a subplot always
intercepted clicks because it sits on top in SVG z-order. `clickData.points[0]` always
reflected that last trace's y-value.

**How it is prevented in plotsigs:** When `use_gl=False` (Dash mode), all signal traces
use invisible markers (`marker=dict(size=8, opacity=0.01, maxdisplayed=500)`). This causes
Plotly to populate `bbox.y0`/`bbox.y1` (absolute page-pixel positions) for **every** point
at the clicked x — not just the topmost trace. The clientside callback picks the signal
whose marker center is closest to the real mouse y captured by the `mousedown` listener.
See [Dash Implementation Notes](dash-implementation.md) for the full callback chain.

---

## Open

### DASH-06 — Smoothed signal y-snap ignores smoothed values
**Status:** Open  
**File:** `dash_app.py` → `_add_annotation()`, `_find_nearest_signal()`

**Symptom:** When the "Rolling Average" tool is active and the user places a point note,
the annotation y-value snaps to the original (unsmoothed) signal value, not the smoothed
one displayed in the plot.

**Root cause:** `_find_nearest_signal` calls `sig.evaluate(t)[pos]` which always returns
the raw signal. The smoothed y is only embedded in the trace via `fig.update_traces(y=...)`
inside `_build_main_figure` and is not accessible to the signal-resolver.

**Workaround:** None. The arrow will point slightly off the smoothed line.

---

### DASH-07 — Console warning: `xaxis.matches: "x"` ignored to avoid infinite loop
**Status:** Open / harmless  
**Affects:** Browser DevTools console only

**Symptom:** Every time the main figure is rendered, the browser console shows:
```
WARN: ignored xaxis.matches: "x" to avoid an infinite loop
```

**Root cause:** `make_subplots(shared_xaxes=True)` sets `xaxis.matches = "x"` on the
first x-axis (self-referential). Plotly fires this warning internally.

**Impact:** None — axis synchronisation works correctly. There is no way to suppress
it without disabling the shared-axis behaviour.

---

### DASH-08 — No annotation persistence across browser sessions
**Status:** Open / by design  
**File:** `dash_app.py`

Annotations are stored in `dcc.Store` (browser memory). Refreshing the page or
closing the tab loses all annotations. The "Save as HTML" button bakes them into
the downloaded file, but there is no way to reload a previous session's annotations
into a running Dash app.

**Planned fix:** See [Roadmap — ROAD-03](roadmap.md#road-03--annotation-exportimport-as-json).
