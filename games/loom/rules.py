"""Loom — draft cards into a 3x3 weave; every completed row, column and diagonal pays at once.

The rulesheet is the ``Loom`` class docstring.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from itertools import product
from random import Random

from gd_cards import Card, Deck
from gd_gamecore import GMLike

ROUNDS = 7
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
    anchor: int = 0  # rotating seat used to break ties in the draft order
    order: list[int] = field(default_factory=list)  # this round's turn order, first to last
    turn_index: int = 0
    draw_pile: list[Card] = field(default_factory=list)
    discard_pile: list[Card] = field(default_factory=list)
    market: list[Card] = field(default_factory=list)
    grids: list[list[list[tuple[Card, bool] | None]]] = field(default_factory=list)
    hands: list[Card | None] = field(default_factory=list)
    banked: list[float] = field(default_factory=list)  # public, permanent points
    closed: list[list[bool]] = field(default_factory=list)  # thread already paid out
    phase: str = "turn"
    step_stage: str = "draw"  # "draw" -> "choose" -> "weave"
    drawn: Card | None = None  # card taken from the market this turn (public)
    strand: str | None = None  # "drawn" or "hidden": the card announced in step 2
    final_order: list[int] = field(default_factory=list)


class Loom:
    """Loom — weave a 3x3 grid of drafted cards into scoring threads.

    RULESHEET
    =========
    Players: 2-4. Components: one standard 52-card deck (no jokers, no dice).
    Ranks A,2,...,10,J,Q,K in four suits.

    THE POINT OF THE GAME
    ---------------------
    You own a 3x3 grid, your **weave**. Its cells are addressed (row, column), rows 0-2 top to
    bottom, columns 0-2 left to right. Eight lines run through it — 3 rows, 3 columns and the
    2 diagonals (0,0)-(1,1)-(2,2) and (0,2)-(1,1)-(2,0). Each line is a **thread**. The moment a
    thread holds its third card it is scored as a 3-card poker hand and the points are **banked**
    immediately and permanently. Banked points can never fall.

    The catch: the loom is cut after **7 rounds**, and you place exactly one card per round. Nine
    cells, seven cards — **two cells of your weave stay bare for ever**, and every thread that runs
    through a bare cell scores nothing at all. You cannot have everything; you must decide early
    which threads you abandon and spend your last placements closing the ones you kept.

    The second catch: banked points are public, and they set the draft order (below). Closing a
    thread pays you now and pushes you to the back of the queue next round.

    SETUP
    -----
    Shuffle the deck face-down as the draw pile. Deal each player one card face-down as their
    **hidden hand** card; you may look at your own at any time. All grids start empty, all banked
    scores are 0. A random seat is chosen as the first round's **anchor**.

    DRAFT ORDER (each round)
    ------------------------
    At the start of every round the turn order is recomputed: **the player with the fewest banked
    points goes first**, then the next fewest, and so on; the leader picks last. Ties are broken
    by seat, starting from the round's anchor and going clockwise, and the anchor itself moves one
    seat clockwise every round, so nobody owns the first pick by seating. In round 1 all scores are
    0, so the order is simply the anchor and then clockwise.

    ROUND STRUCTURE
    ---------------
    Reveal cards from the draw pile face-up into the **market** until it holds P+1 cards (3 for two
    players, 4 for three, 5 for four). In the draft order above, each player takes exactly one turn.
    When everyone has played, every card still in the market is discarded face-down and is out of
    the game. Then the next round starts with a fresh market and a freshly computed order. After
    round 7 the loom is cut and the game ends.

    A TURN — THREE DECISIONS
    ------------------------
    1. **Draw a thread.** Take one face-up card from the market. Everyone sees which card you take.
       You now hold two cards: the **drawn** card and your **hidden** hand card. (The market shrinks
       as the round goes on, so the first player to act has P+1 cards to choose from and the last
       has 2 — that is what the earlier picks are worth.)
    2. **Choose the strand.** Announce which of the two you will weave: "drawn" or "hidden". You do
       not show the hidden card when you choose it.
    3. **Weave it.** Put the chosen card in any empty cell of your own grid.
       * "drawn": the card is placed **face-up**; your hidden hand card is unchanged.
       * "hidden": your hand card is placed **face-down** and stays secret until the loom is cut;
         the card you just drew becomes your new hidden hand card. Opponents saw what you took, so
         what they do not know is which older card you just buried.
       A face-down card counts normally for its owner's threads — but only its owner knows what it
       is, so only its owner knows exactly why a score jumped.

    SCORING A THREAD
    ----------------
    When your placement fills the third cell of a thread, score that thread at once, add it to your
    banked total (it is announced) and mark the thread closed. Order inside a thread never matters,
    and a thread pays only its single best pattern:

    * **Three of a kind** — all three ranks equal: **9 points**
    * **Straight flush** — three consecutive ranks, one suit: **8 points**
    * **Straight** — three consecutive ranks, mixed suits: **4 points**
    * **Flush** — one suit, not a straight: **3 points**
    * **Pair** — exactly two ranks equal: **1 point**
    * anything else: **0 points**

    Straights run A-2-3, 2-3-4, ..., J-Q-K, Q-K-A. The ace is low or high; K-A-2 does not count.
    A straight flush is never also paid as a straight or a flush. One placement can close two or
    three threads at once, and each of them pays.

    A WORKED TURN
    -------------
    Three players. Ann has banked 0, Bo 4, Cid 1, so the order is Ann, Cid, Bo. The market shows
    7H 7C 9S 2D. Ann's grid already has 7S at (0,0) and 7D at (0,2); her hidden card is KD.
    Ann draws 7C (market now 7H 9S 2D for Cid). She announces "drawn" and weaves 7C at (0,1). The
    top row is now 7S 7C 7D — three of a kind, **9 points banked at once**. Her banked total is 9,
    so next round she will pick last. Cid draws 9S, announces "hidden", places his secret card
    face-down at (1,1) — nobody knows what went in — and 9S becomes his new hidden card. Bo must
    take one of 7H or 2D.

    END OF GAME AND A WORKED FINISH
    -------------------------------
    After the seventh round every face-down card is turned up. Your leftover hidden hand card is
    discarded and never scores. Your final score is your banked total; nothing is added for the
    threads still open. Example final weave (X = bare cell):

        row 0:  5H  6H  7H
        row 1:  5S   X  9D
        row 2:  5D  QC   X

    Column 0 is 5H 5S 5D — three of a kind, 9. Row 0 is 5H 6H 7H — straight flush, 8. Row 1, row 2,
    column 2 and both diagonals all run through a bare cell and pay nothing; column 1 (6H, QC and
    the bare (1,1)) also pays nothing. Total: **17**. Note the two bare cells were chosen to be
    (1,1) and (2,2), which kills five threads — leaving two cells on the same row or column kills
    fewer, and the best you can ever close is five of the eight threads.

    While the game is running this implementation shows banked points plus a **shadow** value of
    one fifth of what each two-card thread could still become; the shadow is a hint only, never
    banked, and only banked points decide the game.

    TIE-BREAKS
    ----------
    Equal totals are separated by: (1) the higher single best closed thread; (2) more cards of
    their most common suit in the grid; (3) the player who was **later** in the final round's draft
    order. In this implementation these are folded into the reported score as a fraction below
    0.001, so the ranking is always strict.

    STRATEGY
    --------
    The centre cell touches four threads and the corners three, but with only seven cards you will
    never fill both. Bank early and you draft last for the rest of the game — with a P+1 market
    that can cost you the exact card a thread needed. Sitting on a nearly-finished thread keeps you
    at the front of the queue; the risk is the loom being cut with the thread still open. Burying a
    dead card face-down refreshes your secret and hides which thread you are really building, and
    taking a card your neighbour obviously needs is free whenever the market is about to be
    discarded anyway.
    """

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
        s = LoomState(
            n_players=self.n_players,
            anchor=rng.randrange(self.n_players),
            draw_pile=list(deck.cards),
            grids=[[[None] * SIZE for _ in range(SIZE)] for _ in range(self.n_players)],
            hands=[None] * self.n_players,
            banked=[0.0] * self.n_players,
            closed=[[False] * len(THREADS) for _ in range(self.n_players)],
        )
        for p in range(self.n_players):
            s.hands[p] = s.draw_pile.pop(0)
        s.order = self._round_order(s)
        self._refill_market(s)
        return s

    def _round_order(self, s: LoomState) -> list[int]:
        """Fewest banked points drafts first; ties by seat clockwise from the rotating anchor."""
        return sorted(
            range(self.n_players),
            key=lambda p: (s.banked[p], (p - s.anchor) % self.n_players),
        )

    def _refill_market(self, s: LoomState) -> None:
        while len(s.market) < self.market_size and s.draw_pile:
            s.market.append(s.draw_pile.pop(0))

    def current_player(self, s: LoomState) -> int:
        return s.order[s.turn_index]

    # -- actions -------------------------------------------------------------------------
    def _empty_cells(self, s: LoomState, p: int) -> list[tuple[int, int]]:
        return [(r, c) for r in range(SIZE) for c in range(SIZE) if s.grids[p][r][c] is None]

    def legal_actions(self, s: LoomState) -> list[tuple]:
        if s.phase != "turn":
            return []
        p = self.current_player(s)
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
        p = self.current_player(s)
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
        self._bank_threads(s, p, (r, c))

        s.turn_index += 1
        if s.turn_index == self.n_players:  # end of round
            s.discard_pile.extend(s.market)
            s.market.clear()
            if s.round == ROUNDS:
                self._finish(s)
                return s
            s.round += 1
            s.turn_index = 0
            s.anchor = (s.anchor + 1) % self.n_players
            s.order = self._round_order(s)
            self._refill_market(s)
        return s

    def _bank_threads(self, s: LoomState, p: int, cell: tuple[int, int]) -> None:
        """Pay out, once and for ever, every thread this placement just completed."""
        for t, thread in enumerate(THREADS):
            if cell not in thread or s.closed[p][t]:
                continue
            cells = [s.grids[p][r][c] for (r, c) in thread]
            if any(x is None for x in cells):
                continue
            s.closed[p][t] = True
            s.banked[p] += float(thread_score(tuple(x[0] for x in cells)))

    def _finish(self, s: LoomState) -> None:
        s.final_order = list(s.order)
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

    def _shadow(self, s: LoomState, p: int, factor: float) -> float:
        """Hint value of two-card threads that could still close; never banked."""
        total = 0.0
        for t, thread in enumerate(THREADS):
            if s.closed[p][t]:
                continue
            cards = [s.grids[p][r][c] for (r, c) in thread]
            cards = [x[0] for x in cards if x is not None]
            if len(cards) != 2:
                continue
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
            return [
                s.banked[p] + self._shadow(s, p, FACTOR) for p in range(self.n_players)
            ]
        totals = list(s.banked)
        for p in range(self.n_players):  # tie-breaks folded in as < 0.001
            best = max(self._thread_values(s, p))
            suits = [int(cell[0].suit) for row in s.grids[p] for cell in row if cell is not None]
            top_suit = max((suits.count(x) for x in set(suits)), default=0)
            seat = s.final_order.index(p) if p in s.final_order else 0
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
            "rounds_total": ROUNDS,
            "phase": s.phase,
            "step": s.step_stage,
            "order": tuple(s.order),
            "current_player": self.current_player(s) if s.phase == "turn" else None,
            "banked": tuple(s.banked),
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
            "open_threads": tuple(not x for x in s.closed[p]),
            "draw_count": len(s.draw_pile),
            "discard_count": len(s.discard_pile),
        }

    def describe(self, s: LoomState) -> str:
        if s.phase == "game_over":
            return "game over; banked=" + ", ".join(
                f"seat {p}: {s.banked[p]:g}" for p in range(self.n_players)
            )
        market = " ".join(f"{i}:{c}" for i, c in enumerate(s.market)) or "empty"
        held = f" drawn={s.drawn}" if s.drawn is not None else ""
        return (
            f"round {s.round}/{ROUNDS} order={s.order} turn=seat {self.current_player(s)} "
            f"step={s.step_stage}{held}; market: {market}; "
            f"banked={[f'{v:g}' for v in s.banked]}; draw={len(s.draw_pile)}"
        )


GAME = Loom
