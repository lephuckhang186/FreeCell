"""Rendering code for board, cards, and overlays."""

from __future__ import annotations

from pathlib import Path

import pygame

from .constants import (
    CARD_CORNER_RADIUS,
    CARD_HEIGHT,
    CARD_WIDTH,
    COLOR_BG,
    COLOR_CARD_BLACK,
    COLOR_CARD_BORDER,
    COLOR_CARD_FACE,
    COLOR_CARD_RED,
    COLOR_FELT_NOISE,
    COLOR_HEADER,
    COLOR_HINT,
    COLOR_PANEL,
    COLOR_SHADOW,
    COLOR_SLOT,
    COLOR_SLOT_BORDER,
    COLOR_TEXT,
    COLOR_WIN,
    HEADER_HEIGHT,
    SHADOW_ALPHA,
)
from .layout import BoardLayout
from .models import Card, SUIT_SYMBOLS, Suit, is_red
from .state import GameState


class Renderer:
    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen
        self.font_small = pygame.font.SysFont("segoeui", 20)
        self.font_card = pygame.font.SysFont("segoeui", 26, bold=True)
        self.font_title = pygame.font.SysFont("segoeui", 34, bold=True)
        self.font_button = pygame.font.SysFont("segoeui", 22, bold=True)
        self.font_win = pygame.font.SysFont("segoeui", 52, bold=True)
        self.button_icons = self._load_button_icons()

    def _load_button_icons(self) -> dict[str, pygame.Surface]:
        asset_dir = Path(__file__).resolve().parent.parent / "asset"
        icon_files = {
            "New": "new.png",
            "Undo": "undo.png",
            "Hint": "hint.png",
        }
        icons: dict[str, pygame.Surface] = {}
        for key, filename in icon_files.items():
            full_path = asset_dir / filename
            if full_path.exists():
                icons[key] = pygame.image.load(str(full_path)).convert_alpha()
        return icons

    def draw_background(self) -> None:
        self.screen.fill(COLOR_BG)
        # Subtle felt noise for depth.
        for y in range(0, self.screen.get_height(), 16):
            color = COLOR_FELT_NOISE if (y // 16) % 2 == 0 else COLOR_BG
            pygame.draw.line(self.screen, color, (0, y), (self.screen.get_width(), y), 1)

    def draw_header(self, score: int, elapsed: float) -> None:
        """Draw the top title bar: title on left, Score + Time on right."""
        W = self.screen.get_width()
        pygame.draw.rect(self.screen, COLOR_HEADER, (0, 0, W, HEADER_HEIGHT))

        cy = HEADER_HEIGHT // 2

        # Title (left)
        title_surf = self.font_title.render("FreeCell", True, COLOR_TEXT)
        self.screen.blit(title_surf, (14, cy - title_surf.get_height() // 2))

        # Time (right edge)
        mins = int(elapsed) // 60
        secs = int(elapsed) % 60
        time_surf = self.font_title.render(f"Time: {mins:02d}:{secs:02d}", True, COLOR_TEXT)
        time_x = W - time_surf.get_width() - 14
        self.screen.blit(time_surf, (time_x, cy - time_surf.get_height() // 2))

        # Score (left of time)
        score_surf = self.font_title.render(f"Score: {score}", True, COLOR_TEXT)
        score_x = time_x - score_surf.get_width() - 44
        self.screen.blit(score_surf, (score_x, cy - score_surf.get_height() // 2))

    def draw_slot(self, rect: pygame.Rect, label: str = "", highlighted: bool = False) -> None:
        pygame.draw.rect(self.screen, COLOR_SLOT, rect, border_radius=CARD_CORNER_RADIUS)
        border_color = COLOR_HINT if highlighted else COLOR_SLOT_BORDER
        border_width = 4 if highlighted else 2
        pygame.draw.rect(self.screen, border_color, rect, width=border_width, border_radius=CARD_CORNER_RADIUS)
        if label:
            txt = self.font_small.render(label, True, COLOR_TEXT)
            self.screen.blit(txt, txt.get_rect(center=rect.center))

    def draw_card(self, card: Card, x: float, y: float, shadow: bool = True) -> None:
        card_rect = pygame.Rect(round(x), round(y), CARD_WIDTH, CARD_HEIGHT)
        if shadow:
            sh = pygame.Surface((CARD_WIDTH + 8, CARD_HEIGHT + 8), pygame.SRCALPHA)
            pygame.draw.rect(sh, (*COLOR_SHADOW, SHADOW_ALPHA), sh.get_rect(), border_radius=CARD_CORNER_RADIUS + 2)
            self.screen.blit(sh, (card_rect.x + 3, card_rect.y + 4))

        pygame.draw.rect(self.screen, COLOR_CARD_FACE, card_rect, border_radius=CARD_CORNER_RADIUS)
        pygame.draw.rect(self.screen, COLOR_CARD_BORDER, card_rect, width=2, border_radius=CARD_CORNER_RADIUS)

        color = COLOR_CARD_RED if is_red(card.suit) else COLOR_CARD_BLACK
        label = self.font_card.render(card.label, True, color)
        self.screen.blit(label, (card_rect.x + 10, card_rect.y + 8))

        suit = self.font_title.render(card.label[-1], True, color)
        self.screen.blit(suit, (card_rect.right - 35, card_rect.bottom - 42))

    def draw_static_board(
        self,
        layout: BoardLayout,
        state: GameState,
        highlight_targets: set[tuple[str, int]] | None = None,
    ) -> None:
        highlight_targets = highlight_targets or set()
        panel = pygame.Rect(12, 12, self.screen.get_width() - 24, self.screen.get_height() - 24)
        pygame.draw.rect(self.screen, COLOR_PANEL, panel, width=2, border_radius=16)

        # Free cell slots — no label (matches reference image)
        for i, rect in enumerate(layout.free_cells):
            self.draw_slot(rect, highlighted=("freecell", i) in highlight_targets)

        # Foundation slots — show suit symbol
        for i, rect in enumerate(layout.foundations):
            suit = list(Suit)[i]
            self.draw_slot(rect, highlighted=("foundation", i) in highlight_targets)
            suit_color = COLOR_CARD_RED if is_red(suit) else COLOR_TEXT
            suit_txt = self.font_title.render(SUIT_SYMBOLS[suit], True, suit_color)
            self.screen.blit(suit_txt, suit_txt.get_rect(center=rect.center))

        for i, rect in enumerate(layout.tableau):
            self.draw_slot(rect, highlighted=("tableau", i) in highlight_targets)

    def draw_action_buttons(
        self,
        buttons: list[tuple[str, pygame.Rect]],
        pressed: str = "",
    ) -> None:
        for label, rect in buttons:
            is_pressed = label == pressed

            # Slight Y lift when pressed (button "rises" toward user)
            draw_rect = rect.move(0, -3 if is_pressed else 0)

            # Background — brighter when pressed
            overlay = pygame.Surface((draw_rect.width, draw_rect.height), pygame.SRCALPHA)
            if is_pressed:
                pygame.draw.rect(overlay, (80, 80, 80, 210), overlay.get_rect(), border_radius=10)
            else:
                pygame.draw.rect(overlay, (0, 0, 0, 170), overlay.get_rect(), border_radius=10)
            self.screen.blit(overlay, draw_rect.topleft)

            # Border — glowing white when pressed
            border_color = (200, 200, 200) if is_pressed else (70, 70, 70)
            pygame.draw.rect(self.screen, border_color, draw_rect, width=2, border_radius=10)

            # Optional icon (New / Undo / Hint)
            icon = self.button_icons.get(label)
            icon_w = 0
            if icon is not None:
                icon_size = draw_rect.height - 14
                scaled = pygame.transform.smoothscale(icon, (icon_size, icon_size))
                icon_w = icon_size + 6

            # Measure text to compute center
            txt = self.font_button.render(label, True, (235, 244, 235))
            total_w = icon_w + txt.get_width()
            start_x = draw_rect.x + (draw_rect.width - total_w) // 2

            # Draw icon
            if icon is not None:
                icon_rect = scaled.get_rect()
                icon_rect.centery = draw_rect.centery
                icon_rect.x = start_x
                self.screen.blit(scaled, icon_rect)

            # Draw text centered
            txt_rect = txt.get_rect()
            txt_rect.centery = draw_rect.centery
            txt_rect.x = start_x + icon_w
            self.screen.blit(txt, txt_rect)

    def draw_state_cards(
        self,
        layout: BoardLayout,
        state: GameState,
        hidden_tableau: tuple[int, int] | None = None,
        hidden_freecell: int | None = None,
        hidden_foundation: int | None = None,
        hidden_cards: set[Card] | None = None,
    ) -> None:
        hidden_cards = hidden_cards or set()
        for i, card in enumerate(state.free_cells):
            if card is None:
                continue
            if hidden_freecell == i:
                continue
            if card in hidden_cards:
                continue
            rect = layout.free_cells[i]
            self.draw_card(card, rect.x, rect.y)

        for i, suit in enumerate(Suit):
            if hidden_foundation == i:
                continue
            pile = state.foundations[suit]
            if pile:
                if pile[-1] in hidden_cards:
                    continue
                rect = layout.foundations[i]
                self.draw_card(pile[-1], rect.x, rect.y)

        for col_idx, col in enumerate(state.tableau):
            hidden_from = -1
            if hidden_tableau and hidden_tableau[0] == col_idx:
                hidden_from = hidden_tableau[1]
            for row_idx, card in enumerate(col):
                if hidden_from >= 0 and row_idx >= hidden_from:
                    continue
                if card in hidden_cards:
                    continue
                rect = layout.card_rect_in_tableau(col_idx, row_idx)
                self.draw_card(card, rect.x, rect.y)

    def draw_win_overlay(self) -> None:
        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 120))
        self.screen.blit(overlay, (0, 0))
        txt = self.font_win.render("YOU WIN!", True, COLOR_WIN)
        sub = self.font_title.render("Press R for a new deal", True, COLOR_TEXT)
        self.screen.blit(txt, txt.get_rect(center=(self.screen.get_width() // 2, self.screen.get_height() // 2 - 24)))
        self.screen.blit(sub, sub.get_rect(center=(self.screen.get_width() // 2, self.screen.get_height() // 2 + 24)))
