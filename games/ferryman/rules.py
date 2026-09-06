"""Ferryman — pay a card to carry a passenger across the river, and watch your last fare.

RULESHEET
=========
Players: 2-4.  Components: standard 52-card deck (no jokers) + one six-sided die.
Card rank: A=1, 2-10 face value, J=11, Q=12, K=13.

Setup
-----
Shuffle the deck. Deal 4 cards face-down to each player (their hand). Turn 4 cards face-up in a
row: this is the **Dock**. The rest of the deck stays face-down. The **Toll** pile starts empty
(face-up stack; only its top card is ever available). Each player has an empty face-up **Shore**,
kept as a *stack in the order the passengers landed*, so everyone can see whose passenger came
ashore last. Seat 0 starts round 1; play is clockwise. The single reshuffle is "unused".

Rounds, the start seat and the Tide
-----------------------------------
A round is one turn by each player. Round 1 starts at seat 0, round 2 at seat 1, round 3 at seat 2
and so on, so the first-to-act advantage rotates. Before the round's first player acts, roll the
die: the result 1-6 is the **Tide** for that round. A hand card is **buoyant** this round if its
rank equals the Tide or the Tide + 7 (Tide 1: aces and 8s, Tide 2: 2s and 9s, ... Tide 6: 6s and
kings). A buoyant card can pay for any passenger, whatever the ranks.

Hand limit
----------
A hand may never hold more than 6 cards. Any action that would break this is illegal.

Turn — do exactly one
---------------------
1. **Ferry** — choose a Dock card D and a hand card H with rank(H) >= rank(D), *or* H buoyant this
   round. Put H face-up on top of the Toll pile and put D on top of your Shore stack. If H and D
   share a suit (a *kin fare*) take 2 **kin points**, which are yours for good. Then refill the
   empty Dock slot with the top deck card if the deck still has one.
2. **Poach** — only if some rival's ferry total is *strictly higher* than yours (see The Ledger).
   Choose such a rival and the passenger on **top of their Shore stack** — the one they landed
   most recently. Pay a hand card H with rank(H) >= that passenger's rank, or H buoyant, onto the
   Toll pile, then move that passenger from their Shore onto the top of your own Shore stack. No
   kin points are earned by poaching. The Dock is not touched.
3. **Wade** — take the top card of the Toll pile into your hand. Legal only if the Toll pile is not
   empty and your hand holds fewer than 6 cards. You may take back a card you paid yourself.
4. **Draw** — take the top deck card into your hand. Legal only if the deck is not empty and your
   hand holds fewer than 6 cards.
5. **Pass** — legal only when Ferry, Poach, Wade and Draw are all illegal.

Nothing enters your hand without spending a whole turn on it, so every card in hand is a coin.

The Ledger — how passengers pay
-------------------------------
Passengers pay nothing when they land. Your **ferry total** is always read fresh off your Shore,
so it changes the moment a passenger leaves it. For each suit separately, look at your Shore cards
of that suit and sort them by rank:
* the **highest** of that suit pays its full rank,
* the **second highest** pays half its rank, rounded down,
* every further card of that suit pays exactly 1.
Add your kin points. That is your ferry total, at any moment of the game and at the end.

So a second King of your best suit is nearly worthless, while a first card in a fresh suit pays in
full — and the passenger you just landed is the only one a trailing rival can take away from you.

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
  same number of turns, then play stops;
* the Dock and the deck are both empty — the game ends immediately;
* every player passes in a row (as many consecutive passes as there are players).

Final scoring
-------------
Your score is your ferry total (Ledger + kin points), plus for each of the four suits +5 to the
player with strictly the most Shore cards of that suit (nobody scores that suit if two or more
players tie), minus 1 for every card left in your hand.

Highest score wins. Ties are broken in this order: most Shore cards, then highest single Shore card
rank, then fewest cards in hand, then the higher seat number. This implementation folds the
tie-break into the returned score as a fraction smaller than one point, so a game never ends in a
true draw.

Worked example turn
-------------------
Round 3, Tide 5 (5s and Queens are buoyant). The Dock shows K♠ 9♦ 4♥ 7♣. Beth's Shore stack is
(3♠, Q♦) — Q♦ on top — and her ferry total is 3♠ full (3) + Q♦ full (12) = 15. Ann's Shore is
(J♠, 2♠): J♠ pays 11, 2♠ pays half of 2 = 1, so Ann's total is 12. Ann holds Q♥ 8♦ 5♣ 6♠.
* Ann could ferry K♠ with the buoyant Q♥ (a Queen pays for anything at Tide 5): K♠ would land on her
  Shore, but it is her second spade after J♠, so it would pay only 13 // 2 = 6, lifting her to 18.
* Instead Ann poaches: Beth's total (15) is strictly higher than hers (12), so Ann may take the top
  of Beth's Shore, the Q♦. She pays Q♥ (rank 12 >= 12) onto the Toll pile and moves Q♦ to her Shore.
  Beth drops to 3 and Ann rises to 11 + 1 + 12 = 24. No kin points: poaching pays none.
* The Q♥ now sits on the Toll pile, so Beth may spend her next turn wading it back — and Ann's Q♦
  is now the top of Ann's Shore, so any player who falls behind Ann can poach it straight back.

Worked end-of-game scoring
--------------------------
Ann's Shore is (J♠, 2♠, Q♦, 7♦, 5♦) and she took 2 kin points; she holds 3 cards.
* Spades: J♠ pays 11, 2♠ pays 2 // 2 = 1 → 12.
* Diamonds: Q♦ pays 12, 7♦ pays 7 // 2 = 3, 5♦ pays 1 → 16.
* Ledger 28 + 2 kin = 30. She has the most diamonds of anyone: +5. Hand penalty: -3.
* Final score 32.

Strategy
--------
Open a fresh suit rather than pile a second big card into an old one, keep a cheap passenger on top
of your Shore as a shield when you lead, and remember that the moment you take the lead the whole
table is allowed to rob you.
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
    shore: tuple[tuple[Card, ...], ...]  # stack in landing order; last element is the top
    kin: tuple[int, ...]
    dock: tuple[Card, ...]
    deck: tuple[Card, ...]
    toll: tuple[Card, ...]  # stack; top card is the last element
    tide: int
    cur: int
    start_seat: int
    turn_in_round: int
    round_index: int
    passes: int
    reshuffle_used: bool = False
    end_triggered: bool = False
    over: bool = False


def _buoyant(c: Card, tide: int) -> bool:
    """A hand card is buoyant when its rank is the Tide or the Tide + 7."""
    return c.rank == tide or c.rank == tide + 7


def ledger(shore: tuple[Card, ...]) -> int:
    """Diminishing fares: per suit the highest card pays full, the second half, the rest 1 each."""
    total = 0
    for suit in Suit:
        ranks = sorted((c.rank for c in shore if c.suit == suit), reverse=True)
        for i, r in enumerate(ranks):
            total += r if i == 0 else (r // 2 if i == 1 else 1)
    return total


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
            kin=(0,) * self.n_players,
            dock=dock,
            deck=tuple(deck.cards),
            toll=(),
            tide=roll_d6(rng).values[0],
            cur=0,
            start_seat=0,
            turn_in_round=0,
            round_index=1,
            passes=0,
        )

    def current_player(self, s: FerryState) -> int:
        return s.cur

    # -- helpers -------------------------------------------------------------------------
    def ferry_total(self, s: FerryState, p: int) -> int:
        """Public running total of player ``p``: Ledger value of the Shore plus kin points."""
        return ledger(s.shore[p]) + s.kin[p]

    # -- actions -------------------------------------------------------------------------
    def legal_actions(self, s: FerryState) -> list[tuple]:
        hand = s.hands[s.cur]
        acts: list[tuple] = [
            ("ferry", str(d), str(h))
            for d in s.dock
            for h in hand
            if h.rank >= d.rank or _buoyant(h, s.tide)
        ]
        mine = self.ferry_total(s, s.cur)
        for q in range(self.n_players):
            if q == s.cur or not s.shore[q] or self.ferry_total(s, q) <= mine:
                continue
            target = s.shore[q][-1]
            acts += [
                ("poach", q, str(target), str(h))
                for h in hand
                if h.rank >= target.rank or _buoyant(h, s.tide)
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
        shore = [list(sh) for sh in s.shore]
        kin = list(s.kin)
        emptied = False

        if a[0] == "ferry":
            d = next(c for c in dock if str(c) == a[1])
            h = next(c for c in hand if str(c) == a[2])
            hand.remove(h)
            toll.append(h)
            dock.remove(d)
            shore[p].append(d)
            if d.suit == h.suit:
                kin[p] += KIN_BONUS
            if deck:
                dock.append(deck.pop(0))
                emptied = not deck
        elif a[0] == "poach":
            q = a[1]
            h = next(c for c in hand if str(c) == a[3])
            hand.remove(h)
            toll.append(h)
            shore[p].append(shore[q].pop())
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
            shore=tuple(tuple(sh) for sh in shore),
            kin=tuple(kin),
            dock=tuple(dock),
            deck=tuple(deck),
            toll=tuple(toll),
            passes=passes,
            reshuffle_used=reshuffle_used,
            end_triggered=end_triggered,
        )

        turn_in_round = s.turn_in_round + 1
        over = (
            passes >= self.n_players
            or (not s.dock and not s.deck)
            or (s.end_triggered and turn_in_round >= self.n_players)
        )
        if over:
            return replace(s, over=True, turn_in_round=turn_in_round)
        if turn_in_round >= self.n_players:  # a new round: rotate the start seat, roll a fresh Tide
            start = (s.start_seat + 1) % self.n_players
            return replace(
                s,
                cur=start,
                start_seat=start,
                turn_in_round=0,
                round_index=s.round_index + 1,
                tide=roll_d6(rng).values[0],
            )
        return replace(s, cur=(p + 1) % self.n_players, turn_in_round=turn_in_round)

    def is_terminal(self, s: FerryState) -> bool:
        return s.over

    # -- scoring -------------------------------------------------------------------------
    def scores(self, s: FerryState) -> list[float]:
        """Ledger + kin + suit majorities - cards in hand, with the tie-break as a sub-point tail."""
        out = [float(self.ferry_total(s, p)) for p in range(self.n_players)]
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
            ("totals", tuple(self.ferry_total(s, q) for q in range(self.n_players))),
            ("hand_sizes", tuple(len(h) for h in s.hands)),
            ("to_act", s.cur),
            ("round", s.round_index),
            ("start_seat", s.start_seat),
            ("reshuffled", s.reshuffle_used),
            ("ending", s.end_triggered),
        )

    def describe(self, s: FerryState) -> str:
        dock = " ".join(str(c) for c in s.dock) or "-"
        top = str(s.toll[-1]) if s.toll else "-"
        tops = [str(sh[-1]) if sh else "-" for sh in s.shore]
        return (
            f"round {s.round_index} tide {s.tide} (buoyant: {s.tide}/{s.tide + 7}) seat {s.cur} to act "
            f"(round starts at seat {s.start_seat}); dock: {dock}; toll top {top} ({len(s.toll)}); "
            f"deck {len(s.deck)}"
            f"{' [reshuffled]' if s.reshuffle_used else ''}{' [ending]' if s.end_triggered else ''}; "
            f"totals {[self.ferry_total(s, p) for p in range(self.n_players)]}; "
            f"exposed {tops}; hands {[len(h) for h in s.hands]}"
        )


GAME = Ferryman
