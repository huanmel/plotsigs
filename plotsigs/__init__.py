"""
plotsigs — Control system signal & timing diagram library.

Quick start:
    from plotsigs import Diagram

    d = Diagram("My Test", t_end=60)
    cmd = d.add_stepped("Set Speed", [(0, 1000), (10, 8500), (22, 1000)])
    d.add_lagged("Running Speed", source=cmd, tau=1.8)
    d.add_threshold(1500, label="MIN")
    d.render("output.svg")

Load from YAML:
    from plotsigs import load_yaml
    d = load_yaml("diagram.yaml")
    d.render(show=True)
"""

__version__ = "0.1.0"

from plotsigs.diagram import Diagram
from plotsigs.signals import Signal, SteppedSignal, LaggedSignal, RawSignal, DigitalSignal, DerivedSignal, EnumeratedSignal, to_digital_bps
from plotsigs.annotations import Threshold, ToleranceBand, PctToleranceBand, VLine, VSpan, PhaseLabel, Callout
from plotsigs.loader import load_yaml
from plotsigs.quickplot import plot_signals, plot_signals_from_yaml
from plotsigs.export import export_drawio, export_excalidraw
from plotsigs.spec import render_spec
from plotsigs import analysis, sim

__all__ = [
    "Diagram",
    "Signal",
    "SteppedSignal",
    "LaggedSignal",
    "RawSignal",
    "DigitalSignal",
    "Threshold",
    "ToleranceBand",
    "VLine",
    "VSpan",
    "PhaseLabel",
    "Callout",
    "load_yaml",
    "render_spec",
    "plot_signals",
    "plot_signals_from_yaml",
    "export_drawio",
    "export_excalidraw",
    "DerivedSignal",
    "EnumeratedSignal",
    "to_digital_bps",
    "PctToleranceBand",
    "analysis",
    "sim",
]
