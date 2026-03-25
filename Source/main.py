"""
FreeCell – a fully playable solitaire card game implemented with pygame.

Rules
-----
* 52 cards are dealt face-up into 8 tableau columns.
* The four **free cells** (top-left) can each hold one card at a time.
* The four **foundation piles** (top-right) are built up by suit from Ace to King.
* You may move a card to:
    - a free cell (if it is empty),
    - the top of a tableau column if the card is one rank lower and the opposite
      colour of the column's top card (or the column is empty),
    - a foundation pile if it is the correct next card for that suit.
* You win when all 52 cards are on the foundations.

Controls
--------
* **Left-click** a card to select it; click a valid destination to move it.
* Press **N** to start a new game.
* Press **Z** or **Ctrl+Z** to undo the last move.
* Close the window or press **Escape** to quit.
"""

import pygame
import random
import sys
from copy import deepcopy

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCREEN_W, SCREEN_H = 1024, 768

CARD_W, CARD_H = 71, 96
CARD_RADIUS = 6

TABLEAU_X0 = 20          # x of first tableau column
TABLEAU_Y0 = 200         # y of first tableau row
COL_GAP = 118            # horizontal gap between columns
ROW_OFFSET = 28          # vertical offset between stacked cards

FREECELL_X0 = 20
FREECELL_Y0 = 20
FOUNDATION_X0 = TABLEAU_X0 + 4 * COL_GAP
FOUNDATION_Y0 = 20

SUITS = ["♠", "♥", "♦", "♣"]
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
RANK_VALUES = {r: i + 1 for i, r in enumerate(RANKS)}

RED_SUITS = {"♥", "♦"}

# Colours
BG_COLOR = (0, 100, 0)
CARD_BG = (255, 255, 240)
CARD_OUTLINE = (80, 80, 80)
CARD_SELECTED = (255, 220, 0)
EMPTY_SLOT_COLOR = (0, 80, 0)
EMPTY_SLOT_OUTLINE = (100, 180, 100)
WIN_OVERLAY = (0, 0, 0, 160)
TEXT_COLOR = (240, 240, 240)
RED_COLOR = (200, 30, 30)
BLACK_COLOR = (20, 20, 20)


# ---------------------------------------------------------------------------
# Card
# ---------------------------------------------------------------------------

class Card:
    def __init__(self, suit: str, rank: str):
        self.suit = suit
        self.rank = rank
        self.value = RANK_VALUES[rank]

    @property
    def is_red(self) -> bool:
        return self.suit in RED_SUITS

    def __repr__(self):
        return f"{self.rank}{self.suit}"

    def __eq__(self, other):
        return isinstance(other, Card) and self.suit == other.suit and self.rank == other.rank

    def __hash__(self):
        return hash((self.suit, self.rank))


# ---------------------------------------------------------------------------
# Game logic
# ---------------------------------------------------------------------------

class FreeCell:
    """Pure-logic FreeCell state (no rendering)."""

    NUM_TABLEAU = 8
    NUM_FREECELLS = 4
    NUM_FOUNDATIONS = 4

    def __init__(self):
        self.tableau: list[list[Card]] = [[] for _ in range(self.NUM_TABLEAU)]
        self.freecells: list[Card | None] = [None] * self.NUM_FREECELLS
        self.foundations: list[list[Card]] = [[] for _ in range(self.NUM_FOUNDATIONS)]
        self._suit_to_foundation: dict[str, int] = {s: i for i, s in enumerate(SUITS)}
        self.deal()

    def deal(self):
        """Shuffle and deal 52 cards into 8 tableau columns."""
        self.tableau = [[] for _ in range(self.NUM_TABLEAU)]
        self.freecells = [None] * self.NUM_FREECELLS
        self.foundations = [[] for _ in range(self.NUM_FOUNDATIONS)]

        deck = [Card(s, r) for s in SUITS for r in RANKS]
        random.shuffle(deck)
        for i, card in enumerate(deck):
            self.tableau[i % self.NUM_TABLEAU].append(card)

    # ------------------------------------------------------------------
    # Move validation helpers
    # ------------------------------------------------------------------

    def _foundation_top(self, suit: str) -> Card | None:
        pile = self.foundations[self._suit_to_foundation[suit]]
        return pile[-1] if pile else None

    def can_move_to_foundation(self, card: Card) -> bool:
        top = self._foundation_top(card.suit)
        if top is None:
            return card.value == 1  # only Ace starts a foundation
        return card.value == top.value + 1

    def can_move_to_tableau(self, card: Card, col: int) -> bool:
        col_cards = self.tableau[col]
        if not col_cards:
            return True
        top = col_cards[-1]
        return top.is_red != card.is_red and card.value == top.value - 1

    def can_move_to_freecell(self) -> bool:
        return any(c is None for c in self.freecells)

    # ------------------------------------------------------------------
    # Moves
    # ------------------------------------------------------------------

    def move_to_foundation(self, card: Card, source_type: str, source_idx: int) -> bool:
        if not self.can_move_to_foundation(card):
            return False
        self._remove_card(card, source_type, source_idx)
        self.foundations[self._suit_to_foundation[card.suit]].append(card)
        return True

    def move_to_tableau(self, card: Card, source_type: str, source_idx: int, dest_col: int) -> bool:
        if not self.can_move_to_tableau(card, dest_col):
            return False
        self._remove_card(card, source_type, source_idx)
        self.tableau[dest_col].append(card)
        return True

    def move_to_freecell(self, card: Card, source_type: str, source_idx: int) -> bool:
        if source_type == "freecell":
            return False  # already in a freecell
        for i, cell in enumerate(self.freecells):
            if cell is None:
                self._remove_card(card, source_type, source_idx)
                self.freecells[i] = card
                return True
        return False

    def _remove_card(self, card: Card, source_type: str, source_idx: int):
        if source_type == "tableau":
            assert self.tableau[source_idx][-1] == card
            self.tableau[source_idx].pop()
        elif source_type == "freecell":
            self.freecells[source_idx] = None
        elif source_type == "foundation":
            self.foundations[source_idx].pop()

    # ------------------------------------------------------------------
    # Win condition
    # ------------------------------------------------------------------

    def is_won(self) -> bool:
        return all(len(pile) == 13 for pile in self.foundations)


# ---------------------------------------------------------------------------
# Renderer / UI
# ---------------------------------------------------------------------------

class FreeCellGame:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption("FreeCell")
        self.clock = pygame.time.Clock()

        # Use a font that supports Unicode suit symbols (♠ ♥ ♦ ♣).
        # "segoeui" covers them on Windows; "dejavusans" / "notosans" on Linux/macOS.
        _font_candidates = ["segoeui", "dejavusans", "notosans", "arial", "freesans"]
        _font_name = next(
            (f for f in _font_candidates if f in pygame.font.get_fonts()),
            None,  # fall back to pygame default
        )
        self.font_card = pygame.font.SysFont(_font_name, 18, bold=True)
        self.font_ui = pygame.font.SysFont(_font_name, 22, bold=True)
        self.font_big = pygame.font.SysFont(_font_name, 60, bold=True)

        self.game = FreeCell()
        self.history: list[tuple] = []  # stack of (tableau, freecells, foundations) snapshots

        # Selection state
        self.selected_card: Card | None = None
        self.selected_source_type: str | None = None
        self.selected_source_idx: int | None = None

    # ------------------------------------------------------------------
    # Snapshot helpers for undo
    # ------------------------------------------------------------------

    def _snapshot(self):
        return (
            deepcopy(self.game.tableau),
            deepcopy(self.game.freecells),
            deepcopy(self.game.foundations),
        )

    def _restore(self, snap):
        self.game.tableau, self.game.freecells, self.game.foundations = snap

    # ------------------------------------------------------------------
    # Drawing helpers
    # ------------------------------------------------------------------

    def _draw_card(self, card: Card | None, x: int, y: int, selected: bool = False):
        """Draw a single card (or an empty slot if card is None)."""
        rect = pygame.Rect(x, y, CARD_W, CARD_H)
        if card is None:
            pygame.draw.rect(self.screen, EMPTY_SLOT_COLOR, rect, border_radius=CARD_RADIUS)
            pygame.draw.rect(self.screen, EMPTY_SLOT_OUTLINE, rect, 2, border_radius=CARD_RADIUS)
            return

        outline_color = CARD_SELECTED if selected else CARD_OUTLINE
        pygame.draw.rect(self.screen, CARD_BG, rect, border_radius=CARD_RADIUS)
        pygame.draw.rect(self.screen, outline_color, rect, 2 if not selected else 3,
                         border_radius=CARD_RADIUS)

        color = RED_COLOR if card.is_red else BLACK_COLOR
        rank_surf = self.font_card.render(card.rank, True, color)
        suit_surf = self.font_card.render(card.suit, True, color)
        self.screen.blit(rank_surf, (x + 4, y + 2))
        self.screen.blit(suit_surf, (x + 4, y + 2 + rank_surf.get_height()))

        # bottom-right corner (rotated)
        rank_surf2 = self.font_card.render(card.rank, True, color)
        suit_surf2 = self.font_card.render(card.suit, True, color)
        rank_surf2 = pygame.transform.rotate(rank_surf2, 180)
        suit_surf2 = pygame.transform.rotate(suit_surf2, 180)
        self.screen.blit(rank_surf2,
                         (x + CARD_W - rank_surf2.get_width() - 4,
                          y + CARD_H - rank_surf2.get_height() - 2))
        self.screen.blit(suit_surf2,
                         (x + CARD_W - suit_surf2.get_width() - 4,
                          y + CARD_H - rank_surf2.get_height() - suit_surf2.get_height() - 2))

    def _draw_empty_foundation(self, x: int, y: int, suit: str):
        rect = pygame.Rect(x, y, CARD_W, CARD_H)
        pygame.draw.rect(self.screen, EMPTY_SLOT_COLOR, rect, border_radius=CARD_RADIUS)
        pygame.draw.rect(self.screen, EMPTY_SLOT_OUTLINE, rect, 2, border_radius=CARD_RADIUS)
        s = self.font_card.render(suit, True, EMPTY_SLOT_OUTLINE)
        self.screen.blit(s, (x + CARD_W // 2 - s.get_width() // 2,
                              y + CARD_H // 2 - s.get_height() // 2))

    def _draw(self):
        self.screen.fill(BG_COLOR)
        g = self.game

        # ---- Free cells ----
        for i, card in enumerate(g.freecells):
            x = FREECELL_X0 + i * COL_GAP
            sel = (self.selected_source_type == "freecell" and self.selected_source_idx == i)
            self._draw_card(card, x, FREECELL_Y0, selected=sel)

        # ---- Foundations ----
        for i, (suit, pile) in enumerate(zip(SUITS, g.foundations)):
            x = FOUNDATION_X0 + i * COL_GAP
            if pile:
                sel = (self.selected_source_type == "foundation" and self.selected_source_idx == i)
                self._draw_card(pile[-1], x, FOUNDATION_Y0, selected=sel)
            else:
                self._draw_empty_foundation(x, FOUNDATION_Y0, suit)

        # ---- Tableau ----
        for col, column in enumerate(g.tableau):
            x = TABLEAU_X0 + col * COL_GAP
            if not column:
                self._draw_card(None, x, TABLEAU_Y0)
            for row, card in enumerate(column):
                y = TABLEAU_Y0 + row * ROW_OFFSET
                sel = (self.selected_source_type == "tableau"
                       and self.selected_source_idx == col
                       and row == len(column) - 1)
                self._draw_card(card, x, y, selected=sel)

        # ---- HUD ----
        hint = self.font_ui.render("N = New game   Z = Undo   Esc = Quit", True, TEXT_COLOR)
        self.screen.blit(hint, (SCREEN_W - hint.get_width() - 10, SCREEN_H - 32))

        # ---- Win screen ----
        if g.is_won():
            overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
            overlay.fill(WIN_OVERLAY)
            self.screen.blit(overlay, (0, 0))
            msg = self.font_big.render("You Win!", True, (255, 215, 0))
            self.screen.blit(msg, (SCREEN_W // 2 - msg.get_width() // 2,
                                    SCREEN_H // 2 - msg.get_height() // 2))
            sub = self.font_ui.render("Press N to play again", True, TEXT_COLOR)
            self.screen.blit(sub, (SCREEN_W // 2 - sub.get_width() // 2,
                                    SCREEN_H // 2 + msg.get_height() // 2 + 10))

        pygame.display.flip()

    # ------------------------------------------------------------------
    # Hit-testing
    # ------------------------------------------------------------------

    def _card_rect(self, x: int, y: int) -> pygame.Rect:
        return pygame.Rect(x, y, CARD_W, CARD_H)

    def _hit_test(self, mx: int, my: int):
        """
        Return (source_type, source_idx, card) for the topmost card at (mx, my),
        or (None, None, None) if no card was clicked.
        """
        g = self.game

        # Free cells
        for i, card in enumerate(g.freecells):
            x = FREECELL_X0 + i * COL_GAP
            if card and self._card_rect(x, FREECELL_Y0).collidepoint(mx, my):
                return "freecell", i, card

        # Foundations (allow selecting top of foundation)
        for i, pile in enumerate(g.foundations):
            x = FOUNDATION_X0 + i * COL_GAP
            if pile and self._card_rect(x, FOUNDATION_Y0).collidepoint(mx, my):
                return "foundation", i, pile[-1]

        # Tableau – iterate columns in reverse to hit topmost card first
        for col in range(g.NUM_TABLEAU - 1, -1, -1):
            column = g.tableau[col]
            x = TABLEAU_X0 + col * COL_GAP
            # Check from top of column downward to find the *topmost visible* hit
            for row in range(len(column) - 1, -1, -1):
                y = TABLEAU_Y0 + row * ROW_OFFSET
                if self._card_rect(x, y).collidepoint(mx, my):
                    # Only allow picking the actual top card
                    if row == len(column) - 1:
                        return "tableau", col, column[row]
                    return None, None, None  # middle of stack – ignore

        return None, None, None

    def _hit_test_destination(self, mx: int, my: int):
        """
        Return (dest_type, dest_idx) for a valid drop zone at (mx, my).
        """
        g = self.game

        # Free cells
        for i in range(g.NUM_FREECELLS):
            x = FREECELL_X0 + i * COL_GAP
            if self._card_rect(x, FREECELL_Y0).collidepoint(mx, my):
                return "freecell", i

        # Foundations
        for i in range(g.NUM_FOUNDATIONS):
            x = FOUNDATION_X0 + i * COL_GAP
            if self._card_rect(x, FOUNDATION_Y0).collidepoint(mx, my):
                return "foundation", i

        # Tableau columns – hit the top card or the empty slot area
        for col in range(g.NUM_TABLEAU):
            column = g.tableau[col]
            x = TABLEAU_X0 + col * COL_GAP
            if column:
                top_row = len(column) - 1
                y = TABLEAU_Y0 + top_row * ROW_OFFSET
            else:
                y = TABLEAU_Y0
            if self._card_rect(x, y).collidepoint(mx, my):
                return "tableau", col

        return None, None

    # ------------------------------------------------------------------
    # Move execution
    # ------------------------------------------------------------------

    def _try_move(self, dest_type: str, dest_idx: int):
        card = self.selected_card
        src_type = self.selected_source_type
        src_idx = self.selected_source_idx
        g = self.game

        snap = self._snapshot()
        moved = False

        if dest_type == "foundation":
            moved = g.move_to_foundation(card, src_type, src_idx)
        elif dest_type == "freecell":
            if g.freecells[dest_idx] is None:
                moved = g.move_to_freecell(card, src_type, src_idx)
        elif dest_type == "tableau":
            moved = g.move_to_tableau(card, src_type, src_idx, dest_idx)

        if moved:
            self.history.append(snap)

        self.selected_card = None
        self.selected_source_type = None
        self.selected_source_idx = None

    def _auto_move_to_foundation(self):
        """Try to automatically move a card to the foundation after every move."""
        g = self.game
        moved = True
        while moved:
            moved = False
            for src_type, src_idx, card in self._all_top_cards():
                if g.can_move_to_foundation(card):
                    # Only auto-move if safe (Ace, 2, or rank <= min_foundation + 1)
                    min_found = min(
                        len(pile) for pile in g.foundations
                    )
                    if card.value <= min_found + 2:
                        snap = self._snapshot()
                        if g.move_to_foundation(card, src_type, src_idx):
                            self.history.append(snap)
                            moved = True
                            break

    def _all_top_cards(self):
        g = self.game
        result = []
        for i, card in enumerate(g.freecells):
            if card:
                result.append(("freecell", i, card))
        for col, column in enumerate(g.tableau):
            if column:
                result.append(("tableau", col, column[-1]))
        return result

    # ------------------------------------------------------------------
    # Event loop
    # ------------------------------------------------------------------

    def run(self):
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()

                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        pygame.quit()
                        sys.exit()
                    if event.key == pygame.K_n:
                        self.game.deal()
                        self.history.clear()
                        self.selected_card = None
                        self.selected_source_type = None
                        self.selected_source_idx = None
                    if event.key == pygame.K_z:
                        if self.history:
                            self._restore(self.history.pop())
                            self.selected_card = None
                            self.selected_source_type = None
                            self.selected_source_idx = None

                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    mx, my = event.pos

                    if self.selected_card is None:
                        # Select a card
                        src_type, src_idx, card = self._hit_test(mx, my)
                        if card:
                            self.selected_card = card
                            self.selected_source_type = src_type
                            self.selected_source_idx = src_idx
                    else:
                        # Deselect if clicking the same card
                        src_type, src_idx, card = self._hit_test(mx, my)
                        if (card == self.selected_card
                                and src_type == self.selected_source_type
                                and src_idx == self.selected_source_idx):
                            self.selected_card = None
                            self.selected_source_type = None
                            self.selected_source_idx = None
                        else:
                            # Try to move to destination
                            dest_type, dest_idx = self._hit_test_destination(mx, my)
                            if dest_type:
                                self._try_move(dest_type, dest_idx)
                                self._auto_move_to_foundation()

            self._draw()
            self.clock.tick(60)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    FreeCellGame().run()
