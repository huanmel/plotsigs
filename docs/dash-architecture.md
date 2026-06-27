# plotsigs Dash Architecture

Design reference for the Dash backend. Describes the intended architecture,
the rationale behind key decisions, and what we deliberately exclude.

---

## Scope and constraints

plotsigs is a **single-user, local-server tool**. The Dash app is launched with
`run_dash(diagram)` and serves one browser tab. This changes almost every
architectural decision relative to production web-app guidance.

| Constraint | Implication |
| --- | --- |
| Single user, local server | No Redis, no session isolation, no multi-user state |
| Data loaded once at startup | Diagram object and NumPy arrays live in the Python process for the server's lifetime |
| Typical dataset: 10–100 signals, 10k–200k points each | MB-scale, not GB-scale — zero-copy memory mapping is unnecessary |
| Annotations are the primary interactive output | Click detection accuracy matters more than raw throughput |
| Tool is for engineers inspecting control system logs | Precise y-value snapping and readable phase labels take priority over cosmetic polish |

---

## Architecture layers

### 1. Data layer — NumPy, loaded once

Signal data lives in the `Diagram` object as pre-computed `np.ndarray` values via
`sig.evaluate(t)`. These arrays are computed once when `run_dash(d)` is called and
remain in Python process memory for the lifetime of the server.

**What we use:** NumPy arrays directly. Pandas is acceptable for file loading;
signal data is converted to NumPy before the Dash app starts.

**What we don't use:** Polars, PyArrow lazy frames, memory-mapped files, Redis.
These solve GB-scale problems. At MB scale, a NumPy array accessed directly in
a callback is faster than any lazy-loading indirection.

**Rule:** Signal data never passes through a `dcc.Store`. Stores hold only UI
state — annotation dicts, tool selection, cursor positions, zoom range. Data
stays in the Python object.

---

### 2. Rendering layer — WebGL + customdata

All signal traces use `go.Scattergl` (WebGL/GPU rendering). The SVG `go.Scatter`
fallback (`use_gl=False`) is temporary and will be removed once ROAD-22 is complete.

**Click detection via `customdata` (not `bbox`):**

Each trace carries signal identity in its `customdata` array:

```python
go.Scattergl(
    x=t, y=values,
    customdata=[[sig.name, group_idx]] * len(t),
    ...
)
```

`go.Scattergl` returns `customdata` in `clickData` even without `bbox`. With
`hovermode="closest"`, Plotly's WebGL hit-testing computes geometric distance
across all canvas traces — no DOM z-order bias, no invisible overlay traces needed.

This replaces the current approach (invisible `go.Scatter` markers + `mousedown`
y-capture + `bbox` pixel comparison) and is the target state after ROAD-22.

**hovermode strategy:**

| Mode | hovermode | Reason |
| --- | --- | --- |
| View / zoom | `"x unified"` | Synchronized tooltip across all subplots |
| Annotation / delta cursor | `"closest"` | WebGL selects geometrically nearest trace |

Switch is a `Patch` triggered by tool selection — no figure rebuild needed.

**plotly-resampler (optional, future):**

For datasets beyond ~50k points per signal, wrapping the figure in
`FigureResampler` sends ~2,000 display points per viewport and fetches
high-resolution slices on zoom. This is additive — it does not change the
trace layout or callback structure. Planned as ROAD-20, after ROAD-22
stabilises the trace layout.

---

### 3. Callback architecture — clientside first

A round-trip to the Python server costs ~50–150 ms on localhost. Any interaction
that doesn't require Python data should run entirely in the browser.

**Clientside (JavaScript) — no server round-trip:**

| Callback | Trigger | What it does |
| --- | --- | --- |
| Visibility toggle | Checklist change | Sets `trace.visible` on figure data copy |
| hovermode switch | Tool selection | Patches `layout.hovermode` |
| x-axis sync | `relayoutData` from either graph | Propagates zoom range to analysis pane |
| Cursor-y resolve | `clickData` | Reads `customdata[0]` from nearest point (after ROAD-22) |

**Python callbacks — server required:**

| Callback | Trigger | Why Python is needed |
| --- | --- | --- |
| `_update_main` | Tool change, annotation store update | Full figure rebuild; signal evaluation |
| `_add_annotation` | Click in annotation mode | Reads `sig.evaluate(t)`, writes annotation store |
| `_set_cursor` | Click in delta mode | Reads signal value, writes cursor store |
| `_download_html` | Download button | `fig.write_html()` with injected JS |
| Analysis pane | Tool change + signal selection | FFT, xcorr, rolling average computation |

**Rule:** If the callback only rearranges data already in the browser (visibility,
zoom, hovermode), make it clientside. Python callbacks are for anything that reads
from the `Diagram` object or writes persistent state.

---

### 4. State management — stores for UI only

All `dcc.Store` components hold serialisable UI state only.

| Store | Contents | Max size |
| --- | --- | --- |
| `annotations-store` | List of annotation dicts (type, t, y, label, color) | Small — one dict per annotation |
| `cursor-store` | `{C1: float, C2: float}` | Tiny |
| `tool-store` | `{tool: str, color: str, auto: bool}` | Tiny |
| `legend-store` | `[{idx: int, name: str, group: int}, ...]` | One entry per trace — KB scale |

Signal arrays, time vectors, and evaluated data never enter a store. A callback
needing signal data calls `sig.evaluate(t)` on the server-side `Diagram` object.

---

## Trace layout contract

Consistent trace ordering is required for `curveNumber → signal` mapping.
`_build_main_figure` must produce traces in a documented, stable order.

**Current order (pre-ROAD-22, SVG mode):**

```
[group 0 signals...] [group 0 fills...] [group 1 signals...] [group 1 fills...] ...
```

**Target order (post-ROAD-22, WebGL mode):**

```
[group 0 signals (Scattergl)...] [group 0 fills (Scatter)...] [group 1 ...] ...
```

Fill traces (tolerance bands, shaded areas) remain `go.Scatter` because they
do not need click detection and `go.Scattergl` does not support `fill="tonext"`.

`trace_meta` — a list built alongside the figure — records `{group_idx, sig_idx,
is_signal, is_fill}` for each trace index. `_find_nearest_signal` uses this to
map `curveNumber` to a group, then reads signal identity from `customdata`.

**Stability rule:** Do not add trace types between ROAD-22 and the features that
depend on it (ROAD-13, ROAD-16, ROAD-19). New trace types must be appended at the
end of each group's block, and `trace_meta` must be updated to match.

---

## What we explicitly don't use

| Technology | Why excluded |
| --- | --- |
| Polars / PyArrow | Data is MB-scale NumPy; Polars adds a dependency with no benefit at this scale |
| Redis / external cache | Single-user local server; Python process memory is the cache |
| `dcc.Store` for signal data | Serialising NumPy arrays to JSON defeats the purpose; pass `Diagram` by reference |
| `bbox` click detection | Replaced by `customdata` after ROAD-22; invisible marker trick removed |
| `mousedown` y-capture | Replaced by `hovermode="closest"` + geometric hit-testing after ROAD-22 |
| `go.Scatter` for signal traces | Temporary until ROAD-22; SVG caps at ~15k points per trace |
| dash-extensions EventListener | `customdata` approach removes the need for raw DOM click coordinates |

---

## Migration path

| State | Rendering | Click detection | Blocker |
| --- | --- | --- | --- |
| **Now** | `go.Scatter` SVG | Invisible markers + `bbox` + `mousedown` y | — |
| **After ROAD-21** | `go.Scatter` SVG | Same | Visibility toggle clientside |
| **After ROAD-22** | `go.Scattergl` WebGL | `customdata` + `hovermode="closest"` | Trace layout refactor |
| **After ROAD-20** | `go.Scattergl` WebGL + resampler | Same as ROAD-22 | ROAD-22 first |

---

## Summary

The target architecture is deliberately minimal:

- **Data**: NumPy in Python memory, never serialised to the browser
- **Rendering**: `go.Scattergl` (WebGL), full data on initial load, resampler optional
- **Click detection**: `customdata` identity, `hovermode="closest"` during annotation tools
- **Callbacks**: clientside JS for all interaction that doesn't touch signal data; Python only for annotation state and signal evaluation
- **State**: `dcc.Store` for UI metadata only — annotations, cursor, tool selection
