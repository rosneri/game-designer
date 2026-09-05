"""Bindle — push a card across the table and take what comes back.

RULESHEET
=========
Players: 2-4.  Components: 52-card deck + 2 jokers (54 cards) and one six-sided die.

Every player runs a stall: a face-up stack whose top card is all that matters. You score by
laying rank-adjacent cards to grow a chain — on your own stall for a safe payout, or onto a
rival's stall ("hawking") where an adjacent card pays *you* their new chain length but leaves
them a longer chain to milk, while a junk card wrecks their chain and pays nothing. Either way
the rival must hand you a card from their hand before they learn what you brought.

Cards and adjacency
-------------------
Ranks: Ace = 1, 2-10 face value, Jack = 11, Queen = 12, King = 13. Two cards are *adjacent*
when their ranks differ by exactly 1 (no wraparound: Ace touches only 2, King only Queen).
A joker has no rank and no suit; a joker is adjacent to nothing and nothing is adjacent to a
joker. Cards are written like "7H" (seven of hearts), "TS" (ten of spades), "AD", "KC",
and the jokers are "JK1" and "JK2".

Setup
-----
Shuffle all 54 cards. Deal 4 cards to each player as a private hand. The rest is the face-down
draw pile. Every stall starts empty (chain length 0) and every score starts at 0. The deal also
fixes the start player: the cut is random, so no seat is structurally favoured (this is the one
simplification of the paper rules, which nail the start player to seat 0). Play is clockwise.

Laying a card
-------------
Laying a card onto a stall (yours or a rival's):
* If the stall is empty, or the card is not adjacent to the current top card, or either card is
  a joker: the card goes on top, the chain length L becomes 1, and the lay scores 0.
* Otherwise the card goes on top, L increases by 1, and the lay scores L points — or 2xL if the
  new card matches the suit of the card it covers.
Points from a lay always go to the player who laid the card, whatever stall it landed on.

Your turn
---------
Take exactly one action:

1. **Lay** — ``("lay", card)``. Lay a card from your hand on your own stall, score it, then draw
   the top card of the pile (skip the draw if the pile is empty).

2. **Hawk** — ``("swap", card, seat)``. Push a card face down to a rival who has at least one
   card in hand. Without seeing it, the rival answers with one card of their own, face down
   (``("give", card)``). Then, in order:
   a. Your card is revealed and laid on the *rival's* stall. An adjacent card pays *you* their
      new chain length (doubled on a suit match); anything else resets their chain to 1 and pays
      nothing.
   b. Roll the die. On a 1 or 2 customs *inspect* the rival's answer: it is shown to everybody,
      and if it is a joker the rival loses 2 points at once (scores may go negative). On 3-6 the
      card stays secret and only you see it.
   c. You take the rival's card into your hand.
   d. The rival draws the top card of the pile (skip if the pile is empty).
   You never draw after hawking; the rival does. Hand sizes stay at 4 while the pile lasts.

Jokers
------
A joker can be laid on any stall (chain resets to 1, scores 0, and the next card laid there also
scores 0) or handed over as an answer to a hawk. Every joker still in your hand at the bell costs
you 5 points.

Edge cases
----------
A player with an empty hand cannot be hawked at, and their turn is skipped (it still counts as a
turn of the round). If no rival can be targeted, only Lay is available. Empty hands are only
possible after the pile has run dry.

End of game
-----------
The moment the draw pile becomes empty, the round is played out: turns continue (with no further
draws) until the player immediately before the start player has acted, then the game ends. Every
player takes exactly the same number of turns.

Final score = points collected - 5 per joker in hand. Highest score wins; equal scores share the
win. (For groups that want an outright winner, break ties by longer own chain, then higher top
card of your own stall, then fewer jokers.)

Strategy note: the fat gift-lay onto a rival's long chain pays you now but hands them a longer
chain to farm, so the greedy hawk is often the losing hawk; and answering a hawk with a joker is
free money unless customs stop you.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from random import Random
from typing import Any

from gd_gamecore import GMLike

HAND = 4
JOKER_PENALTY = 5
INSPECT_PENALTY = 2
INSPECT_MAX = 2  # die 1-2 inspects the handed-over card
RANKS = "A23456789TJQK"
SUITS = "SHDC"


def rank_of(card: str) -> int:
    """Rank 1..13, or 0 for a joker."""
    return 0 if card.startswith("JK") else RANKS.index(card[0]) + 1


def suit_of(card: str) -> str:
    return "" if card.startswith("JK") else card[1]


def adjacent(a: str, b: str) -> bool:
    ra, rb = rank_of(a), rank_of(b)
    return ra > 0 and rb > 0 and abs(ra - rb) == 1


def make_deck() -> list[str]:
    return [r + s for s in SUITS for r in RANKS] + ["JK1", "JK2"]


@dataclass
class BindleState:
    hands: list[list[str]]
    stalls: list[list[str]]
    chain: list[int]
    points: list[int]
    draw: list[str]
    current: int
    start: int
    phase: str = "main"  # "main" | "respond"
    pending: tuple[int, int, str] | None = None  # (initiator, target, hidden card)
    over: bool = False
    log: list[str] = field(default_factory=list)


class Bindle:
    """See the module docstring for the rulesheet."""

    def __init__(self, n_players: int, gm: GMLike | None = None):
        if not 2 <= n_players <= 4:
            raise ValueError("2-4 players")
        self.n_players = n_players
        self.gm = gm

    # -- lifecycle -----------------------------------------------------------------------
    def setup(self, rng: Random) -> BindleState:
        deck = make_deck()
        rng.shuffle(deck)
        n = self.n_players
        hands = [sorted(deck[i * HAND:(i + 1) * HAND]) for i in range(n)]
        draw = deck[n * HAND:]
        start = rng.randrange(n)  # random cut for the start player: seats stay symmetric
        return BindleState(
            hands=hands,
            stalls=[[] for _ in range(n)],
            chain=[0] * n,
            points=[0] * n,
            draw=draw,
            current=start,
            start=start,
            log=[f"start seat {start}"],
        )

    def current_player(self, s: BindleState) -> int:
        return s.pending[1] if s.phase == "respond" else s.current

    def legal_actions(self, s: BindleState) -> list[tuple]:
        p = self.current_player(s)
        if s.phase == "respond":
            return [("give", c) for c in s.hands[p]]
        acts: list[tuple] = [("lay", c) for c in s.hands[p]]
        targets = [t for t in range(self.n_players) if t != p and s.hands[t]]
        acts += [("swap", c, t) for c in s.hands[p] for t in targets]
        return acts

    # -- mechanics -----------------------------------------------------------------------
    def _lay(self, s: BindleState, card: str, stall: int, scorer: int) -> int:
        top = s.stalls[stall][-1] if s.stalls[stall] else None
        if top is not None and adjacent(top, card):
            s.chain[stall] += 1
            gain = s.chain[stall] * (2 if suit_of(card) == suit_of(top) else 1)
        else:
            s.chain[stall] = 1
            gain = 0
        s.stalls[stall].append(card)
        s.points[scorer] += gain
        return gain

    def _draw(self, s: BindleState, p: int) -> None:
        if s.draw:
            s.hands[p].append(s.draw.pop(0))
            s.hands[p].sort()

    def _advance(self, s: BindleState) -> None:
        last = (s.start - 1) % self.n_players
        while True:
            if not s.draw and s.current == last:
                s.over = True
                return
            s.current = (s.current + 1) % self.n_players
            if s.hands[s.current]:
                return  # an empty-handed seat is skipped but still burns its turn

    def step(self, s: BindleState, a: Any, rng: Random) -> BindleState:
        if self.is_terminal(s):
            raise ValueError("game over")
        if a not in self.legal_actions(s):
            raise ValueError(f"illegal action {a}")
        s = copy.deepcopy(s)
        p = self.current_player(s)
        kind = a[0]
        if kind == "lay":
            card = a[1]
            s.hands[p].remove(card)
            gain = self._lay(s, card, p, p)
            s.log.append(f"seat {p} laid {card} on own stall (+{gain})")
            self._draw(s, p)
            self._advance(s)
        elif kind == "swap":
            card, target = a[1], a[2]
            s.hands[p].remove(card)
            s.pending = (p, target, card)
            s.phase = "respond"
            s.log.append(f"seat {p} hawks seat {target}")
        else:  # ("give", card)
            initiator, target, hawked = s.pending
            given = a[1]
            s.hands[target].remove(given)
            gain = self._lay(s, hawked, target, initiator)
            s.log.append(f"seat {initiator} laid {hawked} on seat {target} (+{gain})")
            die = rng.randint(1, 6)
            if die <= INSPECT_MAX:
                s.log.append(f"customs roll {die}: seat {target} handed over {given}")
                if given.startswith("JK"):
                    s.points[target] -= INSPECT_PENALTY
                    s.log.append(f"contraband! seat {target} -{INSPECT_PENALTY}")
            else:
                s.log.append(f"customs roll {die}: handover unseen")
            s.hands[initiator].append(given)
            s.hands[initiator].sort()
            self._draw(s, target)
            s.pending, s.phase = None, "main"
            self._advance(s)
        del s.log[:-8]
        return s

    def is_terminal(self, s: BindleState) -> bool:
        return s.over

    def scores(self, s: BindleState) -> list[float]:
        return [
            float(pt - JOKER_PENALTY * sum(1 for c in h if c.startswith("JK")))
            for pt, h in zip(s.points, s.hands)
        ]

    # -- views ---------------------------------------------------------------------------
    def observe(self, s: BindleState, p: int) -> dict:
        pend = None
        if s.pending is not None:
            initiator, target, card = s.pending
            pend = (initiator, target, card if p == initiator else "?")
        return {
            "seat": p,
            "hand": tuple(s.hands[p]),
            "hand_sizes": tuple(len(h) for h in s.hands),
            "tops": tuple(st[-1] if st else "-" for st in s.stalls),
            "chains": tuple(s.chain),
            "points": tuple(s.points),
            "draw": len(s.draw),
            "phase": s.phase,
            "pending": pend,
            "to_act": self.current_player(s),
            "log": tuple(s.log[-4:]),
        }

    def describe(self, s: BindleState) -> str:
        tops = ", ".join(
            f"s{i}:{(st[-1] if st else '-')}/L{s.chain[i]}" for i, st in enumerate(s.stalls)
        )
        who = self.current_player(s)
        return (
            f"pile={len(s.draw)} points={s.points} stalls[{tops}] "
            f"hands={[len(h) for h in s.hands]} phase={s.phase} to act: seat {who}"
            + (" (game over)" if s.over else "")
        )


GAME = Bindle
