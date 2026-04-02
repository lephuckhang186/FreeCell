"""Kỹ thuật / cơ sở dùng chung cho BFS, IDS, UCS, A*."""

from __future__ import annotations

import sys
import threading
import time

from .models import is_red
from .rules import (
    PileRef,
    PileType,
    apply_move,
    max_movable_cards,
    pick_cards,
    validate_move,
)
from .state import GameState

# Bật DEBUG_STATS=True để in thống kê định kỳ; mỗi nhóm solver dùng REPORT_INTERVAL riêng.
DEBUG_STATS = True
REPORT_INTERVAL_BFS_IDS = 1000  # BFS, IDS (DFS iterative deepening)
REPORT_INTERVAL_UCS_ASTAR = 100  # UCS, A*

# Sentinel: IDS dls() trả về khi bị hủy (UI timeout / cancel event)
SOLVER_IDS_CANCELLED = object()


class MoveCostConfig:
    """Cấu hình cho move_cost function."""

    def __init__(self, algorithm: str = "ucs"):
        self.algorithm = algorithm  # 'ucs' hoặc 'astar'

        if algorithm == "ucs":
            self.BASE_COST = 10.0
            self.EPSILON = 0.001
            self.MIN_COST = 0.1
            self.FC_PENALTY_BASE = 8.0
            self.FC_PENALTY_PER_EMPTY = 3.0
            self.FOUNDATION_REWARD = 15.0
            self.EMPTY_COLUMN_REWARD = 1.0
            self.FREECELL_RELEASE_REWARD = 3.0
            self.NATURAL_MOVE_REWARD = 2.0
            self.FOUNDATION_SRC_PENALTY = 15.0
        else:
            self.BASE_COST = 1.0
            self.EPSILON = 0.001
            self.MIN_COST = 0.001
            self.FC_PENALTY_BASE = 0.02
            self.FC_PENALTY_PER_EMPTY = 0.01
            self.FOUNDATION_REWARD = 0.05
            self.EMPTY_COLUMN_REWARD = 0.03
            self.FREECELL_RELEASE_REWARD = 0.02
            self.NATURAL_MOVE_REWARD = 0.01
            self.FOUNDATION_SRC_PENALTY = 3.0

    def get_epsilon(self) -> float:
        return self.EPSILON

    def get_min_cost(self) -> float:
        return self.MIN_COST


class FreeCellSolverBase:
    def __init__(
        self,
        initial_state: GameState,
        cancel_event: threading.Event | None = None,
    ):
        self.initial_state = initial_state
        self._cancel_event = cancel_event

    def _solver_cancelled(self) -> bool:
        return self._cancel_event is not None and self._cancel_event.is_set()

    def _return_cancelled(
        self, start_time: float, expanded_nodes: int, **extra: object
    ) -> dict:
        out: dict = {
            "path": None,
            "search_time": time.time() - start_time,
            "expanded_nodes": expanded_nodes,
            "cancelled": True,
        }
        out.update(extra)
        return out

    def _report_stats(
        self,
        phase: str,
        start_time: float,
        expanded_nodes: int,
        frontier_size: int,
        depth: int,
        *,
        interval: int,
    ) -> None:
        if not DEBUG_STATS:
            return
        if expanded_nodes > 0 and expanded_nodes % interval:
            return
        elapsed = time.time() - start_time
        print(
            f"[DEBUG][{phase}] expanded={expanded_nodes}, frontier={frontier_size}, depth={depth}, elapsed={elapsed:.2f}s"
        )

    def hash_state(self, state: GameState) -> bytes:
        suit_idx = {"C": 0, "D": 1, "H": 2, "S": 3}

        f_bytes = []
        for s in ("C", "D", "H", "S"):
            pile = state.foundations.get(s, [])
            f_bytes.append(pile[-1].rank if pile else 0)

        fc_bytes = []
        for c in state.free_cells:
            if c is None:
                fc_bytes.append(0)
            else:
                fc_bytes.append(suit_idx[c.suit.value] * 13 + c.rank)
        fc_bytes.sort()

        tab_cols = []
        for col in state.tableau:
            col_b = bytearray()
            for c in col:
                col_b.append(suit_idx[c.suit.value] * 13 + c.rank)
            tab_cols.append(bytes(col_b))
        tab_cols.sort()

        tab_bytes = bytearray()
        for b in tab_cols:
            tab_bytes.extend(b)
            tab_bytes.append(255)

        return bytes(f_bytes + fc_bytes) + bytes(tab_bytes)

    def _state_exact_key(self, state: GameState) -> bytes:
        suit_idx = {"C": 0, "D": 1, "H": 2, "S": 3}
        f_bytes = []
        for s in ("C", "D", "H", "S"):
            pile = state.foundations.get(s, [])
            f_bytes.append(pile[-1].rank if pile else 0)

        fc_bytes = []
        for c in state.free_cells:
            if c is None:
                fc_bytes.append(0)
            else:
                fc_bytes.append(suit_idx[c.suit.value] * 13 + c.rank)

        tab_bytes = bytearray()
        for col in state.tableau:
            for c in col:
                tab_bytes.append(suit_idx[c.suit.value] * 13 + c.rank)
            tab_bytes.append(255)

        return bytes(f_bytes + fc_bytes) + bytes(tab_bytes)

    def is_win_state(self, state: GameState) -> bool:
        return sum(len(pile) for pile in state.foundations.values()) == 52

    def _tableau_sequences(self, column: list) -> list[tuple[int, int]]:
        sequences: list[tuple[int, int]] = []
        if not column:
            return sequences
        seq_len = 1
        sequences.append((len(column) - 1, seq_len))
        prev_card = column[-1]
        for idx in range(len(column) - 2, -1, -1):
            candidate = column[idx]
            if (
                is_red(candidate.suit) == is_red(prev_card.suit)
                or candidate.rank != prev_card.rank + 1
            ):
                break
            seq_len += 1
            sequences.append((idx, seq_len))
            prev_card = candidate
        return sequences

    def _fmt_card(self, card) -> str:
        if card is None:
            return "__"
        rank_map = {1: "A", 11: "J", 12: "Q", 13: "K"}
        r = rank_map.get(card.rank, str(card.rank))
        s = card.suit.value[0].upper()
        return f"{r}{s}"

    def _fmt_pile(self, pile_ref: PileRef) -> str:
        short = {
            PileType.TABLEAU: "TAB",
            PileType.FREECELL: "FC",
            PileType.FOUNDATION: "FND",
        }
        return f"{short[pile_ref.kind]}[{pile_ref.index}]"

    def _fmt_move(self, state: GameState, move: tuple) -> str:
        src, dst, start_idx = move
        cards = pick_cards(state, src, start_idx)
        cards_str = ",".join(self._fmt_card(c) for c in cards) if cards else "?"
        return f"{cards_str} {self._fmt_pile(src)}->{self._fmt_pile(dst)}"

    def _fmt_state_brief(self, state: GameState) -> str:
        fnd = []
        for s in ("C", "D", "H", "S"):
            pile = state.foundations.get(s, [])
            fnd.append(f"{s}:{pile[-1].rank if pile else 0}")
        fc_empty = sum(1 for c in state.free_cells if c is None)
        tab_empty = sum(1 for col in state.tableau if not col)
        fc_cards = [self._fmt_card(c) for c in state.free_cells]
        return (
            f"FND=[{','.join(fnd)}] "
            f"FC=[{','.join(fc_cards)}]({fc_empty} trống) "
            f"TAB_empty={tab_empty}"
        )

    def _is_safe_to_foundation(self, state: GameState, card) -> bool:
        from .models import Suit

        if card.rank <= 2:
            return True
        needed_below = card.rank - 2
        if is_red(card.suit):
            black_suits = [Suit.CLUBS, Suit.SPADES]
            return all(
                len(state.foundations.get(s, [])) >= needed_below for s in black_suits
            )
        red_suits = [Suit.DIAMONDS, Suit.HEARTS]
        return all(
            len(state.foundations.get(s, [])) >= needed_below for s in red_suits
        )

    def _apply_forced_foundations(self, state: GameState) -> tuple[bool, list]:
        any_applied = False
        moves_applied = []
        changed = True
        while changed:
            changed = False
            for fc_idx, card in enumerate(state.free_cells):
                if card is None:
                    continue
                src = PileRef(PileType.FREECELL, fc_idx)
                for f_idx in range(4):
                    dst = PileRef(PileType.FOUNDATION, f_idx)
                    if validate_move(state, src, dst, [card]).ok and self._is_safe_to_foundation(
                        state, card
                    ):
                        apply_move(state, src, dst, -1)
                        moves_applied.append((src, dst, -1))
                        changed = True
                        any_applied = True
                        break
            for col_idx, col in enumerate(state.tableau):
                if not col:
                    continue
                card = col[-1]
                src = PileRef(PileType.TABLEAU, col_idx)
                for f_idx in range(4):
                    dst = PileRef(PileType.FOUNDATION, f_idx)
                    if validate_move(state, src, dst, [card]).ok and self._is_safe_to_foundation(
                        state, card
                    ):
                        apply_move(state, src, dst, -1)
                        moves_applied.append((src, dst, -1))
                        changed = True
                        any_applied = True
                        break
        return any_applied, moves_applied

    def get_all_possible_move(self, state: GameState):
        moves = []

        tableau_sources = [
            PileRef(PileType.TABLEAU, idx)
            for idx, column in enumerate(state.tableau)
            if column
        ]
        freecell_sources = [
            PileRef(PileType.FREECELL, idx)
            for idx, card in enumerate(state.free_cells)
            if card
        ]
        src_piles = tableau_sources + freecell_sources

        dst_tableau = [PileRef(PileType.TABLEAU, i) for i in range(8)]

        empty_fc_idx = -1
        for idx in range(4):
            if state.free_cells[idx] is None:
                empty_fc_idx = idx
                break

        dst_freecells = []
        for idx, card in enumerate(state.free_cells):
            if card is None:
                if idx == empty_fc_idx:
                    dst_freecells.append(PileRef(PileType.FREECELL, idx))

        dst_foundations = [PileRef(PileType.FOUNDATION, i) for i in range(4)]
        dst_piles = dst_tableau + dst_freecells + dst_foundations

        empty_tab_count = sum(1 for col in state.tableau if not col)

        for src in src_piles:
            if src.kind == PileType.TABLEAU:
                sequences = self._tableau_sequences(state.tableau[src.index])
            else:
                sequences = [(-1, 1)]
            if not sequences:
                continue

            for dst in dst_piles:
                if src == dst:
                    continue
                allow_multi = dst.kind == PileType.TABLEAU
                max_cards = max_movable_cards(state, dst.index) if allow_multi else 1

                for start_index, seq_len in sequences:
                    if not allow_multi and seq_len != 1:
                        continue
                    if allow_multi and seq_len > max_cards:
                        continue

                    if (
                        dst.kind == PileType.TABLEAU
                        and not state.tableau[dst.index]
                        and src.kind == PileType.TABLEAU
                        and start_index == len(state.tableau[src.index]) - 1
                        and empty_tab_count >= 2
                    ):
                        continue

                    if (
                        dst.kind == PileType.TABLEAU
                        and not state.tableau[dst.index]
                        and src.kind == PileType.TABLEAU
                        and len(state.tableau[src.index]) == 1
                    ):
                        continue

                    cards = pick_cards(state, src, start_index)
                    if not cards:
                        continue

                    result = validate_move(state, src, dst, cards)
                    if result.ok:
                        moves.append((src, dst, start_index))

        def _score_move(m: tuple[PileRef, PileRef, int]) -> int:
            dst_pile = m[1]
            if dst_pile.kind == PileType.FOUNDATION:
                return -1
            if dst_pile.kind == PileType.TABLEAU:
                return 0
            if dst_pile.kind == PileType.FREECELL:
                return 1
            return 2

        moves.sort(key=_score_move)
        return moves

    def _auto_move_to_foundation_v2(self, state: GameState):
        from .models import Suit

        _SUITS = list(Suit)
        _SUIT_TO_IDX = {s: i for i, s in enumerate(_SUITS)}

        auto_moves = []
        auto_cards = []
        changed = True
        while changed:
            changed = False
            for i, card in enumerate(state.free_cells):
                if card and self._is_safe_to_foundation_v2(card, state):
                    src, dst = (
                        PileRef(PileType.FREECELL, i),
                        PileRef(PileType.FOUNDATION, _SUIT_TO_IDX[card.suit]),
                    )
                    _, moved = apply_move(state, src, dst, -1)
                    auto_moves.append((src, dst, -1))
                    auto_cards.append(moved)
                    changed = True
                    break
            if changed:
                continue
            for i, col in enumerate(state.tableau):
                if col and self._is_safe_to_foundation_v2(col[-1], state):
                    card = col[-1]
                    src, dst = (
                        PileRef(PileType.TABLEAU, i),
                        PileRef(PileType.FOUNDATION, _SUIT_TO_IDX[card.suit]),
                    )
                    si = len(col) - 1
                    _, moved = apply_move(state, src, dst, si)
                    auto_moves.append((src, dst, si))
                    auto_cards.append(moved)
                    changed = True
                    break
        return auto_moves, auto_cards

    def _is_safe_to_foundation_v2(self, card, state) -> bool:
        from .models import Suit

        suit = card.suit
        rank = card.rank

        foundation_top = len(state.foundations.get(suit, []))
        if rank != foundation_top + 1:
            return False

        opposite_suits = {
            Suit.SPADES: [Suit.HEARTS, Suit.DIAMONDS],
            Suit.CLUBS: [Suit.HEARTS, Suit.DIAMONDS],
            Suit.HEARTS: [Suit.SPADES, Suit.CLUBS],
            Suit.DIAMONDS: [Suit.SPADES, Suit.CLUBS],
        }

        if rank <= 2:
            return True

        for opp in opposite_suits[suit]:
            if len(state.foundations.get(opp, [])) < rank - 1:
                return False
        return True

    def get_move_cost(
        self,
        current_state: GameState,
        move: tuple[PileRef, PileRef, int],
        config: MoveCostConfig | None = None,
    ) -> float:
        if config is None:
            config = MoveCostConfig("ucs")
        src, dst, start_index = move
        cost = config.BASE_COST

        empty_freecell = sum(1 for fc in current_state.free_cells if fc is None)
        empty_tableau = sum(1 for col in current_state.tableau if not col)
        total_freecell = len(current_state.free_cells)

        if dst.kind == PileType.FOUNDATION:
            cost -= config.FOUNDATION_REWARD
        elif dst.kind == PileType.FREECELL:
            penalty = config.FC_PENALTY_BASE + (
                empty_freecell * config.FC_PENALTY_PER_EMPTY
            )
            cost += penalty
        elif dst.kind == PileType.TABLEAU:
            if src.kind == PileType.TABLEAU and start_index == 0:
                reward = config.EMPTY_COLUMN_REWARD * (1 + empty_tableau * 0.5)
                cost -= reward
            elif src.kind == PileType.FREECELL:
                occupied_freecell = total_freecell - empty_freecell
                reward = config.FREECELL_RELEASE_REWARD * (
                    1 + occupied_freecell * 0.5
                )
                cost -= reward
            if self._is_natural_tableau_move(current_state, src, dst, start_index):
                cost -= config.NATURAL_MOVE_REWARD

        if src.kind == PileType.FOUNDATION:
            cost += config.FOUNDATION_SRC_PENALTY
            if dst.kind == PileType.FREECELL:
                cost += config.FOUNDATION_SRC_PENALTY

        if config.algorithm == "ucs" and self._is_useless_move(
            current_state, src, dst, start_index
        ):
            cost += config.EPSILON * 0.5

        min_cost = config.get_epsilon()
        return max(cost, min_cost)

    def _is_natural_tableau_move(
        self, state: GameState, src: PileRef, dst: PileRef, start_index: int
    ) -> bool:
        src_pile = pick_cards(state, src, start_index)
        dst_pile = state.tableau[dst.index] if dst.kind == PileType.TABLEAU else []
        if not dst_pile or not src_pile:
            return False

        top_dst = dst_pile[-1]
        moved_card = src_pile[0]

        return is_red(top_dst.suit) != is_red(moved_card.suit) and top_dst.rank == moved_card.rank + 1

    def _is_useless_move(
        self, state: GameState, src: PileRef, dst: PileRef, start_index: int
    ) -> bool:
        if src.kind == PileType.FREECELL and dst.kind == PileType.FREECELL:
            return True

        src_pile_len = (
            len(state.tableau[src.index]) if src.kind == PileType.TABLEAU else 1
        )
        if (
            src.kind == PileType.TABLEAU
            and dst.kind == PileType.TABLEAU
            and src_pile_len - start_index == 1
            and start_index == 0
        ):
            return True

        return False

    def heuristic(self, state: GameState) -> int:
        cards_in_foundation = sum(len(pile) for pile in state.foundations.values())
        h_score = (52 - cards_in_foundation) * 5

        for col_idx, col in enumerate(state.tableau):
            if not col:
                continue

            for i in range(len(col)):
                card = col[i]

                if i < len(col) - 1:
                    next_card = col[i + 1]
                    if is_red(card.suit) == is_red(next_card.suit) or next_card.rank != card.rank - 1:
                        h_score += 2

                foundation_pile = state.foundations.get(card.suit, [])
                next_needed_rank = len(foundation_pile) + 1
                if card.rank == next_needed_rank:
                    cards_blocking = len(col) - 1 - i
                    h_score += cards_blocking * 10

            reversal_penalty = 0
            for i in range(len(col) - 1):
                lower = col[i]
                for j in range(i + 1, len(col)):
                    upper = col[j]
                    if lower.suit == upper.suit and lower.rank < upper.rank:
                        reversal_penalty += 1
            h_score += min(reversal_penalty, 20) * 2

        occupied_fc = sum(1 for c in state.free_cells if c is not None)
        h_score += occupied_fc * 2

        return h_score
