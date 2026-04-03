"""Rendering code for board, cards, and overlays."""

from __future__ import annotations

from pathlib import Path

import pygame

from .constants import (
    BACKGROUND_USE_IMAGE,
    CARD_CORNER_RADIUS,
    CARD_FACE_ART_INSET,
    CARD_FACE_OUTLINE_COLOR,
    CARD_FACE_OUTLINE_WIDTH,
    CARD_HEIGHT,
    CARD_WIDTH,
    COLOR_BG,
    COLOR_CARD_BLACK,
    COLOR_CARD_FACE,
    COLOR_CARD_RED,
    COLOR_FELT_BEVEL_HIGHLIGHT,
    COLOR_FELT_BEVEL_SHADOW,
    COLOR_FELT_SLOT_FACE,
    COLOR_GAME_OVER,
    COLOR_HINT_GLOW,
    FOOTER_BG,
    FOOTER_BEVEL_DK,
    FOOTER_BEVEL_LT,
    FOOTER_INNER_MARGIN,
    FOOTER_PANEL_FACE,
    FOOTER_PANEL_GAP,
    FOOTER_PANEL_PAD_X,
    FOOTER_TEXT,
    COLOR_SHADOW,
    COLOR_STRIPE,
    COLOR_STRIPE_ALPHA,
    COLOR_STRIPE_SPACING,
    COLOR_STRIPE_WIDTH,
    COLOR_SLOT_TARGET_RING,
    COLOR_TEXT,
    COLOR_WIN,
    FOOTER_HEIGHT,
    FOOTER_INFO_FONT_SIZE,
    SHADOW_ALPHA,
    SHADOW_ALPHA_SOFT,
    CARD_SHADOW_OFFSET,
    CARD_SHADOW_SCALE_OUTER,
    CARD_SHADOW_SCALE_INNER,
    CARD_BEVEL_HI_ALPHA,
    CARD_BEVEL_LO_ALPHA,
    SOLVER_AUTOSOLVE_TIMEOUT_S,
    SOLVER_BTN_ACCENTS,
    NEW_GAME_LEVEL_RANGES,
    # Menu constants
    MENU_BTN_MARGIN,
    MENU_DROPUP_WIDTH,
    MENU_DROPUP_ROW_H,
    MENU_DROPUP_PAD,
    MENU_DROPUP_GAP,
    MENU_DROPUP_RADIUS,
    MENU_SUBMENU_WIDTH,
    MENU_SUBMENU_ROW_H,
    MENU_SUBMENU_PAD,
    MENU_SUBMENU_GAP,
    MENU_SUBMENU_RADIUS,
    MENU_SUB2_CELL_W,
    MENU_SUB2_ROW_H,
    MENU_ITEMS,
    MENU_ITEMS_WITH_SUBMENU,
    MENU_GLYPHS,
    SOLVE_ALGO_ORDER,
    MENU_BG,
    MENU_BORDER,
    MENU_TEXT_COLOR,
    MENU_TEXT_HOVER,
    MENU_HOVER_FACE,
    MENU_ARROW,
)
from .layout import BoardLayout
from .models import Card, SUIT_SYMBOLS, Suit, is_red
from .state import GameState


def _lerp_color(
    a: tuple[int, int, int], b: tuple[int, int, int], t: float
) -> tuple[int, int, int]:
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


# ── Menu geometry helpers (used by game.py too) ────────────────────────────────


def menu_button_rect(screen_w: int, screen_h: int) -> pygame.Rect:
    """Rect of the ☰ button sitting inside the footer bar."""
    btn_size = FOOTER_HEIGHT - 2 * MENU_BTN_MARGIN
    return pygame.Rect(
        screen_w - MENU_BTN_MARGIN - btn_size,
        screen_h - FOOTER_HEIGHT + MENU_BTN_MARGIN,
        btn_size,
        btn_size,
    )


def dropup_layout(
    screen_w: int, screen_h: int
) -> tuple[pygame.Rect, dict[str, pygame.Rect]]:
    """Outer rect + per-item rects for the main dropup, anchored above ☰."""
    btn = menu_button_rect(screen_w, screen_h)
    n = len(MENU_ITEMS)
    menu_h = n * MENU_DROPUP_ROW_H + 2 * MENU_DROPUP_PAD
    menu_w = MENU_DROPUP_WIDTH
    x = btn.right - menu_w
    y = btn.top - MENU_DROPUP_GAP - menu_h
    outer = pygame.Rect(x, y, menu_w, menu_h)
    rects: dict[str, pygame.Rect] = {}
    iy = y + MENU_DROPUP_PAD
    for item in MENU_ITEMS:
        rects[item] = pygame.Rect(x + 3, iy, menu_w - 6, MENU_DROPUP_ROW_H)
        iy += MENU_DROPUP_ROW_H
    return outer, rects


def submenu_layout(
    parent_rect: pygame.Rect,
    items: list[str],
    width: int = MENU_SUBMENU_WIDTH,
    row_h: int = MENU_SUBMENU_ROW_H,
    pad: int = MENU_SUBMENU_PAD,
    screen_h: int = 0,
) -> tuple[pygame.Rect, dict[str, pygame.Rect]]:
    """Flyout-left submenu anchored to *parent_rect*, clamped to screen."""
    n = len(items)
    sub_h = n * row_h + 2 * pad
    x = parent_rect.left - MENU_SUBMENU_GAP - width
    y = parent_rect.top
    # Clamp so submenu doesn't go below window
    if screen_h > 0 and y + sub_h > screen_h:
        y = max(0, screen_h - sub_h)
    outer = pygame.Rect(x, y, width, sub_h)
    rects: dict[str, pygame.Rect] = {}
    iy = y + pad
    for item in items:
        rects[item] = pygame.Rect(x + 3, iy, width - 6, row_h)
        iy += row_h
    return outer, rects


def sub2_layout(
    parent_rect: pygame.Rect,
    items: list[str],
    screen_h: int = 0,
) -> tuple[pygame.Rect, dict[str, pygame.Rect]]:
    """Level-number flyout (narrower cells)."""
    return submenu_layout(
        parent_rect,
        items,
        MENU_SUB2_CELL_W,
        MENU_SUB2_ROW_H,
        MENU_SUBMENU_PAD,
        screen_h,
    )


# ── Renderer ───────────────────────────────────────────────────────────────────


class Renderer:
    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen
        self.font_small = pygame.font.SysFont("segoeui", 20)
        self.font_card = pygame.font.SysFont("segoeui", 26, bold=True)
        self.font_title = pygame.font.SysFont("segoeui", 34, bold=True)
        self.font_foundation_suit = pygame.font.SysFont("segoeui", 56, bold=True)
        self.font_button = pygame.font.SysFont("segoeui", 22, bold=True)
        self.font_footer_info = pygame.font.SysFont("Tahoma", FOOTER_INFO_FONT_SIZE)
        self.font_win = pygame.font.SysFont("segoeui", 52, bold=True)
        self.font_menu_glyph = pygame.font.SysFont("segoe ui symbol", 15)
        self.font_menu_item = pygame.font.SysFont("Tahoma", 14)
        self.card_images = self._load_card_images()
        self.bg_image_orig = self._load_bg_image()
        self.bg_image_scaled = None
        self.last_screen_size = (0, 0)
        self.loading_frames = self._load_gif_frames("loading.gif")

    # ── asset loading ──────────────────────────────────────────────────────

    def _load_bg_image(self) -> pygame.Surface | None:
        full_path = Path(__file__).resolve().parent.parent / "asset" / "background.jpg"
        if full_path.exists():
            return pygame.image.load(str(full_path)).convert()
        return None

    def _load_gif_frames(self, filename: str) -> list[pygame.Surface]:
        full_path = Path(__file__).resolve().parent.parent / "asset" / filename
        frames = []
        if full_path.exists():
            try:
                from PIL import Image

                img = Image.open(str(full_path))
                for frame in range(img.n_frames):
                    img.seek(frame)
                    frame_rgba = img.convert("RGBA")
                    raw_str = frame_rgba.tobytes("raw", "RGBA")
                    surf = pygame.image.frombuffer(raw_str, frame_rgba.size, "RGBA")

                    # scale down to fit footer
                    orig_w, orig_h = surf.get_size()
                    target_h = FOOTER_HEIGHT - 4
                    if orig_h > 0:
                        target_w = int(orig_w * (target_h / orig_h))
                        surf = pygame.transform.smoothscale(
                            surf, (max(1, target_w), max(1, target_h))
                        )
                    frames.append(surf)
            except Exception as e:
                print(f"Failed to load GIF frames: {e}")
        return frames

    def _load_card_images(self) -> dict[Card, pygame.Surface]:
        asset_dir = Path(__file__).resolve().parent.parent / "asset" / "card"
        suit_names = {
            Suit.CLUBS: "clubs",
            Suit.DIAMONDS: "diamonds",
            Suit.HEARTS: "hearts",
            Suit.SPADES: "spades",
        }
        images: dict[Card, pygame.Surface] = {}
        for suit in Suit:
            for rank in range(1, 14):
                card = Card(suit=suit, rank=rank)
                filename = f"{rank}_of_{suit_names[suit]}.png"
                full_path = asset_dir / filename
                if full_path.exists():
                    img = pygame.image.load(str(full_path)).convert_alpha()
                    images[card] = self._compose_card_face_from_png(img)
        return images

    def _compose_card_face_from_png(self, img: pygame.Surface) -> pygame.Surface:
        pad = CARD_FACE_ART_INSET
        inner_w = max(1, CARD_WIDTH - 2 * pad)
        inner_h = max(1, CARD_HEIGHT - 2 * pad)
        scaled = pygame.transform.smoothscale(img, (inner_w, inner_h))
        canvas = pygame.Surface((CARD_WIDTH, CARD_HEIGHT), pygame.SRCALPHA)
        canvas.fill((255, 255, 255, 255))
        canvas.blit(scaled, (pad, pad))
        return self._clip_rounded_surface(canvas, CARD_CORNER_RADIUS)

    def _clip_rounded_surface(
        self, surf: pygame.Surface, border_radius: int
    ) -> pygame.Surface:
        w, h = surf.get_size()
        rounded = pygame.Surface((w, h), pygame.SRCALPHA)
        rounded.blit(surf, (0, 0))
        mask = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(
            mask, (255, 255, 255, 255), mask.get_rect(), border_radius=border_radius
        )
        rounded.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        return rounded

    # ── background / textures ──────────────────────────────────────────────

    def _draw_diagonal_stripes(self, target: pygame.Surface) -> None:
        if COLOR_STRIPE_ALPHA <= 0:
            return
        w, h = target.get_size()
        overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        c = (*COLOR_STRIPE[:3], COLOR_STRIPE_ALPHA)
        stride = COLOR_STRIPE_SPACING
        thick = COLOR_STRIPE_WIDTH
        for i in range(-2 * h, 2 * w, stride):
            pygame.draw.line(overlay, c, (i, 0), (i + int(h * 0.62), h), thick)
        target.blit(overlay, (0, 0))

    def draw_background(self) -> None:
        self.screen.fill(COLOR_BG)
        if BACKGROUND_USE_IMAGE and self.bg_image_orig:
            curr_size = self.screen.get_size()
            if self.last_screen_size != curr_size:
                self.bg_image_scaled = pygame.transform.smoothscale(
                    self.bg_image_orig, curr_size
                )
                self.last_screen_size = curr_size
            if self.bg_image_scaled:
                dim = pygame.Surface(curr_size, pygame.SRCALPHA)
                dim.fill((12, 18, 32, 210))
                self.screen.blit(self.bg_image_scaled, (0, 0))
                self.screen.blit(dim, (0, 0))
        self._draw_diagonal_stripes(self.screen)

    # ── card shadows / bevels ──────────────────────────────────────────────

    def _draw_soft_card_shadow(self, card_rect: pygame.Rect) -> None:
        ox, oy = CARD_SHADOW_OFFSET, CARD_SHADOW_OFFSET + 1
        for scale, alpha in (
            (CARD_SHADOW_SCALE_OUTER, SHADOW_ALPHA_SOFT),
            (CARD_SHADOW_SCALE_INNER, SHADOW_ALPHA),
        ):
            sw = int(CARD_WIDTH * scale) + 4
            sh = int(CARD_HEIGHT * scale) + 4
            layer = pygame.Surface((sw, sh), pygame.SRCALPHA)
            pygame.draw.rect(
                layer,
                (*COLOR_SHADOW, alpha),
                layer.get_rect(),
                border_radius=CARD_CORNER_RADIUS + 2,
            )
            lx = card_rect.x - (sw - CARD_WIDTH) // 2 + ox
            ly = card_rect.y - (sh - CARD_HEIGHT) // 2 + oy
            self.screen.blit(layer, (lx, ly))

    def _draw_card_bevel(self, card_rect: pygame.Rect) -> None:
        w, h = CARD_WIDTH, CARD_HEIGHT
        r = CARD_CORNER_RADIUS
        gr = max(2, r - 2)
        ov = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(
            ov,
            (255, 255, 255, CARD_BEVEL_HI_ALPHA),
            pygame.Rect(2, 2, w - 4, max(7, h // 4 + 2)),
            border_radius=gr,
        )
        shade = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(
            shade,
            (0, 0, 0, CARD_BEVEL_LO_ALPHA),
            pygame.Rect(2, h * 11 // 20, w - 4, h // 2 - 2),
            border_radius=gr,
        )
        ov.blit(shade, (0, 0))
        mask = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=r)
        ov.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        self.screen.blit(ov, card_rect.topleft)

    # ── generic bevel face (green, used for menu items) ────────────────────

    def _menu_inner_face(
        self, w: int, h: int, radius: int, is_pressed: bool, is_hover: bool
    ) -> pygame.Surface:
        body = pygame.Surface((w, h), pygame.SRCALPHA)
        steps = max(6, h // 3)
        for s in range(steps):
            t = s / max(steps - 1, 1)
            if is_pressed:
                top, bot = (52, 118, 64), (30, 80, 40)
            elif is_hover:
                top, bot = (78, 158, 92), (52, 118, 64)
            else:
                top, bot = (62, 138, 76), (40, 98, 50)
            c = _lerp_color(bot, top, t)
            y0 = int(s * h / steps)
            y1 = int((s + 1) * h / steps)
            pygame.draw.rect(body, (*c, 255), pygame.Rect(0, y0, w, max(1, y1 - y0)))
        gloss = pygame.Surface((w, h), pygame.SRCALPHA)
        gr = max(2, radius - 2)
        pygame.draw.rect(
            gloss,
            (255, 255, 255, 40),
            pygame.Rect(2, 2, w - 4, max(5, h // 3)),
            border_radius=gr,
        )
        body.blit(gloss, (0, 0))
        mask = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(
            mask, (255, 255, 255, 255), mask.get_rect(), border_radius=radius
        )
        body.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        return body

    # ── felt slots ─────────────────────────────────────────────────────────

    def _draw_sunken_felt_slot(
        self, rect: pygame.Rect, *, highlighted: bool = False
    ) -> None:
        w, h = rect.size
        r = min(CARD_CORNER_RADIUS, min(w, h) // 2)
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(
            surf, (*COLOR_FELT_SLOT_FACE, 255), surf.get_rect(), border_radius=r
        )
        dk = COLOR_FELT_BEVEL_SHADOW
        lt = COLOR_FELT_BEVEL_HIGHLIGHT
        ln = 2
        pygame.draw.line(surf, dk, (r, 2), (w - r, 2), ln)
        pygame.draw.line(surf, dk, (2, r), (2, h - r), ln)
        pygame.draw.line(surf, lt, (r, h - 3), (w - r, h - 3), ln)
        pygame.draw.line(surf, lt, (w - 3, r), (w - 3, h - r), ln)
        self.screen.blit(surf, rect.topleft)
        if highlighted:
            pygame.draw.rect(
                self.screen, COLOR_SLOT_TARGET_RING, rect, width=3, border_radius=r
            )

    def draw_slot(
        self, rect: pygame.Rect, label: str = "", highlighted: bool = False
    ) -> None:
        pass

    # ── cards ──────────────────────────────────────────────────────────────

    def draw_card(self, card: Card, x: float, y: float, shadow: bool = True) -> None:
        card_rect = pygame.Rect(round(x), round(y), CARD_WIDTH, CARD_HEIGHT)
        if shadow:
            self._draw_soft_card_shadow(card_rect)
        if card in self.card_images:
            self.screen.blit(self.card_images[card], card_rect)
        else:
            pygame.draw.rect(
                self.screen,
                COLOR_CARD_FACE,
                card_rect,
                border_radius=CARD_CORNER_RADIUS,
            )
            color = COLOR_CARD_RED if is_red(card.suit) else COLOR_CARD_BLACK
            label = self.font_card.render(card.label, True, color)
            self.screen.blit(label, (card_rect.x + 10, card_rect.y + 8))
            suit_surf = self.font_title.render(card.label[-1], True, color)
            self.screen.blit(suit_surf, (card_rect.right - 35, card_rect.bottom - 42))
        self._draw_card_bevel(card_rect)
        pygame.draw.rect(
            self.screen,
            CARD_FACE_OUTLINE_COLOR,
            card_rect,
            width=CARD_FACE_OUTLINE_WIDTH,
            border_radius=CARD_CORNER_RADIUS,
        )

    # ── static board (slots) ──────────────────────────────────────────────

    def draw_static_board(
        self,
        layout: BoardLayout,
        state: GameState,
        highlight_targets: set[tuple[str, int]] | None = None,
    ) -> None:
        highlight_targets = highlight_targets or set()
        for i, rect in enumerate(layout.free_cells):
            highlighted = ("freecell", i) in highlight_targets
            self._draw_sunken_felt_slot(rect, highlighted=highlighted)
        for i, rect in enumerate(layout.foundations):
            highlighted = ("foundation", i) in highlight_targets
            self._draw_sunken_felt_slot(rect, highlighted=highlighted)
            suit = list(Suit)[i]
            if not state.foundations[suit]:
                sym = SUIT_SYMBOLS[suit]
                if is_red(suit):
                    lo_c = (
                        max(0, COLOR_CARD_RED[0] - 50),
                        max(0, COLOR_CARD_RED[1] - 8),
                        max(0, COLOR_CARD_RED[2] - 8),
                    )
                    hi_c = COLOR_CARD_RED
                else:
                    lo_c = (6, 7, 9)
                    hi_c = COLOR_CARD_BLACK
                lo = self.font_foundation_suit.render(sym, True, lo_c)
                hi = self.font_foundation_suit.render(sym, True, hi_c)
                cx, cy = rect.center
                self.screen.blit(lo, lo.get_rect(center=(cx + 2, cy + 3)))
                self.screen.blit(hi, hi.get_rect(center=(cx, cy)))

    # ── state cards ────────────────────────────────────────────────────────

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
            if card is None or hidden_freecell == i or card in hidden_cards:
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

    # ── footer bar ─────────────────────────────────────────────────────────

    def _draw_footer_inset_cell(self, rect: pygame.Rect) -> None:
        pygame.draw.rect(self.screen, FOOTER_PANEL_FACE, rect)
        x, y, w, h = rect
        pygame.draw.line(self.screen, FOOTER_BEVEL_DK, (x, y), (x + w - 1, y), 1)
        pygame.draw.line(self.screen, FOOTER_BEVEL_DK, (x, y), (x, y + h - 1), 1)
        pygame.draw.line(
            self.screen, FOOTER_BEVEL_LT, (x, y + h - 1), (x + w - 1, y + h - 1), 1
        )
        pygame.draw.line(
            self.screen, FOOTER_BEVEL_LT, (x + w - 1, y), (x + w - 1, y + h - 1), 1
        )

    def _draw_footer_raised_button(
        self, rect: pygame.Rect, is_hover: bool, is_active: bool
    ) -> None:
        """Classic bevel button (raised normally, sunken when active)."""
        x, y, w, h = rect
        if is_active:
            face = (210, 206, 197)
            tl, br = FOOTER_BEVEL_DK, FOOTER_BEVEL_LT
        elif is_hover:
            face = (250, 247, 240)
            tl, br = FOOTER_BEVEL_LT, FOOTER_BEVEL_DK
        else:
            face = FOOTER_PANEL_FACE
            tl, br = FOOTER_BEVEL_LT, FOOTER_BEVEL_DK
        pygame.draw.rect(self.screen, face, rect)
        pygame.draw.line(self.screen, tl, (x, y), (x + w - 1, y), 1)
        pygame.draw.line(self.screen, tl, (x, y), (x, y + h - 1), 1)
        pygame.draw.line(self.screen, br, (x, y + h - 1), (x + w - 1, y + h - 1), 1)
        pygame.draw.line(self.screen, br, (x + w - 1, y), (x + w - 1, y + h - 1), 1)

    def draw_footer_bar(
        self,
        score: int,
        elapsed: float,
        moves: int,
        foundation_cards: int,
        deal_label: str,
        freecells_occupied: int,
        menu_btn_hover: bool = False,
        menu_is_open: bool = False,
        solver_anim_time: float = -1.0,
    ) -> None:
        w, h = self.screen.get_size()
        bar_top = h - FOOTER_HEIGHT
        pygame.draw.rect(self.screen, FOOTER_BG, (0, bar_top, w, FOOTER_HEIGHT))

        mins = int(elapsed) // 60
        secs = int(elapsed) % 60
        labels = [
            f"{mins}:{secs:02d}",
            f"{foundation_cards}/52",
            f"{freecells_occupied}/4 \u00b7 {moves} \u00b7 {score}",
            deal_label,
        ]

        inner = FOOTER_INNER_MARGIN
        gap = FOOTER_PANEL_GAP
        pad_x = FOOTER_PANEL_PAD_X
        row_h = FOOTER_HEIGHT - 2 * inner
        y_cell = bar_top + inner

        # Reserve space for menu button
        btn_size = FOOTER_HEIGHT - 2 * MENU_BTN_MARGIN
        btn_area = btn_size + MENU_BTN_MARGIN + gap
        x = inner

        max_text_w = w - inner - btn_area - gap * 3
        surfaces = [self.font_footer_info.render(s, True, FOOTER_TEXT) for s in labels]
        natural = sum(su.get_width() + 2 * pad_x for su in surfaces)
        stretch_id = 3  # deal_label stretches
        extra = max(0, max_text_w - natural)
        widths: list[int] = []
        for i, su in enumerate(surfaces):
            cell_w = su.get_width() + 2 * pad_x
            if i == stretch_id:
                cell_w += extra
            widths.append(cell_w)

        for i, su in enumerate(surfaces):
            cw = widths[i]
            cell = pygame.Rect(x, y_cell, cw, row_h)
            self._draw_footer_inset_cell(cell)
            tx = x + pad_x + (cw - 2 * pad_x - su.get_width()) // 2
            ty = bar_top + (FOOTER_HEIGHT - su.get_height()) // 2
            self.screen.blit(su, (tx, ty))
            x += cw + gap

        # ☰ menu button
        btn_rect = menu_button_rect(w, h)
        self._draw_footer_raised_button(btn_rect, menu_btn_hover, menu_is_open)
        # Draw three horizontal lines (hamburger icon)
        lc = (30, 30, 30) if menu_btn_hover or menu_is_open else FOOTER_TEXT
        cx, cy = btn_rect.center
        half = btn_size // 3
        for dy in [-4, 0, 4]:
            pygame.draw.line(
                self.screen, lc, (cx - half, cy + dy), (cx + half, cy + dy), 2
            )

        # Draw walking loading gif over footer if solving
        if solver_anim_time >= 0.0 and self.loading_frames:
            duration = 4.0
            progress = (solver_anim_time % duration) / duration

            frame_idx = int(solver_anim_time * 10) % len(self.loading_frames)
            frame_surf = self.loading_frames[frame_idx]
            frame_w, frame_h = frame_surf.get_size()

            anim_x = int(progress * (w + frame_w)) - frame_w
            # Walk ON TOP of the footer bar, not inside it
            anim_y = bar_top - frame_h

            self.screen.blit(frame_surf, (anim_x, anim_y))

    # ── dropup menu ────────────────────────────────────────────────────────

    def draw_dropup(
        self,
        outer: pygame.Rect,
        item_rects: dict[str, pygame.Rect],
        hover_item: str | None,
    ) -> None:
        # Shadow
        sh = pygame.Surface((outer.w + 6, outer.h + 6), pygame.SRCALPHA)
        pygame.draw.rect(
            sh, (0, 0, 0, 50), sh.get_rect(), border_radius=MENU_DROPUP_RADIUS + 2
        )
        self.screen.blit(sh, (outer.x - 2, outer.y + 3))
        # Background
        bg = pygame.Surface(outer.size, pygame.SRCALPHA)
        bg.fill(MENU_BG)
        pygame.draw.rect(
            bg, MENU_BORDER, bg.get_rect(), width=1, border_radius=MENU_DROPUP_RADIUS
        )
        self.screen.blit(bg, outer.topleft)
        # Items
        for key in MENU_ITEMS:
            rect = item_rects[key]
            is_h = hover_item == key
            has_sub = key in MENU_ITEMS_WITH_SUBMENU
            self._draw_dropup_item(rect, key, is_h, has_sub)

    def _draw_dropup_item(
        self, rect: pygame.Rect, label: str, is_hover: bool, has_submenu: bool
    ) -> None:
        r = min(5, rect.h // 2)
        if is_hover:
            pygame.draw.rect(self.screen, MENU_HOVER_FACE, rect, border_radius=r)
            # Raised bevel
            pygame.draw.line(
                self.screen,
                FOOTER_BEVEL_LT,
                (rect.x, rect.y),
                (rect.right - 1, rect.y),
                1,
            )
            pygame.draw.line(
                self.screen,
                FOOTER_BEVEL_LT,
                (rect.x, rect.y),
                (rect.x, rect.bottom - 1),
                1,
            )
            pygame.draw.line(
                self.screen,
                FOOTER_BEVEL_DK,
                (rect.x, rect.bottom - 1),
                (rect.right - 1, rect.bottom - 1),
                1,
            )
            pygame.draw.line(
                self.screen,
                FOOTER_BEVEL_DK,
                (rect.right - 1, rect.y),
                (rect.right - 1, rect.bottom - 1),
                1,
            )
        tc = MENU_TEXT_HOVER if is_hover else MENU_TEXT_COLOR
        # Glyph
        glyph = MENU_GLYPHS.get(label, "")
        if glyph:
            gs = self.font_menu_glyph.render(glyph, True, tc)
            self.screen.blit(gs, (rect.x + 10, rect.centery - gs.get_height() // 2))
        # Text
        display = label.title()
        if label == "NEW GAME":
            display = "New Game"
        ts = self.font_menu_item.render(display, True, tc)
        self.screen.blit(ts, (rect.x + 32, rect.centery - ts.get_height() // 2))
        # Arrow
        if has_submenu:
            ar = self.font_menu_item.render(MENU_ARROW, True, tc)
            self.screen.blit(ar, (rect.right - 20, rect.centery - ar.get_height() // 2))

    # ── generic submenu panel ──────────────────────────────────────────────

    def draw_submenu(
        self,
        outer: pygame.Rect,
        items: list[tuple[str, str]],
        item_rects: dict[str, pygame.Rect],
        hover_item: str | None,
        has_sub: bool = False,
        accent_map: dict[str, tuple[int, int, int]] | None = None,
    ) -> None:
        # Shadow
        sh = pygame.Surface((outer.w + 4, outer.h + 4), pygame.SRCALPHA)
        pygame.draw.rect(
            sh, (0, 0, 0, 40), sh.get_rect(), border_radius=MENU_SUBMENU_RADIUS + 2
        )
        self.screen.blit(sh, (outer.x - 1, outer.y + 2))
        # Background
        bg = pygame.Surface(outer.size, pygame.SRCALPHA)
        bg.fill(MENU_BG)
        pygame.draw.rect(
            bg, MENU_BORDER, bg.get_rect(), width=1, border_radius=MENU_SUBMENU_RADIUS
        )
        self.screen.blit(bg, outer.topleft)
        # Items
        for key, display in items:
            rect = item_rects[key]
            is_h = hover_item == key
            r = min(4, rect.h // 2)
            if is_h:
                pygame.draw.rect(self.screen, MENU_HOVER_FACE, rect, border_radius=r)
                pygame.draw.line(
                    self.screen,
                    FOOTER_BEVEL_LT,
                    (rect.x, rect.y),
                    (rect.right - 1, rect.y),
                    1,
                )
                pygame.draw.line(
                    self.screen,
                    FOOTER_BEVEL_LT,
                    (rect.x, rect.y),
                    (rect.x, rect.bottom - 1),
                    1,
                )
                pygame.draw.line(
                    self.screen,
                    FOOTER_BEVEL_DK,
                    (rect.x, rect.bottom - 1),
                    (rect.right - 1, rect.bottom - 1),
                    1,
                )
                pygame.draw.line(
                    self.screen,
                    FOOTER_BEVEL_DK,
                    (rect.right - 1, rect.y),
                    (rect.right - 1, rect.bottom - 1),
                    1,
                )
            tc = MENU_TEXT_HOVER if is_h else MENU_TEXT_COLOR
            # Accent strip (for solver algorithms)
            if accent_map and key in accent_map:
                strip = pygame.Rect(rect.left + 3, rect.top + 5, 3, rect.height - 10)
                pygame.draw.rect(self.screen, accent_map[key], strip, border_radius=1)
            ts = self.font_menu_item.render(display, True, tc)
            tx = rect.x + (14 if accent_map else 10)
            self.screen.blit(ts, (tx, rect.centery - ts.get_height() // 2))
            if has_sub:
                ar = self.font_menu_item.render(MENU_ARROW, True, tc)
                self.screen.blit(
                    ar, (rect.right - 18, rect.centery - ar.get_height() // 2)
                )

    # ── overlays ───────────────────────────────────────────────────────────

    def draw_pause_overlay(self) -> None:
        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 110))
        self.screen.blit(overlay, (0, 0))
        title = self.font_win.render("PAUSED", True, COLOR_TEXT)
        sub = self.font_title.render("Nhan MENU hoac P de tiep tuc", True, COLOR_TEXT)
        cx, cy = self.screen.get_width() // 2, self.screen.get_height() // 2
        self.screen.blit(title, title.get_rect(center=(cx, cy - 28)))
        self.screen.blit(sub, sub.get_rect(center=(cx, cy + 22)))

    def draw_win_overlay(self) -> None:
        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 120))
        self.screen.blit(overlay, (0, 0))
        txt = self.font_win.render("YOU WIN!", True, COLOR_WIN)
        sub = self.font_title.render("Press R for a new deal", True, COLOR_TEXT)
        self.screen.blit(
            txt,
            txt.get_rect(
                center=(
                    self.screen.get_width() // 2,
                    self.screen.get_height() // 2 - 24,
                )
            ),
        )
        self.screen.blit(
            sub,
            sub.get_rect(
                center=(
                    self.screen.get_width() // 2,
                    self.screen.get_height() // 2 + 24,
                )
            ),
        )

    def draw_solver_timeout_game_over_overlay(self) -> None:
        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        self.screen.blit(overlay, (0, 0))
        title = self.font_win.render("GAME OVER", True, COLOR_GAME_OVER)
        sub = self.font_title.render(
            f"Auto-solve qua {SOLVER_AUTOSOLVE_TIMEOUT_S // 60} phut",
            True,
            COLOR_TEXT,
        )
        hint = self.font_small.render("Nhan R hoac New de choi lai", True, COLOR_TEXT)
        cx, cy = self.screen.get_width() // 2, self.screen.get_height() // 2
        self.screen.blit(title, title.get_rect(center=(cx, cy - 40)))
        self.screen.blit(sub, sub.get_rect(center=(cx, cy + 8)))
        self.screen.blit(hint, hint.get_rect(center=(cx, cy + 52)))
