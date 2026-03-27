"""Mutable game state and setup helpers."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .models import Card, Suit


@dataclass(slots=True)
class GameState:
    # 8 tableau columns
    tableau: list[list[Card]] = field(default_factory=lambda: [[] for _ in range(8)])
    # 4 free cells (None means empty)
    free_cells: list[Card | None] = field(default_factory=lambda: [None, None, None, None])
    # 4 foundation piles by suit
    foundations: dict[Suit, list[Card]] = field(
        default_factory=lambda: {s: [] for s in (Suit.CLUBS, Suit.DIAMONDS, Suit.HEARTS, Suit.SPADES)}
    )
    won: bool = False


def build_shuffled_deck(rng: random.Random) -> list[Card]:
    """Create and shuffle a standard 52-card deck."""
    deck = [Card(suit=suit, rank=rank) for suit in Suit for rank in range(1, 14)]
    rng.shuffle(deck)
    return deck


def deal_new_game(seed: int | None = None) -> GameState:
    """Generate a fresh FreeCell board."""
    rng = random.Random(seed)
    deck = build_shuffled_deck(rng)
    state = GameState()

    # Deal one by one into 8 tableau columns.
    for idx, card in enumerate(deck):
        state.tableau[idx % 8].append(card)
    return state

