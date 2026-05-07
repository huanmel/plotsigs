"""
Style defaults — all visual constants in one place.
Override by passing kwargs to signal/annotation constructors,
or swap out this module entirely for a custom theme.
"""

import matplotlib.pyplot as plt

# Figure background
FIG_BG   = "#f8f9fa"
AXES_BG  = "#ffffff"

# Grid
GRID_LS    = "--"
GRID_ALPHA = 0.4

# Default signal colors (fallback if user doesn't specify)
COLOR_CMD      = "#2ecc71"   # command / set-point (green)
COLOR_RESPONSE = "#e74c3c"   # physical response (red/orange)
COLOR_DIGITAL  = "#2980b9"   # digital signal (blue)
COLOR_FAULT    = "#c0392b"   # fault markers
COLOR_STARTUP  = "#f39c12"   # startup windows (amber)
COLOR_BAND     = "#3498db"   # threshold bands (blue)
COLOR_TOL      = "#9b59b6"   # tolerance corridors (purple)
COLOR_RAW      = "#e67e22"   # measured / raw data (orange)

# Typography
FONT_SIZE_TITLE    = 11
FONT_SIZE_LABEL    = 9
FONT_SIZE_TICK     = 8
FONT_SIZE_ANNOT    = 7.5
FONT_SIZE_PHASE    = 7

# Digital panel
DIGITAL_LANE_HEIGHT = 1.4    # vertical spacing between digital signal lanes
DIGITAL_SIGNAL_SCALE = 0.9   # how tall each 0→1 pulse is within its lane

# Right-margin fraction reserved for threshold labels
RIGHT_MARGIN = 0.92

def apply():
    """Apply global rcParams. Called once at render time."""
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.linestyle": GRID_LS,
        "grid.alpha": GRID_ALPHA,
        "axes.labelsize": FONT_SIZE_LABEL,
        "xtick.labelsize": FONT_SIZE_TICK,
        "ytick.labelsize": FONT_SIZE_TICK,
    })
