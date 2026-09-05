"""Pit Lane — a race along a row of face-up cards.

RULESHEET
=========
Players: 2-4.  Components: one standard 52-card deck, no jokers, no dice.

The four Kings are the racers: K-spades is seat 0, K-hearts seat 1, K-diamonds seat 2,
K-clubs seat 3. Kings of unused seats are removed. The other 48 cards (A through Q in
every suit) are the play deck.

Setup
-----
Shuffle the 48-card play deck. Deal 24 cards face up in a row: these are track spaces 1
(left) to 24 (right). Space 0 is the starting grid, space 25 is "finished". Deal 3 cards
face down to each player; hands are secret. The rest of the deck is the face-down draw
pile. The discard pile starts empty. All racers stand on space 0. Seat 0 is the start
player and takes the first turn. Play goes clockwise.

Your turn
---------
Take exactly one action.

**A. Move** — Play one card from your hand face up onto the discard pile and drive forward:

* A, 2, 3, 4, 5, 6 move you 1 space. 7, 8, 9, 10, J, Q move you 2 spaces.
* Slipstream: if you would stop on a space that holds another racer that has not
  finished, move 1 more space. Repeat until your space is free (or you finish).
* If you stop on space 25 or further, your racer is finished. Put it on space 25. It
  never moves again.
* Otherwise look at the track card on your space. If the card you played has the same
  suit **or** the same rank as that track card, pocket the track card: put it face down
  in your score pile. Then fill the empty space with the top card of the draw pile. If no
  card can be drawn, the space stays empty for the rest of the game.
* If the space is empty, or the cards do not match, nothing more happens.

**B. Refuel** — Choose one source:

* ("refuel", "deck"): draw the top 2 cards of the draw pile into your hand.
* ("refuel", "discard"): take the top face-up card of the discard pile into your hand,
  then draw 1 card from the draw pile.

The hand limit is 6. Stop drawing when you hold 6 cards; the extra cards are not drawn.
You may not refuel with 6 cards in hand. If a source is empty you take only what is
there, and a refuel that would give you no card at all is not legal.

**C. Pass** — Legal only when your racer has finished, or when you have no legal Move and
no legal Refuel. While your racer is on the track and any Move or Refuel is legal, you
must take one of them.

Reshuffle
---------
When a card must be drawn and the draw pile is empty, take every card of the discard pile
except its top card, shuffle them, and use them as the new draw pile. If that gives zero
cards, the draw is simply skipped.

End of the game
---------------
The game ends in any of these cases.

1. Finish line: as soon as a racer finishes, the round is played out. Play continues
   clockwise until the turn comes back to the start player (seat 0). Then the game ends.
   Other racers may also finish during this last round.
2. Stall: every player in turn takes a Pass, one full round with no Move and no Refuel.
3. Safety cap: the game also ends after 150 turns per player. This cap only protects
   against endless play; a normal game is far shorter.

Scoring
-------
* Distance: 1 point per space of your racer's position (0-24). A finished racer scores 32
  (24 spaces plus an 8 point finish bonus).
* Pocketed cards: the rank value of every card in your score pile, A = 1, 2-10 = face
  value, J = 11, Q = 12.

The highest total wins.

Tie-break, in order: further racer position (finished counts as 25), then more cards in
the score pile, then the later seat number (seat 0 loses ties, which pays back the first
turn advantage). This implementation adds these tie-breaks to ``scores`` as tiny
fractions (less than 0.03 in total), so they never change the order of real point totals.

Strategy note: a high card covers ground, but a low card that matches the track can be
worth more than the space it buys. Refuelling costs a turn, so plan two or three moves
ahead, and remember that a rival on your space gives you a free extra space.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from random import Random

from gd_gamecore import GMLike

TRACK_LEN = 24
FINISH = TRACK_LEN + 1  # space 25
HAND_START = 3
HAND_LIMIT = 6
FINISH_BONUS = 8
TURNS_PER_PLAYER_CAP = 150

RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q"]
SUITS = ["S", "H", "D", "C"]
RANK_VALUE = {r: i + 1 for i, r in enumerate(RANKS)}  # A=1 ... Q=12


def rank_of(card: str) -> str:
    return card[:-1]


def suit_of(card: str) -> str:
    return card[-1]


def value_of(card: str) -> int:
    return RANK_VALUE[rank_of(card)]


def speed_of(card: str) -> int:
    """Distance a card drives: 1 for A-6, 2 for 7-Q."""
    return 1 if value_of(card) <= 6 else 2


@dataclass
class PitLaneState:
    track: list[str | None]  # index 0 unused; 1..24 are the track spaces
    hands: list[list[str]]
    piles: list[list[str]]  # face-down score piles
    positions: list[int]
    finished: list[bool]
    draw: list[str]  # index 0 is the top of the draw pile
    discard: list[str]  # last item is the top of the discard pile
    current: int = 0
    start_player: int = 0
    final_round: bool = False
    passes: int = 0
    turns: int = 0
    over: bool = False
    log: str = field(default="setup")


class PitLane:
    """See the module docstring for the rulesheet."""

    def __init__(self, n_players: int, gm: GMLike | None = None):
        if not 2 <= n_players <= 4:
            raise ValueError("2-4 players")
        self.n_players = n_players
        self.gm = gm

    # ------------------------------------------------------------------ lifecycle
    def setup(self, rng: Random) -> PitLaneState:
        deck = [r + s for s in SUITS for r in RANKS]
        rng.shuffle(deck)
        track: list[str | None] = [None] + deck[:TRACK_LEN]
        rest = deck[TRACK_LEN:]
        hands: list[list[str]] = [[] for _ in range(self.n_players)]
        for _ in range(HAND_START):
            for h in hands:
                h.append(rest.pop(0))
        for h in hands:
            h.sort()
        return PitLaneState(
            track=track,
            hands=hands,
            piles=[[] for _ in range(self.n_players)],
            positions=[0] * self.n_players,
            finished=[False] * self.n_players,
            draw=rest,
            discard=[],
        )

    def current_player(self, s: PitLaneState) -> int:
        return s.current

    # ------------------------------------------------------------------ actions
    def _draw_capacity(self, s: PitLaneState) -> int:
        """Cards that could still be drawn from the draw pile, reshuffle included."""
        return len(s.draw) + max(0, len(s.discard) - 1)

    def legal_actions(self, s: PitLaneState) -> list[tuple]:
        p = s.current
        if s.over or s.finished[p]:
            return [("pass",)]
        acts: list[tuple] = [("move", c) for c in sorted(s.hands[p])]
        if len(s.hands[p]) < HAND_LIMIT:
            if self._draw_capacity(s) > 0:
                acts.append(("refuel", "deck"))
                acts.append(("refuel", "discard"))
            elif s.discard:
                acts.append(("refuel", "discard"))
        return acts or [("pass",)]

    def step(self, state: PitLaneState, a, rng: Random) -> PitLaneState:
        s = copy.deepcopy(state)
        if a not in self.legal_actions(s):
            raise ValueError(f"illegal action {a!r} for seat {s.current}")
        p = s.current
        kind = a[0]
        if kind == "move":
            self._do_move(s, p, a[1], rng)
            s.passes = 0
        elif kind == "refuel":
            self._do_refuel(s, p, a[1], rng)
            s.passes = 0
        else:
            s.passes += 1
            s.log = f"seat {p} passes"
        s.turns += 1
        s.current = (s.current + 1) % self.n_players
        if s.passes >= self.n_players:
            s.over = True
        elif s.final_round and s.current == s.start_player:
            s.over = True
        elif s.turns >= TURNS_PER_PLAYER_CAP * self.n_players:
            s.over = True
        return s

    # ------------------------------------------------------------------ helpers
    def _draw_one(self, s: PitLaneState, rng: Random) -> str | None:
        """Top card of the draw pile, reshuffling the discard pile when needed."""
        if not s.draw:
            if len(s.discard) <= 1:
                return None
            pool = s.discard[:-1]
            s.discard = s.discard[-1:]
            rng.shuffle(pool)
            s.draw = pool
        return s.draw.pop(0)

    def _do_move(self, s: PitLaneState, p: int, card: str, rng: Random) -> None:
        s.hands[p].remove(card)
        s.discard.append(card)
        pos = s.positions[p] + speed_of(card)
        while pos <= TRACK_LEN and any(
            q != p and not s.finished[q] and s.positions[q] == pos for q in range(self.n_players)
        ):
            pos += 1  # slipstream past an occupied space
        if pos >= FINISH:
            s.positions[p] = FINISH
            s.finished[p] = True
            s.final_round = True
            s.log = f"seat {p} plays {card} and finishes"
            return
        s.positions[p] = pos
        target = s.track[pos]
        took = ""
        if target is not None and (suit_of(target) == suit_of(card) or rank_of(target) == rank_of(card)):
            s.piles[p].append(target)
            s.track[pos] = self._draw_one(s, rng)
            took = f", pockets {target}"
        s.log = f"seat {p} plays {card} to space {pos}{took}"

    def _do_refuel(self, s: PitLaneState, p: int, source: str, rng: Random) -> None:
        got: list[str] = []
        if source == "discard" and s.discard and len(s.hands[p]) < HAND_LIMIT:
            got.append(s.discard.pop())
        draws = 2 if source == "deck" else 1
        for _ in range(draws):
            if len(s.hands[p]) + len(got) >= HAND_LIMIT:
                break
            c = self._draw_one(s, rng)
            if c is None:
                break
            got.append(c)
        s.hands[p].extend(got)
        s.hands[p].sort()
        s.log = f"seat {p} refuels from {source} ({len(got)} card(s))"

    # ------------------------------------------------------------------ end
    def is_terminal(self, s: PitLaneState) -> bool:
        return s.over

    def _total(self, s: PitLaneState, p: int) -> float:
        dist = TRACK_LEN + FINISH_BONUS if s.finished[p] else s.positions[p]
        return float(dist + sum(value_of(c) for c in s.piles[p]))

    def scores(self, s: PitLaneState) -> list[float]:
        out = []
        for p in range(self.n_players):
            pos = FINISH if s.finished[p] else s.positions[p]
            tb = 1e-3 * pos + 1e-5 * len(s.piles[p]) + 1e-7 * p  # documented tie-breaks
            out.append(self._total(s, p) + tb)
        return out

    # ------------------------------------------------------------------ views
    def observe(self, s: PitLaneState, p: int) -> dict:
        return {
            "seat": p,
            "hand": tuple(s.hands[p]),
            "my_pile": tuple(s.piles[p]),
            "track": tuple(s.track[1:]),
            "positions": tuple(s.positions),
            "finished": tuple(s.finished),
            "hand_sizes": tuple(len(h) for h in s.hands),
            "pile_sizes": tuple(len(x) for x in s.piles),
            "draw": len(s.draw),
            "discard_top": s.discard[-1] if s.discard else None,
            "discard": len(s.discard),
            "current": s.current,
            "final_round": s.final_round,
            "passes": s.passes,
            "turns": s.turns,
        }

    def describe(self, s: PitLaneState) -> str:
        board = " ".join(f"{i}:{c or '--'}" for i, c in enumerate(s.track[1:], start=1))
        pos = [FINISH if f else q for q, f in zip(s.positions, s.finished)]
        return (
            f"turn {s.turns} seat {s.current} to act; positions={pos} "
            f"hands={[len(h) for h in s.hands]} piles={[len(x) for x in s.piles]} "
            f"draw={len(s.draw)} discard_top={s.discard[-1] if s.discard else '--'}"
            f"{' FINAL ROUND' if s.final_round else ''}\n"
            f"track: {board}\nlast: {s.log}"
        )


GAME = PitLane
