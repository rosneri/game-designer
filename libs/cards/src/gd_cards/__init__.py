"""Standard 52-card deck with optional jokers. Pure, deterministic given a Random."""
from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from enum import IntEnum
from random import Random


class Suit(IntEnum):
    CLUBS = 0
    DIAMONDS = 1
    HEARTS = 2
    SPADES = 3

    @property
    def symbol(self) -> str:
        return "♣♦♥♠"[self]

    @property
    def color(self) -> str:
        return "red" if self in (Suit.DIAMONDS, Suit.HEARTS) else "black"


RANK_NAMES = {1: "A", 11: "J", 12: "Q", 13: "K"}
JOKER_RANK = 0


@dataclass(frozen=True, order=True)
class Card:
    """rank 1..13 (A=1, J=11, Q=12, K=13); rank 0 = joker (suit ignored, index in ``suit`` 0/1)."""

    rank: int
    suit: Suit | int

    @property
    def is_joker(self) -> bool:
        return self.rank == JOKER_RANK

    @property
    def rank_name(self) -> str:
        if self.is_joker:
            return "★"
        return RANK_NAMES.get(self.rank, str(self.rank))

    def high_value(self, ace_high: bool = True) -> int:
        """Numeric strength; Ace counts 14 when ace_high else 1. Joker 15."""
        if self.is_joker:
            return 15
        if self.rank == 1 and ace_high:
            return 14
        return self.rank

    def __str__(self) -> str:
        if self.is_joker:
            return f"★{self.suit}"
        return f"{self.rank_name}{Suit(self.suit).symbol}"

    @classmethod
    def parse(cls, s: str) -> Card:
        s = s.strip()
        if s.startswith("★") or s.upper().startswith("JOKER"):
            idx = int("".join(ch for ch in s if ch.isdigit()) or 0)
            return cls(JOKER_RANK, idx)
        sym = s[-1]
        suit = {"♣": Suit.CLUBS, "♦": Suit.DIAMONDS, "♥": Suit.HEARTS, "♠": Suit.SPADES,
                "C": Suit.CLUBS, "D": Suit.DIAMONDS, "H": Suit.HEARTS, "S": Suit.SPADES}[sym.upper() if sym.isalpha() else sym]
        r = s[:-1].upper()
        rank = {"A": 1, "J": 11, "Q": 12, "K": 13}.get(r) or int(r)
        return cls(rank, suit)


def standard_deck(jokers: int = 0) -> list[Card]:
    """Return an ordered 52-card deck plus ``jokers`` (0..2) jokers."""
    if not 0 <= jokers <= 2:
        raise ValueError("jokers must be 0..2")
    cards = [Card(rank, suit) for suit in Suit for rank in range(1, 14)]
    cards += [Card(JOKER_RANK, i) for i in range(jokers)]
    return cards


class Deck:
    """Mutable draw pile. All randomness comes from the supplied Random."""

    def __init__(self, cards: Iterable[Card] | None = None, jokers: int = 0):
        self.cards: list[Card] = list(cards) if cards is not None else standard_deck(jokers)

    def shuffle(self, rng: Random) -> Deck:
        rng.shuffle(self.cards)
        return self

    def draw(self, n: int = 1) -> list[Card]:
        if n > len(self.cards):
            raise IndexError("not enough cards")
        out, self.cards = self.cards[:n], self.cards[n:]
        return out

    def draw_one(self) -> Card:
        return self.draw(1)[0]

    def deal(self, n_players: int, per_player: int) -> list[list[Card]]:
        hands: list[list[Card]] = [[] for _ in range(n_players)]
        for _ in range(per_player):
            for h in hands:
                h.append(self.draw_one())
        return hands

    def put_bottom(self, cards: Iterable[Card]) -> None:
        self.cards.extend(cards)

    def put_top(self, cards: Iterable[Card]) -> None:
        self.cards = list(cards) + self.cards

    def __len__(self) -> int:
        return len(self.cards)

    def __iter__(self) -> Iterator[Card]:
        return iter(self.cards)

    def __bool__(self) -> bool:
        return bool(self.cards)


__all__ = ["JOKER_RANK", "Card", "Deck", "Suit", "standard_deck"]
