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
    FAB_PANEL_FILL,
    FAB_PANEL_LINE,
    FAB_SHADOW_ALPHA,
    COLOR_GAME_OVER,
    COLOR_HINT_GLOW,
    FOOTER_BG,
    FOOTER_BEVEL_DK,
    FOOTER_BEVEL_LT,
    FOOTER_GRIP_WIDTH,
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
    FAB_AI_DROPDOWN_GAP,
    FAB_AI_DROPDOWN_OFFSET_X,
    FAB_AI_DROPDOWN_OFFSET_Y,
    FAB_AI_DROPDOWN_ROW_H,
    FAB_AI_DROPDOWN_WIDTH,
    FAB_AI_ALGO_ORDER,
    FAB_CELL,
    FAB_GAP,
    FAB_MAIN_ORDER,
    FAB_PAD,
    FAB_RADIUS,
    FAB_TOOLTIPS,
    SHADOW_ALPHA,
    SHADOW_ALPHA_SOFT,
    CARD_SHADOW_OFFSET,
    CARD_SHADOW_SCALE_OUTER,
    CARD_SHADOW_SCALE_INNER,
    CARD_BEVEL_HI_ALPHA,
    CARD_BEVEL_LO_ALPHA,
    SOLVER_AUTOSOLVE_TIMEOUT_S,
    SOLVER_BTN_ACCENTS,
    TOOLBAR_BUTTON_GLYPHS,
    NEW_GAME_LEVEL_RANGES,
)
from .layout import BoardLayout
from .models import Card, SUIT_SYMBOLS, Suit, is_red
from .state import GameState


def _lerp_color(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def fab_outer_size() -> tuple[int, int]:
    n = len(FAB_MAIN_ORDER)
    ih = n * FAB_CELL + (n - 1) * FAB_GAP
    return FAB_CELL + 2 * FAB_PAD, ih + 2 * FAB_PAD


def fab_icon_rects(fx: int, fy: int) -> dict[str, pygame.Rect]:
    rects: dict[str, pygame.Rect] = {}
    x = fx + FAB_PAD
    y = fy + FAB_PAD
    for key in FAB_MAIN_ORDER:
        rects[key] = pygame.Rect(x, y, FAB_CELL, FAB_CELL)
        y += FAB_CELL + FAB_GAP
    return rects


def fab_ai_dropdown_layout(ai_cell: pygame.Rect) -> tuple[pygame.Rect, dict[str, pygame.Rect]]:
    """Vertical list of algorithms directly under the AI cell (horizontal bar = one column)."""
    algos = FAB_AI_ALGO_ORDER
    row = FAB_AI_DROPDOWN_ROW_H
    w = FAB_AI_DROPDOWN_WIDTH
    pad = 4
    inner_h = pad * 2 + row * len(algos)
    left = ai_cell.centerx - w // 2 + FAB_AI_DROPDOWN_OFFSET_X
    top = ai_cell.bottom + FAB_AI_DROPDOWN_GAP + FAB_AI_DROPDOWN_OFFSET_Y
    outer = pygame.Rect(left, top, w, inner_h)
    rects: dict[str, pygame.Rect] = {}
    y = top + pad
    for a in algos:
        rects[a] = pygame.Rect(left + 3, y, w - 6, row)
        y += row
    return outer, rects


def fab_ai_dropdown_visible(pos: tuple[int, int], fx: int, fy: int) -> bool:
    rects = fab_icon_rects(fx, fy)
    ai = rects["AI"]
    drop_outer, _ = fab_ai_dropdown_layout(ai)
    left_b = min(ai.left, drop_outer.left)
    right_b = max(ai.right, drop_outer.right)
    gap_bridge = pygame.Rect(left_b, ai.bottom, right_b - left_b, FAB_AI_DROPDOWN_GAP)
    return bool(
        ai.collidepoint(pos)
        or drop_outer.collidepoint(pos)
        or gap_bridge.collidepoint(pos)
    )


def fab_hit_at(pos: tuple[int, int], fx: int, fy: int) -> tuple[str, str | None]:
    rects = fab_icon_rects(fx, fy)
    ai = rects["AI"]
    drop_outer, algo_rects = fab_ai_dropdown_layout(ai)

    if fab_ai_dropdown_visible(pos, fx, fy):
        for name in FAB_AI_ALGO_ORDER:
            if algo_rects[name].collidepoint(pos):
                return ("algo", name)

    ow, oh = fab_outer_size()
    outer = pygame.Rect(fx, fy, ow, oh)
    for key in FAB_MAIN_ORDER:
        if rects[key].collidepoint(pos):
            return ("main", key)
    if drop_outer.collidepoint(pos):
        return ("panel", None)
    if fab_ai_dropdown_visible(pos, fx, fy):
        return ("panel", None)
    if outer.collidepoint(pos):
        return ("panel", None)
    return ("none", None)


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
        self.font_button_glyph = pygame.font.SysFont("segoe ui symbol", 23, bold=True)
        self.font_fab_tip = pygame.font.SysFont("segoeui", 16, bold=True)
        self.font_fab_dd_hover = pygame.font.SysFont("segoeui", 20, bold=True)
        self.card_images = self._load_card_images()
        self.bg_image_orig = self._load_bg_image()
        self.bg_image_scaled = None
        self.last_screen_size = (0, 0)

    def _load_bg_image(self) -> pygame.Surface | None:
        full_path = Path(__file__).resolve().parent.parent / "asset" / "background.jpg"
        if full_path.exists():
            return pygame.image.load(str(full_path)).convert()
        return None

    def _load_card_images(self) -> dict[Card, pygame.Surface]:
        asset_dir = Path(__file__).resolve().parent.parent / "asset" / "card"
        suit_names = {Suit.CLUBS: "clubs", Suit.DIAMONDS: "diamonds", Suit.HEARTS: "hearts", Suit.SPADES: "spades"}
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
        """Scale art slightly smaller and center so rank/suit clear the rounded top-left."""
        pad = CARD_FACE_ART_INSET
        inner_w = max(1, CARD_WIDTH - 2 * pad)
        inner_h = max(1, CARD_HEIGHT - 2 * pad)
        scaled = pygame.transform.smoothscale(img, (inner_w, inner_h))
        canvas = pygame.Surface((CARD_WIDTH, CARD_HEIGHT), pygame.SRCALPHA)
        canvas.fill((255, 255, 255, 255))
        canvas.blit(scaled, (pad, pad))
        return self._clip_rounded_surface(canvas, CARD_CORNER_RADIUS)

    def _clip_rounded_surface(self, surf: pygame.Surface, border_radius: int) -> pygame.Surface:
        """Multiply alpha by a rounded rect so square PNG corners don't show past the card outline."""
        w, h = surf.get_size()
        rounded = pygame.Surface((w, h), pygame.SRCALPHA)
        rounded.blit(surf, (0, 0))
        mask = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(
            mask,
            (255, 255, 255, 255),
            mask.get_rect(),
            border_radius=border_radius,
        )
        rounded.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        return rounded

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
        """Subtle raised-card look: light along top, soft shade toward bottom-right."""
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

    def draw_background(self) -> None:
        self.screen.fill(COLOR_BG)
        if BACKGROUND_USE_IMAGE and self.bg_image_orig:
            curr_size = self.screen.get_size()
            if self.last_screen_size != curr_size:
                self.bg_image_scaled = pygame.transform.smoothscale(self.bg_image_orig, curr_size)
                self.last_screen_size = curr_size
            if self.bg_image_scaled:
                dim = pygame.Surface(curr_size, pygame.SRCALPHA)
                dim.fill((12, 18, 32, 210))
                self.screen.blit(self.bg_image_scaled, (0, 0))
                self.screen.blit(dim, (0, 0))
        self._draw_diagonal_stripes(self.screen)

    def _draw_footer_inset_cell(self, rect: pygame.Rect) -> None:
        """Sunken field: darker top/left, lighter bottom/right (classic Win32)."""
        pygame.draw.rect(self.screen, FOOTER_PANEL_FACE, rect)
        x, y, w, h = rect
        pygame.draw.line(self.screen, FOOTER_BEVEL_DK, (x, y), (x + w - 1, y), 1)
        pygame.draw.line(self.screen, FOOTER_BEVEL_DK, (x, y), (x, y + h - 1), 1)
        pygame.draw.line(self.screen, FOOTER_BEVEL_LT, (x, y + h - 1), (x + w - 1, y + h - 1), 1)
        pygame.draw.line(self.screen, FOOTER_BEVEL_LT, (x + w - 1, y), (x + w - 1, y + h - 1), 1)

    def _draw_footer_resize_grip(self, bar_top: int) -> None:
        w = self.screen.get_width()
        gx = w - FOOTER_GRIP_WIDTH
        cy = bar_top + FOOTER_HEIGHT // 2
        c = (120, 118, 115)
        for i in range(3):
            o = i * 4
            pygame.draw.line(
                self.screen,
                c,
                (gx + 3 + o, cy + 4 - o),
                (gx + 9 + o, cy - 2 - o),
                1,
            )

    def draw_footer_bar(
        self,
        score: int,
        elapsed: float,
        moves: int,
        foundation_cards: int,
        deal_label: str,
        freecells_occupied: int,
    ) -> None:
        w, h = self.screen.get_size()
        bar_top = h - FOOTER_HEIGHT
        pygame.draw.rect(self.screen, FOOTER_BG, (0, bar_top, w, FOOTER_HEIGHT))

        mins = int(elapsed) // 60
        secs = int(elapsed) % 60
        labels = [
            f"{mins}:{secs:02d}",
            f"{foundation_cards}/52",
            deal_label,
            f"{freecells_occupied}/4 · {moves} · {score}",
        ]

        inner = FOOTER_INNER_MARGIN
        gap = FOOTER_PANEL_GAP
        pad_x = FOOTER_PANEL_PAD_X
        row_h = FOOTER_HEIGHT - 2 * inner
        y_cell = bar_top + inner
        x = inner

        max_text_w = w - inner * 2 - FOOTER_GRIP_WIDTH - gap * (len(labels) - 1) - 8
        surfaces = [self.font_footer_info.render(s, True, FOOTER_TEXT) for s in labels]
        natural = sum(su.get_width() + 2 * pad_x for su in surfaces) + gap * (len(labels) - 1)
        stretch_id = 2
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

        self._draw_footer_resize_grip(bar_top)

    def draw_new_game_menu(self, mode: str, category: str | None, hover: str | None) -> None:
        """Dim board + pick difficulty (easy/medium/hard) then pick LEVEL."""
        sw, sh = self.screen.get_size()
        dim = pygame.Surface((sw, sh), pygame.SRCALPHA)
        dim.fill((8, 24, 12, 150))
        self.screen.blit(dim, (0, 0))
        if mode == "levels":
            cat = category or "easy"
            lo, hi = NEW_GAME_LEVEL_RANGES.get(cat, (1, 1))
            title = self.font_button.render(
                f"New game — {cat} level ({lo}-{hi})",
                True,
                (248, 250, 252),
            )
            opts = [(str(lvl), str(lvl)) for lvl in range(lo, hi + 1)]
        else:
            title = self.font_button.render("New game — difficulty", True, (248, 250, 252))
            opts = [("easy", "Easy"), ("medium", "Medium"), ("hard", "Hard")]

        self.screen.blit(title, title.get_rect(center=(sw // 2, sh // 2 - 72)))
        bw, bh = 168, 52
        gap = 14
        total_w = len(opts) * bw + (len(opts) - 1) * gap
        x0 = (sw - total_w) // 2
        y0 = sh // 2 - 10
        cr = min(12, bh // 3)
        for i, (key, label) in enumerate(opts):
            rect = pygame.Rect(x0 + i * (bw + gap), y0, bw, bh)
            is_h = hover == key
            face = self._fab_inner_face(bw, bh, cr, False, is_h)
            self.screen.blit(face, rect.topleft)
            line = (240, 255, 250) if is_h else (190, 210, 195)
            pygame.draw.rect(self.screen, line, rect, width=2, border_radius=cr)
            txt = self.font_footer_info.render(label, True, (255, 255, 255) if is_h else (235, 245, 238))
            self.screen.blit(txt, txt.get_rect(center=rect.center))
        hint = self.font_footer_info.render("Click outside to cancel", True, (200, 215, 205))
        self.screen.blit(hint, hint.get_rect(center=(sw // 2, y0 + bh + 36)))

    def _button_inner_face(
        self,
        w: int,
        h: int,
        radius: int,
        is_pressed: bool,
        is_hover: bool,
    ) -> pygame.Surface:
        body = pygame.Surface((w, h), pygame.SRCALPHA)
        steps = max(6, h // 3)
        for s in range(steps):
            t = s / max(steps - 1, 1)
            if is_pressed:
                top, bot = (78, 82, 88), (58, 62, 68)
            elif is_hover:
                top, bot = (118, 122, 130), (88, 92, 100)
            else:
                top, bot = (98, 102, 112), (68, 72, 80)
            c = _lerp_color(bot, top, t)
            y0 = int(s * h / steps)
            y1 = int((s + 1) * h / steps)
            pygame.draw.rect(body, (*c, 255), pygame.Rect(0, y0, w, max(1, y1 - y0)))
        gloss = pygame.Surface((w, h), pygame.SRCALPHA)
        gr = max(2, radius - 2)
        pygame.draw.rect(
            gloss,
            (255, 255, 255, 48),
            pygame.Rect(2, 2, w - 4, max(6, h // 3)),
            border_radius=gr,
        )
        body.blit(gloss, (0, 0))
        mask = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=radius)
        body.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        return body

    def _fab_inner_face(
        self,
        w: int,
        h: int,
        radius: int,
        is_pressed: bool,
        is_hover: bool,
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
        pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=radius)
        body.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        return body

    def _draw_sunken_felt_slot(
        self,
        rect: pygame.Rect,
        *,
        highlighted: bool = False,
    ) -> None:
        w, h = rect.size
        r = min(CARD_CORNER_RADIUS, min(w, h) // 2)
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(surf, (*COLOR_FELT_SLOT_FACE, 255), surf.get_rect(), border_radius=r)
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
                self.screen,
                COLOR_SLOT_TARGET_RING,
                rect,
                width=3,
                border_radius=r,
            )

    def draw_slot(self, rect: pygame.Rect, label: str = "", highlighted: bool = False) -> None:
        pass

    def draw_card(self, card: Card, x: float, y: float, shadow: bool = True) -> None:
        card_rect = pygame.Rect(round(x), round(y), CARD_WIDTH, CARD_HEIGHT)
        if shadow:
            self._draw_soft_card_shadow(card_rect)

        if card in self.card_images:
            self.screen.blit(self.card_images[card], card_rect)
        else:
            pygame.draw.rect(self.screen, COLOR_CARD_FACE, card_rect, border_radius=CARD_CORNER_RADIUS)

            color = COLOR_CARD_RED if is_red(card.suit) else COLOR_CARD_BLACK
            label = self.font_card.render(card.label, True, color)
            self.screen.blit(label, (card_rect.x + 10, card_rect.y + 8))

            suit = self.font_title.render(card.label[-1], True, color)
            self.screen.blit(suit, (card_rect.right - 35, card_rect.bottom - 42))

        self._draw_card_bevel(card_rect)

        pygame.draw.rect(
            self.screen,
            CARD_FACE_OUTLINE_COLOR,
            card_rect,
            width=CARD_FACE_OUTLINE_WIDTH,
            border_radius=CARD_CORNER_RADIUS,
        )

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
                    lo_c = (max(0, COLOR_CARD_RED[0] - 50), max(0, COLOR_CARD_RED[1] - 8), max(0, COLOR_CARD_RED[2] - 8))
                    hi_c = COLOR_CARD_RED
                else:
                    lo_c = (6, 7, 9)
                    hi_c = COLOR_CARD_BLACK
                lo = self.font_foundation_suit.render(sym, True, lo_c)
                hi = self.font_foundation_suit.render(sym, True, hi_c)
                cx, cy = rect.center
                self.screen.blit(lo, lo.get_rect(center=(cx + 2, cy + 3)))
                self.screen.blit(hi, hi.get_rect(center=(cx, cy)))

    def draw_floating_toolbar(
        self,
        fab_x: int,
        fab_y: int,
        hover_main: str | None,
        hover_algo: str | None,
        pressed_main: str | None,
        pressed_algo: str | None,
        dragging: bool,
    ) -> None:
        """Single draggable floating strip: icons only; AI opens algorithm dropdown on hover."""
        mx, my = pygame.mouse.get_pos()
        mouse_pos = (mx, my)
        cr = min(8, FAB_CELL // 2)

        ow, oh = fab_outer_size()
        outer = pygame.Rect(fab_x, fab_y, ow, oh)
        sh = pygame.Surface((ow + 8, oh + 8), pygame.SRCALPHA)
        pygame.draw.rect(
            sh,
            (0, 36, 8, FAB_SHADOW_ALPHA),
            sh.get_rect(),
            border_radius=FAB_RADIUS + 2,
        )
        self.screen.blit(sh, (outer.x - 2, outer.y + 3))

        panel = pygame.Surface((ow, oh), pygame.SRCALPHA)
        panel.fill(FAB_PANEL_FILL)
        pygame.draw.rect(
            panel,
            FAB_PANEL_LINE,
            panel.get_rect(),
            width=1,
            border_radius=FAB_RADIUS,
        )
        self.screen.blit(panel, outer.topleft)

        rects = fab_icon_rects(fab_x, fab_y)
        show_ai_dd = fab_ai_dropdown_visible(mouse_pos, fab_x, fab_y)

        if show_ai_dd:
            ai_cell = rects["AI"]
            drop_outer, algo_rects = fab_ai_dropdown_layout(ai_cell)
            dd_bg = pygame.Surface(drop_outer.size, pygame.SRCALPHA)
            dd_bg.fill(FAB_PANEL_FILL)
            pygame.draw.rect(dd_bg, FAB_PANEL_LINE, dd_bg.get_rect(), width=1, border_radius=10)
            self.screen.blit(dd_bg, drop_outer.topleft)
            drr = min(6, FAB_AI_DROPDOWN_ROW_H // 2)
            for algo in FAB_AI_ALGO_ORDER:
                ar = algo_rects[algo]
                is_h = hover_algo == algo
                is_p = pressed_algo == algo
                acc = SOLVER_BTN_ACCENTS.get(algo, (140, 140, 150))
                face = self._fab_inner_face(ar.w, ar.h, drr, bool(is_p), bool(is_h))
                self.screen.blit(face, ar.topleft)
                line = (230, 255, 236) if is_p else ((190, 245, 200) if is_h else (64, 118, 72))
                pygame.draw.rect(self.screen, line, ar, width=2, border_radius=drr)
                strip = pygame.Rect(ar.left + 2, ar.top + 4, 3, ar.height - 8)
                pygame.draw.rect(self.screen, acc, strip, border_radius=1)
                if is_h:
                    t = self.font_fab_dd_hover.render(algo, True, (255, 255, 255))
                else:
                    t = self.font_small.render(algo, True, (245, 248, 252))
                self.screen.blit(t, t.get_rect(center=ar.center))

        for key, cell in rects.items():
            is_h = not dragging and hover_main == key
            is_p = pressed_main == key
            dy = 1 if is_p else (-1 if is_h else 0)
            btn = cell.move(0, dy)

            if key == "HINT" and is_h and not dragging:
                for g in range(4, 0, -1):
                    glow = pygame.Surface((btn.w + g * 3, btn.h + g * 3), pygame.SRCALPHA)
                    a = max(0, 22 - g * 5)
                    pygame.draw.rect(
                        glow,
                        (*COLOR_HINT_GLOW[:3], a),
                        glow.get_rect(),
                        border_radius=cr + g,
                    )
                    self.screen.blit(glow, glow.get_rect(center=btn.center).topleft)

            face = self._fab_inner_face(btn.w, btn.h, cr, bool(is_p), bool(is_h))
            self.screen.blit(face, btn.topleft)
            line = (240, 255, 245) if is_p else ((200, 248, 210) if is_h else (72, 128, 82))
            pygame.draw.rect(self.screen, line, btn, width=2, border_radius=cr)

            ch = TOOLBAR_BUTTON_GLYPHS.get(key, "")
            if ch:
                gcol = (255, 255, 255) if is_h else (245, 248, 252)
                gsurf = self.font_button_glyph.render(ch, True, gcol)
                self.screen.blit(gsurf, gsurf.get_rect(center=btn.center))

        if not dragging and hover_main and hover_main in FAB_TOOLTIPS:
            tip = self.font_fab_tip.render(FAB_TOOLTIPS[hover_main], True, (255, 255, 255))
            cell = rects[hover_main]
            sw = self.screen.get_width()
            pad_x, pad_y = 10, 6
            gap = 8
            tw, th = tip.get_size()
            bg_w, bg_h = tw + pad_x * 2, th + pad_y * 2
            bg_x = cell.right + gap
            if bg_x + bg_w > sw - 8:
                bg_x = max(8, sw - bg_w - 8)
            bg_y = cell.centery - bg_h // 2
            bg_y = max(4, min(bg_y, self.screen.get_height() - bg_h - 4))
            bg = pygame.Surface((bg_w, bg_h), pygame.SRCALPHA)
            pygame.draw.rect(bg, (0, 0, 0, 200), bg.get_rect(), border_radius=6)
            self.screen.blit(bg, (bg_x, bg_y))
            tip_x = bg_x + bg_w - pad_x - tw
            tip_y = bg_y + pad_y
            self.screen.blit(tip, (tip_x, tip_y))

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
        self.screen.blit(txt, txt.get_rect(center=(self.screen.get_width() // 2, self.screen.get_height() // 2 - 24)))
        self.screen.blit(sub, sub.get_rect(center=(self.screen.get_width() // 2, self.screen.get_height() // 2 + 24)))

    def draw_solver_timeout_game_over_overlay(self) -> None:
        """Shown when auto-solve exceeds SOLVER_AUTOSOLVE_TIMEOUT_S."""
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
