# plotsigs

**Control system signal & timing diagram library.**

Fluent Python API for creating annotated analog + digital timing diagrams for
control system documentation, test case specs, and fault analysis reports.
Works with synthetic signals, real CSV/DataFrame data, or simulation outputs.

---

## Motivation

Simulink/MATLAB plots are great during development but hard to annotate
reproducibly for specs and reports. draw.io / Excalidraw are flexible but
manual and tedious. PlantUML timing diagrams only support stepped discrete
levels, not smooth analog curves.

`plotsigs` fills the gap: text-defined, version-controllable, publication-quality
diagrams with smooth analog curves, digital signal lanes, transient analysis
overlays, phase labels, and cross-panel event-duration markers.

---

## Install

```bash
pip install -e .           # from repo root (editable install)
```

Dependencies: `matplotlib`, `numpy`, `pandas`, `PyYAML` — nothing else.

---

## Three entry points

### 1. One-liner from a DataFrame

```python
from plotsigs import plot_signals
import pandas as pd

df = pd.read_csv("my_log.csv")

plot_signals(df, groups=[
    ["AC_Set_Speed", "Compressor_Running_Speed"],   # analog — auto-detected
    ["AC_Enable", "DrvrOut_IsRunOk"],               # digital — auto-detected (0/1 values)
    ["Board_Temp"],
], title="Compressor log", output="output/quick.png")
```

### 2. Python API (full control)

```python
from plotsigs import Diagram
import pandas as pd

df = pd.read_csv("my_log.csv")

d = Diagram("Compressor Speed Control", t_end=df["time"].max(), figsize=(14, 10))

# Define phases first — returned objects used by analysis
ph_idle    = d.add_phase(0,  10, "IDLE")
ph_startup = d.add_phase(10, 18, "STARTUP")
ph_steady  = d.add_phase(18, 60, "STEADY")

# Analog group: measured signals + transient analysis
g = d.add_group("Speed [RPM]")
g.add_measured("AC_Set_Speed",             df, color="#2ecc71")
g.add_measured("Compressor_Running_Speed", df, color="#e74c3c")
g.add_threshold(8500, label="MAX 8500",    color="#c0392b")
g.add_transient_analysis(
    "AC_Set_Speed", "Compressor_Running_Speed",
    tolerance_pct=5.0,
    phase=ph_startup,         # window taken from phase object
    show_crosshairs=True,
)

# Error subplot
g_err = d.add_group("Tracking error [RPM]")
g_err.add_derived("Error", "AC_Set_Speed", "Compressor_Running_Speed", color="#8e44ad")
g_err.add_threshold(0, label="zero", ls="-", lw=0.6, color="#aaaaaa")

# Digital group + event-duration annotation
g_flags = d.add_digital_group()
g_flags.add_measured_digital("AC_Enable",       df, color="#2980b9")
g_flags.add_measured_digital("DrvrOut_IsRunOk", df, color="#27ae60")
g_flags.add_event_duration(
    "Error",  100,              # event A: error drops below 100 RPM
    "DrvrOut_IsRunOk",          # event B: run-OK flag goes HIGH
    phase=ph_startup,
    color="#e74c3c",
)

d.render(output="output/analysis.png", show=True)
```

### 3. YAML config

```yaml
# analysis.yaml
title: "Compressor log — transient analysis"
figsize: [14, 10]
xlabel: "Time [s]"

csv:
  file: my_log.csv
  time_col: timestamps

groups:
  - ylabel: "Speed [RPM]"
    signals:
      - name: AC_Set_Speed
        type: measured
        color: "#2ecc71"
      - name: EC1_Compressor_Running_Speed
        type: measured
        color: "#e74c3c"
    annotations:
      - type: transient_analysis
        reference: AC_Set_Speed
        feedback:  EC1_Compressor_Running_Speed
        tolerance_pct: 5.0
        phase: STARTUP          # resolved against annotations list
        show_crosshairs: true

  - ylabel: "Tracking error [RPM]"
    signals:
      - name: Error
        type: derived
        a: AC_Set_Speed
        b: EC1_Compressor_Running_Speed
        color: "#8e44ad"

  - ylabel: "Digital flags"
    mode: digital
    signals:
      - name: AC_Enable_Disable_Compressor
        type: measured_digital
        color: "#2980b9"

annotations:
  - { type: phase, t0: 0,  t1: 14, label: IDLE }
  - { type: phase, t0: 14, t1: 19, label: STARTUP }
  - { type: phase, t0: 19, t1: 70, label: STEADY }
```

```python
from plotsigs import load_yaml

d = load_yaml("analysis.yaml")
d.render(output="output/analysis.png", show=True)
```

---

## Key concepts

### Groups

Each `Diagram` contains one or more **groups** — subplots rendered in order:

```python
g_speed = d.add_group("Speed [RPM]")      # analog subplot
g_flags = d.add_digital_group()           # stacked binary lane subplot
g_temp  = d.add_group("Temp [°C]")        # another analog subplot below
```

### Phase-first workflow

Define `PhaseLabel` objects *before* analysis so analyses can reference them:

```python
ph_idle    = d.add_phase(0,  10, "IDLE")      # returns PhaseLabel
ph_startup = d.add_phase(10, 18, "STARTUP")

g.add_transient_analysis(
    "Set Speed", "Running Speed",
    phase=ph_startup,      # sets after_t=10, before_t=18 automatically
    after_t=11.0,          # explicit after_t overrides phase.t0 when needed
)
```

### Synthetic vs measured signals

```python
# Synthetic (no data needed)
cmd = g.add_stepped("Set Speed", [(0, 0), (5, 8500)])      # piecewise constant
g.add_lagged("Response", source=cmd, tau=2.0)              # 1st-order lag

# From a DataFrame
g.add_measured("AC_Set_Speed", df)                         # analog
g.add_measured_digital("DrvrOut_IsRunOk", df)             # 0/1 lane
g.add_derived("Error", "AC_Set_Speed", "Running_Speed")   # computed a − b
```

### Converting numpy arrays — `to_digital_bps()`

When you have a signal as a dense numpy array (e.g. computed from a simulation
or derived from conditions), convert it to breakpoints so you can add it as a
`DigitalSignal`:

```python
import numpy as np
from plotsigs import Diagram, to_digital_bps

t    = np.linspace(0, 100, 5000)
mode = np.where(t < 30, 1.0, np.where(t < 70, 2.0, 3.0))  # integer codes

# Derive binary signals from the mode array
heater_on = (mode == 1).astype(float)   # numpy array → DigitalSignal
cooler_on = (mode == 3).astype(float)

d = Diagram("My Diagram", t_end=100)
g_flags = d.add_digital_group("Actuators")
g_flags.add_digital("Heater ON", to_digital_bps(t, heater_on), color="#e74c3c")
g_flags.add_digital("Cooler ON", to_digital_bps(t, cooler_on), color="#3498db")
```

`to_digital_bps()` strips redundant samples and keeps only transition points,
so it works efficiently even on dense simulation arrays with thousands of points.

### Plant simulation — `plotsigs.sim`

`plotsigs.sim` provides ready-to-use ODE integrators so diagram scripts focus
on what to show, not on implementing integrators:

```python
from plotsigs.sim import (
    first_order,              # G(s) = 1/(τs+1)  — scipy.lsim
    second_order,             # G(s) = ωn²/(s²+2ζωn·s+ωn²)  — scipy.lsim
    second_order_saturated,   # 2nd-order + actuator rate limit  — Euler
    second_order_disturbed,   # 2nd-order + additive forcing     — Euler
    transport_delay,          # pure time delay (zero-order hold)
)

t   = np.linspace(0, 100, 5000)
u   = np.where(t < 10, 20.0, 27.0)   # setpoint step

y1  = first_order(t, u, tau=8.0)                              # 1st-order lag
y2  = second_order(t, u, omega_n=0.3, zeta=0.4)              # 2nd-order step
y3  = second_order_disturbed(t, u, 0.3, 0.1,
                             disturbance=np.where(t>50, 0.3, 0.0))  # + heat load
y4  = transport_delay(y2, t, delay=5.0)                       # 5 s dead time

g.add_raw("Response", t, y2, color="#e74c3c")
```

---

## Reusable diagram templates

When multiple scenarios share the same group layout — same panels, same
annotations, same threshold lines — define a helper function that takes a
`Diagram` and adds the groups to it. Each scenario then calls the helper once
and customises only what differs:

```python
MODE_LABELS = {1: "Heating", 2: "Circulation", 3: "Cooling"}
MODE_COLORS = {1: "#e74c3c", 2: "#9b59b6", 3: "#3498db"}
DEAD = 4.0  # °C

def add_tms_groups(d, t, T_MR, T_SP, mode):
    """Standard 3-panel TMS layout: Temperature + Error + Mode."""
    g_temp = d.add_group("Temperature [°C]")
    g_temp.add_raw("T_SP", t, T_SP, color="#2ecc71", lw=2.0)
    g_temp.add_raw("T_MR", t, T_MR, color="#e74c3c", lw=1.8)
    g_temp.add_tolerance("T_SP", DEAD, color="#9b59b6",
                         label=f"+-{DEAD:.0f} degC mode band")

    g_err = d.add_group("T_ERR [°C]")
    g_err.add_derived("T_err", "T_MR", "T_SP", color="#8e44ad")
    g_err.add_threshold( DEAD, label=f"+{DEAD} -> Cooling", color="#3498db", ls="--")
    g_err.add_threshold(-DEAD, label=f"-{DEAD} -> Heating", color="#e74c3c", ls="--")

    g_mode = d.add_group("TMS Mode")
    g_mode.add_enum("Mode", t, mode, labels=MODE_LABELS, colors=MODE_COLORS)
    return g_temp, g_err, g_mode

# Scenario A — clean step response
d_a = Diagram("Scenario A", t_end=T_END)
g_temp, g_err, g_mode = add_tms_groups(d_a, t, T_MR_a, T_SP, mode_a)
g_temp.add_transient_analysis("T_SP", "T_MR", tolerance_pct=5.0)  # add on top
d_a.render(output="output/scenario_a.png", show=False)

# Scenario B — same template, different data
d_b = Diagram("Scenario B — Disturbed", t_end=T_END)
g_temp, g_err, g_mode = add_tms_groups(d_b, t, T_MR_b, T_SP, mode_b)
g_temp.add_callout("T_MR", 80, label="Boundary chattering", offset=(3, 1.5))
d_b.render(output="output/scenario_b.png", show=False)
```

The same pattern works for **naive vs. correct** comparisons: add two mode
panels to one diagram using the same time/temperature data but different mode
arrays, then let the reader compare them visually:

```python
d = Diagram("Standard vs. Hysteresis", t_end=T_END, figsize=(14, 13))
# Shared temperature panel
g_temp = d.add_group("Temperature [°C]")
g_temp.add_raw("T_SP", t, T_SP, color="#2ecc71", lw=2.0)
g_temp.add_raw("T_MR", t, T_MR, color="#e74c3c", lw=1.8)
# Two separate mode panels
d.add_group("Mode — Standard").add_enum(
    "Mode_std",  t, mode_std,  labels=MODE_LABELS, colors=MODE_COLORS)
d.add_group("Mode — Hysteresis").add_enum(
    "Mode_hyst", t, mode_hyst, labels=MODE_LABELS, colors=MODE_COLORS)
d.render(output="output/comparison.png", show=False)
```

See [`examples/ex_template_function.py`](examples/ex_template_function.py) and
[`examples/ex_compare_naive_correct.py`](examples/ex_compare_naive_correct.py)
for complete working versions.

---

## API reference

### `Diagram`

```python
d = Diagram(
    title,
    t_end,               # required for synthetic signals; auto-derived for CSV
    t_start=0,
    n_points=2000,
    figsize=(14, 8),
    xlabel="Time [s]",
    analog_ratio=3,      # subplot height ratio
    digital_ratio=1,
)
```

| Method | Returns | Description |
| --- | --- | --- |
| `add_group(ylabel)` | `SignalGroup` | Add an analog subplot |
| `add_digital_group(ylabel)` | `SignalGroup` | Add a digital stacked-lane subplot |
| `add_phase(t0, t1, label, color, show_vline, vline_label, status)` | `PhaseLabel` | Phase arrow on x-axis; `status="pass"` → green, `status="fail"` → red + × marker |
| `add_vline(t, label, color, ls, panel)` | `self` | Vertical marker across all subplots |
| `add_vspan(t0, t1, label, color, alpha, panel)` | `self` | Shaded region across all subplots |
| `render(output, show, dpi)` | `Figure` | Build and optionally save the figure |

### `SignalGroup` — analog signals

| Method | Returns | Description |
| --- | --- | --- |
| `add_stepped(name, breakpoints, color, lw)` | `SteppedSignal` | Piecewise-constant command |
| `add_lagged(name, source, tau, color, lw)` | `LaggedSignal` | First-order lag response |
| `add_raw(name, t_data, v_data, color)` | `RawSignal` | Signal from numpy arrays |
| `add_measured(name, df, time_col, value_col, color)` | `RawSignal` | Signal from a DataFrame column |
| `add_derived(name, a, b, color)` | `DerivedSignal` | Computed `a − b`; a/b are signal names or objects |
| `add_enum(name, t_data, v_data, labels, colors)` | `EnumeratedSignal` | Integer state-machine signal; zoom-reactive labels, colored bands per level |

### `SignalGroup` — analog annotations

| Method | Description |
| --- | --- |
| `add_threshold(value, label, color, ls)` | Horizontal threshold line |
| `add_tolerance(signal_name, tolerance, color)` | Fixed ± shaded band |
| `add_pct_tolerance(signal_name, pct, color)` | Proportional ±pct% shaded band (tracks signal value) |
| `add_callout(signal_name, t, label, offset)` | Arrow annotation at a point on a signal |
| `add_transient_analysis(reference, feedback, ...)` | Full step-response annotation overlay (see below) |

#### `add_transient_analysis()`

```python
g.add_transient_analysis(
    reference,           # setpoint signal name
    feedback,            # feedback signal name
    tolerance_pct=5.0,   # half-width of error band as % of setpoint
    phase=None,          # PhaseLabel — sets after_t / before_t from phase window
    after_t=None,        # restrict analysis to t >= after_t (overrides phase.t0)
    before_t=None,       # restrict analysis to t <= before_t (overrides phase.t1)
    show_settling=True,  # Ts line + label
    show_overshoot=True, # OS% callout at peak
    show_rise_time=True, # Tr label at 10%–90% crossing
    show_crosshairs=True,# MATLAB-style dashed lines to each characteristic
    ts_label_pos="above_band",  # "above_band" | "below_band" | "signal" | "top"
    settling_color="#27ae60",
    overshoot_color="#e74c3c",
    rise_time_color="#3498db",
)
```

Draws:

- ±`tolerance_pct`% shaded band tracking the setpoint
- Settling time `Ts` (first moment feedback stays inside band permanently)
- Peak overshoot `OS%` callout
- Rise time `Tr` (10%–90% of step height)
- MATLAB-style cross-hair dashed lines for each characteristic

### `SignalGroup` — digital signals

| Method | Description |
| --- | --- |
| `add_digital(name, breakpoints, color)` | Synthetic 0/1 signal |
| `add_measured_digital(name, df, time_col, color)` | 0/1 column from a DataFrame |

#### `add_event_duration()` — time between two events

```python
g_flags.add_event_duration(
    signal_a,            # signal whose threshold crossing starts the measurement
    threshold_a,         # threshold value for signal_a
    signal_b,            # signal whose edge ends the measurement
    direction_a="below", # "below" (drops under) | "above" (rises over)
    edge_b="rise",       # "rise" (0→1) | "fall" (1→0)
    phase=None,          # PhaseLabel — restrict event search window
    after_t=None,
    before_t=None,
    label_fmt="{:.1f}s", # format string for the duration label
    color="#e74c3c",
    y_pos=0.6,           # annotation height (0–1 axes fraction)
)
```

Draws a double-headed arrow between the two detected event times.
`signal_a` and `signal_b` may live in any group — they are looked up from
the shared diagram signal map.

### `plot_signals()` — quick DataFrame plots

```python
from plotsigs import plot_signals

plot_signals(
    df,
    groups,              # list of: signal name | [names] | {"signals": [...], "ylabel": "..."}
    title="",
    time_col="time",
    figsize=(14, 8),
    output=None,         # path or list of paths
    show=True,
)
```

`groups` format options:

```python
# Auto-detect mode (0/1 columns → digital, others → analog)
["Signal_A", "Signal_B"]               # one signal per subplot
[["Signal_A", "Signal_B"], "Signal_C"] # two in first subplot, one in second
[{"signals": ["A", "B"], "ylabel": "Speed [RPM]", "mode": "digital"}]
```

### `load_yaml()` — declarative YAML diagrams

```python
from plotsigs import load_yaml

# Basic load
d = load_yaml("diagram.yaml")

# With a pre-loaded DataFrame (any source: CSV, Parquet, SQL, simulation)
df = pd.read_parquet("log.parquet")
d  = load_yaml("template.yaml", data=df)

# With per-run overrides (batch processing)
d = load_yaml("template.yaml", data=df, overrides={
    "title":       "Run 001",
    "annotations": [{"type": "phase", "t0": 0, "t1": 14, "label": "IDLE"}, ...],
})
```

### `analysis` module

Pure-numpy functions — callable from notebooks without a `Diagram`:

```python
from plotsigs import analysis

# Step-response characteristics (matches MATLAB stepinfo())
info = analysis.stepinfo(t, setpoint, feedback, after_t=5.0, before_t=20.0)
# → {"RiseTime": ..., "SettlingTime": ..., "Overshoot": ..., "Peak": ..., ...}

# Individual characteristic functions
ts = analysis.settling_time(t, setpoint, feedback, threshold_pct=5.0, after_t=5.0)
os = analysis.overshoot(t, setpoint, feedback, after_t=5.0)
rt = analysis.rise_time(t, setpoint, feedback, after_t=5.0)

# Event detection
t_cross = analysis.find_crossing(t, error, threshold=100, direction="below", after_t=1.0)
t_edge  = analysis.find_edge(t, digital_sig, edge="rise", after_t=t_cross)

# Step detection (multi-step traces)
steps = analysis.find_steps(t, setpoint, min_step_pct=5.0)
# → [{"t": float, "from_val": float, "to_val": float, "size": float}, ...]
```

---

## YAML format reference

### Signal types

| `type` | Equivalent Python | Required fields |
| --- | --- | --- |
| `stepped` | `add_stepped()` | `breakpoints: [[t, v], ...]` |
| `lagged` | `add_lagged()` | `source:`, `tau:` |
| `raw` | `add_raw()` | `t:`, `v:` (inline arrays) |
| `measured` | `add_measured()` | column name in CSV/DataFrame |
| `measured_digital` | `add_measured_digital()` | column name in CSV/DataFrame |
| `derived` | `add_derived()` | `a:`, `b:` (signal names) |

### Group annotation types

| `type` | Equivalent Python |
| --- | --- |
| `tolerance` | `add_tolerance()` |
| `callout` | `add_callout()` |
| `transient_analysis` | `add_transient_analysis()` |

### Top-level annotations

| `type` | Equivalent Python |
| --- | --- |
| `phase` | `d.add_phase()` |
| `vline` | `d.add_vline()` |
| `vspan` | `d.add_vspan()` |

---

## Batch processing

### Multiple logs from one YAML template

When many log files share the same signal names and analysis config but differ
in timing (phase boundaries), define a template YAML with no data source and
supply data + phases per run from Python:

```python
import pandas as pd
from plotsigs import load_yaml

TEMPLATE = "examples/compressor_analysis_template.yaml"

LOGS = [
    {"title": "Run 001", "file": "log_001.csv",
     "phases": {"IDLE": (0, 14), "STARTUP": (14, 19), "STEADY": (19, 70)},
     "output": "output/run_001.png"},
    {"title": "Run 002", "file": "log_002.csv",
     "phases": {"IDLE": (0, 6.8), "STARTUP": (6.8, 11.9), "STEADY": (11.9, 80)},
     "output": "output/run_002.png"},
]

for log in LOGS:
    df = pd.read_csv(log["file"])   # swap for read_parquet, read_sql, etc.
    d  = load_yaml(TEMPLATE, data=df, overrides={
        "title":       log["title"],
        "annotations": [{"type": "phase", "t0": t0, "t1": t1, "label": label}
                        for label, (t0, t1) in log["phases"].items()],
    })
    d.render(output=log["output"], show=False)
```

### Script-based batch runner

When each case has its own Python script (simulation parameters, bespoke
annotations, computed captions), run them all via subprocess and collect
pass/fail results:

```python
import subprocess, sys, time
from pathlib import Path

SCRIPTS = [
    "cases/tms_baseline.py",
    "cases/tms_fix_hysteresis.py",
    "cases/tms_flt_vcu_offline.py",
    # ...
]

ok, failed = [], []
for script in SCRIPTS:
    label = Path(script).stem
    t0 = time.perf_counter()
    result = subprocess.run(
        [sys.executable, script],
        capture_output=True, text=True,
        env={**__import__("os").environ, "MPLBACKEND": "Agg"},  # non-interactive
    )
    elapsed = time.perf_counter() - t0
    if result.returncode == 0:
        ok.append(label);  print(f"  OK  {label:<40} ({elapsed:.1f}s)")
    else:
        failed.append(label); print(f"FAIL  {label:<40}")
        print(result.stderr.strip())

print(f"\n{len(ok)}/{len(SCRIPTS)} scripts succeeded.")
if failed:
    sys.exit(1)
```

Set `MPLBACKEND=Agg` in the subprocess environment to force non-interactive
rendering — avoids GUI windows and works in CI.
See [`examples/ex_batch.py`](examples/ex_batch.py) for a complete runner.

---

## Examples

See **[docs/examples-gallery.md](docs/examples-gallery.md)** for the full catalog with rendered output images.
For the interactive Plotly/Dash backend see **[docs/examples.md](docs/examples.md)**.

| File | Demonstrates |
| --- | --- |
| `ex_quickplot.py` | `plot_signals()` one-liner — auto-detect, shorthand, dict spec |
| `ex_quickplot_from_yaml.py` | `plot_signals_from_yaml()` from a YAML config |
| `ex_plot_from_script.py` | Pure Python API — stepped / lagged / digital / annotations |
| `ex_plot_from_csv.py` | `add_measured()` / `add_measured_digital()` from DataFrame |
| `ex_plot_control_transient.py` | `add_transient_analysis()` — single step and multi-step |
| `ex_plot_csv_analysis_sim.py` | Phase-first workflow + `add_event_duration()` on sim data |
| `ex_plot_from_yaml.py` | YAML loader — synthetic + real CSV data |
| `ex_real_log_analysis.py` | Real compressor log — phase-first + transient analysis |
| `ex_multi_log_analysis.py` | Batch template — two logs, one YAML, overrides per run |
| `ex_template_function.py` | Reusable diagram template + `plotsigs.sim` + `to_digital_bps()` |
| `ex_compare_naive_correct.py` | Dual-panel naive vs. correct — hysteresis fix, phase pass/fail |
| `ex_enum_phases.py` | `add_enum()` zoom-reactive labels + phase `status="pass"/"fail"` |
| `ex_batch.py` | Subprocess batch runner — regenerate all outputs, collect pass/fail |

Run any example from the repo root:

```bash
python examples/ex_plot_control_transient.py
```

---

## Project structure

```text
plotsigs/
├── plotsigs/
│   ├── __init__.py         # public API re-exports
│   ├── diagram.py          # Diagram + SignalGroup — fluent builder API
│   ├── signals.py          # Signal classes (evaluated lazily at render time)
│   ├── annotations.py      # Annotation dataclasses — pure data, no matplotlib
│   ├── analysis.py         # Pure-numpy step-response and event-detection functions
│   ├── renderer.py         # All matplotlib drawing logic
│   ├── renderer_plotly.py  # Plotly figure builder (interactive HTML)
│   ├── dash_app.py         # Full Dash application (browser app)
│   ├── loader.py           # YAML → Diagram loader
│   ├── quickplot.py        # plot_signals() one-liner API
│   └── style.py            # Visual constants / theme defaults
├── docs/
│   ├── index.md            # Documentation home
│   ├── examples.md         # Script + data file reference
│   ├── issues.md           # Bug log (fixed and open)
│   ├── roadmap.md          # Planned features
│   └── dash-implementation.md  # Plotly/Dash internals and quirks
├── examples/               # Runnable examples (see table above)
├── tests/
│   └── test_signals.py
├── pyproject.toml
└── README.md
```

---

## Design principles

1. **Data and rendering are separated.** `signals.py` and `annotations.py`
   are pure Python dataclasses with no matplotlib imports. Only `renderer.py`
   touches matplotlib — easy to add Plotly or SVG backends later.

2. **Signals are lazy.** Each signal has an `evaluate(t)` method called at
   render time. Derived signals always see the correct time axis regardless of
   definition order.

3. **Phase-first is the natural workflow.** `add_phase()` returns a `PhaseLabel`
   object that carries its own time window. Pass it to `add_transient_analysis()`
   or `add_event_duration()` to avoid repeating coordinates.

4. **Any data source is welcome.** `add_measured()` / `add_measured_digital()`
   accept any pandas DataFrame — CSV, Parquet, SQL, FMU simulation, or in-memory
   arrays from tests. The `load_yaml()` `data=` parameter does the same for
   YAML-driven workflows.

5. **Everything is overridable.** Colors, line widths, font sizes all have
   sensible defaults in `style.py` but every constructor accepts kwargs that
   flow through to matplotlib.
