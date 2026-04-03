"""Data models and utility helpers for cards and piles."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Suit(str, Enum):
    CLUBS = "C"
    DIAMONDS = "D"
    HEARTS = "H"
    SPADES = "S"


RANK_LABELS = {
    1: "A",
    2: "2",
    3: "3",
    4: "4",
    5: "5",
    6: "6",
    7: "7",
    8: "8",
    9: "9",
    10: "10",
    11: "J",
    12: "Q",
    13: "K",
}

SUIT_SYMBOLS = {
    Suit.CLUBS: "♣",
    Suit.DIAMONDS: "♦",
    Suit.HEARTS: "♥",
    Suit.SPADES: "♠",
}


def is_red(suit: Suit) -> bool:
    return suit in (Suit.HEARTS, Suit.DIAMONDS)


@dataclass(frozen=True, slots=True)
class Card:
    suit: Suit
    rank: int

    @property
    def label(self) -> str:
        return f"{RANK_LABELS[self.rank]}{SUIT_SYMBOLS[self.suit]}"
