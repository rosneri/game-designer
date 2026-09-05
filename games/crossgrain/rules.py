"""Crossgrain — a trick-taking game where the suit you must follow can change mid-trick.

RULESHEET
=========
Players: 2-4.  Components: standard 52-card deck, no jokers, no dice.

Ranks low to high: 2 3 4 5 6 7 8 9 10 J Q K A.  Suits (C, D, H, S) have no ranking
and there is no trump.  Seats are numbered 0..n-1 clockwise.

Setup
-----
The game is a fixed number of hands with a fixed hand size:

    players | hands | cards per player per hand
       2    |   4   | 13
       3    |   4   | 13
       4    |   4   | 13

Each hand, shuffle all 52 cards and deal 13 cards to every player; with 2 or 3 players the
undealt remainder is set aside face down, unused for that hand.  The leader of the first trick
of hand h (hands counted from 0) is seat h mod n.  Scores start at 0 and carry across hands.

Playing a trick
---------------
The leader plays any card.  Its suit becomes the trick's *current suit* and it becomes the
*previous card*.  Play continues clockwise until every player has played exactly one card.
On your turn you must play one card from your hand, choosing among these options:

1. **Follow** — play any card of the current suit.  The current suit does not change.
2. **Cut** — play any card whose rank equals the rank of the previous card (the card played
   immediately before yours, whatever it was).  The current suit changes to the suit of the
   card you just played.
3. **Dead play** — only if you hold no card of the current suit and no card matching the
   previous card's rank: play any card.  The current suit does not change.

If you can follow or cut you must do one of them, but you choose freely between the two and
among the qualifying cards.  Whatever you play becomes the new previous card.

The grain token
---------------
A card in the trick is **live** while its suit equals the current suit.  After every card is
played, look at the trick: the player holding the highest live card takes the **grain token**,
which is worth 1 point.  The leader always takes it with the opening card.  When a later card
takes over — a higher card of the current suit, or a cut that swings the suit — the token moves:
the old holder loses that 1 point and the new holder gains it.  Points from the token are
scored immediately, so the token can change hands several times inside one trick.

Resolving a trick
-----------------
When all n cards are down, the *final suit* is the current suit at that moment.  Every card
of the final suit is live (including the led card and any dead play that happens to be of that
suit); all others are dead.  There is always at least one live card, because the card that most
recently set the current suit is of that suit.  The player holding the grain token wins the
trick — that is the highest live card.  The trick is worth 1 point per live card (1..n): the
winner already holds 1 point from the token and scores the remaining live cards now.  The
winner leads the next trick and won cards are set aside for the rest of the hand.

End of hand
-----------
A hand ends when every hand is empty.  The player who won the most tricks in that hand scores
a 3-point bonus; if two or more players tie for most tricks, nobody gets the bonus.  Then the
next hand is dealt.

End of game
-----------
The game ends after the last hand.  Most points wins.  Ties are broken by, in order:
1. most tricks won over the whole game;
2. among those still tied, the player who won a trick most recently (higher global trick
   index wins);
3. otherwise the lowest seat number.

Clarifications (implementation choices)
---------------------------------------
* The previous card is always the card played immediately before yours; it may itself have
  been a lead, a follow, a cut or a dead play.
* If the previous card was a dead play of another suit, a card can both follow (same suit as
  the current suit) and match that rank.  Both readings leave the current suit unchanged, so
  such a card is simply one legal play.
* A dead play never changes the current suit, but its rank can be cut by the next player.
* With 2 players the previous card for the second player is always the led card.
* ``scores()`` reports raw points; the tie-break chain above is exposed separately through
  ``ranking(s)`` and shown in ``describe`` — points alone decide the reported score.

Strategy note: cutting late steals the grain cheaply but shrinks the trick's value, following
pumps a trick you may not win, and a discarded dead card can come alive if the grain swings back.
"""
from __future__ import annotations

import copy
from random import Random
from typing import Any

from gd_gamecore import GMLike

SUITS = ("C", "D", "H", "S")
RANKS = ("2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A")
RANK_VALUE = {r: i + 2 for i, r in enumerate(RANKS)}
DECK = tuple(r + s for s in SUITS for r in RANKS)

# players -> (number of hands, cards per player per hand)
LAYOUT = {2: (4, 13), 3: (4, 13), 4: (4, 13)}
MOST_TRICKS_BONUS = 3


def rank_of(card: str) -> str:
    return card[:-1]


def suit_of(card: str) -> str:
    return card[-1]


def value_of(card: str) -> int:
    return RANK_VALUE[rank_of(card)]


class Crossgrain:
    """See module docstring for the rulesheet."""

    def __init__(self, n_players: int, gm: GMLike | None = None):
        if n_players not in LAYOUT:
            raise ValueError("2-4 players")
        self.n_players = n_players
        self.gm = gm
        self.hands_total, self.hand_size = LAYOUT[n_players]

    # -- lifecycle -----------------------------------------------------------------------
    def setup(self, rng: Random) -> dict[str, Any]:
        s: dict[str, Any] = {
            "hand_index": 0,
            "hands": [],
            "scores": [0] * self.n_players,
            "tricks_won": [0] * self.n_players,
            "tricks_this_hand": [0] * self.n_players,
            "last_trick_index": [-1] * self.n_players,
            "trick_counter": 0,
            "current_trick": [],
            "current_suit": None,
            "previous_card": None,
            "grain_holder": None,
            "leader": 0,
            "turn": 0,
            "phase": "play",
            "log": [],
        }
        self._deal(s, rng)
        return s

    def _deal(self, s: dict[str, Any], rng: Random) -> None:
        deck = list(DECK)
        rng.shuffle(deck)
        n, k = self.n_players, self.hand_size
        s["hands"] = [sorted(deck[i * k:(i + 1) * k]) for i in range(n)]
        s["tricks_this_hand"] = [0] * n
        s["leader"] = s["hand_index"] % n
        s["turn"] = s["leader"]
        s["current_trick"] = []
        s["current_suit"] = None
        s["previous_card"] = None
        s["grain_holder"] = None

    # -- core ----------------------------------------------------------------------------
    def current_player(self, s: dict[str, Any]) -> int:
        return s["turn"]

    def _playable(self, s: dict[str, Any], p: int) -> list[str]:
        hand = s["hands"][p]
        if not s["current_trick"]:  # leader: anything
            return list(hand)
        suit = s["current_suit"]
        prev_rank = rank_of(s["previous_card"])
        opts = [c for c in hand if suit_of(c) == suit or rank_of(c) == prev_rank]
        return opts if opts else list(hand)  # dead play

    def legal_actions(self, s: dict[str, Any]) -> list[tuple[str, str]]:
        if s["phase"] != "play":
            return []
        return [("play", c) for c in self._playable(s, s["turn"])]

    def step(self, state: dict[str, Any], a: Any, rng: Random) -> dict[str, Any]:
        s = copy.deepcopy(state)
        if s["phase"] != "play":
            raise ValueError("game is over")
        if not (isinstance(a, tuple) and len(a) == 2 and a[0] == "play"):
            raise ValueError(f"bad action {a!r}")
        card = a[1]
        p = s["turn"]
        if card not in self._playable(s, p):
            raise ValueError(f"{card} is not a legal play for seat {p}")

        s["hands"][p].remove(card)
        led = not s["current_trick"]
        cut = (not led) and rank_of(card) == rank_of(s["previous_card"]) and suit_of(card) != s["current_suit"]
        if led or cut:
            s["current_suit"] = suit_of(card)
        s["previous_card"] = card
        s["current_trick"].append((p, card))
        s["turn"] = (p + 1) % self.n_players
        self._update_grain(s)

        if len(s["current_trick"]) == self.n_players:
            self._resolve_trick(s)
            if not any(s["hands"]):
                self._end_hand(s, rng)
        return s

    def _update_grain(self, s: dict[str, Any]) -> None:
        """Move the 1-point grain token to whoever now holds the highest live card."""
        suit = s["current_suit"]
        live = [(seat, c) for seat, c in s["current_trick"] if suit_of(c) == suit]
        holder = max(live, key=lambda sc: value_of(sc[1]))[0]
        if holder != s["grain_holder"]:
            if s["grain_holder"] is not None:
                s["scores"][s["grain_holder"]] -= 1
            s["scores"][holder] += 1
            s["grain_holder"] = holder

    def _resolve_trick(self, s: dict[str, Any]) -> None:
        suit = s["current_suit"]
        live = [(seat, c) for seat, c in s["current_trick"] if suit_of(c) == suit]
        winner = max(live, key=lambda sc: value_of(sc[1]))[0]
        s["scores"][winner] += len(live) - 1  # the grain token already paid 1 point
        s["tricks_won"][winner] += 1
        s["tricks_this_hand"][winner] += 1
        s["last_trick_index"][winner] = s["trick_counter"]
        s["log"].append((s["hand_index"], suit, winner, len(live)))
        s["trick_counter"] += 1
        s["current_trick"] = []
        s["current_suit"] = None
        s["previous_card"] = None
        s["grain_holder"] = None
        s["leader"] = winner
        s["turn"] = winner

    def _end_hand(self, s: dict[str, Any], rng: Random) -> None:
        best = max(s["tricks_this_hand"])
        leaders = [i for i, t in enumerate(s["tricks_this_hand"]) if t == best]
        if len(leaders) == 1:
            s["scores"][leaders[0]] += MOST_TRICKS_BONUS
        s["hand_index"] += 1
        if s["hand_index"] >= self.hands_total:
            s["phase"] = "game_over"
        else:
            self._deal(s, rng)

    def is_terminal(self, s: dict[str, Any]) -> bool:
        return s["phase"] == "game_over"

    def scores(self, s: dict[str, Any]) -> list[float]:
        return [float(v) for v in s["scores"]]

    def ranking(self, s: dict[str, Any]) -> list[int]:
        """Seats ordered best-first using the full tie-break chain."""
        return sorted(
            range(self.n_players),
            key=lambda p: (-s["scores"][p], -s["tricks_won"][p], -s["last_trick_index"][p], p),
        )

    # -- views ---------------------------------------------------------------------------
    def observe(self, s: dict[str, Any], p: int) -> dict[str, Any]:
        return {
            "seat": p,
            "hand": tuple(s["hands"][p]),
            "hand_sizes": tuple(len(h) for h in s["hands"]),
            "hand_index": s["hand_index"],
            "hands_total": self.hands_total,
            "trick": tuple((seat, c) for seat, c in s["current_trick"]),
            "current_suit": s["current_suit"],
            "previous_card": s["previous_card"],
            "grain_holder": s["grain_holder"],
            "leader": s["leader"],
            "to_move": s["turn"],
            "scores": tuple(s["scores"]),
            "tricks_this_hand": tuple(s["tricks_this_hand"]),
            "tricks_won": tuple(s["tricks_won"]),
            "legal": tuple(c for c in self._playable(s, p)) if s["turn"] == p and s["phase"] == "play" else (),
            "phase": s["phase"],
        }

    def describe(self, s: dict[str, Any]) -> str:
        if s["phase"] == "game_over":
            order = self.ranking(s)
            return f"game over: scores={s['scores']} tricks={s['tricks_won']} winner=seat {order[0]}"
        trick = " ".join(f"{seat}:{c}" for seat, c in s["current_trick"]) or "empty"
        return (
            f"hand {s['hand_index'] + 1}/{self.hands_total} scores={s['scores']} "
            f"tricks_this_hand={s['tricks_this_hand']} leader=seat {s['leader']} "
            f"to_move=seat {s['turn']} suit={s['current_suit'] or '-'} "
            f"prev={s['previous_card'] or '-'} trick: {trick}"
        )


GAME = Crossgrain
