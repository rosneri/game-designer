"""Undercroft — a torchlit corridor of monsters and loot.

RULESHEET
=========
Players: 2-4.  Components: one standard 52-card deck (no jokers) and one six-sided die.

Card values: 2-10 at face value, Jack 11, Queen 12, King 13, Ace 14. Cards are written
rank+suit, e.g. ``7S``, ``TD``, ``QH``, ``AC``. Black cards (spades S, clubs C) are monsters
while they lie in the corridor. Red cards (hearts H, diamonds D) are loot while they lie in
the corridor. Any card held by a player is gear (a possible weapon), whatever its colour.

Setup
-----
Shuffle the deck. Deal 3 cards face down to each player as their hand. Deal 4 cards face up
in a row: the corridor. Position 0 is the leftmost card (nearest the entrance), position 3 the
rightmost. The rest of the cards form the face-down draw pile. Each player starts with an
empty trophy pile and an empty hoard, both face up. Seat 0 starts; play is clockwise. The
hand limit is 5 cards.

Corridor terms
--------------
A corridor card at position i is *guarded* if it is red and the card at position i-1 exists
and is black. A red card at position 0, or a red card whose left neighbour is red, is
*unguarded*. Each corridor card may carry a *pot*: a stack of face-up cards lying beneath it.
Pots start empty and only ever grow under monsters that have been fought and survived.

Turn
----
On your turn you must take exactly one of these actions if any is legal. If none is legal,
your turn is skipped.

1. **Fight** — legal if you hold at least one card and the corridor contains at least one
   black card. Choose one black corridor card (the monster) and one card from your hand (the
   weapon). Reveal the weapon and roll the die. Your attack total is the weapon's value, plus
   2 if the weapon's suit is *identical* to the monster's suit (spade vs spade, club vs club;
   matching colour alone is not enough), plus the die result.

   * Attack total >= monster's value: you win. The weapon is spent: it is discarded and takes
     no further part in the game. The monster goes to your trophy pile. All cards in the
     monster's pot go to your hoard. If the card immediately to the monster's right (position i+1) exists and is
     red, it goes to your hoard too, together with any cards in its pot.
   * Attack total < monster's value: you lose. The weapon goes face up into the monster's pot,
     making that monster a fatter prize for whoever finishes it. Nothing else happens.

2. **Loot** — legal if the corridor contains at least one unguarded red card. Take one
   unguarded red card, together with any cards in its pot, into your hoard.

3. **Rest** — legal if your hand holds fewer than 5 cards and the draw pile is not empty.
   Draw from the top of the draw pile until you have drawn 2 cards, or your hand reaches 5,
   or the draw pile is empty, whichever comes first. (With an empty draw pile Rest is illegal
   even with an empty hand.)

Refill
------
After the action, close any gaps: slide the remaining corridor cards left, keeping their order
and keeping each card's pot beneath it. Then deal cards face up from the top of the draw pile
onto the right end of the corridor until the corridor holds 4 cards or the draw pile is empty.
New corridor cards arrive with empty pots. A weapon put on the bottom of the draw pile this
turn can be dealt out again later if it reaches the top.

End trigger
-----------
At the end of any turn (after the refill), if the draw pile is empty or the corridor holds
fewer than 4 cards, the end is
triggered. Once set, the end trigger is never cleared. The game ends at the end of the first
turn that is both (a) taken or skipped by the last seat (seat number = player count minus 1)
and (b) taken while the end trigger is set. So every player gets the same number of turns.

Scoring
-------
Your score is the sum of the values of all cards in your trophy pile plus all cards in your
hoard. Cards in hand score nothing. Highest score wins. Tie-breaks, applied in order until one
player remains: (1) most cards in the trophy pile; (2) highest single card value in the trophy
pile (no trophies counts as 0); (3) fewest cards in trophy pile plus hoard; (4) highest seat
number.

Implementation notes / chosen readings of ambiguous points
----------------------------------------------------------
* The die is rolled after the weapon and monster are fixed and is never rerolled.
* The weapon is moved (discarded on a win, pot on a loss) before the refill. Because spent
  weapons leave the game and the draw pile is never replenished, the pile always runs dry and
  the game always ends.
* ``scores`` returns the raw point totals; the documented tie-breaks are applied as tiny
  lexicographic bonuses far smaller than one point, so the ranking is strict while the whole
  number part still reads as the player's point total.
"""
from __future__ import annotations

import copy
from random import Random
from typing import Any

from gd_gamecore import GMLike

RANKS = {"2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9,
         "T": 10, "J": 11, "Q": 12, "K": 13, "A": 14}
SUITS = ("S", "H", "D", "C")
BLACK = ("S", "C")
HAND_LIMIT = 5
START_HAND = 3
CORRIDOR = 4
REST_DRAW = 2


def value(card: str) -> int:
    """Card value: 2-10 face, J=11, Q=12, K=13, A=14."""
    return RANKS[card[0]]


def suit(card: str) -> str:
    return card[1]


def is_black(card: str) -> bool:
    return card[1] in BLACK


def is_red(card: str) -> bool:
    return card[1] not in BLACK


class Undercroft:
    """See module docstring for the rulesheet."""

    def __init__(self, n_players: int, gm: GMLike | None = None):
        if not 2 <= n_players <= 4:
            raise ValueError("2-4 players")
        self.n_players = n_players
        self.gm = gm

    # -- lifecycle -----------------------------------------------------------------------
    def setup(self, rng: Random) -> dict:
        deck = [r + s for s in SUITS for r in RANKS]
        rng.shuffle(deck)
        hands = [sorted(deck[i * START_HAND:(i + 1) * START_HAND]) for i in range(self.n_players)]
        deck = deck[self.n_players * START_HAND:]
        corridor = [[c, []] for c in deck[:CORRIDOR]]
        deck = deck[CORRIDOR:]
        return {
            "deck": deck,
            "discard": [],
            "corridor": corridor,
            "hands": hands,
            "trophies": [[] for _ in range(self.n_players)],
            "hoard": [[] for _ in range(self.n_players)],
            "turn": 0,
            "end_triggered": False,
            "over": False,
            "last_roll": None,
            "log": "",
        }

    def current_player(self, s: dict) -> int:
        return s["turn"]

    # -- rules ---------------------------------------------------------------------------
    def _unguarded(self, corridor: list) -> list[int]:
        out = []
        for i, (card, _pot) in enumerate(corridor):
            if is_red(card) and (i == 0 or is_red(corridor[i - 1][0])):
                out.append(i)
        return out

    def legal_actions(self, s: dict) -> list[tuple]:
        if s["over"]:
            return []
        p = s["turn"]
        hand, corridor = s["hands"][p], s["corridor"]
        acts: list[tuple] = []
        for i, (card, _pot) in enumerate(corridor):
            if is_black(card):
                for w in hand:
                    acts.append(("fight", i, w))
        for i in self._unguarded(corridor):
            acts.append(("loot", i))
        if len(hand) < HAND_LIMIT and s["deck"]:
            acts.append(("rest",))
        if not acts:
            acts.append(("skip",))  # forced no-op: the turn is skipped
        return acts

    def step(self, s: dict, a: tuple, rng: Random) -> dict:
        if s["over"]:
            raise ValueError("game is over")
        if a not in self.legal_actions(s):
            raise ValueError(f"illegal action {a}")
        s = copy.deepcopy(s)
        p = s["turn"]
        s["last_roll"] = None
        kind = a[0]

        if kind == "fight":
            i, weapon = a[1], a[2]
            monster, pot = s["corridor"][i]
            roll = rng.randint(1, 6)
            s["last_roll"] = roll
            bonus = 2 if suit(weapon) == suit(monster) else 0
            total = value(weapon) + bonus + roll
            s["hands"][p].remove(weapon)
            if total >= value(monster):
                s["discard"].append(weapon)  # spent: out of the game
                s["trophies"][p].append(monster)
                s["hoard"][p].extend(pot)
                taken = [i]
                if i + 1 < len(s["corridor"]) and is_red(s["corridor"][i + 1][0]):
                    nxt, npot = s["corridor"][i + 1]
                    s["hoard"][p].append(nxt)
                    s["hoard"][p].extend(npot)
                    taken.append(i + 1)
                s["corridor"] = [e for j, e in enumerate(s["corridor"]) if j not in taken]
                s["log"] = f"seat {p} fought {monster} with {weapon} (roll {roll}, total {total}): slain"
            else:
                s["corridor"][i][1].append(weapon)
                s["log"] = f"seat {p} fought {monster} with {weapon} (roll {roll}, total {total}): missed"
        elif kind == "loot":
            i = a[1]
            card, pot = s["corridor"].pop(i)
            s["hoard"][p].append(card)
            s["hoard"][p].extend(pot)
            s["log"] = f"seat {p} looted {card}" + (f" +{len(pot)} pot" if pot else "")
        elif kind == "rest":
            drawn = []
            while len(drawn) < REST_DRAW and len(s["hands"][p]) < HAND_LIMIT and s["deck"]:
                drawn.append(s["deck"].pop(0))
                s["hands"][p].append(drawn[-1])
            s["hands"][p].sort()
            s["log"] = f"seat {p} rested (drew {len(drawn)})"
        else:  # skip
            s["log"] = f"seat {p} had no legal action"

        # refill: gaps are already closed by the list operations above
        while len(s["corridor"]) < CORRIDOR and s["deck"]:
            s["corridor"].append([s["deck"].pop(0), []])
        if not s["deck"] or len(s["corridor"]) < CORRIDOR:
            s["end_triggered"] = True
        if s["end_triggered"] and p == self.n_players - 1:
            s["over"] = True
        else:
            s["turn"] = (p + 1) % self.n_players
        return s

    def is_terminal(self, s: dict) -> bool:
        return bool(s["over"])

    # -- scoring -------------------------------------------------------------------------
    def _points(self, s: dict, p: int) -> int:
        return sum(value(c) for c in s["trophies"][p]) + sum(value(c) for c in s["hoard"][p])

    def scores(self, s: dict) -> list[float]:
        # tie-breaks as sub-point lexicographic bonuses (each strictly finer than the last)
        out = []
        for p in range(self.n_players):
            tro = s["trophies"][p]
            b1 = len(tro) / 60.0                      # most trophies      (< 1/2)
            b2 = (max((value(c) for c in tro), default=0)) / 14.0 / 3600.0
            b3 = (60 - min(60, len(tro) + len(s["hoard"][p]))) / 60.0 / 216000.0
            b4 = p / 4.0 / 12960000.0
            out.append(float(self._points(s, p)) + b1 + b2 + b3 + b4)
        return out

    # -- views ---------------------------------------------------------------------------
    def observe(self, s: dict, p: int) -> dict[str, Any]:
        return {
            "seat": p,
            "hand": tuple(s["hands"][p]),
            "corridor": tuple((c, tuple(pot)) for c, pot in s["corridor"]),
            "hand_sizes": tuple(len(h) for h in s["hands"]),
            "trophies": tuple(tuple(t) for t in s["trophies"]),
            "hoard": tuple(tuple(h) for h in s["hoard"]),
            "points": tuple(self._points(s, q) for q in range(self.n_players)),
            "deck": len(s["deck"]),
            "turn": s["turn"],
            "end_triggered": s["end_triggered"],
            "last_roll": s["last_roll"],
        }

    def describe(self, s: dict) -> str:
        cor = " | ".join(
            c + (f"(+{len(pot)})" if pot else "") for c, pot in s["corridor"]
        ) or "empty"
        pts = [self._points(s, q) for q in range(self.n_players)]
        tail = " END TRIGGERED" if s["end_triggered"] else ""
        return (
            f"corridor: {cor}; deck={len(s['deck'])} points={pts} "
            f"hands={[len(h) for h in s['hands']]} turn=seat {s['turn']}{tail}"
            + (f"; {s['log']}" if s["log"] else "")
        )


GAME = Undercroft
