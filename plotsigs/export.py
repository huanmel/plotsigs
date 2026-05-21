"""
plotsigs/export.py
==================
Export a rendered Diagram to draw.io (.drawio) or Excalidraw (.excalidraw).

Strategy — hybrid export:
  - Background: the full diagram rendered to PNG (base64-embedded in the file)
  - Foreground: key text/arrow annotations added as native editable shapes
    so collaborators can rename labels, move them, or add new ones without
    touching Python.

Native shapes exported:
  - Diagram title
  - Phase bracket arrows + label text
  - Phase vertical-line labels (rotated)
  - Threshold line labels (right-side)
  - VLine labels
  - VSpan labels

Transient-analysis characteristics (Ts, Tr, OS%) stay in the background PNG.
"""

from __future__ import annotations

import base64
import io
import json
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, List

import matplotlib
matplotlib.use("Agg")  # ensure non-interactive backend for offscreen render
import matplotlib.pyplot as plt

if TYPE_CHECKING:
    from .diagram import Diagram


# ── Format-agnostic shape primitives ─────────────────────────────────────────

@dataclass
class TextShape:
    x: float
    y: float
    w: float
    h: float
    text: str
    color: str = "#555555"
    font_size: int = 11
    align: str = "center"   # "left" | "center" | "right"
    rotation: float = 0.0   # degrees; positive = counter-clockwise


@dataclass
class ArrowShape:
    x1: float
    y1: float
    x2: float
    y2: float
    color: str = "#555555"
    double_headed: bool = True
    lw: float = 1.0


# ── Coordinate mapper ─────────────────────────────────────────────────────────

class _CoordMapper:
    """Maps diagram/data coordinates to image-pixel coordinates.

    Pixel convention: (0, 0) = top-left corner of the PNG.
    matplotlib convention: y=0 at bottom, image: y=0 at top.
    """

    def __init__(self, fig, axes, dpi: int):
        w_in, h_in = fig.get_size_inches()
        self.px_w = w_in * dpi
        self.px_h = h_in * dpi
        self._axes = axes

    # ── helpers ───────────────────────────────────────────────────────────────

    def _ax(self, idx: int):
        return self._axes[idx]

    def t_to_x(self, t: float, ax_idx: int = 0) -> float:
        """Time value → pixel x (all axes share the same x-axis)."""
        ax = self._ax(ax_idx)
        bb = ax.get_position()
        xlim = ax.get_xlim()
        x0 = bb.x0 * self.px_w
        w  = bb.width * self.px_w
        return x0 + (t - xlim[0]) / (xlim[1] - xlim[0]) * w

    def axes_top_px(self, ax_idx: int) -> float:
        """Pixel y of the TOP edge of axes[ax_idx] (0 = top of image)."""
        bb = self._ax(ax_idx).get_position()
        return (1.0 - bb.y1) * self.px_h

    def axes_bottom_px(self, ax_idx: int) -> float:
        """Pixel y of the BOTTOM edge of axes[ax_idx]."""
        bb = self._ax(ax_idx).get_position()
        return (1.0 - bb.y0) * self.px_h

    def axes_right_px(self, ax_idx: int) -> float:
        """Pixel x of the RIGHT edge of axes[ax_idx]."""
        bb = self._ax(ax_idx).get_position()
        return bb.x1 * self.px_w

    def data_to_px(self, t: float, v: float, ax_idx: int) -> tuple[float, float]:
        """Data (t, value) in group ax_idx → (px_x, px_y)."""
        ax = self._ax(ax_idx)
        bb = ax.get_position()
        xlim, ylim = ax.get_xlim(), ax.get_ylim()
        x = bb.x0 * self.px_w + (t - xlim[0]) / (xlim[1] - xlim[0]) * (bb.width  * self.px_w)
        y = (1.0 - bb.y1) * self.px_h + (1.0 - (v - ylim[0]) / (ylim[1] - ylim[0])) * (bb.height * self.px_h)
        return x, y

    def axes_fraction_to_px(self, ax_idx: int, xf: float, yf: float) -> tuple[float, float]:
        """Axes-fraction (0..1) coords → pixel coords."""
        bb = self._ax(ax_idx).get_position()
        px = bb.x0 * self.px_w + xf * bb.width  * self.px_w
        py = (1.0 - bb.y0) * self.px_h - yf * bb.height * self.px_h
        return px, py


# ── Shared render pipeline ────────────────────────────────────────────────────

def _render_background(diagram: "Diagram", dpi: int) -> tuple:
    """
    Render the diagram to an in-memory PNG and return
    (fig, png_b64_str, active_groups, coord_mapper).
    """
    from . import renderer as _renderer

    fig = _renderer.render(diagram)

    buf = io.BytesIO()
    # No bbox_inches="tight" so figure dimensions stay exactly fig.get_size_inches()*dpi
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches=None)
    buf.seek(0)
    png_b64 = base64.b64encode(buf.read()).decode("ascii")

    axes = fig.get_axes()
    active = [g for g in diagram._groups if g.signals]
    cm = _CoordMapper(fig, axes, dpi)

    plt.close(fig)
    return fig, png_b64, active, axes, cm


# ── Shape extraction ──────────────────────────────────────────────────────────

def _extract_shapes(diagram: "Diagram", active, axes, cm: _CoordMapper) -> list:
    shapes: list[TextShape | ArrowShape] = []

    # Title
    if diagram.title:
        shapes.append(TextShape(
            x=cm.px_w / 2 - cm.px_w * 0.4,
            y=2,
            w=cm.px_w * 0.8,
            h=22,
            text=diagram.title,
            color="#222222",
            font_size=13,
        ))

    # Phase labels + bracket arrows (drawn below the bottom axes)
    if diagram._phase_labels:
        n_axes = len(axes)
        arrow_y = cm.axes_bottom_px(n_axes - 1) + 18   # pixels below bottom subplot
        label_y = arrow_y + 5

        for ph in diagram._phase_labels:
            x1 = cm.t_to_x(ph.t0)
            x2 = cm.t_to_x(ph.t1)
            shapes.append(ArrowShape(x1, arrow_y, x2, arrow_y,
                                     color=ph.color, double_headed=True, lw=0.9))
            shapes.append(TextShape(
                x=(x1 + x2) / 2 - (x2 - x1) / 2,
                y=label_y,
                w=max(x2 - x1, 20),
                h=14,
                text=ph.label,
                color=ph.color,
                font_size=8,
            ))

        # Phase vline labels (rotated text at top of first axes, one per phase)
        top_y = cm.axes_top_px(0)
        for ph in diagram._phase_labels:
            if not ph.show_vline or not ph.vline_label or not ph.label:
                continue
            x = cm.t_to_x(ph.t0)
            shapes.append(TextShape(
                x=x - 5,
                y=top_y + 4,
                w=10,
                h=55,
                text=ph.label,
                color=ph.color,
                font_size=7,
                align="right",
                rotation=90,
            ))

    # Threshold labels (right side of each analog group's axes)
    for grp_idx, grp in enumerate(active):
        if grp.mode != "analog":
            continue
        ax = axes[grp_idx]
        rx = cm.axes_right_px(grp_idx) + 5
        xlim = ax.get_xlim()
        for th in grp.thresholds:
            if not th.label:
                continue
            _, py = cm.data_to_px(xlim[1], th.value, grp_idx)
            shapes.append(TextShape(
                x=rx,
                y=py - 7,
                w=88,
                h=14,
                text=th.label,
                color=th.color,
                font_size=8,
                align="left",
            ))

    # VLine labels
    for vl in diagram._vlines:
        if not vl.label:
            continue
        x = cm.t_to_x(vl.t)
        # label_y is axes fraction of the first axes
        _, py = cm.axes_fraction_to_px(0, 0, vl.label_y)
        shapes.append(TextShape(
            x=x + 4,
            y=py - 9,
            w=80,
            h=16,
            text=vl.label,
            color=vl.color,
            font_size=9,
            align="left",
        ))

    # VSpan labels
    for vs in diagram._vspans:
        if not vs.label:
            continue
        xm = (cm.t_to_x(vs.t0) + cm.t_to_x(vs.t1)) / 2
        _, py = cm.axes_fraction_to_px(0, 0, vs.label_y)
        shapes.append(TextShape(
            x=xm - 50,
            y=py - 9,
            w=100,
            h=16,
            text=vs.label,
            color=vs.color,
            font_size=9,
        ))

    return shapes


# ── draw.io serializer ────────────────────────────────────────────────────────

def export_drawio(diagram: "Diagram", path, dpi: int = 150) -> None:
    """
    Export *diagram* to a draw.io (.drawio) file at *path*.

    The full rendered diagram is embedded as a PNG background image;
    key annotations (phase labels, threshold labels, title) are added
    as native editable draw.io shapes on top.

    Parameters
    ----------
    diagram : Diagram
    path    : str or Path — must end with .drawio
    dpi     : raster resolution of the background PNG
    """
    _, png_b64, active, axes, cm = _render_background(diagram, dpi)
    shapes = _extract_shapes(diagram, active, axes, cm)

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    W, H = round(cm.px_w), round(cm.px_h)

    # Build mxGraph XML tree
    mxfile = ET.Element("mxfile", host="plotsigs")
    diag   = ET.SubElement(mxfile, "diagram", name="diagram")
    model  = ET.SubElement(diag, "mxGraphModel",
                           dx="1034", dy="546",
                           grid="0", gridSize="10",
                           guides="1", tooltips="1",
                           connect="1", arrows="1",
                           fold="1", page="0",
                           pageScale="1",
                           pageWidth=str(W), pageHeight=str(H),
                           math="0", shadow="0")
    root   = ET.SubElement(model, "root")
    ET.SubElement(root, "mxCell", id="0")
    ET.SubElement(root, "mxCell", id="1", parent="0")

    cell_id = 2

    # Background image
    img_style = (
        "shape=image;verticalLabelPosition=bottom;labelBackgroundColor=default;"
        "verticalAlign=top;align=center;strokeColor=none;fillColor=none;"
        f"image=data:image/png,{png_b64};"
    )
    img_cell = ET.SubElement(root, "mxCell",
                             id=str(cell_id), value="",
                             style=img_style, vertex="1", parent="1")
    ET.SubElement(img_cell, "mxGeometry",
                  x="0", y="0", width=str(W), height=str(H),
                  **{"as": "geometry"})
    cell_id += 1

    def _add_text(s: TextShape):
        nonlocal cell_id
        rot_part = f"rotation={s.rotation:.0f};" if s.rotation else ""
        align_map = {"left": "left", "center": "center", "right": "right"}
        style = (
            f"text;html=1;strokeColor=none;fillColor=none;"
            f"align={align_map.get(s.align, 'center')};"
            f"verticalAlign=middle;whiteSpace=wrap;rounded=0;"
            f"fontSize={s.font_size};fontColor={s.color};{rot_part}"
        )
        cell = ET.SubElement(root, "mxCell",
                             id=str(cell_id), value=s.text,
                             style=style, vertex="1", parent="1")
        ET.SubElement(cell, "mxGeometry",
                      x=f"{s.x:.1f}", y=f"{s.y:.1f}",
                      width=f"{s.w:.1f}", height=f"{s.h:.1f}",
                      **{"as": "geometry"})
        cell_id += 1

    def _add_arrow(a: ArrowShape):
        nonlocal cell_id
        start = "open" if a.double_headed else "none"
        style = (
            f"endArrow=open;startArrow={start};endFill=0;startFill=0;"
            f"strokeColor={a.color};strokeWidth={a.lw:.1f};"
        )
        cell = ET.SubElement(root, "mxCell",
                             id=str(cell_id), value="",
                             style=style, edge="1", parent="1")
        geo = ET.SubElement(cell, "mxGeometry",
                            relative="1", **{"as": "geometry"})
        ET.SubElement(geo, "mxPoint",
                      x=f"{a.x1:.1f}", y=f"{a.y1:.1f}", **{"as": "sourcePoint"})
        ET.SubElement(geo, "mxPoint",
                      x=f"{a.x2:.1f}", y=f"{a.y2:.1f}", **{"as": "targetPoint"})
        cell_id += 1

    for shape in shapes:
        if isinstance(shape, TextShape):
            _add_text(shape)
        elif isinstance(shape, ArrowShape):
            _add_arrow(shape)

    tree = ET.ElementTree(mxfile)
    ET.indent(tree, space="  ")
    tree.write(path, encoding="unicode", xml_declaration=True)


# ── Excalidraw serializer ─────────────────────────────────────────────────────

def export_excalidraw(diagram: "Diagram", path, dpi: int = 150) -> None:
    """
    Export *diagram* to an Excalidraw (.excalidraw) file at *path*.

    The full rendered diagram is embedded as a PNG background image;
    key annotations are added as native editable Excalidraw elements.

    Parameters
    ----------
    diagram : Diagram
    path    : str or Path — must end with .excalidraw
    dpi     : raster resolution of the background PNG
    """
    _, png_b64, active, axes, cm = _render_background(diagram, dpi)
    shapes = _extract_shapes(diagram, active, axes, cm)

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    W, H = round(cm.px_w), round(cm.px_h)
    bg_file_id = "plotsigs-bg"

    def _uid() -> str:
        return str(uuid.uuid4())

    def _common(**extra) -> dict:
        return {
            "id": _uid(),
            "angle": 0,
            "strokeWidth": 1,
            "strokeStyle": "solid",
            "roughness": 0,
            "opacity": 100,
            "groupIds": [],
            "roundness": None,
            "isDeleted": False,
            "boundElements": None,
            "updated": 0,
            "link": None,
            "locked": False,
            **extra,
        }

    elements = []

    # Background image element
    elements.append({
        **_common(),
        "type": "image",
        "x": 0,
        "y": 0,
        "width": W,
        "height": H,
        "backgroundColor": "transparent",
        "fillStyle": "solid",
        "strokeColor": "transparent",
        "fileId": bg_file_id,
        "status": "saved",
        "scale": [1, 1],
    })

    def _align_excalidraw(align: str) -> str:
        return {"left": "left", "center": "center", "right": "right"}.get(align, "center")

    for shape in shapes:
        if isinstance(shape, TextShape):
            elements.append({
                **_common(),
                "type": "text",
                "x": shape.x,
                "y": shape.y,
                "width": shape.w,
                "height": shape.h,
                "angle": -shape.rotation * 3.14159265 / 180.0,
                "strokeColor": shape.color,
                "backgroundColor": "transparent",
                "fillStyle": "solid",
                "text": shape.text,
                "originalText": shape.text,
                "fontSize": shape.font_size,
                "fontFamily": 3,           # monospace; change to 1 for hand-drawn
                "textAlign": _align_excalidraw(shape.align),
                "verticalAlign": "middle",
                "containerId": None,
                "lineHeight": 1.25,
            })
        elif isinstance(shape, ArrowShape):
            dx = shape.x2 - shape.x1
            dy = shape.y2 - shape.y1
            elements.append({
                **_common(),
                "type": "arrow",
                "x": shape.x1,
                "y": shape.y1,
                "width": abs(dx),
                "height": abs(dy),
                "strokeColor": shape.color,
                "backgroundColor": "transparent",
                "fillStyle": "solid",
                "strokeWidth": round(shape.lw),
                "startArrowhead": "arrow" if shape.double_headed else None,
                "endArrowhead": "arrow",
                "points": [[0, 0], [dx, dy]],
                "lastCommittedPoint": None,
                "startBinding": None,
                "endBinding": None,
            })

    doc = {
        "type": "excalidraw",
        "version": 2,
        "source": "plotsigs",
        "elements": elements,
        "appState": {
            "gridSize": None,
            "viewBackgroundColor": "#ffffff",
        },
        "files": {
            bg_file_id: {
                "mimeType": "image/png",
                "id": bg_file_id,
                "dataURL": f"data:image/png;base64,{png_b64}",
                "created": 0,
                "lastRetrieved": 0,
            }
        },
    }

    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
