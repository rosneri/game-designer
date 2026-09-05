"""Open Outcry — four suits are four stocks; the top ticker card is the price.

RULESHEET
=========
Players: 2-4.  Components: standard 52-card deck (no jokers) + one six-sided die.

Ranks and prices
----------------
Ace = 1, 2-10 face value, Jack = 11, Queen = 12, King = 13.  The four 7s are removed
before the shuffle and placed face-up as the base card of four *ticker piles*, one per
suit (clubs, diamonds, hearts, spades), in the middle of the table.  **The price of a
suit is always the rank of the top card of its ticker pile**, so every price starts at 7.

Setup
-----
Shuffle the remaining 48 cards into a face-down draw pile and deal 5 cards to each
player.  The discard pile starts empty.  Each player has an empty face-up *portfolio*
(their shares) and an empty face-down *vault* (banked points).  Seats are numbered 0..n-1
clockwise.

Rounds and turn order
---------------------
Play proceeds in rounds.  In round r (counting from 1) the start seat is seat
(r-1) mod n and play goes clockwise from there until every player who is still in the
game has taken exactly one turn; then the market correction is rolled and the next round
begins.  A player whose hand is empty is **out**: they take no further turns but keep
their portfolio and vault for scoring.  (A player only ever runs out of cards at the end
of their own turn, so every round is completed by the players who started it.)

Your turn — choose exactly one action
-------------------------------------
1. **Trade** — play any card from your hand face-up onto the ticker pile of its own suit.
   That suit's price becomes the rank of the card you played.  Play a King to pump, an
   Ace to crash.  The card is gone for good.
2. **Invest** — put a card from your hand face-up into your portfolio as one share of its
   suit.  Legal only if the card's rank is **greater than or equal to** the current price
   of its suit, so a crashed stock is cheap to enter and a pumped one demands a big card.
   A share is worth the *final* price of its suit at game end.
3. **Sell** — cash out one share from your portfolio.  Take the top card of that suit's
   ticker pile and put it face-down in your vault (it scores its rank, i.e. exactly the
   price you sold at).  Then put your share card face-up on top of that ticker pile, so
   the suit's price becomes the rank of your former share.  Selling is a swap, so the
   ticker pile never empties — and cashing out usually drags the price down for everybody
   still holding that stock.

After your action, draw one card if the draw pile is not empty.  If it is empty you do
not draw.  You may never pass while you hold a card: trading a card is always legal.

Market correction (end of every completed round)
------------------------------------------------
Roll the die once.  On 1-4 the matching suit is corrected — 1 = clubs, 2 = diamonds,
3 = hearts, 4 = spades: if that ticker pile holds two or more cards, its top card goes to
the discard pile and the price reverts to the rank of the card now revealed; if the pile
holds only one card nothing happens.  On 5 or 6 there is no correction.  The discard pile
is never reshuffled.  The correction is rolled at the end of every completed round,
including the last one.

Information
-----------
Hands are hidden.  Portfolios and ticker piles are fully public, including every card
buried in a ticker pile, so the price a correction would reveal is known to all.  Vault
cards are face-down: only their owner knows the values, everybody knows the counts.

End of game and scoring
-----------------------
The game ends when every player's hand is empty (only possible once the draw pile is
exhausted).  Score = the sum of the ranks of your vault cards + the final price of each
suit you hold a share in.  Highest score wins.

Tie-break (in order): higher vault total; then more cards in the portfolio; then the
higher single portfolio card (by rank, then suit clubs < diamonds < hearts < spades);
then the player who ran out of cards earlier.  In this implementation the tie-break is
folded into ``scores`` as a bonus smaller than 0.01, so it can never overturn a genuine
one-point difference.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from random import Random

from gd_cards import Card, Suit
from gd_gamecore import GMLike

HAND = 5
BASE_RANK = 7  # the four 7s open every ticker
SUITS = (Suit.CLUBS, Suit.DIAMONDS, Suit.HEARTS, Suit.SPADES)


@dataclass
class OOState:
    draw: list[Card]
    discard: list[Card]
    ticker: list[list[Card]]          # per suit, bottom -> top; price = ticker[suit][-1].rank
    hands: list[list[Card]]
    portfolio: list[list[Card]]
    vault: list[list[Card]]
    out: list[bool]
    order: list[int]                  # seats still to act this round, in turn order
    rnd: int = 1
    turn_no: int = 0
    last_turn: list[int] = field(default_factory=list)   # turn number of a seat's final turn
    last_roll: int = 0                # last correction die (0 = none rolled yet)
    done: bool = False


class OpenOutcry:
    """See module docstring for the rulesheet."""

    def __init__(self, n_players: int, gm: GMLike | None = None):
        if not 2 <= n_players <= 4:
            raise ValueError("2-4 players")
        self.n_players = n_players
        self.gm = gm

    # -- helpers -------------------------------------------------------------------------
    @staticmethod
    def price(s: OOState, suit: int) -> int:
        return s.ticker[int(suit)][-1].rank

    def _round_order(self, s: OOState) -> list[int]:
        start = (s.rnd - 1) % self.n_players
        return [q for i in range(self.n_players)
                if not s.out[q := (start + i) % self.n_players]]

    # -- lifecycle -----------------------------------------------------------------------
    def setup(self, rng: Random) -> OOState:
        ticker = [[Card(BASE_RANK, su)] for su in SUITS]
        draw = [Card(r, su) for su in SUITS for r in range(1, 14) if r != BASE_RANK]
        rng.shuffle(draw)
        hands = [[] for _ in range(self.n_players)]
        for _ in range(HAND):
            for h in hands:
                h.append(draw.pop())
        s = OOState(
            draw=draw, discard=[], ticker=ticker, hands=hands,
            portfolio=[[] for _ in range(self.n_players)],
            vault=[[] for _ in range(self.n_players)],
            out=[False] * self.n_players, order=[],
            last_turn=[-1] * self.n_players,
        )
        s.order = self._round_order(s)
        return s

    def current_player(self, s: OOState) -> int:
        return s.order[0] if s.order else 0

    def legal_actions(self, s: OOState) -> list[tuple]:
        if s.done or not s.order:
            return []
        p = s.order[0]
        acts = [("trade", str(c)) for c in s.hands[p]]
        acts += [("invest", str(c)) for c in s.hands[p] if c.rank >= self.price(s, c.suit)]
        acts += [("sell", str(c)) for c in s.portfolio[p]]
        return acts

    def step(self, s: OOState, a: tuple, rng: Random) -> OOState:
        s = copy.deepcopy(s)
        if s.done or not s.order:
            raise ValueError("game is over")
        p = s.order[0]
        kind, code = a[0], a[1]
        card = Card.parse(code)
        suit = int(card.suit)
        if kind == "trade":
            if card not in s.hands[p]:
                raise ValueError(f"{card} not in hand of seat {p}")
            s.hands[p].remove(card)
            s.ticker[suit].append(card)
        elif kind == "invest":
            if card not in s.hands[p]:
                raise ValueError(f"{card} not in hand of seat {p}")
            if card.rank < self.price(s, suit):
                raise ValueError(f"{card} is below the price of {Suit(suit).name}")
            s.hands[p].remove(card)
            s.portfolio[p].append(card)
        elif kind == "sell":
            if card not in s.portfolio[p]:
                raise ValueError(f"{card} not in portfolio of seat {p}")
            s.portfolio[p].remove(card)
            s.vault[p].append(s.ticker[suit].pop())   # banked at the current price
            s.ticker[suit].append(card)               # the share becomes the new price
        else:
            raise ValueError(f"unknown action {a!r}")

        if s.draw:
            s.hands[p].append(s.draw.pop())
        s.turn_no += 1
        if not s.hands[p]:
            s.out[p] = True
            s.last_turn[p] = s.turn_no
        s.order.pop(0)

        if not s.order:                       # the round is complete -> market correction
            s.last_roll = rng.randint(1, 6)
            if s.last_roll <= 4:
                pile = s.ticker[s.last_roll - 1]
                if len(pile) >= 2:
                    s.discard.append(pile.pop())
            s.rnd += 1
            s.order = self._round_order(s)
            if not s.order:
                s.done = True
        return s

    def is_terminal(self, s: OOState) -> bool:
        return s.done

    # -- scoring -------------------------------------------------------------------------
    def _raw(self, s: OOState, p: int) -> int:
        return (sum(c.rank for c in s.vault[p])
                + sum(self.price(s, c.suit) for c in s.portfolio[p]))

    def _tb_key(self, s: OOState, p: int) -> tuple:
        best = max(((c.rank, int(c.suit)) for c in s.portfolio[p]), default=(0, 0))
        last = s.last_turn[p] if s.last_turn[p] >= 0 else 10**6
        return (sum(c.rank for c in s.vault[p]), len(s.portfolio[p]), best, -last)

    def scores(self, s: OOState) -> list[float]:
        raw = [self._raw(s, p) for p in range(self.n_players)]
        rank = sorted(range(self.n_players), key=lambda p: self._tb_key(s, p), reverse=True)
        bonus = [0.0] * self.n_players
        for i, p in enumerate(rank):
            bonus[p] = 0.001 * (self.n_players - 1 - i)
        return [raw[p] + bonus[p] for p in range(self.n_players)]

    # -- views ---------------------------------------------------------------------------
    def observe(self, s: OOState, p: int) -> dict:
        return {
            "seat": p,
            "hand": tuple(str(c) for c in sorted(s.hands[p])),
            "prices": tuple(self.price(s, su) for su in SUITS),
            "tickers": tuple(tuple(str(c) for c in s.ticker[su]) for su in SUITS),
            "portfolios": tuple(tuple(str(c) for c in s.portfolio[q]) for q in range(self.n_players)),
            "my_vault": tuple(str(c) for c in s.vault[p]),
            "vault_counts": tuple(len(v) for v in s.vault),
            "hand_sizes": tuple(len(h) for h in s.hands),
            "draw": len(s.draw),
            "discard": len(s.discard),
            "round": s.rnd,
            "to_act": tuple(s.order),
            "out": tuple(s.out),
            "last_roll": s.last_roll,
        }

    def describe(self, s: OOState) -> str:
        prices = " ".join(f"{Suit(su).symbol}{self.price(s, su)}" for su in SUITS)
        who = "game over" if s.done else f"seat {s.order[0]} to act"
        return (f"round {s.rnd} | prices {prices} | draw {len(s.draw)} | "
                f"hands {[len(h) for h in s.hands]} | shares {[len(v) for v in s.portfolio]} | "
                f"vaults {[len(v) for v in s.vault]} | {who}")


GAME = OpenOutcry
