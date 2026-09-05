"""Loom — weave a 3x3 grid of drafted cards into eight scoring threads.

RULESHEET
=========
Players: 2-4.  Components: a standard 52-card deck (no jokers, no dice).
Ranks A,2,...,10,J,Q,K in four suits.

Setup
-----
Shuffle the whole deck face-down as the draw pile. Deal each player one card face-down as
their **hidden hand** (you may look at your own hand card at any time). Each player has an
empty 3x3 grid, their **weave**, cells addressed (row, column) with rows 0-2 top to bottom
and columns 0-2 left to right. A random start player is chosen. The round counter starts at 1.

Round structure
---------------
The game lasts exactly **9 rounds**. At the start of a round, cards are revealed from the draw
pile into a face-up **market** until the market holds P+1 cards (3 for two players, 4 for
three, 5 for four). Then, beginning with the round's start player and going clockwise, each
player takes exactly one turn. When all players have played, every card still in the market is
discarded face-down and is out of the game. The start player then passes clockwise to the
left, and the round counter goes up by one.

Turn — three steps
------------------
A turn is always the same three decisions, taken one after the other by the active player:

1. **Draw a thread.** Take one face-up card from the market. Everyone sees which card you
   took. You now hold two cards: this **drawn** card and your **hidden** hand card.
2. **Choose the strand.** Announce which of the two cards you will weave this turn — the
   drawn card or the hidden one. You do not reveal the hidden card when you choose it.
3. **Weave it.** Place the chosen card in any empty cell of your own grid.
   * The drawn card is placed **face-up**; your hidden hand card stays hidden and unchanged.
   * The hidden card is placed **face-down**, and the drawn card becomes your new hidden
     hand card. Opponents saw the card you took, so the secret is the identity of the card
     you just buried — a card you picked up in an earlier round.

The market holds P+1 cards at the start of a round and each player removes exactly one, so a
card is always on offer, and each player fills exactly one of their nine cells per round.
There is no passing and every step always has at least one legal choice.

End of game
-----------
The game ends the moment round 9 is finished. Every grid is then full. All face-down cards in
all grids are turned face-up. A player's leftover hidden hand card is discarded and never scores.

Scoring
-------
Each player scores their 8 **threads**: the 3 rows, the 3 columns, and the 2 diagonals
(0,0)-(1,1)-(2,2) and (0,2)-(1,1)-(2,0). A thread is exactly 3 cards and scores only its single
best pattern; the order of the cards inside a thread never matters:

* **Three of a kind** — all three ranks equal: **9 points**
* **Straight flush** — three consecutive ranks, all one suit: **8 points**
* **Straight** — three consecutive ranks, mixed suits: **4 points**
* **Flush** — all three cards one suit, not a straight: **3 points**
* **Pair** — exactly two cards share a rank: **1 point**
* anything else: **0 points**

While a grid is still being woven, this implementation reports a **running score**: complete
threads count exactly, and a thread holding two cards that can still grow into a pattern counts
a fifth of that pattern's value. Only the final all-complete total decides the game.

Straight order is A-2-3, 2-3-4, ..., J-Q-K, Q-K-A. The ace is low or high as you like, but
K-A-2 does not count: there is no wrap-around. A straight flush never also pays as a straight
or a flush, and three of a kind can be neither. Your final score is the sum of your 8 threads
(maximum useful total is well under 72). Highest score wins.

Tie-breaks
----------
Tied players are separated in this order: (1) the higher single best thread; (2) more cards of
their most common suit in the grid; (3) the player who sits **later** clockwise from the round-9
start player (they drafted last in the final round, so they are rewarded here). This always
gives one unique winner. In this implementation the three tie-breaks are folded into the final
score as a tiny fraction (less than 0.001 in total), so the reported scores stay readable while
the ranking is strict.

Strategy note
-------------
A card that finishes a row can also sit on a column and a diagonal, so the centre cell (1,1)
touches four threads and the corners three. Weaving the hidden card hides one card from everyone
and refreshes your secret, but it costs you a face-up card you already know; burying a useless
card to steal a strong market card is often worth more than a mediocre placement. Watch which
cards your neighbours need and take them first — the market is discarded at the end of the
round, so denial is free if the card is dead to you anyway.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from itertools import product
from random import Random

from gd_cards import Card, Deck
from gd_gamecore import GMLike

ROUNDS = 9
SIZE = 3
THREADS: tuple[tuple[tuple[int, int], ...], ...] = tuple(
    [tuple((r, c) for c in range(SIZE)) for r in range(SIZE)]
    + [tuple((r, c) for r in range(SIZE)) for c in range(SIZE)]
    + [tuple((i, i) for i in range(SIZE)), tuple((i, SIZE - 1 - i) for i in range(SIZE))]
)
THREE_KIND, STRAIGHT_FLUSH, STRAIGHT, FLUSH, PAIR = 9, 8, 4, 3, 1
FACTOR = 0.2


def thread_score(cards: tuple[Card, ...]) -> int:
    """Best pattern value of a complete 3-card thread (0 if incomplete or nothing)."""
    if len(cards) != SIZE or any(c is None for c in cards):
        return 0
    ranks = [c.rank for c in cards]
    if ranks[0] == ranks[1] == ranks[2]:
        return THREE_KIND
    flush = len({int(c.suit) for c in cards}) == 1
    straight = False
    for vals in product(*[(1, 14) if r == 1 else (r,) for r in ranks]):
        v = sorted(vals)
        if v[0] + 1 == v[1] and v[1] + 1 == v[2]:
            straight = True
            break
    if straight:
        return STRAIGHT_FLUSH if flush else STRAIGHT
    if flush:
        return FLUSH
    return PAIR if len(set(ranks)) == 2 else 0


@dataclass
class LoomState:
    """Full game state. ``grids[p][r][c]`` is None or (Card, face_up)."""

    n_players: int
    round: int = 1
    start_player: int = 0
    current_player: int = 0
    turns_taken: int = 0
    draw_pile: list[Card] = field(default_factory=list)
    discard_pile: list[Card] = field(default_factory=list)
    market: list[Card] = field(default_factory=list)
    grids: list[list[list[tuple[Card, bool] | None]]] = field(default_factory=list)
    hands: list[Card | None] = field(default_factory=list)
    phase: str = "turn"
    step_stage: str = "draw"  # "draw" -> "choose" -> "weave"
    drawn: Card | None = None  # card taken from the market this turn (public)
    strand: str | None = None  # "drawn" or "hidden": the card announced in step 2
    final_start_player: int = 0


class Loom:
    """See module docstring for the rulesheet."""

    def __init__(self, n_players: int, gm: GMLike | None = None):
        if not 2 <= n_players <= 4:
            raise ValueError("2-4 players")
        self.n_players = n_players
        self.gm = gm

    # -- lifecycle -----------------------------------------------------------------------
    @property
    def market_size(self) -> int:
        return self.n_players + 1

    def setup(self, rng: Random) -> LoomState:
        deck = Deck(jokers=0).shuffle(rng)
        start = rng.randrange(self.n_players)
        s = LoomState(
            n_players=self.n_players,
            start_player=start,
            current_player=start,
            draw_pile=list(deck.cards),
            grids=[[[None] * SIZE for _ in range(SIZE)] for _ in range(self.n_players)],
            hands=[None] * self.n_players,
        )
        for p in range(self.n_players):
            s.hands[p] = s.draw_pile.pop(0)
        self._refill_market(s)
        return s

    def _refill_market(self, s: LoomState) -> None:
        while len(s.market) < self.market_size and s.draw_pile:
            s.market.append(s.draw_pile.pop(0))

    def current_player(self, s: LoomState) -> int:
        return s.current_player

    # -- actions -------------------------------------------------------------------------
    def _empty_cells(self, s: LoomState, p: int) -> list[tuple[int, int]]:
        return [(r, c) for r in range(SIZE) for c in range(SIZE) if s.grids[p][r][c] is None]

    def legal_actions(self, s: LoomState) -> list[tuple]:
        if s.phase != "turn":
            return []
        p = s.current_player
        if s.step_stage == "draw":
            return [("draw", i) for i in range(len(s.market))]
        if s.step_stage == "choose":
            acts: list[tuple] = [("strand", "drawn")]
            if s.hands[p] is not None:
                acts.append(("strand", "hidden"))
            return acts
        return [("weave", r, c) for (r, c) in self._empty_cells(s, p)]

    def step(self, s: LoomState, a: tuple, rng: Random) -> LoomState:
        if s.phase != "turn":
            raise ValueError("game is over")
        s = copy.deepcopy(s)
        p = s.current_player
        kind = a[0]
        if kind == "draw":
            if s.step_stage != "draw":
                raise ValueError("not the draw step")
            i = a[1]
            if not 0 <= i < len(s.market):
                raise ValueError(f"no market card {i}")
            s.drawn = s.market.pop(i)
            s.step_stage = "choose"
            return s
        if kind == "strand":
            if s.step_stage != "choose":
                raise ValueError("not the choose step")
            which = a[1]
            if which not in ("drawn", "hidden"):
                raise ValueError(f"unknown strand {which!r}")
            if which == "hidden" and s.hands[p] is None:
                raise ValueError("empty hand")
            s.strand = which
            s.step_stage = "weave"
            return s
        if kind != "weave":
            raise ValueError(f"unknown action {a!r}")
        if s.step_stage != "weave":
            raise ValueError("not the weave step")
        _, r, c = a
        if not (0 <= r < SIZE and 0 <= c < SIZE):
            raise ValueError(f"no cell ({r},{c})")
        if s.grids[p][r][c] is not None:
            raise ValueError(f"cell ({r},{c}) is occupied")
        if s.strand == "drawn":  # face-up, hidden hand card untouched
            s.grids[p][r][c] = (s.drawn, True)
        else:  # bury the hidden card face-down; the drawn card becomes the new secret
            s.grids[p][r][c] = (s.hands[p], False)
            s.hands[p] = s.drawn
        s.drawn = None
        s.strand = None
        s.step_stage = "draw"

        s.turns_taken += 1
        s.current_player = (s.current_player + 1) % self.n_players
        if s.turns_taken == self.n_players:  # end of round
            s.discard_pile.extend(s.market)
            s.market.clear()
            if s.round == ROUNDS:
                self._finish(s)
                return s
            s.round += 1
            s.turns_taken = 0
            s.start_player = (s.start_player + 1) % self.n_players
            s.current_player = s.start_player
            self._refill_market(s)
        return s

    def _finish(self, s: LoomState) -> None:
        s.final_start_player = s.start_player  # round 9 has not advanced it yet
        for p in range(self.n_players):  # flip every buried card face-up
            for r in range(SIZE):
                for c in range(SIZE):
                    cell = s.grids[p][r][c]
                    if cell is not None:
                        s.grids[p][r][c] = (cell[0], True)
            if s.hands[p] is not None:  # leftover hand card is discarded, never scores
                s.discard_pile.append(s.hands[p])
                s.hands[p] = None
        s.phase = "game_over"

    def is_terminal(self, s: LoomState) -> bool:
        return s.phase == "game_over"

    # -- scoring -------------------------------------------------------------------------
    def _thread_values(self, s: LoomState, p: int) -> list[int]:
        out = []
        for thread in THREADS:
            cells = [s.grids[p][r][c] for (r, c) in thread]
            out.append(
                0 if any(x is None for x in cells) else thread_score(tuple(x[0] for x in cells))
            )
        return out

    def _thread_progress(self, s: LoomState, p: int, factor: float) -> float:
        """Running value of a partly woven grid: complete threads exact, pairs of cards partial."""
        total = 0.0
        for thread in THREADS:
            placed = [s.grids[p][r][c] for (r, c) in thread]
            cards = [x[0] for x in placed if x is not None]
            if len(cards) == SIZE:
                total += thread_score(tuple(cards))
            elif len(cards) == 2:
                a, b = cards
                if a.rank == b.rank:
                    best = THREE_KIND
                else:
                    same_suit = int(a.suit) == int(b.suit)
                    va = (1, 14) if a.rank == 1 else (a.rank,)
                    vb = (1, 14) if b.rank == 1 else (b.rank,)
                    near = min(abs(x - y) for x in va for y in vb) in (1, 2)
                    best = (STRAIGHT_FLUSH if same_suit else STRAIGHT) if near else (
                        FLUSH if same_suit else 0)
                total += factor * best
        return total

    def scores(self, s: LoomState) -> list[float]:
        if s.phase != "game_over":
            return [self._thread_progress(s, p, FACTOR) for p in range(self.n_players)]
        totals = [float(sum(self._thread_values(s, p))) for p in range(self.n_players)]
        for p in range(self.n_players):  # tie-breaks folded in as < 0.001
            best = max(self._thread_values(s, p))
            suits = [int(cell[0].suit) for row in s.grids[p] for cell in row if cell is not None]
            top_suit = max((suits.count(x) for x in set(suits)), default=0)
            seat = (p - s.final_start_player) % self.n_players
            totals[p] += best * 1e-4 + top_suit * 1e-6 + seat * 1e-8
        return totals

    # -- views ---------------------------------------------------------------------------
    def _grid_view(self, s: LoomState, p: int, owner_sees: bool) -> tuple[tuple[str, ...], ...]:
        rows = []
        for r in range(SIZE):
            row = []
            for c in range(SIZE):
                cell = s.grids[p][r][c]
                if cell is None:
                    row.append(".")
                elif cell[1] or owner_sees:
                    row.append(str(cell[0]) if cell[1] else f"[{cell[0]}]")
                else:
                    row.append("??")
            rows.append(tuple(row))
        return tuple(rows)

    def observe(self, s: LoomState, p: int) -> dict:
        return {
            "seat": p,
            "round": s.round,
            "phase": s.phase,
            "step": s.step_stage,
            "start_player": s.start_player,
            "current_player": s.current_player,
            "market": tuple(str(c) for c in s.market),
            "drawn": str(s.drawn) if s.drawn is not None else None,
            "strand": s.strand,
            "hand": str(s.hands[p]) if s.hands[p] is not None else None,
            "my_grid": self._grid_view(s, p, owner_sees=True),
            "grids": tuple(
                self._grid_view(s, q, owner_sees=(q == p)) for q in range(self.n_players)
            ),
            "face_down_counts": tuple(
                sum(1 for row in s.grids[q] for cell in row if cell is not None and not cell[1])
                for q in range(self.n_players)
            ),
            "draw_count": len(s.draw_pile),
            "discard_count": len(s.discard_pile),
            "my_threads": tuple(self._thread_values(s, p)),
        }

    def describe(self, s: LoomState) -> str:
        if s.phase == "game_over":
            return "game over; scores=" + ", ".join(
                f"seat {p}: {sum(self._thread_values(s, p))}" for p in range(self.n_players)
            )
        market = " ".join(f"{i}:{c}" for i, c in enumerate(s.market)) or "empty"
        filled = [
            sum(1 for row in s.grids[p] for cell in row if cell is not None)
            for p in range(self.n_players)
        ]
        held = f" drawn={s.drawn}" if s.drawn is not None else ""
        return (
            f"round {s.round}/{ROUNDS} start=seat {s.start_player} turn=seat {s.current_player} "
            f"step={s.step_stage}{held}; market: {market}; cells filled={filled}; "
            f"draw={len(s.draw_pile)}"
        )


GAME = Loom
