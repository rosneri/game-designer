"""Furlong — a horse race on a course the field builds as it runs.

RULESHEET
=========
Players: 2-4.  Components: a standard 52-card deck and one six-sided die.

Remove the four Aces: each player takes one as their racer marker (the suit is only
identity, unused Aces are set aside). The remaining 48 cards (ranks 2 to King) are the
deck. Rank order does not matter; Jack, Queen and King are "face cards".

Setup
-----
Shuffle the deck and deal 6 cards to each player (hands are hidden). Turn the next 3
cards face up in a row: these are track slots 1, 2 and 3. The rest is the draw pile; the
discard pile starts empty. Every racer starts on the start line, position 0, which is not
a slot. The start player is chosen at random. Play is clockwise.

The track
---------
* Slots are numbered 1 to 10; position 11 is the finish line. A slot is "laid" once a
  card has been placed on it. The frontier F is the highest laid slot. The track is
  "complete" when F = 10.
* A laid slot holding a face card is a hurdle. Any other laid slot is flat.
* A hand card C matches a flat slot if it shares the slot card's suit or its rank.
* A hand card C matches a hurdle if it has the same rank as the hurdle card, or if C is
  itself a face card of the hurdle's suit.
* Once the track is complete, every card matches the finish line.
* The hand limit is 8. Any effect that draws cards draws only as many as fit under the
  limit. If the draw pile is empty it is refilled by shuffling the discard pile. If both
  are empty, nothing is drawn.

Your turn
---------
First roll the die: the result is your reach R for this turn (the engine rolls for you at
the start of your turn). Then take exactly one action.

1. **Stride.** Pick a hand card C and a target t with pos < t <= pos + R. The target must
   be a laid slot (t <= F), or t = 11 when the track is complete. C must match slot t (any
   card matches the finish line), and C must also match every hurdle slot h strictly
   between your position and t. Discard C and move your racer to t. *Slipstream:* if
   t <= 10 and at least one other racer already stands on slot t, draw 1 card.

2. **Lay.** Only while the track is incomplete (F < 10). Place a hand card face up as slot
   F + 1, then draw 1 card, then step: if slot pos + 1 is a flat slot you advance to
   pos + 1 (slipstream applies as above). If slot pos + 1 is a hurdle you do not step, so
   laying a face card never lets you step onto it. Laying is the slow but sure step, and it
   lets you choose what every other racer must match.

3. **Breather.** Discard one card of your choice from hand, then draw 2 cards (never
   going above the hand limit of 8). If your hand is empty you just draw 2. Legal whenever
   at least one card remains in the draw or discard pile.

If none of the three actions is legal (no cards in hand and none in the draw or discard
pile) your turn is skipped.

The steward
-----------
The course is always kept open ahead of the field. After each turn, while the track is
incomplete, the steward turns cards from the draw pile onto the next unlaid slots until
the frontier is at least 4 slots ahead of the leading racer (F >= lead + 4), or until the
track is complete, or until no card can be turned. So the die, not the pace of laying, is
what usually limits a stride.

Recycling the course
--------------------
After your action, every laid slot with an index lower than the lowest racer position is
cleared: its card goes to the discard pile. The slot still counts as laid, so the frontier
never moves backwards; no racer can target it again because targets are always ahead of
the mover. While anyone is still on the start line (position 0) nothing is cleared.

Ending the race
---------------
A racer that strides to position 11 has finished and takes no further turns. Play then
continues until the round is complete, that is until the seat immediately
counter-clockwise of the start player has taken its turn, so every player has had the same
number of turns. The race also stops at once if the field has run out of legs: the track is
complete, the draw and discard piles are both empty, and no unfinished racer holds a card
that could stride to any slot ahead of it even on a roll of 6. Finally, the race stops
after 26 full rounds (a safety cap; a real race is decided long before that).

Scoring and winner
------------------
Your score is your racer's position, 0 to 11; highest wins. Ties are broken in this order:
(1) earlier arrival — the racer that last moved on the earlier global turn number, a racer
that never moved counts as arrival 0, (2) the seat that comes first clockwise from the
start player. The engine encodes these tie-breaks as a fraction
smaller than 0.01 added to the position, so the reported score is "position plus a hair"
and the winner is unique.

Clarifications
--------------
* Reach limits stride targets only; Lay and Breather ignore the die.
* Striding to a nearer target than the farthest legal one is allowed — landing on an
  opponent for the slipstream card is a good reason.
* Hurdles gate strides only. The lay step is blocked by a hurdle on pos + 1 and never
  looks anywhere else.
* Hands are private. The discard pile and the laid track are public.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from random import Random

from gd_cards import Card, Suit
from gd_gamecore import GMLike

TRACK_LEN = 10          # slots 1..10
FINISH = 11             # the finish line
HAND_LIMIT = 8
DEAL = 6
OPEN_SLOTS = 3          # slots turned up during setup
ROUND_CAP = 26          # safety terminator
LOOKAHEAD = 4           # slots the steward keeps open ahead of the leading racer
CLEARED = "cleared"     # a laid slot whose card has been recycled


def _is_face(c: Card) -> bool:
    return c.rank >= 11


def _matches(c: Card, slot: Card) -> bool:
    """Does hand card ``c`` match the card on a laid slot?"""
    if _is_face(slot):
        return c.rank == slot.rank or (_is_face(c) and c.suit == slot.suit)
    return c.suit == slot.suit or c.rank == slot.rank


def _deck48() -> list[Card]:
    return [Card(r, s) for s in Suit for r in range(2, 14)]


@dataclass
class FurlongState:
    track: list = field(default_factory=list)      # TRACK_LEN entries: None | Card | CLEARED
    frontier: int = 0
    pos: list[int] = field(default_factory=list)
    arrival: list[int] = field(default_factory=list)
    hands: list[list[Card]] = field(default_factory=list)
    draw_pile: list[Card] = field(default_factory=list)
    discard: list[Card] = field(default_factory=list)
    finished: list[bool] = field(default_factory=list)
    start_player: int = 0
    rel: int = 0            # seat offset of the player to act, relative to start_player
    reach: int = 1          # die result for the current turn
    turn_count: int = 0
    round_count: int = 0
    ending: bool = False    # someone has finished; stop at the end of this round
    over: bool = False


class Furlong:
    """See the module docstring for the rulesheet."""

    def __init__(self, n_players: int, gm: GMLike | None = None):
        if not 2 <= n_players <= 4:
            raise ValueError("2-4 players")
        self.n_players = n_players
        self.gm = gm

    # -- lifecycle ----------------------------------------------------------------------
    def setup(self, rng: Random) -> FurlongState:
        deck = _deck48()
        rng.shuffle(deck)
        n = self.n_players
        hands = [sorted(deck[i * DEAL:(i + 1) * DEAL]) for i in range(n)]
        used = n * DEAL
        track: list = [None] * TRACK_LEN
        for i in range(OPEN_SLOTS):
            track[i] = deck[used + i]
        s = FurlongState(
            track=track,
            frontier=OPEN_SLOTS,
            pos=[0] * n,
            arrival=[0] * n,
            hands=hands,
            draw_pile=deck[used + OPEN_SLOTS:],
            discard=[],
            finished=[False] * n,
            start_player=rng.randrange(n),
            rel=0,
        )
        self._reveal(s, rng)
        s.reach = rng.randint(1, 6)
        return s

    def current_player(self, s: FurlongState) -> int:
        return (s.start_player + s.rel) % self.n_players

    # -- helpers ------------------------------------------------------------------------
    def _slot(self, s: FurlongState, t: int):
        """Card on slot ``t`` (1-based), or None if unlaid/recycled."""
        c = s.track[t - 1]
        return c if isinstance(c, Card) else None

    def _hurdles_ok(self, s: FurlongState, c: Card, lo: int, hi: int) -> bool:
        """Can card ``c`` pass every hurdle strictly between lo and hi?"""
        for h in range(lo + 1, min(hi, TRACK_LEN + 1)):
            sc = self._slot(s, h)
            if sc is not None and _is_face(sc) and not _matches(c, sc):
                return False
        return True

    def _can_draw_any(self, s: FurlongState) -> bool:
        return bool(s.draw_pile or s.discard)

    def _draw(self, s: FurlongState, p: int, n: int, rng: Random) -> None:
        for _ in range(n):
            if len(s.hands[p]) >= HAND_LIMIT:
                break
            if not s.draw_pile:
                if not s.discard:
                    break
                s.draw_pile, s.discard = s.discard, []
                rng.shuffle(s.draw_pile)
            s.hands[p].append(s.draw_pile.pop(0))
        s.hands[p].sort()

    def _reveal(self, s: FurlongState, rng: Random) -> None:
        """Steward: keep the frontier at least LOOKAHEAD slots ahead of the leader."""
        lead = max(s.pos)
        while s.frontier < TRACK_LEN and s.frontier < lead + LOOKAHEAD:
            if not s.draw_pile:
                if not s.discard:
                    return
                s.draw_pile, s.discard = s.discard, []
                rng.shuffle(s.draw_pile)
            s.frontier += 1
            s.track[s.frontier - 1] = s.draw_pile.pop(0)

    def _move(self, s: FurlongState, p: int, t: int, rng: Random) -> None:
        slipstream = t <= TRACK_LEN and any(
            q != p and s.pos[q] == t for q in range(self.n_players)
        )
        s.pos[p] = t
        s.arrival[p] = s.turn_count
        if t >= FINISH:
            s.finished[p] = True
            s.ending = True
        elif slipstream:
            self._draw(s, p, 1, rng)

    # -- actions ------------------------------------------------------------------------
    def legal_actions(self, s: FurlongState) -> list[tuple]:
        if s.over:
            return []
        p = self.current_player(s)
        hand, pos = s.hands[p], s.pos[p]
        acts: list[tuple] = []
        far = pos + s.reach
        complete = s.frontier >= TRACK_LEN
        for c in hand:
            name = str(c)
            for t in range(pos + 1, min(far, s.frontier) + 1):
                sc = self._slot(s, t)
                if sc is not None and _matches(c, sc) and self._hurdles_ok(s, c, pos, t):
                    acts.append(("stride", name, t))
            if complete and far >= FINISH and self._hurdles_ok(s, c, pos, FINISH):
                acts.append(("stride", name, FINISH))
        if not complete:
            acts += [("lay", str(c)) for c in hand]
        if self._can_draw_any(s):
            if hand:
                seen = set()
                for c in hand:
                    if str(c) not in seen:
                        seen.add(str(c))
                        acts.append(("draw", str(c)))
            else:
                acts.append(("draw",))
        return acts or [("skip",)]

    def step(self, s: FurlongState, a, rng: Random) -> FurlongState:
        if s.over:
            raise ValueError("game over")
        if a not in self.legal_actions(s):
            raise ValueError(f"illegal action {a}")
        s = copy.deepcopy(s)
        p = self.current_player(s)
        s.turn_count += 1
        kind = a[0]
        if kind == "stride":
            c = next(x for x in s.hands[p] if str(x) == a[1])
            s.hands[p].remove(c)
            s.discard.append(c)
            self._move(s, p, a[2], rng)
        elif kind == "lay":
            c = next(x for x in s.hands[p] if str(x) == a[1])
            s.hands[p].remove(c)
            s.frontier += 1
            s.track[s.frontier - 1] = c
            self._draw(s, p, 1, rng)
            nxt = self._slot(s, s.pos[p] + 1) if s.pos[p] < TRACK_LEN else None
            if nxt is not None and not _is_face(nxt):
                self._move(s, p, s.pos[p] + 1, rng)
        elif kind == "draw":
            if len(a) > 1:
                c = next(x for x in s.hands[p] if str(x) == a[1])
                s.hands[p].remove(c)
                s.discard.append(c)
            self._draw(s, p, 2, rng)
        self._reveal(s, rng)
        self._recycle(s)
        self._advance(s, rng)
        return s

    def _recycle(self, s: FurlongState) -> None:
        low = min(s.pos)
        for i in range(low - 1):
            if isinstance(s.track[i], Card):
                s.discard.append(s.track[i])
                s.track[i] = CLEARED

    def _stalled(self, s: FurlongState) -> bool:
        """No cards anywhere and nobody could stride even on a 6: the race is dead."""
        if s.frontier < TRACK_LEN or s.draw_pile or s.discard:
            return False
        for p in range(self.n_players):
            if s.finished[p]:
                continue
            pos = s.pos[p]
            for c in s.hands[p]:
                for t in range(pos + 1, min(pos + 6, TRACK_LEN) + 1):
                    sc = self._slot(s, t)
                    if sc is not None and _matches(c, sc) and self._hurdles_ok(s, c, pos, t):
                        return False
                if pos + 6 >= FINISH and self._hurdles_ok(s, c, pos, FINISH):
                    return False
        return True

    def _advance(self, s: FurlongState, rng: Random) -> None:
        n = self.n_players
        if all(s.finished) or self._stalled(s):
            s.over = True
            return
        for _ in range(n + 1):
            s.rel += 1
            if s.rel >= n:
                s.rel = 0
                s.round_count += 1
                if s.ending or s.round_count >= ROUND_CAP:
                    s.over = True
                    return
            if not s.finished[(s.start_player + s.rel) % n]:
                break
        s.reach = rng.randint(1, 6)

    # -- results ------------------------------------------------------------------------
    def is_terminal(self, s: FurlongState) -> bool:
        return s.over

    def scores(self, s: FurlongState) -> list[float]:
        n = self.n_players
        out = []
        for p in range(n):
            rel = (p - s.start_player) % n
            tie = (
                (ROUND_CAP * n - s.arrival[p]) / 1e3       # earlier arrival
                + (n - rel) / 1e6                          # clockwise from the start player
            )
            out.append(float(s.pos[p]) + tie)
        return out

    # -- views --------------------------------------------------------------------------
    def _track_str(self, s: FurlongState) -> list[str]:
        out = []
        for i in range(s.frontier):
            c = s.track[i]
            out.append("--" if c == CLEARED else str(c))
        return out

    def observe(self, s: FurlongState, p: int) -> tuple:
        return (
            ("hand", tuple(str(c) for c in s.hands[p])),
            ("reach", s.reach if self.current_player(s) == p else 0),
            ("me", p),
            ("track", tuple(self._track_str(s))),
            ("frontier", s.frontier),
            ("positions", tuple(s.pos)),
            ("hand_sizes", tuple(len(h) for h in s.hands)),
            ("finished", tuple(s.finished)),
            ("draw_pile", len(s.draw_pile)),
            ("discard", tuple(str(c) for c in s.discard)),
            ("round", s.round_count),
            ("to_act", self.current_player(s)),
        )

    def describe(self, s: FurlongState) -> str:
        head = " ".join(self._track_str(s)[-6:]) or "(no track)"
        return (
            f"round {s.round_count + 1}/{ROUND_CAP} seat {self.current_player(s)} to act with reach {s.reach}; "
            f"positions={s.pos} frontier={s.frontier} (…{head}) "
            f"hands={[len(h) for h in s.hands]} draw={len(s.draw_pile)} discard={len(s.discard)}"
            + (" [final round]" if s.ending else "")
        )


GAME = Furlong
