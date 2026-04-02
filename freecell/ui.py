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
    COLOR_FREECELL_BORDER,
    COLOR_FOUNDATION_BORDER,
    COLOR_FOUNDATION_ICON,
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
            "NEW GAME": "new.png",
            "UNDO": "undo.png",
            "HINT": "hint.png",
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

    def draw_header(self, score: int, elapsed: float, moves: int) -> None:
        """Draw the top title bar: title on left, Score + Time on right."""
        W = self.screen.get_width()
        pygame.draw.rect(self.screen, COLOR_HEADER, (0, 0, W, HEADER_HEIGHT))

        cy = HEADER_HEIGHT // 2

        mins = int(elapsed) // 60
        secs = int(elapsed) % 60
        info_txt = f"Score: {score}    Moves: {moves}    Time: {mins:02d}:{secs:02d}"
        info_surf = self.font_button.render(info_txt, True, (200, 220, 210))
        self.screen.blit(info_surf, (24, cy - info_surf.get_height() // 2))

        title_surf = self.font_title.render("FREECELL", True, COLOR_TEXT)
        title_rect = title_surf.get_rect(center=(W // 2, cy - 10))
        self.screen.blit(title_surf, title_rect)
        
        subtitle = self.font_button.render("MODERN", True, (180, 190, 200))
        sub_rect = subtitle.get_rect(center=(W // 2, cy + 18))
        self.screen.blit(subtitle, sub_rect)

    def draw_slot(self, rect: pygame.Rect, label: str = "", highlighted: bool = False) -> None:
        pass # Now handled natively inside draw_static_board using specific logic per cell type

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

        for i, rect in enumerate(layout.free_cells):
            highlighted = ("freecell", i) in highlight_targets
            overlay = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            pygame.draw.rect(overlay, (20, 30, 40, 100), overlay.get_rect(), border_radius=CARD_CORNER_RADIUS)
            self.screen.blit(overlay, rect.topleft)
            border_c = COLOR_HINT if highlighted else COLOR_FREECELL_BORDER
            border_w = 4 if highlighted else 2
            pygame.draw.rect(self.screen, border_c, rect, width=border_w, border_radius=CARD_CORNER_RADIUS)

        for i, rect in enumerate(layout.foundations):
            highlighted = ("foundation", i) in highlight_targets
            overlay = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            pygame.draw.rect(overlay, (15, 20, 25, 200), overlay.get_rect(), border_radius=CARD_CORNER_RADIUS)
            self.screen.blit(overlay, rect.topleft)
            border_c = COLOR_HINT if highlighted else COLOR_FOUNDATION_BORDER
            border_w = 4 if highlighted else 2
            pygame.draw.rect(self.screen, border_c, rect, width=border_w, border_radius=CARD_CORNER_RADIUS)

            suit = list(Suit)[i]
            suit_txt = self.font_title.render(SUIT_SYMBOLS[suit], True, COLOR_FOUNDATION_ICON)
            self.screen.blit(suit_txt, suit_txt.get_rect(center=rect.center))

        for i, base_rect in enumerate(layout.tableau):
            highlighted = ("tableau", i) in highlight_targets
            
            overlay = pygame.Surface((base_rect.width, base_rect.height), pygame.SRCALPHA)
            pygame.draw.rect(overlay, (20, 30, 40, 100), overlay.get_rect(), border_radius=CARD_CORNER_RADIUS)
            self.screen.blit(overlay, base_rect.topleft)
            
            border_c = COLOR_HINT if highlighted else COLOR_FREECELL_BORDER
            border_w = 4 if highlighted else 2
            pygame.draw.rect(self.screen, border_c, base_rect, width=border_w, border_radius=CARD_CORNER_RADIUS)

    def draw_action_buttons(
        self,
        buttons: list[tuple[str, pygame.Rect]],
        pressed: str = "",
    ) -> None:
        mouse_pos = pygame.mouse.get_pos()
        for label, rect in buttons:
            is_pressed = label == pressed
            is_hover = rect.collidepoint(mouse_pos)

            # Slight Y lift when hovered or pressed
            dy = 0
            if is_pressed:
                dy = 1   # Sink in when pressed
            elif is_hover:
                dy = -2  # Lift slightly when hovered
            draw_rect = rect.move(0, dy)

            # Background — brighter when hovered or pressed
            overlay = pygame.Surface((draw_rect.width, draw_rect.height), pygame.SRCALPHA)
            if is_pressed:
                pygame.draw.rect(overlay, (100, 100, 100, 220), overlay.get_rect(), border_radius=10)
            elif is_hover:
                pygame.draw.rect(overlay, (80, 80, 80, 200), overlay.get_rect(), border_radius=10)
            else:
                pygame.draw.rect(overlay, (20, 25, 30, 170), overlay.get_rect(), border_radius=10)
            self.screen.blit(overlay, draw_rect.topleft)

            # Border — glowing white when pressed/hovered
            border_color = (255, 255, 255) if is_pressed else ((200, 200, 200) if is_hover else (70, 70, 70))
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
