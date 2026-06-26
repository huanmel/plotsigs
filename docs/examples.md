# Examples

All examples are runnable scripts in [`examples/`](../examples/).
Run any of them from the repo root:

```bash
python examples/<script_name>.py
```

Output images are saved to `output/`.

---

## Matplotlib backend (static)

| Script | Demonstrates |
|---|---|
| [ex_quickplot.py](../examples/ex_quickplot.py) | `plot_signals()` one-liner — auto-detect, shorthand, dict spec |
| [ex_quickplot_from_yaml.py](../examples/ex_quickplot_from_yaml.py) | `plot_signals_from_yaml()` from a YAML config |
| [ex_plot_from_script.py](../examples/ex_plot_from_script.py) | Pure Python API — stepped / lagged / digital / annotations |
| [ex_plot_from_csv.py](../examples/ex_plot_from_csv.py) | `add_measured()` / `add_measured_digital()` from DataFrame |
| [ex_plot_control_transient.py](../examples/ex_plot_control_transient.py) | `add_transient_analysis()` — single step and multi-step |
| [ex_plot_csv_analysis_sim.py](../examples/ex_plot_csv_analysis_sim.py) | Phase-first workflow + `add_event_duration()` on sim data |
| [ex_plot_from_yaml.py](../examples/ex_plot_from_yaml.py) | YAML loader — synthetic + real CSV data |
| [ex_real_log_analysis.py](../examples/ex_real_log_analysis.py) | Real compressor log — phase-first + transient analysis |
| [ex_multi_log_analysis.py](../examples/ex_multi_log_analysis.py) | Batch template — two logs, one YAML, overrides per run |
| [ex_template_function.py](../examples/ex_template_function.py) | Reusable diagram template + `plotsigs.sim` + `to_digital_bps()` |
| [ex_compare_naive_correct.py](../examples/ex_compare_naive_correct.py) | Dual-panel naive vs. correct — hysteresis fix, phase pass/fail |
| [ex_enum_phases.py](../examples/ex_enum_phases.py) | `add_enum()` zoom-reactive labels + phase `status="pass"/"fail"` |
| [ex_batch.py](../examples/ex_batch.py) | Subprocess batch runner — regenerate all outputs, collect pass/fail |
| [ex_export.py](../examples/ex_export.py) | Export to PNG / SVG / PDF |
| [ex_render_spec.py](../examples/ex_render_spec.py) | `render_spec()` dict API — matplotlib backend |

---

## Plotly / Dash backend (interactive)

| Script | Demonstrates |
|---|---|
| [ex_render_spec_plotly.py](../examples/ex_render_spec_plotly.py) | `render_spec(..., backend="plotly")` → standalone HTML; `backend="dash"` → full Dash app |

### Running the Dash app

```python
# In ex_render_spec_plotly.py, set:
fig = plotsigs.render_spec(spec, backend="dash")
```

Then open <http://localhost:8050> in your browser.

### Dash sidebar tools

| Tool | What it does |
|---|---|
| Raw Signals | Default view — no analysis overlay |
| Diff A − B | Embeds per-sample difference in hover; analysis pane shows Δ trace |
| Rate of Change dY/dt | Embeds windowed derivative in hover; analysis pane shows dy/dt |
| Rolling Average | Smooths the selected signal in-place on the main graph |
| Δ Measurement | Two-click delta cursor — shows Δt, Δy, dY/dt readout |
| Annotate | Click to place phase lines (vertical) or point notes (arrow to signal) |

### Debug logging

When the Dash app starts, debug output appears in:
- **Terminal** — live `[psig ...]` lines
- **`plotsigs/dash_debug.log`** — timestamped, overwritten each run
- **Browser DevTools console** — `[psig cursor-y]` lines on every click

See [Dash Implementation Notes](dash-implementation.md) for the click-detection
algorithm and known quirks.

---

## Data files

| File | Used by |
|---|---|
| [compressor_sim_data.csv](../examples/compressor_sim_data.csv) | Most examples — synthetic compressor simulation |
| [compressor_real_data_log_1.csv](../examples/compressor_real_data_log_1.csv) | `ex_multi_log_analysis.py`, `ex_real_log_analysis.py` |
| [compressor_real_data_log_2.csv](../examples/compressor_real_data_log_2.csv) | `ex_multi_log_analysis.py` |
| [compressor_plot_data.yaml](../examples/compressor_plot_data.yaml) | `ex_plot_from_yaml.py` |
| [compressor_analysis_template.yaml](../examples/compressor_analysis_template.yaml) | `ex_multi_log_analysis.py` |
| [ex_real_log_analysis.yaml](../examples/ex_real_log_analysis.yaml) | `ex_plot_from_yaml.py` (real log section) |
| [quickplot_config.yaml](../examples/quickplot_config.yaml) | `ex_quickplot_from_yaml.py` |
