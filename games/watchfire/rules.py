"""Watchfire — keep four braziers blazing, or let the night win.

RULESHEET
=========
Players: 2-4.  Components: a standard 52-card deck (the four Jacks are pulled out as role
cards) and one six-sided die.  No jokers.

Ranks and suits
---------------
Ace = 1, numbered cards = face value, Queen = 11, King = 12 (the Jacks are not in play as
normal cards).  A card is **blazing** if its rank is 10 or more (10, Q, K).  Suit order for the
tie-break is Spades > Hearts > Diamonds > Clubs.

Setup
-----
Shuffle the four Jacks face down and deal one to each player; unused Jacks are set aside face
down and are never revealed.  The player holding the **Jack of Spades is the Saboteur**; any
other Jack makes that player a **Keeper**.  With 4 players a Saboteur is always present, with 3
players the chance is 3/4, with 2 players 1/2.  Roles stay secret until final scoring.

Shuffle the remaining 48 cards to form the draw pile and deal 4 cards to each player as a
hidden hand.  Lay out four **braziers**, one per suit, each empty; a brazier holds at most one
face-up card, its **top**.  Each player has a face-down **stash** (empty at start) and there is
one shared face-up **ash** pile.  The start player is chosen at random; play is clockwise.

Your turn
---------
Play exactly one card from your hand with exactly one of the three actions, then draw one card
from the draw pile if it is not empty.

1. **Feed** card C of suit S — legal if brazier S is empty, or if C's rank is strictly higher
   than the rank of brazier S's top.  C becomes the new top.  Any card it replaces goes face
   down into your stash (feeding an empty brazier gains you nothing).
2. **Rake** card C of suit S — legal only if brazier S is not empty, C's rank is strictly lower
   than the top's rank, and C's rank is 5 or less (Ace..5).  Roll the die.  You **succeed** if
   the roll is strictly greater than C's rank (Ace on 2-6, a 2 on 3-6, a 3 on 4-6, a 4 on 5-6,
   a 5 only on 6).  On success the brazier's top goes face down into your stash and C becomes
   the new top.  On failure C goes face up on the ash pile and the brazier is unchanged.
3. **Stash** card C — put it face down into your stash.  Always legal.

Rake with a rank 6 or higher card is never legal (it could never succeed).  Every action is
open to every player whatever their role; only the end-game bonus differs.  Stash contents stay
hidden (the count is public); braziers, the ash pile and the die result are public.

End of the game
---------------
Each turn plays one card and draws one while the pile lasts, so the game is always exactly 48
turns (24 each at 2 players, 16 at 3, 12 at 4) and ends when the draw pile and all hands are
empty.  Nobody can ever be stuck without a card before that point.

Scoring
-------
* **Stash points**: every card in your stash scores its rank (Ace 1, 2-10 face value, Queen 11,
  King 12).  Cards left on the braziers or in the ash pile score for nobody.
* **Watch points**: score each brazier separately.  A brazier is **blazing** if its top has
  rank 10+, otherwise it is **dim** (an empty brazier counts as dim).  Each brazier is worth
  **2.5 x number of players** points (5 / 7.5 / 10).  A blazing brazier pays every Keeper; a dim
  brazier pays the Saboteur only.  So the full set of four braziers is worth 10 x number of
  players (20 / 30 / 40) to whoever the night favours.  Roles are revealed now.
* The **beacon** is **lit** when all four braziers are blazing: that is simply the case where
  every Keeper collects all four brazier awards and the Saboteur collects none.

Highest total wins.  Tie-break, in order: (1) fewer cards in stash; (2) the highest single card
in the stash (rank first, then suit S > H > D > C); (3) the player who acted earliest in the
first round.  The engine folds these tie-breaks into the returned score as a fraction smaller
than one point, so ranking is strict while whole points always dominate.

Mid-game the engine reports a *provisional* score with the same formula, using the braziers as
they stand right now.  Only the state at the end of turn 48 is what counts.

Strategy note: pocketing a King off a brazier is pure profit and looks exactly like sabotage, so
Keepers can rob each other while the Saboteur quietly leaves low cards on top.  A stashed Ace is
worth one point; kept in hand it is your best rake tool.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from random import Random
from typing import Any

from gd_gamecore import GMLike

SUITS = ("S", "H", "D", "C")
RANKS = tuple(range(1, 13))  # 1=Ace .. 10, 11=Queen, 12=King (no Jacks)
RANK_NAME = {1: "A", 11: "Q", 12: "K"}
HAND = 4
BLAZE = 10  # rank at which a card counts as blazing
MAX_RAKE = 5  # highest rank you may rake with
DECK = 48


def card(rank: int, suit: str) -> str:
    return f"{RANK_NAME.get(rank, str(rank))}{suit}"


def rank_of(c: str) -> int:
    head = c[:-1]
    if head == "A":
        return 1
    if head == "Q":
        return 11
    if head == "K":
        return 12
    return int(head)


def suit_of(c: str) -> str:
    return c[-1]


def full_deck() -> list[str]:
    return [card(r, s) for s in SUITS for r in RANKS]


@dataclass
class WatchfireState:
    hands: list[list[str]]
    stashes: list[list[str]]
    roles: list[str]  # "saboteur" / "keeper"
    braziers: dict[str, str | None]
    draw: list[str]
    ash: list[str]
    turn: int
    start_player: int
    current: int
    last_roll: int | None = None
    log: list[str] = field(default_factory=list)


class Watchfire:
    """See module docstring for the rulesheet."""

    def __init__(self, n_players: int, gm: GMLike | None = None):
        if not 2 <= n_players <= 4:
            raise ValueError("2-4 players")
        self.n_players = n_players
        self.gm = gm

    # -- lifecycle -----------------------------------------------------------------------
    def setup(self, rng: Random) -> WatchfireState:
        jacks = ["JS", "JH", "JD", "JC"]
        rng.shuffle(jacks)
        roles = ["saboteur" if jacks[p] == "JS" else "keeper" for p in range(self.n_players)]
        deck = full_deck()
        rng.shuffle(deck)
        hands = [[deck.pop() for _ in range(HAND)] for _ in range(self.n_players)]
        for h in hands:
            h.sort()
        start = rng.randrange(self.n_players)
        return WatchfireState(
            hands=hands,
            stashes=[[] for _ in range(self.n_players)],
            roles=roles,
            braziers={s: None for s in SUITS},
            draw=deck,
            ash=[],
            turn=0,
            start_player=start,
            current=start,
        )

    def current_player(self, s: WatchfireState) -> int:
        return s.current

    # -- actions -------------------------------------------------------------------------
    def legal_actions(self, s: WatchfireState) -> list[tuple]:
        if self.is_terminal(s):
            return []
        acts: list[tuple] = []
        for c in sorted(set(s.hands[s.current])):
            top = s.braziers[suit_of(c)]
            r = rank_of(c)
            if top is None or r > rank_of(top):
                acts.append(("feed", c))
            elif r <= MAX_RAKE and r < rank_of(top):
                acts.append(("rake", c))
            acts.append(("stash", c))
        return acts or [("pass",)]

    def step(self, state: WatchfireState, a: tuple, rng: Random) -> WatchfireState:
        s = copy.deepcopy(state)
        if a not in self.legal_actions(s):
            raise ValueError(f"illegal action {a}")
        p = s.current
        s.last_roll = None
        if a[0] != "pass":
            kind, c = a
            s.hands[p].remove(c)
            suit = suit_of(c)
            top = s.braziers[suit]
            if kind == "feed":
                if top is not None:
                    s.stashes[p].append(top)
                s.braziers[suit] = c
                s.log = [f"seat {p} fed {c}"]
            elif kind == "rake":
                roll = rng.randint(1, 6)
                s.last_roll = roll
                if roll > rank_of(c):
                    s.stashes[p].append(top)  # type: ignore[arg-type]
                    s.braziers[suit] = c
                    s.log = [f"seat {p} raked {c} (rolled {roll}) and took {top}"]
                else:
                    s.ash.append(c)
                    s.log = [f"seat {p} raked {c} (rolled {roll}) and failed"]
            else:
                s.stashes[p].append(c)
                s.log = [f"seat {p} stashed a card"]
            if s.draw:
                s.hands[p].append(s.draw.pop())
                s.hands[p].sort()
        s.turn += 1
        s.current = (p + 1) % self.n_players
        return s

    def is_terminal(self, s: WatchfireState) -> bool:
        return not s.draw and not any(s.hands)

    # -- scoring -------------------------------------------------------------------------
    def _beacon_lit(self, s: WatchfireState) -> bool:
        return all(t is not None and rank_of(t) >= BLAZE for t in s.braziers.values())

    def _bonus(self) -> int:
        return 10 * self.n_players

    def _stash_points(self, s: WatchfireState, p: int) -> int:
        return sum(rank_of(c) for c in s.stashes[p])

    def _tiebreak(self, s: WatchfireState, p: int) -> float:
        """Sub-point fraction (< 0.05) encoding the three tie-breaks, higher is better."""
        few = (DECK - len(s.stashes[p])) / 1000.0  # fewer stashed cards wins
        if s.stashes[p]:
            best = max((rank_of(c), len(SUITS) - SUITS.index(suit_of(c))) for c in s.stashes[p])
            high = (best[0] * 4 + best[1]) / 1e6
        else:
            high = 0.0
        seat = (self.n_players - ((p - s.start_player) % self.n_players)) / 1e8
        return few + high + seat

    def _favourable(self, s: WatchfireState, p: int) -> int:
        """How many braziers currently pay this player's role."""
        keeper = s.roles[p] == "keeper"
        return sum(
            1
            for t in s.braziers.values()
            if (t is not None and rank_of(t) >= BLAZE) == keeper
        )

    def scores(self, s: WatchfireState) -> list[float]:
        per_brazier = self._bonus() / 4.0
        out: list[float] = []
        for p in range(self.n_players):
            total = float(self._stash_points(s, p))
            total += self._favourable(s, p) * per_brazier
            out.append(total + self._tiebreak(s, p))
        return out

    # -- views ---------------------------------------------------------------------------
    def observe(self, s: WatchfireState, p: int) -> dict[str, Any]:
        return {
            "seat": p,
            "role": s.roles[p],
            "hand": tuple(s.hands[p]),
            "my_stash": tuple(s.stashes[p]),
            "braziers": tuple((suit, s.braziers[suit] or "-") for suit in SUITS),
            "beacon_lit": self._beacon_lit(s),
            "stash_counts": tuple(len(x) for x in s.stashes),
            "hand_sizes": tuple(len(h) for h in s.hands),
            "draw_left": len(s.draw),
            "ash": tuple(s.ash),
            "turn": s.turn,
            "current": s.current,
            "last_roll": s.last_roll,
            "log": tuple(s.log),
        }

    def describe(self, s: WatchfireState) -> str:
        braz = " ".join(f"{suit}:{s.braziers[suit] or '-'}" for suit in SUITS)
        state = "LIT" if self._beacon_lit(s) else "dark"
        return (
            f"turn {s.turn}/{DECK} seat {s.current} to act; braziers [{braz}] beacon={state}; "
            f"stashes={[len(x) for x in s.stashes]} hands={[len(h) for h in s.hands]} "
            f"draw={len(s.draw)} ash={len(s.ash)}"
        )


GAME = Watchfire
