"""Centralized constants used by the whole game."""

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
FOOTER_HEIGHT = 34                          # Classic status bar (cream + inset panels)
FOOTER_INFO_FONT_SIZE = 15
FOOTER_BG = (237, 233, 224)                   # ~#EDE9E0
FOOTER_PANEL_FACE = (242, 239, 233)           # ~#F2EFE9
FOOTER_TEXT = (51, 51, 51)                 # ~#333
FOOTER_BEVEL_DK = (135, 135, 135)          # inset shadow (top / left)
FOOTER_BEVEL_LT = (255, 255, 255)            # inset highlight (bottom / right)
FOOTER_INNER_MARGIN = 3
FOOTER_PANEL_GAP = 4
FOOTER_PANEL_PAD_X = 10
FOOTER_GRIP_WIDTH = 16
SLOT_GAP_X = 24

# Toolbar buttons: single rounded face + border (full hit rect)
BUTTON_INNER_RADIUS = 9
# Unicode glyphs shown left of toolbar labels (Segoe UI Symbol / fallback fonts)
TOOLBAR_BUTTON_GLYPHS = {
    "NEW GAME": "✚",
    "UNDO": "↩",
    "REDO": "↪",
    "HINT": "?",
    "MENU": "⏸",
    "AI": "⌕",
}

# Floating toolbar (icon-only strip, draggable)
FAB_CELL = 42
FAB_GAP = 5
FAB_PAD = 10
FAB_RADIUS = 14
FAB_AI_DROPDOWN_ROW_H = 28
FAB_AI_DROPDOWN_WIDTH = 118  # vertical menu panel width (centered under AI cell)
FAB_AI_DROPDOWN_GAP = 8  # vertical gap between AI cell and dropdown
FAB_AI_DROPDOWN_OFFSET_X = 0  # nudge menu left (-) / right (+)
FAB_AI_DROPDOWN_OFFSET_Y = 0  # nudge menu down (+)
FAB_DRAG_THRESHOLD_SQ = 36  # px^2 before treating as drag
FAB_MAIN_ORDER = ("NEW GAME", "UNDO", "REDO", "HINT", "MENU", "AI")
FAB_AI_ALGO_ORDER = ("BFS", "IDS", "UCS", "A*")
FAB_TOOLTIPS = {
    "NEW GAME": "New game",
    "UNDO": "Undo",
    "REDO": "Redo",
    "HINT": "Hint",
    "MENU": "Pause",
    "AI": "Solve",
}

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
# Floating toolbar tuned for green table
FAB_PANEL_FILL = (12, 48, 18, 236)
FAB_PANEL_LINE = (120, 205, 130, 200)
FAB_SHADOW_ALPHA = 42
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
