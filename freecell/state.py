"""Mutable game state and setup helpers."""

from __future__ import annotations

import random
import os
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


def get_card_from_str(card_str: str) -> Card:
    """Convert a string like 'AH', 'TC', '2D' to a Card object."""
    rank_char = card_str[0]
    suit_char = card_str[1]
    
    # Map rank
    if rank_char == 'A':
        rank = 1
    elif rank_char == 'T':
        rank = 10
    elif rank_char == 'J':
        rank = 11
    elif rank_char == 'Q':
        rank = 12
    elif rank_char == 'K':
        rank = 13
    else:
        rank = int(rank_char)
        
    # Map suit
    if suit_char == 'C':
        suit = Suit.CLUBS
    elif suit_char == 'D':
        suit = Suit.DIAMONDS
    elif suit_char == 'H':
        suit = Suit.HEARTS
    elif suit_char == 'S':
        suit = Suit.SPADES
    else:
        raise ValueError(f"Unknown suit: {suit_char}")
        
    return Card(suit=suit, rank=rank)


def generate_state_testcase(testcase_num: int = 1) -> GameState:
    """Load a specific testcase from the testcase folder and generate GameState."""
    state = GameState()
    
    # Locate the testcase file
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    file_path = os.path.join(base_dir, "testcase", f"testcase{testcase_num}.txt")
    
    if not os.path.exists(file_path):
        print(f"Khong tim thay {file_path}, dang fall back ve default deal.")
        return deal_new_game()
        
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    # Standard Freecell text format: cards are listed row by row across columns
    for row_lines in lines:
        if not row_lines.strip():
            continue
        cards = row_lines.strip().split()
        for col_idx, card_str in enumerate(cards):
            card = get_card_from_str(card_str)
            state.tableau[col_idx].append(card)
            
    return state


def deal_new_game(seed: int | None = None) -> GameState:
    """Generate a fresh FreeCell board."""
    rng = random.Random(seed)
    deck = build_shuffled_deck(rng)
    state = GameState()

    # Deal one by one into 8 tableau columns.
    for idx, card in enumerate(deck):
        state.tableau[idx % 8].append(card)
    return state

