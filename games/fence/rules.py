"""Fence — buy the lot or quietly stash the goods.

RULESHEET
=========
Players: 2-4.  Components: one standard 52-card deck (no jokers, no dice).

A pile of stolen goods (the **lot**) sits on the table. Every player is a fence trying to buy
it. Cards are both your money and your prize.

Card values
-----------
2-10 are face value, Jack 11, Queen 12, King 13, Ace 14. Suits break ties only, in the order
Spades > Hearts > Diamonds > Clubs. Two cards never compare equal: compare value first, then
suit. Cards are written rank+suit, e.g. ``AS``, ``10H``, ``2C``.

Setup
-----
Seat the players 0..N-1. Shuffle the deck and deal 5 cards face down to each player. Flip the
top 2 cards of the deck face up to form the lot. The rest is the face-down draw pile. Everyone
starts at 0 points with an empty score pile. The house pile (discards) starts empty.

Round structure
---------------
*Step 1 — Restock.* If the lot is empty and the draw pile is not empty, flip the top 2 cards of
the draw pile into the lot (only 1 if only 1 card remains). If the lot already holds cards,
nothing happens.

*Step 2 — Commit (simultaneous, secret).* Every player who holds at least one card chooses
exactly one card from their hand and one of two modes:

* **Bid** — the card is placed face down as a bid for the lot.
* **Stash** — the card is placed face down to be banked quietly.

Players with an empty hand do not act this round. Nothing is revealed until every acting player
has committed. (In this implementation the choices are collected in seat order as hidden
choices: ``observe`` shows only *how many* players have committed, never what they chose.)

*Step 3 — Resolve.*

1. All committed cards are revealed with their modes.
2. Every stashed card goes to its owner's score pile and scores **half its value, rounded
   down** (A 7, K 6, Q 6, J 5, 10 -> 5, ..., 3 -> 1, 2 -> 1).
3. If at least one player bid, the highest bid (value, then suit) wins. The winner takes
   **every card in the lot** into their score pile and scores the **full value** of each one.
   The winner's own bid card goes to the house pile and is gone for good. Every losing bid card
   is placed face up into the lot, where it sweetens the prize for a later round.
4. If nobody bid, the lot is unchanged.
5. Each player, in seat order from seat 0, draws 1 card from the draw pile if it is not empty.

End of game
-----------
The game ends immediately after a Resolve step in which every hand is empty. Once the draw pile
runs out, hands shrink by one each round; players late in seat order may run out one round
earlier if the pile emptied mid-draw. Cards left in the lot at the end belong to nobody and
score nothing.

Winning
-------
Most points wins. Tie-breaks, in order: (1) among tied players, the one who won a lot most
recently (higher round number) wins; (2) otherwise the lowest seat index wins. ``scores``
encodes this by adding a tiny fraction (always well below 1 point) for recency and low seat, so
the reported number is the point total plus an invisible tie-break nudge.

Strategy
--------
A bid never fails for being too low: if you are the only bidder, a 2 takes the whole lot. But a
losing bid is a donation — a lost Ace becomes 14 points for whoever wins next. Stashing is safe
but small (about half value). Read the table: bluff cheap when you expect everyone to stash, and
save the Ace for a lot that has grown fat.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from random import Random

from gd_gamecore import GMLike

HAND_SIZE = 5
LOT_FLIP = 2
SUITS = "SHDC"  # highest to lowest for tie-breaking
SUIT_ORDER = {s: len(SUITS) - 1 - i for i, s in enumerate(SUITS)}
RANK_NAMES = {11: "J", 12: "Q", 13: "K", 14: "A"}
NAME_RANKS = {v: k for k, v in RANK_NAMES.items()}


def value(card: str) -> int:
    """Rank value of a card string: 2-10 face value, J 11, Q 12, K 13, A 14."""
    r = card[:-1]
    return NAME_RANKS.get(r) or int(r)


def key(card: str) -> tuple[int, int]:
    """Comparison key: value first, suit second (Spades high). Never equal for two cards."""
    return (value(card), SUIT_ORDER[card[-1]])


def make_deck() -> list[str]:
    return [f"{RANK_NAMES.get(r, str(r))}{s}" for s in SUITS for r in range(2, 15)]


@dataclass
class FenceState:
    hands: list[list[str]]
    draw_pile: list[str]
    lot: list[str]
    house: list[str]
    score_piles: list[list[str]]
    points: list[int]
    pending: dict[int, tuple[str, str]] = field(default_factory=dict)  # seat -> (mode, card)
    last_win_round: list[int] = field(default_factory=list)  # -1 = never won a lot
    round: int = 1
    over: bool = False
    log: tuple[str, ...] = ()  # short public summary of the last resolve


class Fence:
    """See module docstring for the rulesheet."""

    def __init__(self, n_players: int, gm: GMLike | None = None):
        if not 2 <= n_players <= 4:
            raise ValueError("2-4 players")
        self.n_players = n_players
        self.gm = gm

    # -- lifecycle -----------------------------------------------------------------------
    def setup(self, rng: Random) -> FenceState:
        deck = make_deck()
        rng.shuffle(deck)
        hands: list[list[str]] = [[] for _ in range(self.n_players)]
        for _ in range(HAND_SIZE):
            for h in hands:
                h.append(deck.pop(0))
        for h in hands:
            h.sort(key=key)
        lot = [deck.pop(0) for _ in range(min(LOT_FLIP, len(deck)))]
        return FenceState(
            hands=hands,
            draw_pile=deck,
            lot=lot,
            house=[],
            score_piles=[[] for _ in range(self.n_players)],
            points=[0] * self.n_players,
            last_win_round=[-1] * self.n_players,
        )

    # -- turn order ----------------------------------------------------------------------
    def _actors(self, s: FenceState) -> list[int]:
        return [p for p in range(self.n_players) if s.hands[p]]

    def current_player(self, s: FenceState) -> int:
        for p in self._actors(s):
            if p not in s.pending:
                return p
        return 0  # terminal / nothing left to decide

    def legal_actions(self, s: FenceState) -> list[tuple[str, str]]:
        if s.over:
            return []
        p = self.current_player(s)
        return [(mode, c) for c in s.hands[p] for mode in ("bid", "stash")]

    # -- transition ----------------------------------------------------------------------
    def step(self, state: FenceState, a: tuple[str, str], rng: Random) -> FenceState:
        s = copy.deepcopy(state)
        if s.over:
            raise ValueError("game is over")
        p = self.current_player(s)
        mode, card = a
        if mode not in ("bid", "stash"):
            raise ValueError(f"bad mode {mode!r}")
        if card not in s.hands[p]:
            raise ValueError(f"{card} not in hand of seat {p}")
        s.hands[p].remove(card)
        s.pending[p] = (mode, card)
        if any(q not in s.pending for q in range(self.n_players) if s.hands[q] or q in s.pending):
            return s  # still collecting hidden commitments
        return self._resolve(s)

    def _resolve(self, s: FenceState) -> FenceState:
        notes: list[str] = []
        bids: list[tuple[int, str]] = []
        for p in sorted(s.pending):
            mode, card = s.pending[p]
            if mode == "stash":
                gain = value(card) // 2
                s.score_piles[p].append(card)
                s.points[p] += gain
                notes.append(f"seat {p} stashed {card} (+{gain})")
            else:
                bids.append((p, card))
        if bids:
            w, wc = max(bids, key=lambda pc: key(pc[1]))
            gain = sum(value(c) for c in s.lot)
            s.score_piles[w].extend(s.lot)
            s.points[w] += gain
            s.last_win_round[w] = s.round
            s.house.append(wc)
            losers = [c for p, c in bids if p != w]
            notes.append(
                f"seat {w} won the lot ({len(s.lot)} cards, +{gain}) with {wc}"
                + (f"; losing bids {' '.join(losers)} join the lot" if losers else "")
            )
            s.lot = losers
        elif s.pending:
            notes.append("nobody bid; the lot stands")
        s.pending = {}
        for p in range(self.n_players):  # draws, seat order
            if s.draw_pile:
                s.hands[p].append(s.draw_pile.pop(0))
                s.hands[p].sort(key=key)
        s.log = tuple(notes)
        if not any(s.hands):
            s.over = True
            return s
        s.round += 1
        if not s.lot and s.draw_pile:  # Step 1: restock for the new round
            s.lot = [s.draw_pile.pop(0) for _ in range(min(LOT_FLIP, len(s.draw_pile)))]
        return s

    # -- results -------------------------------------------------------------------------
    def is_terminal(self, s: FenceState) -> bool:
        return s.over

    def scores(self, s: FenceState) -> list[float]:
        """Points plus a sub-point tie-break nudge: later lot win first, then lower seat."""
        return [
            float(pts) + 1e-4 * (s.last_win_round[p] + 1) + 1e-6 * (self.n_players - p)
            for p, pts in enumerate(s.points)
        ]

    # -- views ---------------------------------------------------------------------------
    def observe(self, s: FenceState, p: int) -> dict:
        return {
            "seat": p,
            "hand": tuple(s.hands[p]),
            "my_commit": s.pending.get(p),
            "lot": tuple(s.lot),
            "lot_value": sum(value(c) for c in s.lot),
            "points": tuple(s.points),
            "hand_sizes": tuple(len(h) for h in s.hands),
            "committed": len(s.pending),
            "draw_pile": len(s.draw_pile),
            "house": len(s.house),
            "score_piles": tuple(tuple(sp) for sp in s.score_piles),
            "last_win_round": tuple(s.last_win_round),
            "round": s.round,
            "over": s.over,
            "last_resolve": s.log,
        }

    def describe(self, s: FenceState) -> str:
        lot = " ".join(s.lot) or "empty"
        tail = "; ".join(s.log)
        return (
            f"round {s.round}{' (over)' if s.over else ''} lot=[{lot}] "
            f"({sum(value(c) for c in s.lot)} pts) points={s.points} "
            f"hands={[len(h) for h in s.hands]} draw={len(s.draw_pile)} "
            f"committed={len(s.pending)}/{len(self._actors(s)) + len(s.pending)}"
            + (f" | last: {tail}" if tail else "")
        )


GAME = Fence
