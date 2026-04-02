"""Centralized constants used by the whole game."""

from __future__ import annotations

# Window
SCREEN_WIDTH = 1360
SCREEN_HEIGHT = 820
FPS = 120
TITLE = "FreeCell (pygame)"

# Card geometry
CARD_WIDTH = 110
CARD_HEIGHT = 150
CARD_CORNER_RADIUS = 12
TABLEAU_GAP_Y = 34

# Global spacing and board layout
OUTER_PADDING = 24
HEADER_HEIGHT = 120                         # Height of title / score / time bar
TOP_ROW_Y = HEADER_HEIGHT + 24             # Card slots start below header
TABLEAU_Y = TOP_ROW_Y + CARD_HEIGHT + 20   # Tableau below top slots (= 246)
SLOT_GAP_X = 24

# Color palette
COLOR_BG = (70, 85, 100)
COLOR_FELT_NOISE = (65, 80, 95)
COLOR_PANEL = (50, 65, 80)
COLOR_HEADER = (45, 55, 65)
COLOR_FREECELL_BORDER = (110, 220, 240)
COLOR_FOUNDATION_BORDER = (50, 60, 70)
COLOR_FOUNDATION_ICON = (80, 90, 100)
COLOR_CARD_FACE = (245, 244, 238)
COLOR_CARD_BORDER = (60, 60, 60)
COLOR_CARD_RED = (183, 32, 32)
COLOR_CARD_BLACK = (25, 25, 25)
COLOR_SHADOW = (0, 0, 0)
COLOR_TEXT = (238, 245, 238)
COLOR_HINT = (255, 224, 120)
COLOR_WIN = (255, 255, 180)

# Animation tuning
DRAG_SMOOTH_FACTOR = 0.28
DROP_ANIM_DURATION = 0.14
SHADOW_ALPHA = 80
DOUBLE_CLICK_SECONDS = 0.28
