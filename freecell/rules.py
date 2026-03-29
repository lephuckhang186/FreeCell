"""Pure move validation and move application logic."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .models import Card, Suit, is_red
from .state import GameState


class PileType(str, Enum):
    TABLEAU = "tableau"
    FREECELL = "freecell"
    FOUNDATION = "foundation"


@dataclass(frozen=True, slots=True)
class PileRef:
    kind: PileType
    index: int


@dataclass(slots=True)
class MoveResult:
    ok: bool
    reason: str = ""


def tableau_descending_alternating(cards: list[Card]) -> bool:
    """True when cards form a valid movable sequence in tableau."""
    for i in range(len(cards) - 1):
        top = cards[i]
        below = cards[i + 1]
        if is_red(top.suit) == is_red(below.suit):
            return False
        if top.rank != below.rank + 1:
            return False
    return True


def count_empty_free_cells(state: GameState) -> int:
    return sum(1 for c in state.free_cells if c is None)


def count_empty_tableau_columns(state: GameState, exclude: int | None = None) -> int:
    return sum(1 for i, col in enumerate(state.tableau) if not col and i != exclude)


def max_movable_cards(state: GameState, dst_column: int) -> int:
    """Max cards allowed in one move based on FreeCell capacity formula."""
    empty_free = count_empty_free_cells(state)
    empty_tableau = count_empty_tableau_columns(state, exclude=dst_column)
    return (empty_free + 1) * (2**empty_tableau)


def can_place_on_tableau(card: Card, dst_col: list[Card]) -> bool:
    if not dst_col:
        return True
    target = dst_col[-1]
    return is_red(card.suit) != is_red(target.suit) and card.rank == target.rank - 1


def can_place_on_foundation(card: Card, pile: list[Card], suit: Suit) -> bool:
    if card.suit != suit:
        return False
    if not pile:
        return card.rank == 1
    return card.rank == pile[-1].rank + 1


def pick_cards(state: GameState, src: PileRef, start_index: int = -1) -> list[Card]:
    """Read cards from source without mutating state."""
    if src.kind == PileType.TABLEAU:
        col = state.tableau[src.index]
        if not col:
            return []
        if start_index < 0:
            start_index = len(col) - 1
        return col[start_index:]
    if src.kind == PileType.FREECELL:
        card = state.free_cells[src.index]
        return [card] if card else []
    if src.kind == PileType.FOUNDATION:
        suit = list(Suit)[src.index]
        pile = state.foundations[suit]
        return [pile[-1]] if pile else []
    return []


def remove_picked_cards(state: GameState, src: PileRef, start_index: int = -1) -> list[Card]:
    """Take cards from source and return them."""
    if src.kind == PileType.TABLEAU:
        col = state.tableau[src.index]
        if start_index < 0:
            start_index = len(col) - 1
        out = col[start_index:]
        del col[start_index:]
        return out
    if src.kind == PileType.FREECELL:
        card = state.free_cells[src.index]
        state.free_cells[src.index] = None
        return [card] if card else []
    if src.kind == PileType.FOUNDATION:
        suit = list(Suit)[src.index]
        pile = state.foundations[suit]
        if not pile:
            return []
        return [pile.pop()]
    return []


def push_cards(state: GameState, dst: PileRef, cards: list[Card]) -> None:
    if dst.kind == PileType.TABLEAU:
        state.tableau[dst.index].extend(cards)
    elif dst.kind == PileType.FREECELL:
        state.free_cells[dst.index] = cards[0]
    else:
        suit = list(Suit)[dst.index]
        state.foundations[suit].append(cards[0])


def validate_move(state: GameState, src: PileRef, dst: PileRef, cards: list[Card]) -> MoveResult:
    if src == dst:
        return MoveResult(False, "Nguon va dich giong nhau.")
    if not cards:
        return MoveResult(False, "Khong co la bai de di chuyen.")

    if dst.kind == PileType.FREECELL:
        if len(cards) != 1:
            return MoveResult(False, "Free Cell chi chua 1 la.")
        if state.free_cells[dst.index] is not None:
            return MoveResult(False, "Free Cell da co la bai.")
        return MoveResult(True)

    if dst.kind == PileType.FOUNDATION:
        if len(cards) != 1:
            return MoveResult(False, "Foundation chi nhan 1 la.")
        suit = list(Suit)[dst.index]
        pile = state.foundations[suit]
        if can_place_on_foundation(cards[0], pile, suit):
            return MoveResult(True)
        return MoveResult(False, "Khong hop le theo thu tu foundation.")

    # Destination is tableau.
    if src.kind == PileType.TABLEAU and len(cards) > 1:
        if not tableau_descending_alternating(cards):
            return MoveResult(False, "Chuoi bai khong dung mau xen ke giam dan.")
        if len(cards) > max_movable_cards(state, dst.index):
            return MoveResult(False, "Vuot qua so la co the di chuyen.")
    elif len(cards) > 1:
        return MoveResult(False, "Chi tableau moi di duoc nhieu la.")

    if can_place_on_tableau(cards[0], state.tableau[dst.index]):
        return MoveResult(True)
    return MoveResult(False, "Khong the dat len cot dich.")


def apply_move(state: GameState, src: PileRef, dst: PileRef, start_index: int = -1,) -> tuple[MoveResult, list[Card]]:
    """Validate and apply move atomically. Returns moved cards when successful."""
    cards = pick_cards(state, src, start_index)
    check = validate_move(state, src, dst, cards)
    if not check.ok:
        return check, []

    moved = remove_picked_cards(state, src, start_index)
    push_cards(state, dst, moved)
    state.won = all(len(pile) == 13 for pile in state.foundations.values())
    return check, moved

