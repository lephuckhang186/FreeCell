"""
Global Game Constants.
Defines layout dimensions, color palettes, and default configurations.
"""

from __future__ import annotations

# Window
SCREEN_WIDTH = 1360
SCREEN_HEIGHT = 820
FPS = 120
TITLE = "FreeCell (pygame)"

# New Game → pick difficulty/level (drives freecell/generate_test.py LEVEL)
NEW_GAME_LEVEL_RANGES: dict[str, tuple[int, int]] = {
    "easy": (1, 3),
    "medium": (4, 7),
    "hard": (8, 10),
}
DEFAULT_NEW_GAME_DIFFICULTY = "easy"
DEFAULT_NEW_GAME_LEVEL = NEW_GAME_LEVEL_RANGES[DEFAULT_NEW_GAME_DIFFICULTY][1]  # 3

# Auto-solve (background thread): max wall time before UI declares game over
SOLVER_AUTOSOLVE_TIMEOUT_S = 5 * 60  # 5 minutes

# Card geometry
CARD_WIDTH = 110
CARD_HEIGHT = 150
CARD_CORNER_RADIUS = 8
# Rounded hairline around card faces (~1pt on typical display; use 2 if too faint)
CARD_FACE_OUTLINE_WIDTH = 1
CARD_FACE_OUTLINE_COLOR = (0, 0, 0)
# Inset scaled PNG art inside the card rect so corner indices sit away from the rounded edge
CARD_FACE_ART_INSET = 5
TABLEAU_GAP_Y = 34

# Global spacing and board layout
OUTER_PADDING = 24
# Board: free cells / foundations / tableau — anchored near top (below OS title bar)
BOARD_TOP_MARGIN = 40
TABLEAU_GAP_BELOW_TOP = 20
TOP_ROW_Y = BOARD_TOP_MARGIN
TABLEAU_Y = TOP_ROW_Y + CARD_HEIGHT + TABLEAU_GAP_BELOW_TOP
FOOTER_HEIGHT = 34  # Classic status bar (cream + inset panels)
FOOTER_INFO_FONT_SIZE = 15
FOOTER_BG = (237, 233, 224)  # ~#EDE9E0
FOOTER_PANEL_FACE = (242, 239, 233)  # ~#F2EFE9
FOOTER_TEXT = (51, 51, 51)  # ~#333
FOOTER_BEVEL_DK = (135, 135, 135)  # inset shadow (top / left)
FOOTER_BEVEL_LT = (255, 255, 255)  # inset highlight (bottom / right)
FOOTER_INNER_MARGIN = 3
FOOTER_PANEL_GAP = 4
FOOTER_PANEL_PAD_X = 10
FOOTER_GRIP_WIDTH = 16
SLOT_GAP_X = 24

# ── Bottom-right menu button (replaces floating toolbar) ──────────────────────
MENU_BTN_MARGIN = 3

# Dropup menu (opens upward from the ☰ button)
MENU_DROPUP_WIDTH = 174
MENU_DROPUP_ROW_H = 32
MENU_DROPUP_PAD = 5
MENU_DROPUP_GAP = 4
MENU_DROPUP_RADIUS = 8

# Submenu (flies out to the left)
MENU_SUBMENU_WIDTH = 120
MENU_SUBMENU_ROW_H = 30
MENU_SUBMENU_PAD = 4
MENU_SUBMENU_GAP = 2
MENU_SUBMENU_RADIUS = 6

# Sub-submenu cells (level numbers)
MENU_SUB2_CELL_W = 46
MENU_SUB2_ROW_H = 28

# Menu structure
MENU_ITEMS = ("NEW GAME", "LOAD GAME", "UNDO", "REDO", "PAUSE", "SOLVE")
MENU_ITEMS_WITH_SUBMENU = {"NEW GAME", "SOLVE"}
MENU_GLYPHS = {
    "NEW GAME": "\u271a",
    "LOAD GAME": "📂",
    "UNDO": "\u21a9",
    "REDO": "\u21aa",
    "PAUSE": "\u23f8",
    "SOLVE": "\u2315",
}
SOLVE_ALGO_ORDER = ("BFS", "IDS", "UCS", "A*")

# Menu colours — matching the cream footer bar (Win32 style)
MENU_BG = (237, 233, 224, 252)
MENU_BORDER = (160, 160, 160)
MENU_TEXT_COLOR = (0, 0, 0)
MENU_TEXT_HOVER = (0, 0, 0)
MENU_HOVER_FACE = (198, 214, 235)  # soft blue highlight (Win32 menu hover)
MENU_ARROW = "\u25c4"

# Color palette — classic Windows FreeCell-style green felt
COLOR_BG = (0, 128, 0)  # #008000
COLOR_BG_DEEP = (0, 96, 0)
# Optional diagonal texture (disabled for flat classic felt)
COLOR_STRIPE = (0, 110, 0)
COLOR_STRIPE_ALPHA = 0
COLOR_STRIPE_SPACING = 36
COLOR_STRIPE_WIDTH = 16
COLOR_FELT_NOISE = (0, 100, 0)
# When False, only COLOR_BG is shown (no asset/background.jpg overlay)
BACKGROUND_USE_IMAGE = False
COLOR_PANEL = (14, 52, 22)
COLOR_HEADER = (14, 52, 22)
# Sunken slots on green felt (Win32-style inset: dark top/left, light bottom/right)
COLOR_FELT_SLOT_FACE = (0, 106, 0)
COLOR_FELT_BEVEL_SHADOW = (0, 70, 0)
COLOR_FELT_BEVEL_HIGHLIGHT = (0, 172, 0)
COLOR_SLOT_TARGET_RING = (255, 228, 100)

COLOR_CARD_FACE = (245, 244, 238)
COLOR_CARD_BORDER = (60, 60, 60)
COLOR_CARD_RED = (183, 32, 32)
COLOR_CARD_BLACK = (25, 25, 25)
COLOR_SHADOW = (0, 0, 0)
COLOR_TEXT = (240, 245, 252)
COLOR_TEXT_SHADOW = (8, 12, 24)
COLOR_HINT = (255, 220, 100)
COLOR_HINT_GLOW = (255, 215, 80)
COLOR_WIN = (255, 255, 200)
COLOR_GAME_OVER = (255, 140, 140)
COLOR_INFO_TEXT = (255, 255, 255)

# Solver toolbar button accent (outline)
SOLVER_BTN_ACCENTS = {
    "IDS": (72, 190, 110),
    "BFS": (230, 85, 95),
    "UCS": (95, 155, 240),
    "A*": (180, 120, 235),
}

# Animation tuning
DRAG_SMOOTH_FACTOR = 0.28
DROP_ANIM_DURATION = 0.14
# Card drop shadow (kept subtle — was easy to read as “too heavy”)
SHADOW_ALPHA = 26
SHADOW_ALPHA_SOFT = 10
CARD_SHADOW_OFFSET = 2
CARD_SHADOW_SCALE_OUTER = 1.05
CARD_SHADOW_SCALE_INNER = 1.02

# Inner bevel gloss / shade on card face (drawn before outline)
CARD_BEVEL_HI_ALPHA = 30
CARD_BEVEL_LO_ALPHA = 20
DOUBLE_CLICK_SECONDS = 0.28
