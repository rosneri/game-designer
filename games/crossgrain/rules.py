"""Crossgrain — a trick-taking game where the suit you must follow can swing mid-trick,
and every player is secretly farming one suit.

RULESHEET
=========
Players: 2-4.  Components: standard 52-card deck, no jokers, no dice.

Ranks low to high: 2 3 4 5 6 7 8 9 10 J Q K A.  Honours are J, Q, K, A.  Suits (C, D, H, S)
have no ranking and there is no trump.  Seats are numbered 0..n-1 clockwise.

Setup
-----
A game is one or two deals, depending on the count:

    players | cards per player | tricks per deal | deals
       2    |       26         |       26        |   1
       3    |       17         |       17        |   1
       4    |       13         |       13        |   2

Shuffle the 52 cards and deal.  With 3 players one card is left over and set aside face down;
with 2 players nothing is left over.  The player who was dealt the single lowest card of the
deal leads the first trick (compare by suit order C, D, H, S first, then by rank; the card is
unique, so this picks exactly one seat and it is never fixed to seat 0).

The pledge
----------
Before any card of a deal is played, each player secretly pledges one suit that they hold: this
is their **grain suit** for that deal.  Pledges are face down and are only revealed when the
deal is scored.  You may pledge any suit you hold at least one card of.  Everything you capture
in that suit is worth double, so the pledge is the plan the rest of your deal serves.

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
played, the player holding the highest live card takes the **grain token**, which is worth
2 points scored immediately.  The leader always takes it with the opening card.  When a later
card takes over — a higher card of the current suit, or a cut that swings the suit — the old
holder loses those 2 points and the new holder gains them.  The token can change hands several
times inside one trick.

Resolving a trick
-----------------
When all n cards are down, the *final suit* is the current suit at that moment.  Every card of
the final suit is live; all others are dead.  There is always at least one live card, because
the card that most recently set the current suit is of that suit.  The holder of the grain
token wins the trick and scores, on top of the 2 points already paid by the token:

* **Width:** 1 point per live card after the first (0 to n-1 points).
* **Harvest:** the winner takes all live cards into their harvest, face up, and scores each of
  them at once — 3 for an honour (J, Q, K, A), 1 for any other card, **doubled** (6 and 2) if
  the final suit is the winner's own pledged grain suit.

Dead cards are discarded and are worth nothing to anybody.  Every live card is of the final
suit, so each trick you win adds cards of exactly one suit to your harvest.  Your pledge stays
face down, but a doubled score jump tells the table what you are farming, and from then on they
will fight to swing tricks off your suit.  The winner leads the next trick.

End of a deal
-------------
When all hands are empty the deal is scored: reveal the pledges and apply, in this order.

1. **Most tricks:** the player who won the most tricks in that deal scores 3 points.  If two or
   more players tie for most tricks, nobody scores it.
2. **Sheaf:** a player who harvested at least one honour (J, Q, K, A) of their pledged suit
   scores 3 more points.
3. **Blight:** a player who harvested no card at all of their pledged suit loses 2 points
   instead.

With 4 players a second deal now follows: hands, harvests and pledges are cleared, everyone
pledges a fresh grain suit, and the points already scored carry over.  With 2 or 3 players the
single deal ends the game.

End of game
-----------
Most points wins.  Scores may go negative.  Ties are broken by, in order:
1. most tricks won in the whole game; 2. among those still tied, the player who won a trick
most recently; 3. otherwise the lowest seat number.

Worked example turn (4 players)
-------------------------------
Seat 1 leads 9H.  Current suit H, previous card 9H, seat 1 takes the grain token (+2, running
scores 0/2/0/0).  Seat 2 holds hearts and plays KH — a follow.  KH beats 9H, so the token moves:
seat 1 −2, seat 2 +2 (0/0/2/0).  Seat 3 holds no heart but holds KD, whose rank matches the
previous card KH — a cut.  The current suit swings to D.  Now only KD is live, so seat 3 takes
the token (0/0/0/2).  Seat 0 holds no diamond and no card of rank K, so it is a dead play: 4S.
The suit stays D; 4S is dead.  Final suit D, one live card (KD).  Seat 3 wins: width pays 0
(one live card), and the harvest of KD pays 3 — but 6 instead if seat 3 pledged diamonds.  So
the cut is worth 5 to a heart farmer and 8 to a diamond farmer (0/0/0/8), and it cost seat 2
the 2 points it had a moment earlier.  9H, KH and 4S are discarded.  Seat 3 leads next.

Worked end-of-deal example (3 players, pledges C / H / H)
---------------------------------------------------------
Over the 17 tricks seat 0 won two tricks that ended in clubs and harvested AC and 7C: doubled,
they paid 6 + 2 = 8 the moment they were won.  Seat 1 harvested KH, 10H and 2H in hearts for
6 + 2 + 2 = 10.  Seat 2 kept winning tricks that ended in spades and diamonds — those paid only
3 or 1 per card — and never won a heart trick.  Running totals after the last trick:
seat 0 = 41, seat 1 = 36, seat 2 = 30.
Most tricks 7 / 5 / 5, so seat 0 alone scores 3 → 44 / 36 / 30.
Sheaf: seat 0 holds AC, an honour of clubs, +3 → 47.  Seat 1 holds KH, +3 → 39.
Blight: seat 2 pledged hearts and harvested none, −2 → 28.
Seat 0 wins 47 to 39 to 28.

Strategy note: cutting is how you steer a trick onto your own grain suit, and a doubled honour
is worth more than three plain cards — but a cut usually shrinks the trick to one live card,
so it kills the width points you would have had by following.  Cutting away from an opponent's
grain suit is the cheapest way to starve a leader, and a hand with no honour in your pledged
suit should think hard about pledging elsewhere: blight is a real 2 points.

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
"""
from __future__ import annotations

import copy
from random import Random
from typing import Any

from gd_gamecore import GMLike

SUITS = ("C", "D", "H", "S")
RANKS = ("2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A")
RANK_VALUE = {r: i + 2 for i, r in enumerate(RANKS)}
SUIT_ORDER = {s: i for i, s in enumerate(SUITS)}
DECK = tuple(r + s for s in SUITS for r in RANKS)
HONOURS = frozenset({"J", "Q", "K", "A"})
# value of one harvested card: honours are worth more, and cards of your own
# pledged grain suit are worth double
HARVEST_PLAIN = 1
HARVEST_HONOUR = 3
GRAIN_MULTIPLIER = 2

# players -> cards dealt to each player (a single deal, a single scoring)
HAND_SIZE = {2: 26, 3: 17, 4: 13}
DEALS = {2: 1, 3: 1, 4: 2}
MOST_TRICKS_BONUS = 3
TOKEN_VALUE = 2
SHEAF_BONUS = 3
BLIGHT = -2


def rank_of(card: str) -> str:
    return card[:-1]


def suit_of(card: str) -> str:
    return card[-1]


def value_of(card: str) -> int:
    return RANK_VALUE[rank_of(card)]


class Crossgrain:
    """See module docstring for the rulesheet."""

    def __init__(self, n_players: int, gm: GMLike | None = None):
        if n_players not in HAND_SIZE:
            raise ValueError("2-4 players")
        self.n_players = n_players
        self.gm = gm
        self.hand_size = HAND_SIZE[n_players]
        self.deals_total = DEALS[n_players]

    # -- lifecycle -----------------------------------------------------------------------
    def setup(self, rng: Random) -> dict[str, Any]:
        s: dict[str, Any] = {
            "hands": [],
            "pledges": [None] * self.n_players,
            "harvest": [[] for _ in range(self.n_players)],
            "scores": [0] * self.n_players,
            "tricks_won": [0] * self.n_players,
            "tricks_this_deal": [0] * self.n_players,
            "deal_index": 0,
            "deals_total": self.deals_total,
            "last_trick_index": [-1] * self.n_players,
            "trick_counter": 0,
            "tricks_total": self.hand_size * self.deals_total,
            "current_trick": [],
            "current_suit": None,
            "previous_card": None,
            "grain_holder": None,
            "leader": 0,
            "turn": 0,
            "phase": "pledge",
            "log": [],
        }
        self._deal(s, rng)
        return s

    def _deal(self, s: dict[str, Any], rng: Random) -> None:
        deck = list(DECK)
        rng.shuffle(deck)
        n, k = self.n_players, self.hand_size
        s["hands"] = [sorted(deck[i * k:(i + 1) * k]) for i in range(n)]
        # the seat dealt the single lowest card of the deal leads the first trick
        lowest_seat, lowest_key = 0, None
        for seat, hand in enumerate(s["hands"]):
            key = min((SUIT_ORDER[suit_of(c)], value_of(c)) for c in hand)
            if lowest_key is None or key < lowest_key:
                lowest_seat, lowest_key = seat, key
        s["leader"] = lowest_seat
        s["turn"] = 0  # pledges are made seat by seat, face down
        s["phase"] = "pledge"
        s["pledges"] = [None] * n
        s["harvest"] = [[] for _ in range(n)]
        s["tricks_this_deal"] = [0] * n
        s["current_trick"] = []
        s["current_suit"] = None
        s["previous_card"] = None
        s["grain_holder"] = None

    # -- core ----------------------------------------------------------------------------
    def current_player(self, s: dict[str, Any]) -> int:
        return s["turn"]

    def _pledge_options(self, s: dict[str, Any], p: int) -> list[str]:
        held = {suit_of(c) for c in s["hands"][p]}
        return [x for x in SUITS if x in held] or list(SUITS)

    def _playable(self, s: dict[str, Any], p: int) -> list[str]:
        hand = s["hands"][p]
        if not s["current_trick"]:  # leader: anything
            return list(hand)
        suit = s["current_suit"]
        prev_rank = rank_of(s["previous_card"])
        opts = [c for c in hand if suit_of(c) == suit or rank_of(c) == prev_rank]
        return opts if opts else list(hand)  # dead play

    def legal_actions(self, s: dict[str, Any]) -> list[tuple[str, str]]:
        if s["phase"] == "pledge":
            return [("pledge", x) for x in self._pledge_options(s, s["turn"])]
        if s["phase"] != "play":
            return []
        return [("play", c) for c in self._playable(s, s["turn"])]

    def step(self, state: dict[str, Any], a: Any, rng: Random) -> dict[str, Any]:
        s = copy.deepcopy(state)
        if s["phase"] == "game_over":
            raise ValueError("game is over")
        if not (isinstance(a, tuple) and len(a) == 2):
            raise ValueError(f"bad action {a!r}")
        if s["phase"] == "pledge":
            return self._step_pledge(s, a)
        return self._step_play(s, a, rng)

    def _step_pledge(self, s: dict[str, Any], a: Any) -> dict[str, Any]:
        if a[0] != "pledge" or a[1] not in self._pledge_options(s, s["turn"]):
            raise ValueError(f"bad pledge {a!r}")
        s["pledges"][s["turn"]] = a[1]
        if s["turn"] + 1 < self.n_players:
            s["turn"] += 1
        else:
            s["phase"] = "play"
            s["turn"] = s["leader"]
        return s

    def _step_play(self, s: dict[str, Any], a: Any, rng: Random) -> dict[str, Any]:
        if a[0] != "play":
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
                self._end_deal(s, rng)
        return s

    def _update_grain(self, s: dict[str, Any]) -> None:
        """Move the grain token to whoever now holds the highest live card."""
        suit = s["current_suit"]
        live = [(seat, c) for seat, c in s["current_trick"] if suit_of(c) == suit]
        holder = max(live, key=lambda sc: value_of(sc[1]))[0]
        if holder != s["grain_holder"]:
            if s["grain_holder"] is not None:
                s["scores"][s["grain_holder"]] -= TOKEN_VALUE
            s["scores"][holder] += TOKEN_VALUE
            s["grain_holder"] = holder

    def _resolve_trick(self, s: dict[str, Any]) -> None:
        suit = s["current_suit"]
        live = [(seat, c) for seat, c in s["current_trick"] if suit_of(c) == suit]
        winner = max(live, key=lambda sc: value_of(sc[1]))[0]
        s["scores"][winner] += len(live) - 1  # width; the token already paid its own points
        cards = sorted(c for _, c in live)
        s["harvest"][winner].extend(cards)
        s["scores"][winner] += sum(self.card_value(c, s["pledges"][winner]) for c in cards)
        s["tricks_won"][winner] += 1
        s["tricks_this_deal"][winner] += 1
        s["last_trick_index"][winner] = s["trick_counter"]
        s["log"].append((s["trick_counter"], suit, winner, len(live)))
        s["trick_counter"] += 1
        s["current_trick"] = []
        s["current_suit"] = None
        s["previous_card"] = None
        s["grain_holder"] = None
        s["leader"] = winner
        s["turn"] = winner

    @staticmethod
    def card_value(card: str, pledge: str | None) -> int:
        """Harvest value of one captured card for a player with this pledge."""
        base = HARVEST_HONOUR if rank_of(card) in HONOURS else HARVEST_PLAIN
        return base * GRAIN_MULTIPLIER if suit_of(card) == pledge else base

    def harvest_value(self, s: dict[str, Any], p: int) -> int:
        """Points seat p has already banked from harvested cards."""
        pledge = s["pledges"][p]
        return sum(self.card_value(c, pledge) for c in s["harvest"][p])

    def harvest_bonus(self, s: dict[str, Any], p: int) -> int:
        """End-of-deal adjustment for seat p: blight, or the honour sheaf bonus."""
        pledge = s["pledges"][p]
        if pledge is None:
            return 0
        mine = [c for c in s["harvest"][p] if suit_of(c) == pledge]
        if not mine:
            return BLIGHT
        if any(rank_of(c) in HONOURS for c in mine):
            return SHEAF_BONUS
        return 0

    def _end_deal(self, s: dict[str, Any], rng: Random) -> None:
        best = max(s["tricks_this_deal"])
        leaders = [i for i, t in enumerate(s["tricks_this_deal"]) if t == best]
        if len(leaders) == 1:
            s["scores"][leaders[0]] += MOST_TRICKS_BONUS
        for p in range(self.n_players):
            s["scores"][p] += self.harvest_bonus(s, p)
        s["deal_index"] += 1
        if s["deal_index"] >= self.deals_total:
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
        over = s["phase"] == "game_over"
        return {
            "seat": p,
            "hand": tuple(s["hands"][p]),
            "hand_sizes": tuple(len(h) for h in s["hands"]),
            "my_pledge": s["pledges"][p],
            "pledges": tuple(s["pledges"]) if over else tuple(
                (x if i == p else ("?" if x is not None else None)) for i, x in enumerate(s["pledges"])
            ),
            "harvest": tuple(tuple(h) for h in s["harvest"]),
            "deal_index": s["deal_index"],
            "deals_total": s["deals_total"],
            "trick_index": s["trick_counter"],
            "tricks_total": s["tricks_total"],
            "trick": tuple((seat, c) for seat, c in s["current_trick"]),
            "current_suit": s["current_suit"],
            "previous_card": s["previous_card"],
            "grain_holder": s["grain_holder"],
            "leader": s["leader"],
            "to_move": s["turn"],
            "scores": tuple(s["scores"]),
            "tricks_won": tuple(s["tricks_won"]),
            "legal": tuple(a[1] for a in self.legal_actions(s)) if s["turn"] == p and not over else (),
            "phase": s["phase"],
        }

    def describe(self, s: dict[str, Any]) -> str:
        if s["phase"] == "game_over":
            order = self.ranking(s)
            bonus = [self.harvest_bonus(s, p) for p in range(self.n_players)]
            return (
                f"game over: scores={s['scores']} pledges={s['pledges']} harvest_bonus={bonus} "
                f"tricks={s['tricks_won']} winner=seat {order[0]}"
            )
        if s["phase"] == "pledge":
            return (
                f"pledging: seat {s['turn']} chooses a grain suit face down "
                f"(first leader will be seat {s['leader']})"
            )
        trick = " ".join(f"{seat}:{c}" for seat, c in s["current_trick"]) or "empty"
        harvest = [len(h) for h in s["harvest"]]
        return (
            f"deal {s['deal_index'] + 1}/{s['deals_total']} trick {s['trick_counter'] + 1}"
            f"/{s['tricks_total']} scores={s['scores']} "
            f"tricks={s['tricks_won']} harvest_sizes={harvest} leader=seat {s['leader']} "
            f"to_move=seat {s['turn']} suit={s['current_suit'] or '-'} "
            f"prev={s['previous_card'] or '-'} trick: {trick}"
        )


GAME = Crossgrain
