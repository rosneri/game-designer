"""Reckoner — a Casino-style capture game where every card you play is a target number.

RULESHEET
=========
Players: 2-4.  Components: one standard 52-card deck (no jokers) and one six-sided die.

Card values
-----------
Ace = 1, 2-10 = face value, Jack = 11, Queen = 12, King = 13. Suits never matter for the
arithmetic; they only tell cards apart (written A\u2660, 7\u2666, 10\u2663, J\u2665, ...).

Setup
-----
Shuffle the 52 cards. Deal 4 cards face down to each player, then 4 cards face up in a row:
that row is the **field**. The remaining cards are the face-down **stock**. Roll the die and
leave it showing. Its value d sets the two **bounty ranks**: d and d + 7.

    die 1 -> A and 8    die 2 -> 2 and 9    die 3 -> 3 and 10
    die 4 -> 4 and J    die 5 -> 5 and Q    die 6 -> 6 and K

Seat 0 takes the first turn and play goes clockwise (seat 0, 1, 2, ..., wrapping). Every
player starts with 0 points, 0 captured cards and a best-single-capture value of 0.

Your turn
---------
Play exactly one card from your hand. Its value is your target **T**. Then choose exactly one:

1. **Sum capture.** Take a set of one or more field cards whose values add to exactly T.
   The field cards and your played card go to your capture pile.
2. **Product capture.** Take a set of two or more field cards whose values multiply to
   exactly T. Aces count as 1 in a product, so a 7 can take A + 7 as a product, and an Ace
   can take two Aces (1 x 1 = 1).
3. **Trail.** Put the played card face up on the field and take nothing. Trailing is always
   allowed, even when a capture is available.

Only one set may be captured per turn; you may not combine two sets. If the field is empty
you must trail (no set exists).

Scoring a capture
-----------------
Let N be the number of cards moved to your capture pile this turn: your played card plus the
field cards taken.

* Sum capture: T x N points.
* Product capture: T x (N + 1) points.
* If T is one of the two current bounty ranks, **double** that result.
* If the capture leaves the field empty, add a flat **+10 sweep bonus** (never doubled).

Add every card taken, the played card included, to your captured-card count. If this turn's
total gain (sweep bonus included) beats your best-single-capture value, it becomes the new
best. You become the last capturer.

Bounty re-roll
--------------
Right after a capture whose target T was a bounty rank, re-roll the die. The new face sets
the bounty ranks from the next turn on. The die is never re-rolled after a trail or after a
capture on a non-bounty rank.

Draw
----
After your play, capture or trail, draw one card from the stock if the stock is not empty.
Then the turn passes clockwise.

Hand exhaustion and game end
----------------------------
While the stock lasts every hand stays at 4 cards. Once the stock is empty hands shrink by
one card per turn, and a player with an empty hand is skipped. The game ends the moment the
last card in any hand has been played: exactly 48 plays at every player count.

Any cards still on the field then go to the **last capturer**, who gains 2 points per card
and adds them to their captured-card count. If nobody ever captured, those cards are simply
discarded. Highest score wins.

Tie-breaks, applied in order until one player remains:

1. Higher captured-card count.
2. Higher best-single-capture value.
3. Higher seat number (acting later in the game is worth compensating).

(Implementation note: the tie-breaks are folded into the reported score as vanishingly small
bonuses - captured cards x 1e-4, best capture x 1e-7, seat x 1e-10 - so that a higher raw
score always wins and only exact ties are decided by the tie-breaks.)

Worked example
--------------
Field A\u2660 2\u2666 3\u2663 6\u2665 9\u2660, die 3 (bounties 3 and 10). Holding a 6 you may sum-capture 6\u2665
alone (N = 2, 12 points), sum-capture A + 2 + 3 (N = 4, 24 points), product-capture 2 x 3
(N = 3, so 6 x 4 = 24 points), or trail. Holding a 10 instead, sum-capturing A + 3 + 6 gives
10 x 4 = 40, doubled to 80 for the bounty rank, and the die is then re-rolled.

Strategy note: a big target that hauls in four small cards beats a big target that grabs one
big card, and every card you trail is ammunition for the player on your left.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from random import Random

from gd_cards import Card, Deck
from gd_dice import roll_d6
from gd_gamecore import GMLike

HAND = 4
FIELD = 4
TOTAL_PLAYS = 52 - FIELD  # 48 turns at every player count
SWEEP_BONUS = 10
LEFTOVER_PER_CARD = 2


def bounty_ranks(die: int) -> tuple[int, int]:
    """The two ranks doubled by die face ``die``: ``die`` and ``die + 7``."""
    return (die, die + 7)


@dataclass(frozen=True)
class ReckonerState:
    hands: tuple[tuple[Card, ...], ...]
    stock: tuple[Card, ...]
    field: tuple[Card, ...]
    points: tuple[int, ...]
    captured: tuple[int, ...]
    best: tuple[int, ...]  # best single-turn gain
    last_capturer: int  # -1 while nobody has captured
    die: int
    current: int
    plays: int
    over: bool


class Reckoner:
    """See module docstring for the rulesheet."""

    def __init__(self, n_players: int, gm: GMLike | None = None):
        if not 2 <= n_players <= 4:
            raise ValueError("2-4 players")
        self.n_players = n_players
        self.gm = gm

    # -- lifecycle -----------------------------------------------------------------------
    def setup(self, rng: Random) -> ReckonerState:
        deck = Deck(jokers=0).shuffle(rng)
        hands = tuple(tuple(sorted(h)) for h in deck.deal(self.n_players, HAND))
        field = tuple(deck.draw(FIELD))
        zeros = (0,) * self.n_players
        return ReckonerState(
            hands=hands,
            stock=tuple(deck.cards),
            field=field,
            points=zeros,
            captured=zeros,
            best=zeros,
            last_capturer=-1,
            die=roll_d6(rng).values[0],
            current=0,
            plays=0,
            over=False,
        )

    def current_player(self, s: ReckonerState) -> int:
        return s.current

    # -- actions -------------------------------------------------------------------------
    def legal_actions(self, s: ReckonerState) -> list[tuple]:
        if s.over:
            return []
        hand = s.hands[s.current]
        vals = [c.rank for c in s.field]
        out: list[tuple] = []
        for card in hand:
            t = card.rank
            for idx in _sum_sets(vals, t):
                out.append(("capture", str(card), "sum", tuple(str(s.field[i]) for i in idx)))
            for idx in _prod_sets(vals, t):
                out.append(("capture", str(card), "prod", tuple(str(s.field[i]) for i in idx)))
            out.append(("trail", str(card)))
        return out

    def step(self, s: ReckonerState, a: tuple, rng: Random) -> ReckonerState:
        if s.over:
            raise ValueError("game is over")
        p = s.current
        kind, card_name = a[0], a[1]
        card = _find(s.hands[p], card_name, f"card {card_name} not in hand of seat {p}")
        hands = list(s.hands)
        hands[p] = tuple(c for c in hands[p] if c != card)
        points, captured, best = list(s.points), list(s.captured), list(s.best)
        field, die, last = list(s.field), s.die, s.last_capturer

        if kind == "trail":
            field.append(card)
        elif kind == "capture":
            mode, names = a[2], a[3]
            taken = [_find(field, n, f"card {n} not on the field") for n in names]
            if len(set(names)) != len(names):
                raise ValueError("a field card may be used only once")
            t, vals = card.rank, [c.rank for c in taken]
            if mode == "sum":
                if not taken or sum(vals) != t:
                    raise ValueError(f"{names} does not add up to {t}")
                gain = t * (len(taken) + 1)
            elif mode == "prod":
                prod = 1
                for v in vals:
                    prod *= v
                if len(taken) < 2 or prod != t:
                    raise ValueError(f"{names} is not a product of {t}")
                gain = t * (len(taken) + 2)
            else:
                raise ValueError(f"unknown capture mode {mode!r}")
            if t in bounty_ranks(die):
                gain *= 2
                die = roll_d6(rng).values[0]  # bounty cashed: the die is re-rolled at once
            for c in taken:
                field.remove(c)
            if not field:
                gain += SWEEP_BONUS
            points[p] += gain
            captured[p] += len(taken) + 1
            best[p] = max(best[p], gain)
            last = p
        else:
            raise ValueError(f"unknown action {a!r}")

        stock = list(s.stock)
        if stock:  # draw back up
            hands[p] = tuple(sorted(hands[p] + (stock.pop(0),)))
        plays = s.plays + 1

        if plays >= TOTAL_PLAYS:  # last card of the last hand has been played
            if field and last >= 0:
                points[last] += LEFTOVER_PER_CARD * len(field)
                captured[last] += len(field)
                field = []
            return ReckonerState(
                tuple(hands), tuple(stock), tuple(field), tuple(points), tuple(captured),
                tuple(best), last, die, p, plays, True,
            )

        nxt = (p + 1) % self.n_players
        while not hands[nxt]:  # empty hands are skipped once the stock has run out
            nxt = (nxt + 1) % self.n_players
        return ReckonerState(
            tuple(hands), tuple(stock), tuple(field), tuple(points), tuple(captured),
            tuple(best), last, die, nxt, plays, False,
        )

    def is_terminal(self, s: ReckonerState) -> bool:
        return s.over

    def scores(self, s: ReckonerState) -> list[float]:
        # raw points first, then the tie-breaks as negligible bonuses (see rulesheet)
        return [
            float(s.points[p]) + 1e-4 * s.captured[p] + 1e-7 * s.best[p] + 1e-10 * p
            for p in range(self.n_players)
        ]

    # -- views ---------------------------------------------------------------------------
    def observe(self, s: ReckonerState, p: int) -> dict:
        return {
            "seat": p,
            "hand": tuple(str(c) for c in s.hands[p]),
            "field": tuple(str(c) for c in s.field),
            "hand_sizes": tuple(len(h) for h in s.hands),
            "stock": len(s.stock),
            "die": s.die,
            "bounty": bounty_ranks(s.die),
            "points": s.points,
            "captured": s.captured,
            "best": s.best,
            "last_capturer": s.last_capturer,
            "current": s.current,
            "plays": s.plays,
            "over": s.over,
        }

    def describe(self, s: ReckonerState) -> str:
        lo, hi = bounty_ranks(s.die)
        field = " ".join(str(c) for c in s.field) or "(empty)"
        return (
            f"play {s.plays}/{TOTAL_PLAYS} seat {s.current} to act; die={s.die} bounty={_name(lo)}/{_name(hi)}; "
            f"field: {field}; stock={len(s.stock)}; points={list(s.points)}; hands={[len(h) for h in s.hands]}"
        )


# -- helpers -----------------------------------------------------------------------------
def _name(rank: int) -> str:
    return {1: "A", 11: "J", 12: "Q", 13: "K"}.get(rank, str(rank))


def _find(cards, name: str, err: str) -> Card:
    for c in cards:
        if str(c) == name:
            return c
    raise ValueError(err)


def _sum_sets(vals: list[int], target: int) -> list[tuple[int, ...]]:
    """Index sets of one or more field cards whose values add to ``target``."""
    out: list[tuple[int, ...]] = []

    def walk(i: int, total: int, chosen: tuple[int, ...]) -> None:
        if total == target and chosen:
            out.append(chosen)
            return  # every value is >= 1, so no superset can still add to target
        for j in range(i, len(vals)):
            if total + vals[j] <= target:
                walk(j + 1, total + vals[j], chosen + (j,))

    walk(0, 0, ())
    return out


def _prod_sets(vals: list[int], target: int) -> list[tuple[int, ...]]:
    """Index sets of two or more field cards whose values multiply to ``target``."""
    out: list[tuple[int, ...]] = []

    def walk(i: int, prod: int, chosen: tuple[int, ...]) -> None:
        if prod == target and len(chosen) >= 2:
            out.append(chosen)
        for j in range(i, len(vals)):
            if prod * vals[j] <= target:  # values are >= 1, so products never shrink
                walk(j + 1, prod * vals[j], chosen + (j,))

    walk(0, 1, ())
    return out


GAME = Reckoner
