"""Dummy Dice Draft — a minimal fixture game for gauntlet tests.

Each player holds 3 cards. On your turn play one card and roll 2d6: you score the roll total,
plus a bonus of BONUS if the card's rank is 7 or higher. The dice are rolled before you choose. Hands refill from the deck (reshuffled from
discards when empty). After ROUNDS rounds per player the highest total wins.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from random import Random

from gd_cards import Card, Deck
from gd_dice import roll_d6
from gd_gamecore import GMLike

ROUNDS = 45
HAND = 3
BONUS = 2


@dataclass
class S:
    turn: int
    hands: list[list[Card]]
    deck: list[Card]
    discard: list[Card]
    score: list[float]
    roll: tuple[int, ...]
    log: list[str] = field(default_factory=list)


class DummyDiceDraft:
    def __init__(self, n_players: int, gm: GMLike | None = None):
        self.n_players = n_players
        self.gm = gm

    def setup(self, rng: Random) -> S:
        d = Deck().shuffle(rng)
        return S(0, d.deal(self.n_players, HAND), d.cards, [], [0.0] * self.n_players, roll_d6(rng, 2).values)

    def current_player(self, s: S) -> int:
        return s.turn % self.n_players

    def legal_actions(self, s: S) -> list:
        return [str(c) for c in s.hands[self.current_player(s)]]

    def step(self, s: S, a, rng: Random) -> S:
        s = copy.deepcopy(s)
        p = self.current_player(s)
        card = next(c for c in s.hands[p] if str(c) == a)
        s.discard += s.hands[p]
        s.hands[p] = []
        gain = sum(s.roll) + (BONUS if card.rank >= 7 else 0)
        s.score[p] += gain
        for _ in range(HAND):
            if not s.deck:
                s.deck, s.discard = s.discard, []
                rng.shuffle(s.deck)
            s.hands[p].append(s.deck.pop())
        s.log = s.log[-5:] + [f"P{p} plays {card} with roll {s.roll} +{gain}"]
        s.roll = roll_d6(rng, 2).values
        s.turn += 1
        return s

    def is_terminal(self, s: S) -> bool:
        return s.turn >= ROUNDS * self.n_players

    def scores(self, s: S) -> list[float]:
        return list(s.score)

    def observe(self, s: S, p: int):
        return {"turn": s.turn, "roll": s.roll, "hand": [str(c) for c in s.hands[p]], "scores": list(s.score)}

    def describe(self, s: S) -> str:
        return f"turn {s.turn} scores {s.score} | " + "; ".join(s.log[-2:])


GAME = DummyDiceDraft
