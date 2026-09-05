"""Sidestep — a no-trump trick-taking game where the suit you must follow can change mid-trick.

RULESHEET
=========
Players: 2-4.  Components: one standard 52-card deck (no jokers) and two six-sided dice.

Rank order, low to high: 2 3 4 5 6 7 8 9 10 J Q K A.  Suits: ♠ ♥ ♦ ♣ (written S H D C).
There is no trump suit. Suits never beat each other by themselves; only the target-suit
mechanism below decides who wins a trick.

Setup
-----
Seats sit in a circle and play clockwise (seat 0, seat 1, ...). Seat 0 is the dealer.

Roll both dice and add them. The total sets the **Crown rank**:
  * total 2-10: the Crown rank is that number;
  * total 11: the Crown rank is J;
  * total 12: the Crown rank is Q.
The four cards of the Crown rank are **Crown cards**. Aces are never Crown.

Shuffle and deal the whole deck clockwise, starting with the player to the dealer's left:
  * 2 players: 26 cards each;
  * 3 players: 17 cards each, and the last card lies face up in the middle as the
    **Remainder**. The winner of the first trick takes it into their captured pile;
  * 4 players: 13 cards each.
Every player starts with an empty captured pile and a score of 0.

Card values
-----------
Each captured card is worth:
  * Crown card: 3 points;
  * Ace: 2 points;
  * K, Q or J that is not the Crown rank: 1 point;
  * every other card: 0 points.

Playing a trick
---------------
The player to the dealer's left leads the first trick. After that the winner of a trick leads
the next one.

1. **Lead.** The leader plays any card. That card is the **current winner** and its suit is the
   **target suit**.
2. **Follow.** In clockwise order every other player plays exactly one card.
   * If you hold at least one card of the target suit you **must** play a card of the target
     suit; you may choose any of them, high or low. If its rank is strictly higher than the
     current winner it becomes the current winner. The target suit does not change.
   * If you hold no card of the target suit you may play **any** card. This is a **sidestep**.
     If the sidestep card's rank is strictly higher than the current winner's rank, it becomes
     the current winner and the **target suit changes to the suit of that card**. Every later
     player in this trick must now follow the new suit. If its rank is equal or lower, nothing
     changes (a sidestep card is never of the target suit, so equal ranks are possible; an equal
     rank does not take the trick).
   * Always check your hand against the target suit at the moment you play. A player who was
     void in the led suit can still be forced to follow a new target suit.
3. **Resolve.** When everyone has played one card, the player of the current winning card takes
   all cards of the trick into their captured pile. The winning card is always of the final
   target suit.
4. **Score at once.** The winner adds the card values of every card in the trick, plus a
   **+1 Sidestep bonus** if the winning card was played as a sidestep. In a 3-player game the
   winner of the first trick also takes the Remainder and adds its card value.
5. The winner leads the next trick.

End of the game
---------------
The game is a single deal. It ends when all hands are empty: 26 tricks with 2 players,
17 tricks with 3 players, 13 tricks with 4 players. The highest score wins.

Tie-break (deterministic)
-------------------------
Among players tied on score, in order:
  1. the player who won **fewer tricks** wins (more points per trick);
  2. else compare captured piles in this fixed order: ♠A, ♥A, ♦A, ♣A, ♠K, ♥K, ♦K, ♣K, ♠Q, ...
     down to ♣2. Walk the list from the top; the first card that one of the tied players
     captured decides the tie in that player's favour;
  3. else the tied player closest to the dealer's left, clockwise, wins.
This implementation folds the tie-break into ``scores`` as a fraction smaller than 1/2, so the
ranking is exact and a final game never ends in a draw.

Notes on this implementation
----------------------------
* The dealer is always seat 0 (choosing the dealer "at random" only rotates the seats, so it
  changes nothing). The first leader is therefore seat 1, or seat 1 = the non-dealer at 2
  players.
* Actions are ``("play", rank, suit)``, for example ``("play", "10", "S")``.
* ``observe`` shows a player their own hand, everything played in the current trick, both
  scores and trick counts, the Crown rank, the target suit and the hand sizes — never another
  player's hand or the contents of captured piles.

Strategy note: a void is a weapon. Keep a short suit so you can sidestep with an Ace and steal
a fat trick, and remember that every card you throw away is also a card your opponents can no
longer be forced to chase.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from random import Random

from gd_dice import roll_d6
from gd_gamecore import GMLike

RANKS = ("2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A")
SUITS = ("S", "H", "D", "C")
SYMBOL = {"S": "♠", "H": "♥", "D": "♦", "C": "♣"}
RANK_VALUE = {r: i + 2 for i, r in enumerate(RANKS)}  # "2" -> 2 ... "A" -> 14
HAND_SIZE = {2: 26, 3: 17, 4: 13}

Card = tuple[str, str]  # (rank, suit)

# Fixed order used by tie-break 2: ♠A, ♥A, ♦A, ♣A, ♠K, ... down to ♣2.
TIEBREAK_ORDER: tuple[Card, ...] = tuple((r, s) for r in reversed(RANKS) for s in SUITS)
TIEBREAK_INDEX = {c: i for i, c in enumerate(TIEBREAK_ORDER)}


def card_str(c: Card) -> str:
    return f"{c[0]}{SYMBOL[c[1]]}"


def crown_rank_for(total: int) -> str:
    """Dice total -> Crown rank: 2-10 as-is, 11 -> J, 12 -> Q."""
    return {11: "J", 12: "Q"}.get(total, str(total))


@dataclass
class SidestepState:
    crown_rank: str
    dice: tuple[int, int]
    dealer: int
    hands: list[list[Card]]
    captured: list[list[Card]]
    points: list[int]
    tricks_won: list[int]
    remainder: Card | None
    trick: list[tuple[int, Card, bool]] = field(default_factory=list)  # (seat, card, was_sidestep)
    leader: int = 0
    to_act: int = 0
    target_suit: str | None = None
    win_idx: int = 0  # index into ``trick`` of the currently winning play
    trick_number: int = 0
    over: bool = False


class Sidestep:
    """See the module docstring for the rulesheet."""

    def __init__(self, n_players: int, gm: GMLike | None = None):
        if n_players not in HAND_SIZE:
            raise ValueError("Sidestep is for 2-4 players")
        self.n_players = n_players
        self.gm = gm

    # ---------------------------------------------------------------- lifecycle
    def setup(self, rng: Random) -> SidestepState:
        dice = roll_d6(rng, 2).values
        crown = crown_rank_for(sum(dice))
        deck = [(r, s) for s in SUITS for r in RANKS]
        rng.shuffle(deck)
        n, size = self.n_players, HAND_SIZE[self.n_players]
        hands: list[list[Card]] = [[] for _ in range(n)]
        i = 0
        for _ in range(size):  # deal one at a time, starting at the dealer's left
            for k in range(n):
                hands[(1 + k) % n].append(deck[i])
                i += 1
        remainder = deck[i] if i < len(deck) else None
        first = 1 % n
        return SidestepState(
            crown_rank=crown,
            dice=(dice[0], dice[1]),
            dealer=0,
            hands=[self._sorted(h) for h in hands],
            captured=[[] for _ in range(n)],
            points=[0] * n,
            tricks_won=[0] * n,
            remainder=remainder,
            leader=first,
            to_act=first,
        )

    @staticmethod
    def _sorted(hand: list[Card]) -> list[Card]:
        return sorted(hand, key=lambda c: (SUITS.index(c[1]), RANK_VALUE[c[0]]))

    def current_player(self, s: SidestepState) -> int:
        return s.to_act

    def legal_actions(self, s: SidestepState) -> list[tuple[str, str, str]]:
        if s.over:
            return []
        hand = s.hands[s.to_act]
        if s.target_suit is not None:
            follow = [c for c in hand if c[1] == s.target_suit]
            if follow:  # must follow the target suit as it stands right now
                hand = follow
        return [("play", c[0], c[1]) for c in hand]

    def step(self, s: SidestepState, a: tuple[str, str, str], rng: Random) -> SidestepState:
        if a not in self.legal_actions(s):
            raise ValueError(f"illegal action {a!r} for seat {s.to_act}")
        s = copy.deepcopy(s)
        p = s.to_act
        card: Card = (a[1], a[2])
        s.hands[p].remove(card)
        sidestep = s.target_suit is not None and card[1] != s.target_suit
        s.trick.append((p, card, sidestep))
        if len(s.trick) == 1:  # the lead sets the first target suit
            s.target_suit, s.win_idx = card[1], 0
        else:
            best = s.trick[s.win_idx][1]
            if RANK_VALUE[card[0]] > RANK_VALUE[best[0]]:
                s.win_idx = len(s.trick) - 1
                if sidestep:  # a winning sidestep moves the target suit
                    s.target_suit = card[1]
        if len(s.trick) == self.n_players:
            self._resolve(s)
        else:
            s.to_act = (p + 1) % self.n_players
        return s

    def _resolve(self, s: SidestepState) -> None:
        w, _, won_by_sidestep = s.trick[s.win_idx]
        cards = [c for _, c, _ in s.trick]
        if s.trick_number == 0 and s.remainder is not None:  # 3-player Remainder
            cards.append(s.remainder)
            s.remainder = None
        s.captured[w].extend(cards)
        s.points[w] += sum(self._value(c, s.crown_rank) for c in cards) + (1 if won_by_sidestep else 0)
        s.tricks_won[w] += 1
        s.trick = []
        s.target_suit = None
        s.win_idx = 0
        s.trick_number += 1
        s.leader = s.to_act = w
        if not any(s.hands):
            s.over = True

    @staticmethod
    def _value(c: Card, crown_rank: str) -> int:
        if c[0] == crown_rank:
            return 3
        if c[0] == "A":
            return 2
        return 1 if c[0] in ("K", "Q", "J") else 0

    def is_terminal(self, s: SidestepState) -> bool:
        return s.over

    # ---------------------------------------------------------------- scoring
    def scores(self, s: SidestepState) -> list[float]:
        """Raw points during play; at the end a fraction < 1/2 encodes the tie-break order."""
        if not s.over:
            return [float(v) for v in s.points]
        n = self.n_players
        keys = []
        for p in range(n):
            pile = sum(1 << (len(TIEBREAK_ORDER) - 1 - TIEBREAK_INDEX[c]) for c in set(s.captured[p]))
            dist = (p - s.dealer - 1) % n  # 0 = closest to the dealer's left
            keys.append((s.points[p], -s.tricks_won[p], pile, -dist))
        order = sorted(range(n), key=lambda p: keys[p])  # worst first; keys are all distinct
        bonus = [0.0] * n
        for rank, p in enumerate(order):
            bonus[p] = rank / (2 * n)  # < 0.5, so it never crosses a whole point of score
        return [s.points[p] + bonus[p] for p in range(n)]

    # ---------------------------------------------------------------- views
    def observe(self, s: SidestepState, p: int) -> dict:
        return {
            "seat": p,
            "crown_rank": s.crown_rank,
            "hand": tuple(card_str(c) for c in s.hands[p]),
            "hand_sizes": tuple(len(h) for h in s.hands),
            "target_suit": s.target_suit,
            "trick": tuple((seat, card_str(c), ss) for seat, c, ss in s.trick),
            "winning_seat": s.trick[s.win_idx][0] if s.trick else None,
            "leader": s.leader,
            "to_act": s.to_act,
            "trick_number": s.trick_number,
            "points": tuple(s.points),
            "tricks_won": tuple(s.tricks_won),
            "captured_counts": tuple(len(c) for c in s.captured),
            "remainder": card_str(s.remainder) if s.remainder else None,
            "over": s.over,
        }

    def describe(self, s: SidestepState) -> str:
        played = " ".join(f"s{seat}:{card_str(c)}{'*' if ss else ''}" for seat, c, ss in s.trick) or "-"
        state = "final" if s.over else f"seat {s.to_act} to play"
        return (
            f"Sidestep crown={s.crown_rank} (dice {s.dice[0]}+{s.dice[1]}) trick {s.trick_number + 1} "
            f"target={s.target_suit or '-'} played=[{played}] points={s.points} tricks={s.tricks_won}; {state}"
        )


GAME = Sidestep
