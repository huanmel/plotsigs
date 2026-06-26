# Roadmap

Feature wishlist and planned improvements for plotsigs.
Items are roughly ordered by priority / effort.

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

Relates to [DASH-08](issues.md#dash-08--no-annotation-persistence-across-browser-sessions).

---

### ROAD-03 — Per-annotation color editing in manager
The annotation color is set globally via the sidebar dropdown before clicking.
Once placed, annotations cannot have their color changed from the manager list.
Add a small color swatch/picker to each annotation manager row.

---

## Medium-term

### ROAD-04 — FFT analysis tool
Add a "Spectrum" tool to the sidebar that shows the DFT magnitude of a selected
signal in the analysis pane. Useful for diagnosing oscillations and noise in
control loops.

**Implementation sketch:**
- New tool value `"fft"` in the tool dropdown
- `np.fft.rfft` + `np.fft.rfftfreq` on the selected signal
- Plot `|X(f)|` in dB (or linear) in `analysis-graph`
- Frequency axis in Hz; optional windowing (Hann)

---

### ROAD-05 — Cross-correlation between two signals
Show the cross-correlation `xcorr(A, B)` as a function of lag τ in the analysis
pane. Useful for identifying transport delays and phase offsets between control
signals.

---

### ROAD-06 — Time-shift overlay (two-signal comparison)
Overlay the same signal from two different time windows (or two separate DataFrames)
on a single subplot, aligned by a user-specified reference time. Useful for
run-to-run comparison without side-by-side layout.

---

### ROAD-07 — Zoom-linked annotation display
When the user zooms in, hide phase labels that are outside the current x-axis
range. Phase labels near the edge of the visible window currently overlap with
the modebar and adjacent labels.

**Approach:** Clientside callback on `relayoutData` → filter visible annotations
using a Patch to set `fig.layout.annotations[i].visible`.

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
