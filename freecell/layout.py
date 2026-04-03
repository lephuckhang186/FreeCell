"""
Layout and Geometry Engine.
Responsible for calculating screen positions and hit-target detection.
"""

from __future__ import annotations

import pygame

from .constants import (
    CARD_HEIGHT,
    CARD_WIDTH,
    FOOTER_HEIGHT,
    OUTER_PADDING,
    SLOT_GAP_X,
    TABLEAU_GAP_Y,
    TABLEAU_Y,
    TOP_ROW_Y,
)
from .rules import PileRef, PileType


class BoardLayout:
    """Precomputes static board rectangles and pointer hit tests."""

    def __init__(self, screen_size: tuple[int, int]) -> None:
        self.screen_width, self.screen_height = screen_size
        self.free_cells: list[pygame.Rect] = []
        self.foundations: list[pygame.Rect] = []
        self.tableau: list[pygame.Rect] = []
        self._build()

    def resize(self, screen_size: tuple[int, int]) -> None:
        """Rebuild geometry when window size changes."""
        self.screen_width, self.screen_height = screen_size
        self._build()

    def _build(self) -> None:
        self.free_cells.clear()
        self.foundations.clear()
        self.tableau.clear()

        # Keep tableau centered, then align top slots with tableau columns.
        tableau_width = 8 * CARD_WIDTH + 7 * SLOT_GAP_X
        board_left = max(OUTER_PADDING, (self.screen_width - tableau_width) // 2)

        x = board_left
        for _ in range(4):
            self.free_cells.append(pygame.Rect(x, TOP_ROW_Y, CARD_WIDTH, CARD_HEIGHT))
            x += CARD_WIDTH + SLOT_GAP_X

        for _ in range(4):
            self.foundations.append(pygame.Rect(x, TOP_ROW_Y, CARD_WIDTH, CARD_HEIGHT))
            x += CARD_WIDTH + SLOT_GAP_X

        x = max(OUTER_PADDING, (self.screen_width - tableau_width) // 2)
        for _ in range(8):
            self.tableau.append(pygame.Rect(x, TABLEAU_Y, CARD_WIDTH, CARD_HEIGHT))
            x += CARD_WIDTH + SLOT_GAP_X

    def card_rect_in_tableau(self, col: int, row: int) -> pygame.Rect:
        base = self.tableau[col]
        return pygame.Rect(
            base.x, base.y + row * TABLEAU_GAP_Y, CARD_WIDTH, CARD_HEIGHT
        )

    def tableau_cards_pick_rect(self, col: int, column_size: int) -> pygame.Rect | None:
        """Strict hit area for grabbing tableau cards (no bleed into foundation / empty space below)."""
        if column_size <= 0:
            return None
        top_r = self.card_rect_in_tableau(col, 0)
        bot_r = self.card_rect_in_tableau(col, column_size - 1)
        return pygame.Rect(top_r.x, top_r.y, CARD_WIDTH, bot_r.bottom - top_r.y)

    def tableau_column_drop_rect(self, col: int) -> pygame.Rect:
        """Vertical strip for dropping onto a tableau column (below top row, full height)."""
        base = self.tableau[col]
        margin_bot = 8
        h = max(1, self.screen_height - base.y - FOOTER_HEIGHT - margin_bot)
        return pygame.Rect(base.x, base.y, CARD_WIDTH, h)

    def drop_target(self, pos: tuple[int, int]) -> PileRef | None:
        for i, rect in enumerate(self.free_cells):
            if rect.collidepoint(pos):
                return PileRef(PileType.FREECELL, i)
        for i, rect in enumerate(self.foundations):
            if rect.collidepoint(pos):
                return PileRef(PileType.FOUNDATION, i)
        for i in range(len(self.tableau)):
            if self.tableau_column_drop_rect(i).collidepoint(pos):
                return PileRef(PileType.TABLEAU, i)
        return None

    def tableau_pick_index(
        self, col: int, pos: tuple[int, int], column_size: int
    ) -> int:
        if column_size <= 0:
            return -1
        py = pos[1]
        base = self.tableau[col]
        last = self.card_rect_in_tableau(col, column_size - 1)
        if py >= last.bottom:
            return -1
        if py < base.y:
            return 0
        for i in range(column_size - 1, -1, -1):
            cr = self.card_rect_in_tableau(col, i)
            if cr.top <= py < cr.bottom:
                return i
        rel_y = py - base.y
        idx = rel_y // TABLEAU_GAP_Y
        return max(0, min(column_size - 1, idx))
