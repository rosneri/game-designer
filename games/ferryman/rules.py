"""Ferryman — pay a card to carry a passenger across the river.

RULESHEET
=========
Players: 2-4.  Components: standard 52-card deck (no jokers) + one six-sided die.
Card rank: A=1, 2-10 face value, J=11, Q=12, K=13.

Setup
-----
Shuffle the deck. Deal 4 cards face-down to each player (their hand). Turn 4 cards face-up in a
row: this is the **Dock**. The rest of the deck stays face-down. The **Toll** pile starts empty
(face-up stack; only its top card is ever available). Each player has an empty face-up **Shore**
(the passengers they have carried) and 0 points. Seat 0 starts; play is clockwise. The single
reshuffle is "unused".

Rounds and the Tide
-------------------
A round is one turn by each player in seat order, starting at seat 0. Before seat 0 acts, roll
the die: the result 1-6 is the **Tide** for that round. A hand card is **buoyant** this round if
its rank equals the Tide or the Tide + 7 (Tide 1: aces and 8s, Tide 2: 2s and 9s, ... Tide 6: 6s
and kings).

Hand limit
----------
A hand may never hold more than 6 cards. Any action that would break this is illegal.

Turn — do exactly one
---------------------
1. **Ferry** — choose a Dock card D and a hand card H with rank(H) >= rank(D), *or* H buoyant this
   round (a buoyant card pays for any passenger, so a 3 can carry a King). Put H face-up on top of
   the Toll pile. Move D to your Shore and score rank(D) points at once. If H and D share a suit
   (a *kin fare*) score 2 extra points. Then refill the empty Dock slot with the top deck card if
   the deck still has one.
2. **Wade** — take the top card of the Toll pile into your hand. Legal only if the Toll pile is
   not empty and your hand holds fewer than 6 cards. You may take back a card you paid yourself.
3. **Draw** — take the top deck card into your hand. Legal only if the deck is not empty and your
   hand holds fewer than 6 cards.
4. **Pass** — legal only when Ferry, Wade and Draw are all illegal.

Nothing enters your hand without spending a whole turn on it, so every card in hand is a coin and
every payment is a gift to your rivals, who may wade it back next turn.

Deck exhaustion and the one reshuffle
-------------------------------------
The moment the deck runs out (the card that empties it may be taken by a refill or by a draw):
if the reshuffle is still "unused", shuffle the whole Toll pile face-down into a new deck, leave
the Toll pile empty and mark the reshuffle "used" — this happens even if the Toll pile was empty,
and if the new deck is therefore empty the game end is triggered at once. If the reshuffle was
already "used", the game end is triggered.

Game end
--------
The game ends when any of these happens:
* the end is triggered as above — the current round is finished so that every player has taken the
  same number of turns, then play stops (if the trigger happens on the last seat's turn, the game
  ends with that turn);
* the Dock and the deck are both empty — the game ends immediately;
* every player passes in a row (as many consecutive passes as there are players).

Final scoring
-------------
Your score is the ferry points you collected, plus for each of the four suits +5 to the player with
strictly the most Shore cards of that suit (nobody scores that suit if two or more players tie),
minus 1 for every card left in your hand.

Highest score wins. Ties are broken in this order: most Shore cards, then highest single Shore card
rank, then fewest cards in hand, then the higher seat number (later seats act last every round, so
the tie repays the positional disadvantage). This implementation folds the tie-break into the
returned score as a fraction smaller than one point, so a game never ends in a true draw.

Strategy
--------
Spend the cheapest coin that does the job, hold buoyant cards for the round in which the die makes
them buoyant, chase a suit majority worth +5, and never leave a King on the Toll pile for the
player on your left.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, replace
from random import Random

from gd_cards import Card, Deck, Suit
from gd_dice import roll_d6
from gd_gamecore import GMLike

HAND_LIMIT = 6
START_HAND = 4
DOCK_SIZE = 4
KIN_BONUS = 2
SUIT_BONUS = 5
HAND_PENALTY = 1


@dataclass(frozen=True)
class FerryState:
    hands: tuple[tuple[Card, ...], ...]
    shore: tuple[tuple[Card, ...], ...]
    points: tuple[int, ...]
    dock: tuple[Card, ...]
    deck: tuple[Card, ...]
    toll: tuple[Card, ...]  # stack; top card is the last element
    tide: int
    cur: int
    round_index: int
    passes: int
    reshuffle_used: bool = False
    end_triggered: bool = False
    over: bool = False


def _buoyant(c: Card, tide: int) -> bool:
    """A hand card is buoyant when its rank is the Tide or the Tide + 7."""
    return c.rank == tide or c.rank == tide + 7


class Ferryman:
    """See the module docstring for the rulesheet."""

    def __init__(self, n_players: int, gm: GMLike | None = None):
        if not 2 <= n_players <= 4:
            raise ValueError("2-4 players")
        self.n_players = n_players
        self.gm = gm

    # -- lifecycle -----------------------------------------------------------------------
    def setup(self, rng: Random) -> FerryState:
        deck = Deck(jokers=0).shuffle(rng)
        hands = tuple(tuple(sorted(h)) for h in deck.deal(self.n_players, START_HAND))
        dock = tuple(deck.draw(DOCK_SIZE))
        return FerryState(
            hands=hands,
            shore=tuple(() for _ in range(self.n_players)),
            points=(0,) * self.n_players,
            dock=dock,
            deck=tuple(deck.cards),
            toll=(),
            tide=roll_d6(rng).values[0],
            cur=0,
            round_index=1,
            passes=0,
        )

    def current_player(self, s: FerryState) -> int:
        return s.cur

    # -- actions -------------------------------------------------------------------------
    def legal_actions(self, s: FerryState) -> list[tuple]:
        hand = s.hands[s.cur]
        acts: list[tuple] = [
            ("ferry", str(d), str(h))
            for d in s.dock
            for h in hand
            if h.rank >= d.rank or _buoyant(h, s.tide)
        ]
        if s.toll and len(hand) < HAND_LIMIT:
            acts.append(("wade",))
        if s.deck and len(hand) < HAND_LIMIT:
            acts.append(("draw",))
        return acts or [("pass",)]

    def step(self, s: FerryState, a: tuple, rng: Random) -> FerryState:
        if s.over:
            raise ValueError("game is over")
        if a not in self.legal_actions(s):
            raise ValueError(f"illegal action {a!r}")
        s = copy.deepcopy(s)
        p = s.cur
        hand = list(s.hands[p])
        deck = list(s.deck)
        toll = list(s.toll)
        dock = list(s.dock)
        shore = list(s.shore)
        points = list(s.points)
        emptied = False

        if a[0] == "ferry":
            d = next(c for c in dock if str(c) == a[1])
            h = next(c for c in hand if str(c) == a[2])
            hand.remove(h)
            toll.append(h)
            dock.remove(d)
            shore[p] = tuple(sorted(shore[p] + (d,)))
            points[p] += d.rank + (KIN_BONUS if d.suit == h.suit else 0)
            if deck:
                dock.append(deck.pop(0))
                emptied = not deck
        elif a[0] == "wade":
            hand.append(toll.pop())
        elif a[0] == "draw":
            hand.append(deck.pop(0))
            emptied = not deck

        passes = s.passes + 1 if a[0] == "pass" else 0
        end_triggered = s.end_triggered
        reshuffle_used = s.reshuffle_used
        if emptied:  # the deck just ran out
            if not reshuffle_used:
                deck, toll = toll, []
                rng.shuffle(deck)
                reshuffle_used = True
                end_triggered = end_triggered or not deck  # empty Toll pile -> empty new deck
            else:
                end_triggered = True

        s = replace(
            s,
            hands=tuple(tuple(sorted(hand)) if i == p else s.hands[i] for i in range(self.n_players)),
            shore=tuple(shore),
            points=tuple(points),
            dock=tuple(dock),
            deck=tuple(deck),
            toll=tuple(toll),
            passes=passes,
            reshuffle_used=reshuffle_used,
            end_triggered=end_triggered,
        )

        over = (
            passes >= self.n_players
            or (not s.dock and not s.deck)
            or (s.end_triggered and p == self.n_players - 1)
        )
        if over:
            return replace(s, over=True)
        nxt = (p + 1) % self.n_players
        if nxt == 0:  # a new round begins: the die sets a fresh Tide
            return replace(s, cur=0, round_index=s.round_index + 1, tide=roll_d6(rng).values[0])
        return replace(s, cur=nxt)

    def is_terminal(self, s: FerryState) -> bool:
        return s.over

    # -- scoring -------------------------------------------------------------------------
    def scores(self, s: FerryState) -> list[float]:
        """Ferry points + suit majorities - cards in hand, with the tie-break as a sub-point tail."""
        out = [float(v) for v in s.points]
        for suit in Suit:
            counts = [sum(c.suit == suit for c in sh) for sh in s.shore]
            best = max(counts)
            if best > 0 and counts.count(best) == 1:
                out[counts.index(best)] += SUIT_BONUS
        for p in range(self.n_players):
            out[p] -= HAND_PENALTY * len(s.hands[p])
            out[p] += (
                1e-2 * len(s.shore[p])
                + 1e-4 * max((c.rank for c in s.shore[p]), default=0)
                + 1e-6 * (HAND_LIMIT - len(s.hands[p]))
                + 1e-8 * p
            )
        return out

    # -- views ---------------------------------------------------------------------------
    def observe(self, s: FerryState, p: int) -> tuple:
        return (
            ("hand", tuple(str(c) for c in s.hands[p])),
            ("dock", tuple(str(c) for c in s.dock)),
            ("toll_top", str(s.toll[-1]) if s.toll else None),
            ("toll_size", len(s.toll)),
            ("deck", len(s.deck)),
            ("tide", s.tide),
            ("shores", tuple(tuple(str(c) for c in sh) for sh in s.shore)),
            ("points", s.points),
            ("hand_sizes", tuple(len(h) for h in s.hands)),
            ("to_act", s.cur),
            ("round", s.round_index),
            ("reshuffled", s.reshuffle_used),
            ("ending", s.end_triggered),
        )

    def describe(self, s: FerryState) -> str:
        dock = " ".join(str(c) for c in s.dock) or "-"
        top = str(s.toll[-1]) if s.toll else "-"
        return (
            f"round {s.round_index} tide {s.tide} (buoyant: {s.tide}/{s.tide + 7}) seat {s.cur} to act; "
            f"dock: {dock}; toll top {top} ({len(s.toll)}); deck {len(s.deck)}"
            f"{' [reshuffled]' if s.reshuffle_used else ''}{' [ending]' if s.end_triggered else ''}; "
            f"points {list(s.points)}; hands {[len(h) for h in s.hands]}"
        )


GAME = Ferryman
