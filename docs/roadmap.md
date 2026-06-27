# Roadmap

Feature wishlist and planned improvements for plotsigs.

> **Priority note:** The Architecture / Performance section below must be completed
> before adding significant new features. ROAD-22 in particular changes the trace
> index layout that all click detection and annotation placement depends on — any
> feature built on top of the current layout will require rework if done after ROAD-22.

---

## Architecture / Performance

These items modify foundational internals (trace layout, callback architecture, rendering
pipeline). They are listed here — not in the feature sections — because they are
prerequisites for everything else scaling correctly. Do not build ROAD-13, ROAD-14,
ROAD-16, or ROAD-19 on top of the current rendering layer until ROAD-21 and ROAD-22
are resolved.

### ROAD-21 — Clientside signal visibility toggle

`_toggle_visibility` currently uses a Python `Patch()` callback — every checkbox click
causes a browser→server round-trip before the trace appears/disappears. This should be
instant since no data processing is needed.

**Approach:** Convert to a clientside callback:

```javascript
function(visible_vals, figure) {
    var p = JSON.parse(JSON.stringify(figure));
    legend_entries.forEach(function(e) {
        p.data[e.idx].visible = visible_vals.includes(String(e.idx));
    });
    return p;
}
```

`legend_entries` can be injected as a `dcc.Store` so the clientside function can read it.

**Risk:** Low — visibility state is independent of annotation and click-detection logic.
Safe to implement now as a quick win before the larger ROAD-22 refactor.

---

### ROAD-22 — Re-enable WebGL in Dash mode

Currently Dash forces `use_gl=False` (all `go.Scatter`, CPU/SVG) because `go.Scattergl`
does not populate `bbox` in `clickData`, which is required for the current two-step
signal click detection approach.

**Preferred approach: `customdata` identity embedding**

`go.Scattergl` still returns `curveNumber`, `x`, `y`, and `customdata` in `clickData`
even without `bbox`. Embed signal identity directly into each trace:

```python
go.Scattergl(
    x=t, y=values,
    customdata=[[sig.name, group_idx]] * len(t),
    ...
)
```

In `_find_nearest_signal`, read identity from `clickData["points"][0]["customdata"]`
instead of comparing pixel positions. No overlay traces, no `bbox`, no `mousedown`
y-capture needed.

With `hovermode="closest"`, Plotly computes geometric distance across all WebGL canvas
traces without DOM z-order bias — this also naturally fixes the digital signal lane
disambiguation (DASH-01 root cause in WebGL mode).

**hovermode conflict:** Current code uses `hovermode="x unified"` for synchronized
hover tooltips. Switch hovermode dynamically: `"x unified"` in view/zoom mode,
`"closest"` when annotation or delta-cursor tool is active (a `Patch` on tool selection).

**What gets removed:** invisible marker trick, `mousedown` y-capture listener,
clientside cursor-y callback, `bbox` comparison logic. The `_classify_traces` /
`trace_meta` structure stays but is simplified.

**Risk: MEDIUM** (lower than the overlay approach — no trace index changes).
`_find_nearest_signal`, `_add_annotation`, and the clientside callback all change, but
the `curveNumber → group_idx` mapping via `trace_meta` stays the same.

**Alternative (if customdata proves insufficient):** Invisible `go.Scatter` overlay
per subplot carrying only markers — provides `bbox` without changing curveNumber mapping
for the `go.Scattergl` signal traces. Higher complexity, deferred unless customdata
approach fails in practice.

Implements the planned fix for [DASH-09](issues.md#dash-09--webgl-disabled-in-dash-mode-svg-rendering-15k-point-limit).

---

### ROAD-20 — plotly-resampler: dynamic downsampling on zoom

Large datasets (>15k points per signal) cause slow SVG rendering in the browser.
[plotly-resampler](https://github.com/predict-idlab/plotly-resampler) solves this by
sending only ~2,000 display-resolution points initially, then fetching full-resolution
data for the current viewport when the user zooms in.

**Approach:**

- Wrap `_build_main_figure` return value with `FigureResampler(fig)`
- Register the resampler's Dash callbacks alongside the existing app callbacks
- On `relayoutData` zoom: resampler callback fetches high-res slice for the visible x-range
- Compatible with existing annotation, visibility, and tool callbacks via `allow_duplicate`

**Risk: MEDIUM.**
Introduces a new callback competing on `relayoutData`. Verify annotation zoom-link
(ROAD-07) and x-axis sync callbacks are not broken. Implement after ROAD-22 so the
resampler wraps the final `go.Scattergl`-based figure, not the transitional SVG one.

Relates to [DASH-09](issues.md#dash-09--webgl-disabled-in-dash-mode-svg-rendering-15k-point-limit).

---

## In Progress / Near-term

### ROAD-01 — Delta cursor snap lines on main figure

Add visible vertical dashed lines at C1 and C2 cursor positions on the main
graph (not just the readout in the sidebar). Currently only the text readout
shows the cursor positions; drawing `add_vline` Patches would make it obvious
which x positions are being measured.

**Approach:** In `_update_main`, when `tool == "delta"` and `cursor_store` has
C1/C2 values, add `fig.add_vline(...)` calls with distinct colors (C1=blue, C2=orange).
Requires passing `cursor_store` as an Input to `_update_main`.

---

### ROAD-02 — Annotation JSON export / import

Allow saving annotations to a `.json` file and loading them back into a Dash
session. Currently annotations survive only for the life of the browser tab.

**Approach:**

- Add "Export annotations" button → `dcc.Download` → JSON of `annotations-store`
- Add `dcc.Upload` component → parse JSON → merge into `annotations-store`
- Because bookmarks share `annotations-store` (see ROAD-16), this export covers phase lines,
  point notes, and bookmarks in one file with no extra work

Relates to [DASH-08](issues.md#dash-08--no-annotation-persistence-across-browser-sessions).

---

### ROAD-03 — Per-annotation color editing in manager

The annotation color is set globally via the sidebar dropdown before clicking.
Once placed, annotations cannot have their color changed from the manager list.
Add a small color swatch/picker to each annotation manager row.

---

## Medium-term

### ROAD-04 — FFT analysis tool (core plugin)

Show the DFT magnitude of a selected signal in the analysis pane.
Useful for diagnosing oscillations and noise in control loops.

Planned as the first core `Analyzer` plugin (see [ROAD-19](#road-19--plugin-system--importers-transformers-and-analyzers)).
The plugin interface is the prerequisite; this becomes one `plotsigs.plugins.fft` entry-point.

**Sketch of the plugin implementation:**

```python
class FftAnalyzer:
    name = "Spectrum (FFT)"
    params = {"window": ["hann", "rect"], "scale": ["dB", "linear"]}

    def run(self, t, values, *, window="hann", scale="dB"):
        # np.fft.rfft + rfftfreq → go.Figure with frequency on x-axis
        ...
```

---

### ROAD-05 — Cross-correlation between two signals (core plugin)

Show `xcorr(A, B)` as a function of lag τ in the analysis pane.
Useful for identifying transport delays and phase offsets between control signals.

Planned as a core `Analyzer` plugin under ROAD-19; requires two signal selectors in
the sidebar (plugin declares `n_inputs = 2`).

---

### ROAD-06 — Time-shift overlay / run-to-run comparison (core plugin)

Overlay the same signal from two different time windows (or two DataFrames) on a
single subplot aligned to a user-specified reference time.
Useful for run-to-run comparison without side-by-side layout.

Planned as a core `Analyzer` plugin under ROAD-19.

---

### ROAD-07 — Zoom-linked annotation display

When the user zooms in, hide phase labels that are outside the current x-axis
range. Phase labels near the edge of the visible window currently overlap with
the modebar and adjacent labels.

**Approach:** Clientside callback on `relayoutData` → filter visible annotations
using a Patch to set `fig.layout.annotations[i].visible`.

---

### ROAD-15 — Synchronized time cursor (PlotJuggler-inspired)

A persistent vertical cursor line that spans all subplots simultaneously and shows
signal values at the current time position in a sidebar readout. Distinct from the
delta cursor (ROAD-01) which is a two-click measurement tool — this is a scrubable
"playhead" you drag left/right to inspect all signals at a single moment.

Note: Plotly's `hovermode="x unified"` + `showspikes=True` already gives a
hover-synced spike line, but it disappears when the mouse leaves the graph.
This feature adds a persistent click-to-place cursor.

**Approach:**

- `dcc.Store(id="timecursor-store")` holds `{t: float | null}`
- Clientside callback on `clickData` (when tool == "timecursor") → write `t` to store
- Python callback: apply `fig.add_vline(x=t)` as a Patch across all subplots
- Sidebar readout lists every signal's value at `t` (sampled via `sig.evaluate`)

---

### ROAD-16 — Bookmarks — named time markers with jump-to navigation

User places a named bookmark at any time position; a small flag appears at the top of
the figure at that x. A bookmark list in the sidebar allows jumping to (zooming to) any
bookmark. Different from phase annotations — bookmarks are time-only navigation aids with
no arrow, no span, and no signal association, intended for "mark this moment, come back later."

**Design: bookmarks share `annotations-store`**

Rather than a separate `bookmarks-store`, bookmarks are stored in the existing `annotations-store`
as `{type: "bookmark", t: float, label: str, color: str}` — a time-only subset of point notes
(`type: "point"` adds `y`, `yaxis`, `sig`). Benefits of sharing one store:

- ROAD-02 (annotation JSON export) and ROAD-18 (save/load layouts) cover bookmarks for free
- The existing annotation manager list renders them with a flag icon — no new UI component
- `_overlay_annotations` adds one branch: `fig.add_annotation(x=t, yref="paper", y=1, showarrow=True, arrowhead=6, ...)`

**Approach:**

- "Bookmark" tool mode in sidebar: click anywhere on the figure places `type="bookmark"` at x
- `_overlay_annotations` renders bookmarks as flag markers pinned to the top x-axis edge
- Bookmark entries in the annotation manager have a "→ Jump" button
- Jump callback: read `t` from the clicked bookmark → write `relayoutData = {"xaxis.range[0]": t - w, "xaxis.range[1]": t + w}`

---

### ROAD-17 — XY scatter mode (PlotJuggler-inspired)

Plot signal A on the X-axis versus signal B on the Y-axis — not versus time.
Useful for phase portraits (position vs. velocity), actuator characterization
(command vs. feedback), and correlation analysis.

**Approach:**

- New tool value `"scatter"` in the tool dropdown
- Two signal dropdowns: "X signal" and "Y signal"
- Analysis pane shows `go.Scatter(x=sig_a.evaluate(t), y=sig_b.evaluate(t), mode="lines+markers")`
- Color-code points by time (colorscale mapped to `t`) to show trajectory direction
- Optionally overlay the current time cursor position as a highlighted point

---

## Long-term / Nice to Have

### ROAD-08 — Dark mode

Add a dark-mode stylesheet toggle. Requires setting `paper_bgcolor`, `plot_bgcolor`,
font colors, and sidebar CSS to dark equivalents, stored in a `dcc.Store`.

---

### ROAD-09 — Persistent layout (local storage)

Save sidebar tool selection, signal visibility, and zoom range to `localStorage`
so the app opens to the same state after a page refresh. Implemented via a
clientside callback reading/writing `window.localStorage`.

---

### ROAD-10 — Multi-file comparison mode

Load two CSV/log files side-by-side in the same Dash session and compare
corresponding signals. Expose a file picker in the sidebar that loads a second
dataset, then render each pair of signals in a split or overlaid view.

---

### ROAD-11 — Matplotlib backend: interactive callout editor

For the matplotlib backend, add a click-to-annotate mode (similar to the Dash
app) using `mpl_interactions` or raw `mpl_connect('button_press_event')`. Write
annotated figures back to a YAML spec so they can be version-controlled.

---

### ROAD-12 — Responsive / tablet layout

The current three-pane layout assumes a wide desktop viewport. On narrower
screens the sidebar and analysis pane push the main graph too narrow.
Add a CSS media query breakpoint that collapses the sidebar to an overlay
drawer and stacks the analysis pane below the main graph.

---

### ROAD-13 — Drag-and-drop signal placement (PlotJuggler-inspired)

Drag a signal name from the sidebar onto any subplot to add it there; drag between
subplots to move it; drag back to the sidebar to remove it from a panel.

This mirrors the core UX of [PlotJuggler](https://github.com/facontidavide/PlotJuggler) —
a signal list on the left, panels on the right, composition by drag-and-drop rather than
by editing a spec file.

**Approach:**

- Add `dcc.Store(id="layout-store")` tracking per-subplot signal assignments: `[{signals, ylabel, mode}, ...]`
- Render sidebar signal list as HTML elements with `draggable=true` and `data-sig` attributes
- Subplot overlay divs get `ondragover` / `ondrop` handlers via a clientside callback
- On drop: update `layout-store` → triggers `_update_main` which rebuilds from the new assignment
- `_build_main_figure` reads `layout-store` when present, falling back to `d._groups` from the spec

Note: closely coupled with ROAD-14 — implement together.

---

### ROAD-14 — Configurable panel layout (PlotJuggler-inspired)

Allow users to add new empty subplots, remove existing ones, and reorder panels at runtime —
without restarting the app or changing the spec.

**Approach:**

- `dcc.Store(id="panels-store")` holds the ordered panel list; initialised from `d._groups` on startup
- "＋ Add panel" button in sidebar → appends an empty entry → figure rebuild
- "×" button injected into each subplot header area → removes that panel entry → figure rebuild
- Panel reorder: clientside JS on panel header `mousedown` → drag-and-drop reordering → update store

Note: closely coupled with ROAD-13 — implement together.

---

### ROAD-18 — Save/load layouts (PlotJuggler-inspired)

Export the complete session state to a single JSON file and restore it in a later
session: panel configuration, signal assignments, signal visibility, tool selection,
zoom range, and annotations — everything needed to reproduce the exact view.

**Approach:**

- "💾 Save layout" button → `dcc.Download` → JSON of all `dcc.Store` contents
  (`panels-store`, `layout-store`, `annotations-store`, `bookmarks-store`, visibility checklist, tool, zoom)
- "📂 Load layout" → `dcc.Upload` → parse JSON → restore all stores in a single callback
- Requires ROAD-13 and ROAD-14 (`layout-store`, `panels-store`) to be in place first
- Supersedes / extends ROAD-02 (annotation-only export) once implemented

---

### ROAD-19 — Plugin system — importers, transformers, and analyzers

Allow third-party code to extend plotsigs without modifying the core package.
Three plugin interfaces cover the full pipeline: getting data in, reshaping signals,
and producing analysis views.

**Interfaces:**

- `Importer`: `name`, `extensions: list[str]`, `load(path) → (t: np.ndarray, df: pd.DataFrame)`
- `Transformer`: `name`, `params: dict`, `apply(t, values, **params) → np.ndarray`
- `Analyzer`: `name`, `n_inputs: int` (1 or 2 signals), `params: dict`,
  `run(t, *values, **params) → go.Figure` — produces the analysis pane figure

The `Analyzer` interface is the foundation for the core analysis tools:
FFT (ROAD-04), cross-correlation (ROAD-05), and time-shift overlay (ROAD-06)
ship as built-in plugins under `plotsigs.plugins.*` and are the first consumers
of the interface. The Dash sidebar tool dropdown becomes a dynamic list of
registered `Analyzer` plugins rather than a hardcoded enum — custom analyzers
appear automatically once installed.

**Discovery:**

- Python entry-points (`plotsigs.importers` / `plotsigs.transformers` / `plotsigs.analyzers`)
- Fallback: `~/.plotsigs/plugins/` directory scan for lower-friction local plugins

**Dash integration:**

- "Load file" button uses registered importers filtered by file extension
- Transformer list populates a "Custom transform" sidebar tool
- Analyzer list populates the analysis tool dropdown; selecting one shows its `params` as sidebar controls
