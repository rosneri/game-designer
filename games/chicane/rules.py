"""Chicane — a card race where the road is built from the deck it is driven on.

RULESHEET
=========
Players: 2-4.  Components: a standard 52-card deck, one six-sided die.  No jokers.

Card values
-----------
Ace = 1, 2-10 = face value, Jack = 11, Queen = 12. The four Kings are not track cards:
they are the racers themselves.

Setup
-----
1. Remove the four Kings. Seat 0 drives the King of Spades, seat 1 the King of Hearts,
   seat 2 the King of Diamonds, seat 3 the King of Clubs. Unused Kings are set aside.
2. Shuffle the remaining 48 cards and deal 5 to each player. Hands are hidden.
3. Flip 8 cards face up in a row: the starting track, positions 1..8 from left to right.
   The rest form the face-down draw pile. An empty discard pile sits beside it.
4. The full track length L depends on the player count: 2 players L = 32, 3 players
   L = 26, 4 players L = 22. The track never holds more than L cards. The finish line is
   position L+1.
5. All racers start on position 0, the grid. Any number of racers may share a position.
6. The hand limit is 7 cards.

Rounds and turn order
---------------------
Play runs in rounds. At the start of a round the players are ordered by racer position,
lowest first, so last place drives first; ties are broken by lower seat index. Each player
takes exactly one turn in that order, then the order is recomputed for the next round.

A turn
------
Roll the die first: the result is this turn's *throttle*, and it is known before the action
is chosen. Then take exactly one action.

1. **Drive.** Play one card from your hand to the discard pile, then advance one position
   at a time, at most *throttle* positions in total. To enter a position you must *clear*
   its track card: the played card's value is greater than or equal to the track card's
   value, OR the played card's suit matches the track card's suit. The one played card is
   compared against every corner you enter. If the next corner cannot be cleared you stop.
   If the next position holds no track card yet (the track is still shorter than L and you
   stand on its last card) you stop. If you stand on position L with the track complete and
   still have throttle left, you enter position L+1 with no clearing needed: you cross the
   finish line. You always drive the maximum distance the card and the throttle allow; you
   may not stop early. Drive is legal only with a card that moves you at least one position.
   *Slipstream:* if a Drive ends on a position occupied by at least one other racer, you
   immediately move 1 further position for free, with no clearing. Slipstream may not put
   you on a position that has no track card, and may not cross the finish line unless you
   are standing on position L. It applies at most once per turn.
2. **Lay.** Legal only while the track holds fewer than L cards. Place one card from your
   hand face up as the new last card of the track, then move your racer forward exactly 1
   position with no clearing needed. Laying never crosses the finish line. A laid card may
   be a brutal corner (a Queen, say) for everyone still behind it, the layer included.
3. **Pit.** Legal only if you hold fewer than 7 cards. Draw 2 cards from the draw pile, or
   only 1 if a second would break the hand limit.

If no action is legal - a full hand with no Drive and no Lay available, or no cards left to
draw - the player simply passes. This is not a real decision. If every player passes in an
unbroken run of turns as long as the player count, the field has stalled and the race ends
at once (nobody can move again, because hands and corners can no longer change).

Reshuffle and the final lap
---------------------------
The first time a draw is needed and the draw pile is empty, the discard pile is shuffled
into a new draw pile and the draw continues: the race is now on its *final lap*. The second
time a draw is needed and the draw pile is empty, the drawer takes whatever is left (maybe
nothing) and the race ends at the end of that turn.

End of the race
---------------
The race ends immediately when a racer reaches position L+1, or at the end of the turn on
which the draw pile runs dry during the final lap. A hard cap of 400 turns is a safety
valve and should never be reached in a normal race.

Scoring
-------
Your score is your racer's position, plus 10 if you crossed the finish line. Highest score
wins. Ties are broken in favour of the racer that moved most recently (the highest turn
number on which its position last changed); between two racers that never moved, the lower
seat index wins. The tie-break is folded into the score as a fraction smaller than one
position, so ranking is strictly deterministic.

Strategy
--------
Low cards are cheap fuel for a Lay, but only high cards and matching suits get you past a
corner, so lay the suits you are long in and let the throttle do the rest. Pitting costs you
a round of movement, yet an empty hand strands you on the asphalt. Because last place drives
first, a big Drive can hand the initiative straight back to the player you just passed.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from random import Random

from gd_cards import Card, Suit, standard_deck
from gd_gamecore import GMLike

HAND_LIMIT = 7
START_HAND = 5
START_TRACK = 8
PIT_DRAW = 2
FINISH_BONUS = 10.0
MAX_TURNS = 400
TRACK_LENGTH = {2: 32, 3: 26, 4: 22}
KING_OF_SEAT = {0: Suit.SPADES, 1: Suit.HEARTS, 2: Suit.DIAMONDS, 3: Suit.CLUBS}


@dataclass
class ChicaneState:
    """Full (god's eye) race state. ``track[i]`` is the corner at position ``i + 1``."""

    hands: list[list[Card]]
    track: list[Card]
    length: int                 # L: full track length; the finish line is L + 1
    pos: list[int]              # racer positions, 0 = grid, L + 1 = past the flag
    draw: list[Card]
    discard: list[Card]
    die: int                    # throttle already rolled for the player to act
    order: list[int]            # seat order for the current round
    order_idx: int
    turn: int                   # number of completed turns
    last_moved: list[int]       # turn index on which each racer last changed position
    passes: int = 0             # consecutive passed turns; n_players in a row ends the race
    final_lap: bool = False
    over: bool = False


def clears(card: Card, corner: Card) -> bool:
    """A played card clears a corner if it out-ranks it (A=1..Q=12) or shares its suit."""
    return card.rank >= corner.rank or card.suit == corner.suit


class Chicane:
    """See the module docstring for the rulesheet."""

    def __init__(self, n_players: int, gm: GMLike | None = None):
        if not 2 <= n_players <= 4:
            raise ValueError("2-4 players")
        self.n_players = n_players
        self.gm = gm

    # ------------------------------------------------------------------ lifecycle
    def setup(self, rng: Random) -> ChicaneState:
        deck = [c for c in standard_deck() if c.rank != 13]  # the Kings are the racers
        rng.shuffle(deck)
        hands = [[] for _ in range(self.n_players)]
        for _ in range(START_HAND):
            for h in hands:
                h.append(deck.pop())
        track = [deck.pop() for _ in range(START_TRACK)]
        s = ChicaneState(
            hands=[sorted(h, key=_key) for h in hands],
            track=track,
            length=TRACK_LENGTH[self.n_players],
            pos=[0] * self.n_players,
            draw=deck,
            discard=[],
            die=1,
            order=list(range(self.n_players)),
            order_idx=0,
            turn=0,
            last_moved=[-1] * self.n_players,
        )
        s.die = rng.randint(1, 6)
        return s

    def current_player(self, s: ChicaneState) -> int:
        return s.order[s.order_idx]

    # ------------------------------------------------------------------ actions
    def legal_actions(self, s: ChicaneState) -> list[tuple]:
        p = self.current_player(s)
        hand = s.hands[p]
        acts: list[tuple] = []
        for c in hand:
            if self._drive_end(s, p, c)[0] > s.pos[p]:
                acts.append(("drive", str(c)))
        if len(s.track) < s.length:
            acts += [("lay", str(c)) for c in hand]
        if len(hand) < HAND_LIMIT and (s.draw or (s.discard and not s.final_lap)):
            acts.append(("pit",))
        return acts or [("pass",)]

    def step(self, s: ChicaneState, a: tuple, rng: Random) -> ChicaneState:
        s = copy.deepcopy(s)
        p = self.current_player(s)
        kind = a[0]
        if kind == "drive":
            card = self._take(s.hands[p], a[1])
            s.discard.append(card)
            new_pos, slip = self._drive_end(s, p, card)
            if new_pos <= s.pos[p]:
                raise ValueError(f"{a} moves nobody")
            self._move(s, p, new_pos)
            if slip:
                self._move(s, p, new_pos + 1)
        elif kind == "lay":
            if len(s.track) >= s.length:
                raise ValueError("track is already full")
            s.track.append(self._take(s.hands[p], a[1]))
            self._move(s, p, s.pos[p] + 1)
        elif kind == "pit":
            if len(s.hands[p]) >= HAND_LIMIT:
                raise ValueError("hand is full")
            self._draw(s, p, min(PIT_DRAW, HAND_LIMIT - len(s.hands[p])), rng)
        elif kind != "pass":
            raise ValueError(f"unknown action {a!r}")
        s.passes = s.passes + 1 if kind == "pass" else 0

        s.turn += 1
        if s.pos[p] > s.length or s.passes >= self.n_players or s.turn >= MAX_TURNS:
            s.over = True
        if s.over:
            return s
        s.order_idx += 1
        if s.order_idx >= self.n_players:
            s.order = sorted(range(self.n_players), key=lambda q: (s.pos[q], q))
            s.order_idx = 0
        s.die = rng.randint(1, 6)
        return s

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _take(hand: list[Card], name: str) -> Card:
        for i, c in enumerate(hand):
            if str(c) == name:
                return hand.pop(i)
        raise ValueError(f"{name} is not in hand")

    @staticmethod
    def _move(s: ChicaneState, p: int, target: int) -> None:
        if target != s.pos[p]:
            s.pos[p] = target
            s.last_moved[p] = s.turn

    def _drive_end(self, s: ChicaneState, p: int, card: Card) -> tuple[int, bool]:
        """Return (position after driving ``card``, whether a slipstream follows)."""
        cur, done = s.pos[p], len(s.track)
        for _ in range(s.die):
            nxt = cur + 1
            if nxt > s.length:                      # the flag: only from L on a full track
                if cur == s.length and done >= s.length:
                    return nxt, False
                break
            if nxt > done:                          # no asphalt laid there yet
                break
            if not clears(card, s.track[nxt - 1]):
                break
            cur = nxt
        if cur == s.pos[p]:
            return cur, False
        crowded = any(q != p and s.pos[q] == cur for q in range(self.n_players))
        slip = crowded and (cur + 1 <= done or (cur == s.length and done >= s.length))
        return cur, slip

    def _draw(self, s: ChicaneState, p: int, n: int, rng: Random) -> None:
        for _ in range(n):
            if not s.draw:
                if s.final_lap or not s.discard:
                    s.over = True               # the deck is spent: the race ends this turn
                    return
                s.draw = s.discard
                s.discard = []
                rng.shuffle(s.draw)
                s.final_lap = True
            s.hands[p].append(s.draw.pop())
        s.hands[p].sort(key=_key)

    # ------------------------------------------------------------------ results
    def is_terminal(self, s: ChicaneState) -> bool:
        return s.over

    def scores(self, s: ChicaneState) -> list[float]:
        out = []
        for p in range(self.n_players):
            base = float(s.pos[p]) + (FINISH_BONUS if s.pos[p] > s.length else 0.0)
            if s.last_moved[p] < 0:                      # never moved: lowest, by seat
                tie = 0.0001 * (self.n_players - p)
            else:                                        # moved later ranks higher
                tie = 0.001 + 0.5 * (s.last_moved[p] + 1) / (s.turn + 1)
            out.append(base + tie)
        return out

    # ------------------------------------------------------------------ views
    def observe(self, s: ChicaneState, p: int) -> dict:
        return {
            "seat": p,
            "hand": tuple(str(c) for c in s.hands[p]),
            "throttle": s.die,
            "to_act": self.current_player(s),
            "track": tuple(str(c) for c in s.track),
            "track_length": s.length,
            "positions": tuple(s.pos),
            "hand_sizes": tuple(len(h) for h in s.hands),
            "draw_pile": len(s.draw),
            "discard_pile": len(s.discard),
            "order": tuple(s.order),
            "turn": s.turn,
            "final_lap": s.final_lap,
            "consecutive_passes": s.passes,
        }

    def describe(self, s: ChicaneState) -> str:
        p = self.current_player(s)
        lane = ", ".join(f"seat {q}@{s.pos[q]}" for q in range(self.n_players))
        return (
            f"turn {s.turn}: seat {p} rolls {s.die} | track {len(s.track)}/{s.length} "
            f"| {lane} | draw {len(s.draw)} discard {len(s.discard)}"
            f"{' | FINAL LAP' if s.final_lap else ''}"
        )


def _key(c: Card) -> tuple[int, int]:
    return (int(c.suit), c.rank)


GAME = Chicane
