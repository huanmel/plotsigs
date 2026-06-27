# plotsigs — documentation

Control system signal & timing diagram library.
Fluent Python API, matplotlib + interactive Plotly/Dash backends.

---

## Contents

| Document | Description |
| --- | --- |
| [Examples gallery](examples-gallery.md) | Numbered examples with rendered output images |
| [Examples reference](examples.md) | Script + data file catalog, Plotly/Dash tool guide |
| [Roadmap](roadmap.md) | Planned features and known gaps |
| [Known Issues](issues.md) | Bug log — fixed and open |
| [Dash Architecture](dash-architecture.md) | Target architecture, design decisions, migration path |
| [Dash Implementation Notes](dash-implementation.md) | Click detection, annotation architecture, Plotly quirks |

---

## Quick links

- [README](../README.md) — install, API reference, concepts
- [examples/](../examples/) — runnable Python scripts
- [plotsigs/dash_app.py](../plotsigs/dash_app.py) — Dash application
- [plotsigs/renderer_plotly.py](../plotsigs/renderer_plotly.py) — Plotly figure builder

---

## Backends

| Backend | Entry point | Output |
| --- | --- | --- |
| `matplotlib` | `d.render()` / `render_spec(..., backend="matplotlib")` | PNG / SVG / PDF |
| `plotly` | `d.render_plotly()` / `render_spec(..., backend="plotly")` | Standalone HTML |
| `dash` | `d.run_dash()` / `render_spec(..., backend="dash")` | Interactive browser app |

## Debug logging (Dash)

When the Dash app is running, all click-detection events are logged to:

- **Terminal** — live `[psig ...]` lines while the app runs
- **`plotsigs/dash_debug.log`** — timestamped file, overwritten each session
- **Browser DevTools console** — `[psig cursor-y]` lines on every click
