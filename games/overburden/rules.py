"""Overburden — stake, survey, and mine a face-down 4x4 ore field.

RULESHEET
=========
Players: 2-4.  Components: one standard 52-card deck (no jokers, no dice).

Card values: A=1, 2-10 face value, J=11, Q=12, K=13. Suits are Spades, Hearts,
Diamonds and Clubs; suit order for tie-breaks is S > H > D > C.

Setup
-----
Shuffle the deck. Deal 16 cards face-down in a 4x4 grid (rows 0-3, columns 0-3);
these are the *ore cards*. Deal 3 cards to each player as a hand. The rest of the
deck is a face-down draw pile. A start player is chosen at random and play then
goes clockwise. Everyone starts with 0 banked points, no territory and no claims.

Board terms
-----------
Every cell holds one ore card, face-down or face-up (*revealed*). A cell is
*unowned* or *owned* by exactly one player. An unowned cell may carry any number
of face-up *claim cards*, each tagged with the player who staked it. Two cells are
*adjacent* only if they share an edge (no diagonals).

Turn
----
On your turn you take exactly one action, then draw 1 card from the draw pile if
it is not empty. There is no hand limit.

1. **Stake** — play one card from your hand face-up as a claim card onto an
   unowned cell. The cell must be adjacent to a cell where you already have a
   claim card or that you own. If you have no claim cards anywhere and own no
   cells, you may stake any unowned cell. The ore card is not touched. Staking
   scores nothing by itself.

2. **Survey** — pick an unowned cell whose ore is face-down and turn that ore
   face-up permanently, for everyone to see. Then draw 1 extra card from the draw
   pile (in addition to the normal end-of-turn draw), if any card is left.

3. **Mine** — pick an unowned cell where you have at least one claim card. If the
   ore is face-down, turn it face-up now. Then compute each player's *strength* on
   the cell: the sum of that player's claim-card values there, where a claim card
   whose suit matches the ore card's suit counts double.
   You succeed if BOTH hold:
     (a) your strength is strictly greater than every other player's strength on
         that cell, and
     (b) your strength is greater than or equal to the ore card's value.
   *Success*: you bank points equal to the ore value, the cell becomes your
   territory (the ore card stays face-up on it), and every claim card on the cell
   — yours and your rivals' — is discarded.
   *Failure*: the ore stays face-up and your single strongest claim card on that
   cell is discarded (highest value after suit doubling; ties broken by highest
   rank, then by suit order S, H, D, C). All other claim cards stay.
   Mining a face-down cell is always allowed (that is the gamble). Mining a
   face-up cell is only allowed when it would succeed.

4. **Pass** — only when you have no legal Stake, Survey or Mine. Passing is
   forced, never a choice.

Line bonuses
------------
For each of the 4 rows and 4 columns, the player who owns strictly more cells in
that line than any other player *holds* the line; a tie means nobody holds it.
Each held line is worth 5 points. Lines are live: your current score is your
banked ore points plus 5 per line you hold right now, and holdings can change
whenever a cell becomes owned.

End of game
-----------
The game ends immediately when any of these is true:
* all 16 cells are owned;
* the draw pile is empty and every hand is empty;
* every player has passed in an unbroken row (one full round of forced passes).

Final scoring
-------------
Score = sum of the ore values of the cells you own + 5 per row or column you hold.
Highest score wins. Tie-break, in order: most owned cells; highest single ore value
among owned cells; most cards in hand; then the tied player who sits latest in
clockwise order counting from the start player (the start player loses all such
ties). This chain always produces a single winner.

Implementation note: the tie-break chain is folded into ``scores`` as a fraction
below 1 that is only added in the final state, so it can never overturn a real
point difference.

Strategy
--------
Surveying costs you a turn but pays a card and turns a gamble into arithmetic.
Cheap cells still buy rows and columns, so a 2 of ore can be worth more than a
King. Suit matching doubles a claim, so a small card of the right suit can win a
cell that a bigger card cannot — but only after somebody has paid to reveal it.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from random import Random

from gd_cards import Card, Deck, Suit
from gd_gamecore import GMLike

SIZE = 4
CELLS = SIZE * SIZE
HAND = 3
LINE_BONUS = 5


def _suit_key(c: Card) -> int:
    """S > H > D > C for tie-breaks (gd_cards orders CLUBS=0 .. SPADES=3)."""
    return int(c.suit)


@dataclass
class OverState:
    ore: list[Card]                                   # 16 cells, index = row * 4 + col
    revealed: list[bool]
    owner: list[int | None]
    claims: list[list[tuple[Card, int]]]              # per cell, (claim card, player)
    hands: list[list[Card]]
    draw: list[Card]
    discard: list[Card] = field(default_factory=list)
    banked: list[int] = field(default_factory=list)
    turn: int = 0
    start: int = 0
    passes: int = 0
    over: bool = False


class Overburden:
    """See the module docstring for the rulesheet."""

    def __init__(self, n_players: int, gm: GMLike | None = None):
        if not 2 <= n_players <= 4:
            raise ValueError("2-4 players")
        self.n_players = n_players
        self.gm = gm

    # -- lifecycle -----------------------------------------------------------------------
    def setup(self, rng: Random) -> OverState:
        deck = Deck(jokers=0).shuffle(rng)
        ore = deck.draw(CELLS)
        hands = deck.deal(self.n_players, HAND)
        start = rng.randrange(self.n_players)
        return OverState(
            ore=ore,
            revealed=[False] * CELLS,
            owner=[None] * CELLS,
            claims=[[] for _ in range(CELLS)],
            hands=hands,
            draw=list(deck.cards),
            banked=[0] * self.n_players,
            turn=start,
            start=start,
        )

    def current_player(self, s: OverState) -> int:
        return s.turn

    # -- helpers -------------------------------------------------------------------------
    @staticmethod
    def _neighbours(i: int) -> list[int]:
        r, c = divmod(i, SIZE)
        out = []
        if r > 0:
            out.append(i - SIZE)
        if r < SIZE - 1:
            out.append(i + SIZE)
        if c > 0:
            out.append(i - 1)
        if c < SIZE - 1:
            out.append(i + 1)
        return out

    @staticmethod
    def _footprint(s: OverState, p: int) -> set[int]:
        """Cells where p owns or has a claim."""
        return {i for i in range(CELLS)
                if s.owner[i] == p or any(q == p for _, q in s.claims[i])}

    @staticmethod
    def _claim_value(card: Card, ore: Card) -> int:
        return card.rank * (2 if int(card.suit) == int(ore.suit) else 1)

    def _strengths(self, s: OverState, i: int) -> list[int]:
        ore = s.ore[i]
        out = [0] * self.n_players
        for card, p in s.claims[i]:
            out[p] += self._claim_value(card, ore)
        return out

    def _mine_succeeds(self, s: OverState, i: int, p: int) -> bool:
        st = self._strengths(s, i)
        mine = st[p]
        return mine >= s.ore[i].rank and all(mine > v for q, v in enumerate(st) if q != p)

    def _lines(self, s: OverState) -> list[int]:
        """5 points per row/column strictly most-owned by a player."""
        bonus = [0] * self.n_players
        groups = [[r * SIZE + c for c in range(SIZE)] for r in range(SIZE)]
        groups += [[r * SIZE + c for r in range(SIZE)] for c in range(SIZE)]
        for g in groups:
            cnt = [0] * self.n_players
            for i in g:
                if s.owner[i] is not None:
                    cnt[s.owner[i]] += 1
            best = max(cnt)
            if best > 0 and cnt.count(best) == 1:
                bonus[cnt.index(best)] += LINE_BONUS
        return bonus

    # -- actions -------------------------------------------------------------------------
    def legal_actions(self, s: OverState) -> list[tuple]:
        if s.over:
            return []
        p = s.turn
        acts: list[tuple] = []
        foot = self._footprint(s, p)
        if foot:
            reach = {j for i in foot for j in self._neighbours(i) if s.owner[j] is None}
        else:
            reach = {i for i in range(CELLS) if s.owner[i] is None}
        for card in s.hands[p]:
            for i in sorted(reach):
                acts.append(("stake", str(card), i // SIZE, i % SIZE))
        for i in range(CELLS):
            if s.owner[i] is None and not s.revealed[i]:
                acts.append(("survey", i // SIZE, i % SIZE))
        for i in range(CELLS):
            if s.owner[i] is None and any(q == p for _, q in s.claims[i]):
                if not s.revealed[i] or self._mine_succeeds(s, i, p):
                    acts.append(("mine", i // SIZE, i % SIZE))
        return acts or [("pass",)]

    def step(self, state: OverState, a: tuple, rng: Random) -> OverState:
        s = copy.deepcopy(state)
        if s.over:
            raise ValueError("game is over")
        legal = self.legal_actions(s)
        if a not in legal:
            raise ValueError(f"illegal action {a!r}")
        p = s.turn
        kind = a[0]
        extra_draw = 0

        if kind == "pass":
            s.passes += 1
        else:
            s.passes = 0

        if kind == "stake":
            _, cs, r, c = a
            i = r * SIZE + c
            card = next(x for x in s.hands[p] if str(x) == cs)
            s.hands[p].remove(card)
            s.claims[i].append((card, p))
        elif kind == "survey":
            i = a[1] * SIZE + a[2]
            s.revealed[i] = True
            extra_draw = 1
        elif kind == "mine":
            i = a[1] * SIZE + a[2]
            s.revealed[i] = True
            ore = s.ore[i]
            if self._mine_succeeds(s, i, p):
                s.banked[p] += ore.rank
                s.owner[i] = p
                s.discard.extend(card for card, _ in s.claims[i])
                s.claims[i] = []
            else:
                mine_claims = [(card, q) for card, q in s.claims[i] if q == p]
                worst = max(mine_claims,
                            key=lambda cq: (self._claim_value(cq[0], ore), cq[0].rank, _suit_key(cq[0])))
                s.claims[i].remove(worst)
                s.discard.append(worst[0])

        for _ in range(extra_draw + 1):
            if s.draw:
                s.hands[p].append(s.draw.pop(0))

        if (all(o is not None for o in s.owner)
                or (not s.draw and not any(s.hands))
                or s.passes >= self.n_players):
            s.over = True
        else:
            s.turn = (s.turn + 1) % self.n_players
        return s

    # -- results -------------------------------------------------------------------------
    def is_terminal(self, s: OverState) -> bool:
        return s.over

    def _raw_scores(self, s: OverState) -> list[int]:
        bonus = self._lines(s)
        return [s.banked[p] + bonus[p] for p in range(self.n_players)]

    def scores(self, s: OverState) -> list[float]:
        raw = self._raw_scores(s)
        if not s.over:
            return [float(v) for v in raw]
        out = []
        for p in range(self.n_players):
            cells = [i for i in range(CELLS) if s.owner[i] == p]
            top = max((s.ore[i].rank for i in cells), default=0)
            seat = (p - s.start) % self.n_players
            tb = (len(cells) * 1e-2 + top * 1e-4
                  + min(len(s.hands[p]), 50) * 1e-6 + seat * 1e-8)
            out.append(float(raw[p]) + tb)
        return out

    # -- views ---------------------------------------------------------------------------
    def observe(self, s: OverState, p: int) -> tuple:
        board = tuple(
            (str(s.ore[i]) if (s.revealed[i] or s.owner[i] is not None) else "??",
             s.owner[i] if s.owner[i] is not None else -1,
             tuple(f"{card}:{q}" for card, q in s.claims[i]))
            for i in range(CELLS)
        )
        return (
            p,
            tuple(str(c) for c in sorted(s.hands[p])),
            board,
            tuple(len(h) for h in s.hands),
            len(s.draw),
            tuple(s.banked),
            tuple(self._lines(s)),
            s.turn,
            s.start,
        )

    def describe(self, s: OverState) -> str:
        rows = []
        for r in range(SIZE):
            cells = []
            for c in range(SIZE):
                i = r * SIZE + c
                face = str(s.ore[i]) if (s.revealed[i] or s.owner[i] is not None) else "??"
                own = f"*{s.owner[i]}" if s.owner[i] is not None else ""
                cl = "".join(f"[{card}{q}]" for card, q in s.claims[i])
                cells.append(f"{face}{own}{cl}")
            rows.append(" | ".join(cells))
        sc = [int(v) for v in self._raw_scores(s)]
        return (f"scores={sc} banked={s.banked} draw={len(s.draw)} "
                f"hands={[len(h) for h in s.hands]} turn=seat {s.turn}"
                + ("" if not s.over else " (over)") + "\n" + "\n".join(rows))


GAME = Overburden
