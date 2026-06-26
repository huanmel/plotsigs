# Dash Implementation Notes

Technical findings from building the Dash backend, ported from the equivalent
implementation in `can_log_utils/work/plotting/plot_analysis.py`.
Each section notes whether plotsigs already applies the correct solution or whether
a latent issue was found and fixed.

See also: [Known Issues](issues.md) for the bug log.

---

## 1. Root cause: Plotly SVG z-order → wrong signal always selected

**Problem**  
When multiple signals share a subplot, the last trace drawn in the SVG sits on top
and always intercepts mouse clicks. `clickData.points[0]` therefore always reflects
that last trace's y-value, regardless of where the user actually clicked.

In `can_log_utils` the last trace in each subplot group (e.g. `HMIDrvr_TempEvap`) was
always selected even when the user clicked visually on a completely different signal
(e.g. `Clim_T_Cabin_SP` at y=20). The `y_click` value in `clickData.points[0]` was
always TempEvap's value, so comparing it against other signals was circular — TempEvap
always won.

**What `plotsigs` does correctly**  
The renderer adds invisible markers (`marker=dict(size=8, opacity=0.01, maxdisplayed=500)`)
when `use_gl=False` (Dash mode). This makes Plotly populate `bbox.y0`/`bbox.y1`
(absolute page-pixel positions) for **every** point in every trace at the clicked x.
`clickData.points` therefore contains ALL signals at that x, each with its own bbox.

The clientside callback then picks the signal whose marker center `(bbox.y0+bbox.y1)/2`
is closest to the real cursor y:

```javascript
var absY = clientY + scrollY;
var pts = clickData.points;
var bestPt = pts[0];
var bestDist = Infinity;
for (var i = 0; i < pts.length; i++) {
    var pt = pts[i];
    if (!pt.bbox) continue;
    var markerY = (pt.bbox.y0 + pt.bbox.y1) / 2;
    var dist = Math.abs(markerY - absY);
    if (dist < bestDist) { bestDist = dist; bestPt = pt; }
}
return {y: bestPt.y, curveNumber: bestPt.curveNumber};
```

This returns the correct `curveNumber` and `y` for the signal actually nearest the
cursor — not just the last one drawn.

---

## 2. Capturing cursor Y: `mousedown` vs `plotly_click`

**Attempted approach (can_log_utils first iteration)**  
Register `gd.on('plotly_click', fn)` inside the CSS injection clientside callback to
capture `eventData.event.clientY`. This immediately hits a timing problem:

```
TypeError: gd.on is not a function
```

The CSS callback fires as soon as the page renders. At that point the Plotly graph div
element exists in the DOM, but Plotly hasn't yet initialised its event system — `gd.on`
is not yet defined. Without a guard the handler never attaches, so
`window._can_click_result` is never set, and `cursor-y-store` always receives `null`.

Fix (if using `plotly_click`) — poll until `gd.on` exists:

```javascript
(function setupClickCapture() {
    var gd = document.getElementById('main-graph');
    if (!gd || !gd.on) { setTimeout(setupClickCapture, 300); return; }  // ← key
    gd.on('plotly_click', function(eventData) { ... });
})();
```

**Better approach — `mousedown` (what plotsigs already does correctly)**  
Listen to the plain DOM `mousedown` event on `document`. This fires before Plotly
processes the click, at the same cursor position. No dependency on `gd.on`:

```javascript
document.addEventListener('mousedown', function(e) {
    window._psig_mousedown_y = e.clientY;
}, {passive: true});
```

The clientside `cursor-y-store` callback then reads `window._psig_mousedown_y` when
`clickData` changes. This is simpler, more reliable, and eliminates the entire
`gd.on` timing race.

**Also correct: fallback when `mousedown_y` is unavailable**  
The `plotsigs` clientside callback already has a sensible fallback:

```javascript
if (clientY === undefined || clientY === null) {
    // can't do bbox comparison; fall back to whatever Plotly hit-tested
    return {y: clickData.points[0].y, curveNumber: clickData.points[0].curveNumber};
}
```

Without this, `cursor-y-store` would remain `null` and Python callbacks would fire
with `cursor_y_data=None`, causing a silent failure with no signal selected.

---

## 3. `add_hline` / `add_hrect` / `add_vline` are shapes, not traces

**Problem in can_log_utils**  
Threshold reference lines were added with `fig.add_hline(...)` and incorrectly counted
as traces when computing `curveNumber → group_idx` offsets. This shifted all group
assignments by the number of hlines, causing the wrong group to be selected.

**Why this doesn't bite plotsigs**  
All threshold lines, phase lines, and grid lines in `renderer_plotly.py` use
`fig.add_hline()`, `fig.add_vline()`, `fig.add_hrect()` — these all go to
`fig.layout.shapes` or `fig.layout.annotations`, **not** to `fig.data`.
They are invisible to `curveNumber`.

The only things that go to `fig.data` and count toward `curveNumber` are actual
`fig.add_trace()` calls: signals and fill bands (tolerance, comparison bands via
`_add_fill_band` with `fill='toself'`).

The `_classify_traces()` function handles fills correctly by checking
`hoverinfo='skip'` and `fill in ('toself', 'tonexty')`.

---

## 4. Fills at group boundaries — edge case in `_classify_traces`

`_find_nearest_signal` walks trace_meta up to `curve_number` and takes the last
non-`None` `group_idx`:

```python
group_idx = 0
for i in range(min(curve_number + 1, len(trace_meta))):
    if trace_meta[i]["group_idx"] is not None:
        group_idx = trace_meta[i]["group_idx"]
```

Because fills are drawn **before** signals within each group in `_draw_analog`, a fill
trace that opens a new group appears after the last signal of the previous group.
If `curve_number` happens to land on such a fill, the walk-back returns the previous
group's index instead of the current one.

**In practice this is harmless** — fills have `hoverinfo='skip'` so Plotly never
generates a click event for them, meaning `curve_number` will never point to a fill
trace in real usage.

---

## 5. Bug: double annotations in the HTML download

**Location**: `_download_html` callback (Callback 14)

**What happens**  
`_build_main_figure` already calls `_overlay_annotations(fig, ...)` which writes vlines
and annotation objects into `fig.layout.shapes` / `fig.layout.annotations`.
Dash serialises this full layout into `main-graph.figure` (the stored figure state).

`_download_html` then does:
```python
fig = go.Figure(
    data=fig_dict.get("data", []),
    layout=fig_dict.get("layout", {}),   # ← already contains the annotations
)
_overlay_annotations(fig, stored_annotations, n_rows)  # ← adds them again
```

Every annotation is duplicated in the downloaded HTML.

**Fix options**

Option A — don't re-apply in download (cleanest):
```python
def _download_html(_, fig_dict, _stored_annotations):
    fig = go.Figure(data=fig_dict["data"], layout=fig_dict["layout"])
    # layout already has annotations from the last _update_main render
    html_str = fig.to_html(include_plotlyjs="cdn", full_html=True,
                           post_script=_PLOTLY_EXTRAS_JS)
    ...
```

Option B — rebuild cleanly from scratch in download:
```python
def _download_html(_, _fig_dict, stored_annotations):
    fig = _build_main_figure(d, stored_annotations=stored_annotations)
    html_str = fig.to_html(...)
```
This guarantees the downloaded HTML is consistent with the current Dash state.

---

## 6. `xaxis.matches: "x"` console warnings

Both plotsigs and can_log_utils produce this warning repeatedly in the browser console:

```
WARN: ignored xaxis.matches: "x" to avoid an infinite loop
```

This is a Plotly internal warning that fires when `shared_xaxes=True` sets
`xaxis.matches="x"` on the first x-axis (self-referential). It is **harmless** — all
axis synchronisation works correctly despite the warning. There is no straightforward
way to suppress it without breaking the shared-axis behaviour.

---

## 7. Callback chain for click detection (documentation)

The full chain when a user clicks the graph:

```
User click
  → DOM mousedown fires → window._psig_mousedown_y = e.clientY
  → Plotly processes click → Dash updates main-graph.clickData
  → clientside callback fires (Input: clickData)
      reads window._psig_mousedown_y + scrollY = absY
      iterates clickData.points[] → picks pt with min |bbox_center - absY|
      returns {y: bestPt.y, curveNumber: bestPt.curveNumber}
      → cursor-y-store.data updated
  → Python _set_cursor fires (Input: cursor-y-store)
      cursor_y_data = {y: <data y of nearest signal>, curveNumber: <cn>}
      _find_nearest_signal(x_click, y_cursor, curve_num, ...) → signal resolved
  → Python _add_annotation fires (Input: cursor-y-store)
      same resolution path if tool == 'annotate'
```

Key invariant: `cursor-y-store` is only written by the clientside callback
(Input: `clickData`), and both Python callbacks (`_set_cursor`, `_add_annotation`)
are only triggered by `cursor-y-store`. This means when a Python callback fires,
the JS has already resolved the correct signal.

---

## 8. `argmin()` + `iat[]` for non-integer DataFrame indices

Applies when the time axis is a float-indexed pandas Series (common in CAN logs).

```python
# WRONG — fails with float index when pos is not an integer label
pos = int(np.argmin(np.abs(df['time'] - x_click)))
y = df[sig_name][pos]

# CORRECT
pos = int(np.argmin(np.abs(df['time'] - x_click)))
y = df[sig_name].iat[pos]   # positional, not label-based
```

In plotsigs this is not an issue because `t` is a plain `np.ndarray` and signal values
are also NumPy arrays accessed with direct indexing:
```python
pos = int(np.argmin(np.abs(t - x_click)))
y = float(sig.evaluate(t)[pos])   # numpy array, integer indexing is fine
```
