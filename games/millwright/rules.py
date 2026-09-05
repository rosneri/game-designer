"""Millwright — fit out a water mill, one mechanism per suit.

RULESHEET
=========
Players: 2-4.  Components: 52-card deck + 2 jokers (54 cards), one six-sided die.

Theme
-----
Each player fits out a water mill with four mechanisms, one per suit: spade sluices,
heart wheels, diamond gears, club millstones. Every turn you take one card from a shared
yard and either bolt it into a mechanism, run a batch of grain through that mechanism for
points, or stash it in your stockroom for later.

Card values
-----------
Rank order for fitting is A (1) low, then 2..10, J (11), Q (12), K (13).
Each card has a *grade*: A-5 are grade 1, 6-10 are grade 2, J/Q/K are grade 3.
Jokers are grade 3 and have no suit and no rank.

Setup
-----
Shuffle all 54 cards face down as the draw pile. Deal 4 cards face up in a row: the yard.
Each player has an empty mill (four mechanisms, one per suit), an empty face-down
stockroom, and a score of 0. A start player is chosen at random; play is clockwise.

Mechanisms and levels
---------------------
A mechanism is an ordered stack of fitted cards. Its *level* is the number of cards in it,
0 to a maximum of 4. A suited card may be fitted into the mechanism of its own suit only
if that mechanism's level is below 4 and the card's rank is strictly higher than the rank
of the top suited card already fitted there. An empty mechanism accepts any rank. A joker
may be fitted into any mechanism below level 4 whatever the ranks. A fitted joker does not
change the mechanism's top rank, so the next suited card must still beat the highest
suited card fitted there.

Rounds
------
A round is one turn per player, clockwise, beginning with the current start player. After
each round the start player role passes one seat clockwise, so every seat leads equally
often.

Turn
----
At the start of your turn the die is rolled. The result is the *pressure* for this turn and
is visible to all. Then do exactly one of the following.

1. **Fit** a card from the yard or from your stockroom into a mechanism where it is legal.
   Score points equal to the mechanism's new level (1, 2, 3 or 4).
2. **Run** a card from the yard or from your stockroom; discard it face up. A suited card
   runs through the mechanism of its suit; for a joker you choose any one of your
   mechanisms. Score grade x that mechanism's level. If the pressure roll is less than or
   equal to that mechanism's level, the score is doubled. A card run from your stockroom
   counts as one grade higher than printed (grade 4 maximum). Running against a level-0
   mechanism is legal and scores 0 — it still clears and refills a yard slot.
3. **Reserve** a card from the yard, face down, into your stockroom. The stockroom holds at
   most 2 cards. This scores nothing now, but stockroom cards dodge the draft, wait for a
   good pressure roll, and run at one grade higher.

Whenever a card is taken from the yard, that slot is immediately refilled from the top of
the draw pile; if the draw pile is empty the slot stays empty. Actions that use a stockroom
card do not touch the yard. If you have no legal action (empty yard and empty stockroom)
you pass.

End of game
-----------
After a round ends, if the draw pile is empty, the next round is the closing round. The
game ends after the closing round. Cards left in the yard or in stockrooms score nothing.

Final scoring
-------------
Add 4 points for each mechanism at level 4. Highest score wins.

Tie-break, in order: more fitted cards in total; then higher sum of ranks of fitted suited
cards (jokers count 0); then the tied player who took their turn later in the closing round
wins. (These tie-breaks are folded into ``scores`` as fractions smaller than one point, so
they never overturn a difference in real points.)

Strategy note
-------------
Low cards are precious foundations and face cards are the payday once the machine hums.
A high pressure roll rewards deep mechanisms; a low roll doubles almost anything, so a
level-1 mechanism only pays double on a roll of 1.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from random import Random

from gd_cards import Card, Deck, Suit
from gd_gamecore import GMLike

YARD = 4
MAX_LEVEL = 4
STOCK = 2
DIE = 6
LEVEL4_BONUS = 4
SUIT_KEYS = ("C", "D", "H", "S")
SUIT_OF = {"C": Suit.CLUBS, "D": Suit.DIAMONDS, "H": Suit.HEARTS, "S": Suit.SPADES}
KEY_OF = {int(s): k for k, s in SUIT_OF.items()}


def grade(c: Card) -> int:
    """Grade of a card: A-5 -> 1, 6-10 -> 2, J/Q/K and jokers -> 3."""
    if c.is_joker:
        return 3
    return 1 if c.rank <= 5 else (2 if c.rank <= 10 else 3)


def top_rank(mech: list[Card]) -> int:
    """Rank of the top (highest) suited card fitted; 0 if the stack holds only jokers."""
    return max((c.rank for c in mech if not c.is_joker), default=0)


@dataclass
class MillState:
    deck: list[Card]
    yard: list[Card | None]
    mechs: list[dict[str, list[Card]]]
    stocks: list[list[Card]]
    scores: list[int]
    current: int
    start_player: int
    turn_in_round: int
    pressure: int
    closing: bool = False
    finished: bool = False
    discard: list[Card] = field(default_factory=list)
    closing_seat: list[int] = field(default_factory=list)  # order index in the closing round


class Millwright:
    """See module docstring for the rulesheet."""

    def __init__(self, n_players: int, gm: GMLike | None = None):
        if not 2 <= n_players <= 4:
            raise ValueError("2-4 players")
        self.n_players = n_players
        self.gm = gm

    # -- lifecycle -----------------------------------------------------------------------
    def setup(self, rng: Random) -> MillState:
        deck = Deck(jokers=2).shuffle(rng)
        yard: list[Card | None] = list(deck.draw(YARD))
        start = rng.randrange(self.n_players)
        return MillState(
            deck=list(deck.cards),
            yard=yard,
            mechs=[{k: [] for k in SUIT_KEYS} for _ in range(self.n_players)],
            stocks=[[] for _ in range(self.n_players)],
            scores=[0] * self.n_players,
            current=start,
            start_player=start,
            turn_in_round=0,
            pressure=rng.randint(1, DIE),
            closing_seat=[0] * self.n_players,
        )

    def current_player(self, s: MillState) -> int:
        return s.current

    # -- rules helpers -------------------------------------------------------------------
    def _cards(self, s: MillState, p: int) -> list[tuple[str, int, Card]]:
        out = [("yard", i, c) for i, c in enumerate(s.yard) if c is not None]
        out += [("stock", i, c) for i, c in enumerate(s.stocks[p])]
        return out

    def _can_fit(self, mech: list[Card], c: Card) -> bool:
        return len(mech) < MAX_LEVEL and (c.is_joker or c.rank > top_rank(mech))

    def _targets(self, c: Card) -> tuple[str, ...]:
        return SUIT_KEYS if c.is_joker else (KEY_OF[int(c.suit)],)

    def legal_actions(self, s: MillState) -> list[tuple]:
        if s.finished:
            return []
        p = s.current
        acts: list[tuple] = []
        for src, i, c in self._cards(s, p):
            for k in self._targets(c):
                if self._can_fit(s.mechs[p][k], c):
                    acts.append(("fit", src, i, k))
                acts.append(("run", src, i, k))
        if len(s.stocks[p]) < STOCK:
            acts += [("reserve", "yard", i) for i, c in enumerate(s.yard) if c is not None]
        return acts or [("pass",)]

    # -- transition ----------------------------------------------------------------------
    def step(self, state: MillState, a: tuple, rng: Random) -> MillState:
        if self.is_terminal(state):
            raise ValueError("game over")
        if a not in self.legal_actions(state):
            raise ValueError(f"illegal action {a}")
        s = copy.deepcopy(state)
        p = s.current
        if a[0] != "pass":
            src, i = a[1], a[2]
            c = s.yard[i] if src == "yard" else s.stocks[p][i]
            if a[0] == "fit":
                mech = s.mechs[p][a[3]]
                mech.append(c)
                s.scores[p] += len(mech)
            elif a[0] == "run":
                lvl = len(s.mechs[p][a[3]])
                g = min(grade(c) + 1, 4) if src == "stock" else grade(c)
                gain = g * lvl
                if lvl and s.pressure <= lvl:
                    gain *= 2
                s.scores[p] += gain
                s.discard.append(c)
            # "reserve" moves the card into the stockroom, scoring nothing now
            if src == "yard":
                if a[0] == "reserve":
                    s.stocks[p].append(c)
                s.yard[i] = s.deck.pop(0) if s.deck else None
            else:
                s.stocks[p].pop(i)
        # -- advance the turn / round
        s.closing_seat[p] = s.turn_in_round
        s.turn_in_round += 1
        if s.turn_in_round >= self.n_players:
            if s.closing:
                s.finished = True
                for q in range(self.n_players):
                    s.scores[q] += LEVEL4_BONUS * sum(
                        1 for m in s.mechs[q].values() if len(m) == MAX_LEVEL
                    )
                return s
            if not s.deck:
                s.closing = True
            s.start_player = (s.start_player + 1) % self.n_players
            s.current = s.start_player
            s.turn_in_round = 0
        else:
            s.current = (s.current + 1) % self.n_players
        s.pressure = rng.randint(1, DIE)
        return s

    def is_terminal(self, s: MillState) -> bool:
        return s.finished

    def scores(self, s: MillState) -> list[float]:
        out = []
        for p in range(self.n_players):
            fitted = [c for m in s.mechs[p].values() for c in m]
            rank_sum = sum(c.rank for c in fitted if not c.is_joker)
            # tie-breaks as sub-point fractions: fitted count, then rank sum, then turn order
            out.append(
                float(s.scores[p])
                + 1e-3 * len(fitted)
                + 1e-6 * rank_sum
                + 1e-9 * s.closing_seat[p]
            )
        return out

    # -- views ---------------------------------------------------------------------------
    def _mech_view(self, m: dict[str, list[Card]]) -> dict:
        return {k: tuple(str(c) for c in m[k]) for k in SUIT_KEYS}

    def observe(self, s: MillState, p: int) -> dict:
        return {
            "seat": p,
            "pressure": s.pressure,
            "to_move": s.current,
            "yard": tuple(str(c) if c else "-" for c in s.yard),
            "deck": len(s.deck),
            "my_mill": self._mech_view(s.mechs[p]),
            "mills": tuple(self._mech_view(s.mechs[q]) for q in range(self.n_players)),
            "my_stock": tuple(str(c) for c in s.stocks[p]),
            "stock_sizes": tuple(len(st) for st in s.stocks),
            "scores": tuple(s.scores),
            "closing": s.closing,
            "start_player": s.start_player,
        }

    def describe(self, s: MillState) -> str:
        mills = " | ".join(
            f"P{q}:" + "/".join(str(len(s.mechs[q][k])) for k in SUIT_KEYS)
            for q in range(self.n_players)
        )
        yard = " ".join(str(c) if c else "--" for c in s.yard)
        tag = "FINISHED" if s.finished else ("closing round" if s.closing else "")
        return (
            f"yard=[{yard}] deck={len(s.deck)} pressure={s.pressure} "
            f"turn=seat {s.current} scores={s.scores} levels {mills} {tag}".strip()
        )


GAME = Millwright
