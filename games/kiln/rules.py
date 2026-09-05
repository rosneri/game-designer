"""Kiln — fire your ware hotter than the dice allow.

RULESHEET
=========
Players: 2-4.  Components: standard 52-card deck (no jokers) + two six-sided dice.

Ranks and printed rank
----------------------
A card's *printed rank* is A=1, 2-10 face value, J=11, Q=12, K=13. The printed rank never
changes and is what you score at the end.

Heat and fired value
--------------------
The two dice together show the *heat* H = the sum of both faces (2..12). A card's *fired value*
this round is its printed rank + H, minus 13 whenever that total exceeds 13, so fired values are
always 1..13. Example at heat 7: a 4 fires as 11, a 9 fires as 3, a King fires as 7. At heat 12
an Ace fires as 13 and a King fires as 12. The heat rotates the whole rank wheel, so which cards
are "hot" changes every round.

Setup
-----
Shuffle the 52 cards and deal 5 to each player. The rest is the face-down draw pile; discards go
face-down beside it and are out of the game. Each player has an empty *kiln* (holds at most one
face-up card, their *ware*) and an empty face-up *cabinet* (their finished, scored cards). The
shuffle also decides which seat starts round 1; the start player then rotates clockwise every
round.

Round
-----
Roll both dice to set the heat. Then, beginning with the round's start player and going
clockwise, each player takes exactly one turn. When every player has taken one turn the round
ends and the next round's start player is the seat clockwise from this round's start player, so
every seat leads equally often.

Turn
----
On your turn you may first *stoke* at most once, then you must take exactly one main action.

* **Stoke** (optional, once per turn): discard one card from your hand face-down, choose either
  die, and re-roll only that die. The new heat applies immediately to everyone for the rest of
  the round (or until somebody else stokes). You cannot stoke with an empty hand.

Main actions:

* **Fire:** play a card from your hand into your own kiln. Legal if your kiln is empty, or if
  the card's fired value is strictly greater than your current ware's fired value. A ware that
  was already there slides into your cabinet (it is finished and scores). The played card
  becomes your new ware.
* **Poach:** play a card from your hand into an opponent's kiln. Legal only if that opponent has
  a ware and your card's fired value is strictly greater than that ware's fired value. Their
  ware goes into *your* cabinet; your card becomes *their* ware. You may not play into an empty
  opponent kiln.
* **Rake:** take your own ware back into your hand; your kiln becomes empty. Legal only if you
  have a ware and your hand holds at most 7 cards (the hand limit is 8).
* **Gather:** draw 2 cards from the draw pile (1 if only 1 card remains). Legal only if the draw
  pile is not empty and you hold 6 or fewer cards.
* **Pass:** legal only if no main action above is legal.

Fired values are always recomputed from the dice on the table at the moment of the check, so a
stoke can make an illegal play legal (or vice versa) inside your own turn.

End of game
-----------
The round-end check ends the game when any of these is true: some cabinet holds at least the
*threshold* number of cards (2 players: 8, 3 players: 6, 4 players: 5); the draw pile is empty;
or the round cap has been reached (2 players: 12 rounds, 3 players: 8, 4 players: 7). The check
happens only at the end of a round, so everybody takes the same number of turns.

Scoring
-------
Each player scores the sum of the printed ranks in their cabinet. Ware still in a kiln scores
nothing. Then, for each of the four suits, the player with strictly the most cards of that suit
in their cabinet scores 5 bonus points; if two or more tie for most, nobody gets that suit.
Highest total wins.

Tie-break (in order, until resolved): more cards in cabinet; then cabinets compared as printed
ranks sorted descending, lexicographically higher wins; then higher printed rank of the ware in
the kiln (empty = 0); then the player who took their turn earliest in the final round. This
chain always resolves, so the game never ends in a draw.

Worked example turn
-------------------
Heat is 7 (dice 3+4). Bea's kiln holds 9♦ (fires as 3). Cal's kiln holds K♠ (fires as 7). It is
Cal's turn; his hand is 4♥, 6♣, Q♦, 2♠.
Fired values at heat 7: 4♥ = 11, 6♣ = 13, Q♦ = 6, 2♠ = 9.
Cal could fire 6♣ (13 > 7) onto his own K♠, sending the King (13 printed points) to his cabinet.
Instead he first stokes: he discards 2♠ and re-rolls one die, turning the 4 into a 1, so the
heat is now 4. Fired values change: 4♥ = 8, 6♣ = 10, Q♦ = 3, and Bea's 9♦ now fires as 13 while
Cal's K♠ fires as 4. Poaching Bea is now impossible (nothing beats 13), so Cal fires 4♥ (8 > 4)
into his own kiln: K♠ moves to his cabinet for 13 points and 4♥ is his new ware, sitting low at
8 — but the heat will change again next round.

Worked end-of-game scoring
--------------------------
Three players, the round cap is reached.
Ann's cabinet: K♠, 7♠, 3♥, 2♠, A♦ = 13+7+3+2+1 = 26, plus 4 spades.
Bea's cabinet: Q♥, J♥, 10♣, 5♦ = 12+11+10+5 = 38, plus 2 hearts, 1 club, 1 diamond.
Cal's cabinet: 9♣, 8♣, 6♦, 4♥, 3♦ = 9+8+6+4+3 = 30, plus 2 clubs, 2 diamonds, 1 heart.
Suit bonuses: spades — Ann has 4 (most) → +5 Ann. Hearts — Bea 2, Cal 1, Ann 1 → +5 Bea. Clubs —
Cal 2, Bea 1 → +5 Cal. Diamonds — Cal 2, Ann 1, Bea 1 → +5 Cal.
Totals: Ann 31, Bea 43, Cal 40. Bea wins.

Strategy note: firing scores the card *underneath*, so a fat ware you leave in the kiln is bait;
raking hides it, gathering buys options, and a single stoke can flip the wheel so that the card
nobody could beat becomes the cheapest card on the table.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from random import Random

from gd_cards import Card, Deck
from gd_gamecore import GMLike

HAND_LIMIT = 8
GATHER_MAX_HAND = 6
GATHER_N = 2
DEAL = 5
CABINET_THRESHOLD = {2: 8, 3: 6, 4: 5}
ROUND_CAP = {2: 12, 3: 8, 4: 7}
SUIT_BONUS = 5
SUIT_LETTERS = "CDHS"


def code(c: Card) -> str:
    """Short readable card code used inside actions, e.g. ``'AS'``, ``'10H'``, ``'KD'``."""
    return f"{c.rank_name}{SUIT_LETTERS[int(c.suit)]}"


def fired(rank: int, heat: int) -> int:
    """Fired value 1..13 of a printed rank under the given heat."""
    return (rank - 1 + heat) % 13 + 1


@dataclass
class KilnState:
    hands: list[list[Card]]
    kiln: list[Card | None]
    cabinet: list[list[Card]]
    draw_pile: list[Card]
    discarded: int
    dice: tuple[int, int]
    round_no: int
    round_start_seat: int
    current_seat: int
    turns_taken: int  # turns already completed this round
    phase: str  # "main" | "after_stoke"
    order_in_round: list[int] = field(default_factory=list)  # seat -> position in the current round
    game_over: bool = False

    @property
    def heat(self) -> int:
        return self.dice[0] + self.dice[1]


class Kiln:
    """See the module docstring for the rulesheet."""

    def __init__(self, n_players: int, gm: GMLike | None = None):
        if not 2 <= n_players <= 4:
            raise ValueError("2-4 players")
        self.n_players = n_players
        self.gm = gm
        self.threshold = CABINET_THRESHOLD[n_players]
        self.round_cap = ROUND_CAP[n_players]

    # -- lifecycle ------------------------------------------------------------------------
    def setup(self, rng: Random) -> KilnState:
        deck = Deck(jokers=0).shuffle(rng)
        hands = [sorted(h) for h in deck.deal(self.n_players, DEAL)]
        start = rng.randrange(self.n_players)  # the shuffle also picks the first start player
        s = KilnState(
            hands=hands,
            kiln=[None] * self.n_players,
            cabinet=[[] for _ in range(self.n_players)],
            draw_pile=list(deck.cards),
            discarded=0,
            dice=(rng.randint(1, 6), rng.randint(1, 6)),
            round_no=1,
            round_start_seat=start,
            current_seat=start,
            turns_taken=0,
            phase="main",
        )
        s.order_in_round = self._order(start)
        return s

    def _order(self, start: int) -> list[int]:
        return [(seat - start) % self.n_players for seat in range(self.n_players)]

    # -- queries --------------------------------------------------------------------------
    def current_player(self, s: KilnState) -> int:
        return s.current_seat

    def _card_of(self, s: KilnState, p: int, c: str) -> Card:
        for card in s.hands[p]:
            if code(card) == c:
                return card
        raise ValueError(f"seat {p} does not hold {c}")

    def _main_actions(self, s: KilnState) -> list[tuple]:
        p, h = s.current_seat, s.heat
        acts: list[tuple] = []
        mine = s.kiln[p]
        floor = fired(mine.rank, h) if mine is not None else 0
        for card in s.hands[p]:
            v = fired(card.rank, h)
            if v > floor:
                acts.append(("fire", code(card)))
            for q in range(self.n_players):
                w = s.kiln[q]
                if (
                    q != p
                    and w is not None
                    and v > fired(w.rank, h)
                    and len(s.cabinet[q]) >= len(s.cabinet[p])  # guild rule: only rob the ones ahead
                ):
                    acts.append(("poach", q, code(card)))
        if mine is not None and len(s.hands[p]) < HAND_LIMIT:
            acts.append(("rake",))
        if s.draw_pile and len(s.hands[p]) <= GATHER_MAX_HAND:
            acts.append(("gather",))
        if not acts:
            acts.append(("pass",))
        return acts

    def legal_actions(self, s: KilnState) -> list[tuple]:
        if s.game_over:
            return []
        acts = self._main_actions(s)
        if s.phase == "main":
            acts += [("stoke", code(card), d) for card in s.hands[s.current_seat] for d in (0, 1)]
        return acts

    def is_terminal(self, s: KilnState) -> bool:
        return s.game_over

    # -- transitions ----------------------------------------------------------------------
    def step(self, state: KilnState, a, rng: Random) -> KilnState:
        s = copy.deepcopy(state)
        if s.game_over:
            raise ValueError("game is over")
        if a not in self.legal_actions(state):
            raise ValueError(f"illegal action {a}")
        p = s.current_seat
        kind = a[0]

        if kind == "stoke":
            card = self._card_of(s, p, a[1])
            s.hands[p].remove(card)
            s.discarded += 1
            dice = list(s.dice)
            dice[a[2]] = rng.randint(1, 6)
            s.dice = (dice[0], dice[1])
            s.phase = "after_stoke"
            return s

        if kind == "fire":
            card = self._card_of(s, p, a[1])
            s.hands[p].remove(card)
            covered = s.kiln[p]
            if covered is not None:
                s.cabinet[p].append(covered)
            s.kiln[p] = card
        elif kind == "poach":
            target = a[1]
            card = self._card_of(s, p, a[2])
            s.hands[p].remove(card)
            s.cabinet[p].append(s.kiln[target])
            s.kiln[target] = card
        elif kind == "rake":
            s.hands[p].append(s.kiln[p])
            s.hands[p].sort()
            s.kiln[p] = None
        elif kind == "gather":
            for _ in range(min(GATHER_N, len(s.draw_pile))):
                s.hands[p].append(s.draw_pile.pop(0))
            s.hands[p].sort()
        # "pass" does nothing
        return self._end_turn(s, rng)

    def _end_turn(self, s: KilnState, rng: Random) -> KilnState:
        s.turns_taken += 1
        s.phase = "main"
        if s.turns_taken < self.n_players:
            s.current_seat = (s.current_seat + 1) % self.n_players
            return s
        # round is over
        done = (
            any(len(c) >= self.threshold for c in s.cabinet)
            or not s.draw_pile
            or s.round_no >= self.round_cap
        )
        if done:
            s.game_over = True
            s.current_seat = s.round_start_seat
            return s
        s.round_no += 1
        s.round_start_seat = (s.round_start_seat + 1) % self.n_players
        s.current_seat = s.round_start_seat
        s.turns_taken = 0
        s.order_in_round = self._order(s.round_start_seat)
        s.dice = (rng.randint(1, 6), rng.randint(1, 6))
        return s

    # -- scoring --------------------------------------------------------------------------
    def _points(self, s: KilnState) -> list[int]:
        pts = [sum(c.rank for c in cab) for cab in s.cabinet]
        for suit in range(4):
            counts = [sum(1 for c in cab if int(c.suit) == suit) for cab in s.cabinet]
            best = max(counts)
            if best > 0 and counts.count(best) == 1:
                pts[counts.index(best)] += SUIT_BONUS
        return pts

    def _tiebreak_key(self, s: KilnState, p: int, pts: list[int]) -> tuple:
        cab = sorted((c.rank for c in s.cabinet[p]), reverse=True)
        ware = s.kiln[p].rank if s.kiln[p] is not None else 0
        return (pts[p], len(cab), tuple(cab), ware, -s.order_in_round[p])

    def scores(self, s: KilnState) -> list[float]:
        pts = self._points(s)
        if not s.game_over:
            return [float(v) for v in pts]
        # Terminal scores carry a sub-point tie-break bonus so a game never ends drawn.
        keys = [self._tiebreak_key(s, p, pts) for p in range(self.n_players)]
        order = sorted(range(self.n_players), key=lambda p: keys[p], reverse=True)
        out = [0.0] * self.n_players
        for rank, p in enumerate(order):
            out[p] = float(pts[p]) + (self.n_players - 1 - rank) * 1e-6
        return out

    # -- views ----------------------------------------------------------------------------
    def observe(self, s: KilnState, p: int) -> tuple:
        h = s.heat
        return (
            ("hand", tuple((code(c), fired(c.rank, h)) for c in s.hands[p])),
            ("hand_sizes", tuple(len(x) for x in s.hands)),
            ("kilns", tuple((code(c), fired(c.rank, h)) if c is not None else None for c in s.kiln)),
            ("cabinets", tuple(tuple(code(c) for c in cab) for cab in s.cabinet)),
            ("points", tuple(self._points(s))),
            ("dice", s.dice),
            ("heat", h),
            ("draw_pile", len(s.draw_pile)),
            ("round", (s.round_no, self.round_cap)),
            ("seat", p),
            ("to_act", s.current_seat),
            ("phase", s.phase),
        )

    def describe(self, s: KilnState) -> str:
        kilns = ", ".join(
            f"s{i}:{code(c)}({fired(c.rank, s.heat)})" if c is not None else f"s{i}:-"
            for i, c in enumerate(s.kiln)
        )
        return (
            f"round {s.round_no}/{self.round_cap} heat={s.heat} (dice {s.dice[0]}+{s.dice[1]}) "
            f"deck={len(s.draw_pile)} | kilns {kilns} | cabinet sizes={[len(c) for c in s.cabinet]} "
            f"points={self._points(s)} | seat {s.current_seat} to act ({s.phase})"
        )


GAME = Kiln
