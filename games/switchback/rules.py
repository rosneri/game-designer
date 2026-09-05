"""Switchback — a climbing game where every card you put down scores immediately.

RULESHEET
=========
Players: 2-4.  Components: one standard 52-card deck, no jokers, no dice.

Ranks from low to high: 2 3 4 5 6 7 8 9 10 J Q K A. Suits (S H D C) never affect ranking;
they only tell two cards of the same rank apart.

Setup
-----
Shuffle the deck. Deal 7 cards to each player. The rest is the face-down **stock** (38 cards
with 2 players, 31 with 3, 24 with 4). Everyone starts with 0 points, 0 ascents won and 0
summits. Seat 0 leads the first ascent. Play is clockwise, skipping players who have passed in
the current ascent.

Combinations
------------
A legal combination is exactly one of:
  * **Single** - 1 card. Its rank is the card's rank.
  * **Pair** - 2 cards of the same rank. Its rank is that rank.
  * **Triple** - 3 cards of the same rank. Its rank is that rank.
  * **Straight** - 3, 4 or 5 cards of strictly consecutive ranks in any suits, no wrap-around.
    2-3-4 is the lowest 3-straight, Q-K-A the highest. The Ace is high only. Its rank is the
    rank of its top card.

Four cards of one rank are not a combination and have no special power. The **shape** of a
combination is its kind together with its size, so a 3-straight and a 4-straight are different
shapes. Combination B beats combination A only if B has the same shape as A and B's rank is
strictly higher.

Ascents
-------
The game is a sequence of ascents. An ascent starts with an empty table and nobody passed.

  * The **leader** must play any legal combination from their hand. A leader may never pass.
  * Then the turn moves clockwise, skipping players who have passed this ascent. With a
    combination on the table you must do exactly one of:
      - **Play** a combination that beats the table combination. It becomes the new table
        combination and you become the holder. Played cards go to a face-down discard and
        never come back.
      - **Pass**. You draw the top card of the stock (nothing if the stock is empty), you are
        out of this ascent and you are skipped until it ends. You may pass even when you could
        play. The draw happens at once, before the turn moves on.

Scoring a play (immediate)
--------------------------
When you play a combination you score **1 point per card played**. If its rank is exactly one
rank above the rank of the combination it beat (a pair of 9s on a pair of 8s, a 3-straight
topped by J on a 3-straight topped by 10), that is a **tight step** and you score **1 extra
point**. A lead is never a tight step.

Ending an ascent
----------------
After every action, look clockwise from the player who just acted for the first player who has
not passed. If that player is the current holder - that is, everybody else has passed - the
ascent ends. The holder scores **2 points** and 1 ascent won, the table is cleared, all pass
flags reset, and the holder leads the next ascent and takes the next turn. With 2 players an
ascent therefore ends as soon as the non-holder passes.

Summit
------
When a play empties your hand you immediately score **3 points** and 1 summit. Then:
  * If the stock is not empty you draw 3 cards from it (or all that remain if fewer than 3),
    and the ascent goes on normally with you as holder.
  * If the stock is empty the game ends at once.
Because of this, no player ever has to act with an empty hand.

End of the game
---------------
The game ends the moment a hand becomes empty while the stock is empty. That player is the
**finisher**. Every player then subtracts **1 point per card still in hand**; the finisher
subtracts nothing. The highest total wins.

The game cannot stall: while the stock lasts every pass and every summit removes a stock card,
and once the stock is empty every ascent removes at least one card from some hand with no
refill, so hands only shrink and a finisher must appear.

Tie-break for the top place, applied in order until it resolves
---------------------------------------------------------------
  1. more summits;
  2. fewer cards left in hand;
  3. more ascents won;
  4. the player met first counting clockwise from the seat just after the finisher (the
     finisher is last in that order).
This always resolves. The implementation folds the tie-break into ``scores`` as a fraction
below 1/2, so the final ranking is exact and a finished game is never a draw.

Notes on this implementation
----------------------------
  * Actions are ``("play", card, ...)`` - for example ``("play", "9H", "9S")`` or
    ``("play", "8C", "9C", "10D")`` - and ``("pass",)``. Cards are written rank+suit, such as
    ``"10S"`` or ``"AH"``.
  * Suits are irrelevant to the rules, so the legal-action list offers each *rank pattern*
    once: when several suits of a rank could fill the same slot, the lowest-sorted card is
    used. Nothing is lost, since which suit you discard can never change the game.
  * ``observe`` shows you your own hand, the table combination, the holder, the pass flags,
    every public counter and the sizes of the other hands and of the stock - never another
    player's cards nor the order of the stock.

Strategy note: passing is not idle time, it is your only supply line, so spend the early
ascents buying cards and keep shapes that opponents cannot answer. Tight steps reward creeping
up by one rank instead of smashing the table with an Ace, and a summit both pays 3 and hands
you three fresh cards - but the moment the stock runs dry every card left in your hand turns
into a penalty, so plan the last descent before it starts.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from random import Random

from gd_gamecore import GMLike

RANKS = ("2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A")
SUITS = ("S", "H", "D", "C")
RANK_INDEX = {r: i for i, r in enumerate(RANKS)}  # "2" -> 0 ... "A" -> 12
SUIT_INDEX = {s: i for i, s in enumerate(SUITS)}

HAND_SIZE = 7
SUMMIT_BONUS = 3
SUMMIT_DRAW = 3
ASCENT_BONUS = 2
TIGHT_STEP_BONUS = 1
STRAIGHT_SIZES = (3, 4, 5)

Card = str  # "7H", "10S", "AC"
Combo = tuple[str, int, int, tuple[Card, ...]]  # (kind, size, rank index, cards)


def card_key(c: Card) -> tuple[int, int]:
    """Sort key: by rank, then by suit order S H D C."""
    return (RANK_INDEX[c[:-1]], SUIT_INDEX[c[-1]])


def rank_of(c: Card) -> int:
    return RANK_INDEX[c[:-1]]


def combo_of(cards: tuple[Card, ...]) -> Combo | None:
    """Classify a set of distinct cards, or return None when it is not a combination."""
    n = len(cards)
    ranks = sorted(rank_of(c) for c in cards)
    if n == 1:
        return ("single", 1, ranks[0], cards)
    if n in (2, 3) and len(set(ranks)) == 1:
        return ("pair" if n == 2 else "triple", n, ranks[0], cards)
    if n in STRAIGHT_SIZES and len(set(ranks)) == n and ranks[-1] - ranks[0] == n - 1:
        return ("straight", n, ranks[-1], cards)
    return None


def combinations_in(hand: list[Card]) -> list[Combo]:
    """Every combination available in ``hand``, one entry per rank pattern (lowest suits used)."""
    by_rank: dict[int, list[Card]] = {}
    for c in sorted(hand, key=card_key):
        by_rank.setdefault(rank_of(c), []).append(c)
    out: list[Combo] = []
    for r in sorted(by_rank):
        group = by_rank[r]
        for kind, size in (("single", 1), ("pair", 2), ("triple", 3)):
            if len(group) >= size:
                out.append((kind, size, r, tuple(group[:size])))
    for size in STRAIGHT_SIZES:
        for lo in range(len(RANKS) - size + 1):
            need = range(lo, lo + size)
            if all(r in by_rank for r in need):
                cards = tuple(by_rank[r][0] for r in need)
                out.append(("straight", size, lo + size - 1, cards))
    return out


def beats(new: Combo, table: Combo) -> bool:
    """Same kind, same size, strictly higher rank."""
    return new[0] == table[0] and new[1] == table[1] and new[2] > table[2]


@dataclass
class SwitchbackState:
    hands: list[list[Card]]
    stock: list[Card]  # top of the stock is the last element
    discard: list[Card] = field(default_factory=list)
    table: Combo | None = None
    holder: int = 0
    passed: list[bool] = field(default_factory=list)
    points: list[int] = field(default_factory=list)
    ascents_won: list[int] = field(default_factory=list)
    summits: list[int] = field(default_factory=list)
    to_act: int = 0
    ascent: int = 1
    over: bool = False
    finisher: int | None = None


class Switchback:
    """See the module docstring for the rulesheet."""

    def __init__(self, n_players: int, gm: GMLike | None = None):
        if not 2 <= n_players <= 4:
            raise ValueError("Switchback is for 2-4 players")
        self.n_players = n_players
        self.gm = gm

    # ---------------------------------------------------------------- lifecycle
    def setup(self, rng: Random) -> SwitchbackState:
        deck = [r + s for s in SUITS for r in RANKS]
        rng.shuffle(deck)
        n = self.n_players
        hands = [sorted(deck[i * HAND_SIZE:(i + 1) * HAND_SIZE], key=card_key) for i in range(n)]
        stock = deck[n * HAND_SIZE:]
        return SwitchbackState(
            hands=hands,
            stock=stock,
            passed=[False] * n,
            points=[0] * n,
            ascents_won=[0] * n,
            summits=[0] * n,
            holder=0,
            to_act=0,
        )

    def current_player(self, s: SwitchbackState) -> int:
        return s.to_act

    def legal_actions(self, s: SwitchbackState) -> list[tuple]:
        if s.over:
            return []
        combos = combinations_in(s.hands[s.to_act])
        if s.table is None:  # a lead: anything goes, and passing is forbidden
            return [("play", *c[3]) for c in combos]
        return [("play", *c[3]) for c in combos if beats(c, s.table)] + [("pass",)]

    def step(self, s: SwitchbackState, a: tuple, rng: Random) -> SwitchbackState:
        s = copy.deepcopy(s)
        if s.over:
            raise ValueError("the game is over")
        p = s.to_act
        if a == ("pass",):
            if s.table is None:
                raise ValueError("the ascent leader may not pass")
            s.passed[p] = True
            if s.stock:
                s.hands[p].append(s.stock.pop())
                s.hands[p].sort(key=card_key)
        elif a and a[0] == "play":
            self._play(s, p, tuple(a[1:]))
            if s.over:
                return s
        else:
            raise ValueError(f"illegal action {a!r}")
        self._advance(s, p)
        return s

    def _play(self, s: SwitchbackState, p: int, cards: tuple[Card, ...]) -> None:
        hand = s.hands[p]
        if len(set(cards)) != len(cards) or any(c not in hand for c in cards):
            raise ValueError(f"seat {p} does not hold {cards}")
        combo = combo_of(cards)
        if combo is None:
            raise ValueError(f"{cards} is not a legal combination")
        if s.table is not None and not beats(combo, s.table):
            raise ValueError(f"{cards} does not beat {s.table[3]}")
        tight = s.table is not None and combo[2] == s.table[2] + 1
        s.points[p] += len(cards) + (TIGHT_STEP_BONUS if tight else 0)
        for c in cards:
            hand.remove(c)
        s.discard.extend(cards)
        s.table, s.holder = combo, p
        if hand:
            return
        s.points[p] += SUMMIT_BONUS  # summit
        s.summits[p] += 1
        if not s.stock:
            s.over, s.finisher = True, p
            return
        for _ in range(min(SUMMIT_DRAW, len(s.stock))):
            hand.append(s.stock.pop())
        hand.sort(key=card_key)

    def _advance(self, s: SwitchbackState, actor: int) -> None:
        """Give the turn to the next active player, ending the ascent when only the holder is left."""
        n = self.n_players
        nxt = next((actor + k) % n for k in range(1, n + 1) if not s.passed[(actor + k) % n])
        if nxt == s.holder:  # everyone else stepped off the trail
            s.points[s.holder] += ASCENT_BONUS
            s.ascents_won[s.holder] += 1
            s.table = None
            s.passed = [False] * n
            s.ascent += 1
            s.to_act = s.holder
        else:
            s.to_act = nxt

    # ---------------------------------------------------------------- results
    def is_terminal(self, s: SwitchbackState) -> bool:
        return s.over

    def scores(self, s: SwitchbackState) -> list[float]:
        out = [float(v) for v in s.points]
        if not s.over:
            return out
        n = self.n_players
        for i in range(n):
            out[i] -= len(s.hands[i])
        first = ((s.finisher or 0) + 1) % n
        order = sorted(
            range(n),
            key=lambda i: (-s.summits[i], len(s.hands[i]), -s.ascents_won[i], (i - first) % n),
        )
        for place, i in enumerate(order):  # a fraction < 1/2 keeps whole points dominant
            out[i] += (n - 1 - place) / (2 * n)
        return out

    # ---------------------------------------------------------------- views
    def observe(self, s: SwitchbackState, p: int) -> dict:
        return {
            "seat": p,
            "hand": tuple(s.hands[p]),
            "to_act": s.to_act,
            "table": None if s.table is None else (s.table[0], s.table[1], RANKS[s.table[2]], s.table[3]),
            "holder": s.holder if s.table is not None else None,
            "passed": tuple(s.passed),
            "hand_sizes": tuple(len(h) for h in s.hands),
            "stock": len(s.stock),
            "points": tuple(s.points),
            "ascents_won": tuple(s.ascents_won),
            "summits": tuple(s.summits),
            "ascent": s.ascent,
            "over": s.over,
        }

    def describe(self, s: SwitchbackState) -> str:
        if s.table is None:
            table = "empty (lead)"
        else:
            table = f"{s.table[0]}-{s.table[1]} {RANKS[s.table[2]]} [{' '.join(s.table[3])}] by seat {s.holder}"
        state = "over" if s.over else f"seat {s.to_act} to act"
        return (
            f"ascent {s.ascent}: table {table}; {state}; stock={len(s.stock)} "
            f"hands={[len(h) for h in s.hands]} passed={[int(b) for b in s.passed]} "
            f"points={s.points} ascents={s.ascents_won} summits={s.summits}"
        )


GAME = Switchback
