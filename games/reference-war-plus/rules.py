"""War Plus — reference game for the Game contract.

RULESHEET
=========
Players: 2-4.  Components: 52-card deck + 2 jokers.  No dice.

Setup
-----
Shuffle all 54 cards. Deal 5 cards to each player. The rest is the draw pile.

Play
----
A round is one *trick*. Starting with the leader (seat 0 in the first trick), each player in
clockwise order commits one card from their hand face-down. Nobody sees the committed cards until every player has committed, so the choice is
effectively simultaneous. (In this implementation the commitments are sequential hidden
choices: ``observe`` shows only *how many* cards are down, never which.)

When every player has committed, all cards are revealed. Card strength: 2 < 3 < ... < 10 < J <
Q < K < A (aces high, A = 14). A joker beats every card (strength 15).

**Every card has a price.** Each player pays half the strength of the card they committed,
rounded up (2-3 cost 1, 10 costs 5, A costs 7, joker costs 8). The trick winner collects the
full strength of every *opposing* card in the trick (plus any pot). So winning with a 5 over a
4 is a good deal; winning with an ace over a 2 is not.

Ties (two equal top cards, or two jokers) mean **no one** wins: the trick's total strength
minus one top card goes into a *pot* that the next trick's winner collects. The leader stays the
same after a tie.

After the reveal each player draws one card from the pile. If the pile has fewer cards than
players, the leftover cards are discarded face-down (hands always stay equal). The winner of a
trick gets the *last word*: they commit last in the next trick, so the player to their left
becomes the new leader.

End and scoring
---------------
The game is played over **two deals**: when every hand is empty, reshuffle all 54 cards and deal
again (the pot, if any, is discarded; points carry over). The game ends after the second deal. Score = strength collected − strength paid (may be
negative). A pot still unresolved at the end is discarded. Highest score wins; ties share.

Strategy note: dump low cards into tricks you expect to lose, win with the cheapest card that
beats the table, and weigh the joker's 15-point price against a fat pot.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from random import Random

from gd_cards import Card, Deck
from gd_gamecore import GMLike

HAND = 5
DEALS = 2
PRICE_DIV = 2


def price(strength: int) -> int:
    """Cost of committing a card: half its strength, rounded up (2..3 -> 1, A -> 7, joker -> 8)."""
    return -(-strength // PRICE_DIV)


@dataclass(frozen=True)
class WarState:
    hands: tuple[tuple[Card, ...], ...]
    deck: tuple[Card, ...]
    leader: int
    played: tuple[tuple[int, Card], ...]  # committed this trick, in commit order
    points: tuple[int, ...]  # collected strength minus paid strength
    pot: int  # opposing-card strength carried over from tied tricks
    deals_left: int = DEALS - 1  # redeals still to come


class WarPlus:
    """See module docstring for the rulesheet."""

    def __init__(self, n_players: int, gm: GMLike | None = None):
        if not 2 <= n_players <= 4:
            raise ValueError("2-4 players")
        self.n_players = n_players
        self.gm = gm

    # -- lifecycle -----------------------------------------------------------------------
    def setup(self, rng: Random) -> WarState:
        return self._deal(rng, (0,) * self.n_players, 0, DEALS - 1)

    def _deal(self, rng: Random, points: tuple[int, ...], leader: int, deals_left: int) -> WarState:
        deck = Deck(jokers=2).shuffle(rng)
        hands = tuple(tuple(sorted(h)) for h in deck.deal(self.n_players, HAND))
        return WarState(hands, tuple(deck.cards), leader, (), points, 0, deals_left)

    def current_player(self, s: WarState) -> int:
        return (s.leader + len(s.played)) % self.n_players

    def legal_actions(self, s: WarState) -> list[Card]:
        return list(s.hands[self.current_player(s)])

    def step(self, s: WarState, a: Card, rng: Random) -> WarState:
        p = self.current_player(s)
        if a not in s.hands[p]:
            raise ValueError(f"{a} not in hand of seat {p}")
        hands = list(s.hands)
        h = list(hands[p])
        h.remove(a)
        hands[p] = tuple(h)
        played = s.played + ((p, a),)
        if len(played) < self.n_players:
            return replace(s, hands=tuple(hands), played=played)
        s = self._resolve(replace(s, hands=tuple(hands), played=played))
        if not any(s.hands) and s.deals_left > 0:
            return self._deal(rng, s.points, s.leader, s.deals_left - 1)
        return s

    def _resolve(self, s: WarState) -> WarState:
        vals = {p: c.high_value() for p, c in s.played}
        best = max(vals.values())
        top = [p for p, v in vals.items() if v == best]
        points, pot, leader = list(s.points), s.pot, s.leader
        for p, v in vals.items():
            points[p] -= price(v)  # everyone pays for the card they committed
        if len(top) == 1:
            w = top[0]
            points[w] += sum(vals.values()) - vals[w] + pot
            pot, leader = 0, (w + 1) % self.n_players  # winner gets the last word next trick
        else:
            pot += sum(vals.values()) - best  # jokers/equal tops: the opposing strength pools
        deck = list(s.deck)
        hands = []
        refill = len(deck) >= self.n_players  # a short remainder is discarded so hands stay equal
        for h in s.hands:
            h = list(h)
            if refill:
                h.append(deck.pop(0))
            hands.append(tuple(sorted(h)))
        if not refill:
            deck = []
        return WarState(tuple(hands), tuple(deck), leader, (), tuple(points), pot, s.deals_left)

    def is_terminal(self, s: WarState) -> bool:
        return not any(s.hands) and not s.played

    def scores(self, s: WarState) -> list[float]:
        return [float(t) for t in s.points]

    # -- views ---------------------------------------------------------------------------
    def observe(self, s: WarState, p: int) -> tuple:
        return (
            tuple(str(c) for c in s.hands[p]),
            len(s.played),
            tuple(len(h) for h in s.hands),
            len(s.deck),
            s.points,
            s.pot,
            s.leader,
            s.deals_left,
        )

    def describe(self, s: WarState) -> str:
        down = ", ".join(f"seat {p}" for p, _ in s.played) or "none"
        return (
            f"deal {DEALS - s.deals_left}/{DEALS} points={list(s.points)} pot={s.pot} deck={len(s.deck)} leader=seat {s.leader}; "
            f"committed: {down}; hand sizes={[len(h) for h in s.hands]}"
        )


GAME = WarPlus
