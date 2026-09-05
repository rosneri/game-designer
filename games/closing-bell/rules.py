"""Closing Bell — four suits are four stocks; the top card of each pile is its price.

RULESHEET
=========
Players: 2-4.  Components: 52 cards + 2 jokers + 1 six-sided die.  Hand size: 4.

Ranks are prices: Ace = 1, 2-10 face value, Jack = 11, Queen = 12, King = 13, Joker = 0.

Setup
-----
Shuffle all 54 cards. Deal 4 cards to each player (a dealt joker is a normal hand card).
The rest is the face-down draw deck. There are four empty market piles, one per suit
(Clubs, Diamonds, Hearts, Spades). Every player starts with an empty face-up portfolio and
an empty face-down vault. A random first player is chosen; play is clockwise.

Price
-----
The price of a suit is the rank of the top card of its market pile. An empty pile costs 0.
A joker on top means price 0.

Wealth (live score)
-------------------
Your wealth = the sum of the ranks of the cards in your vault + the current price of the
suit of every share in your portfolio. Wealth moves every time anybody touches a market.

Turn
----
Take exactly one action, then refill your hand to 4 cards from the deck (nothing if the
deck is empty).

1. Trade (play to market): play one hand card face up on the market pile of its suit; that
   suit's price becomes the card's rank, up or down. A joker may be played on any one pile
   of your choice and sets that pile's price to 0 (a scandal).
2. Buy (invest): play one non-joker hand card face up into your portfolio. It is now one
   share of its suit; its rank never matters again. Buying at price 0 is allowed. Jokers
   can never be bought.
3. Sell: pick a suit where you hold at least one share and whose market pile is not empty.
   Move the top card of that pile into your vault (worth its rank at scoring, a joker 0)
   and discard one share of that suit face up. The suit's price becomes the rank of the
   newly exposed card, or 0 if the pile is now empty. Selling uses no hand card.
4. Pass: legal only when your hand is empty and you have no legal sell. Anybody holding a
   card must trade, buy or sell — trading is always possible, so passing is never a choice.

Once the deck runs out, turns continue with no draws and hands shrink.

End of game and the closing bell
--------------------------------
The game ends the moment the deck is empty and every hand is empty (checked after each
turn). The last player to act then rolls the die: 1 = Clubs, 2 = Diamonds, 3 = Hearts,
4 = Spades — every player scores +2 for each share of that suit. On 5 or 6 nothing happens.

Final score = vault ranks + current price of each share's suit + closing-bell bonus.
Highest score wins.

Tie-breaks, in order: (1) higher total rank in vault; (2) more cards in the vault;
(3) the tied player who acts earlier in turn order counting from the first player. The
implementation folds the tie-breaks into tiny fractions of a point added to the score, so
a reported score of 41.0036 is a 41 that wins ties on a fatter vault.

Clarifications
--------------
* Market piles keep every card played to them, in order; selling lifts only the top card,
  so a crashed stock can be dug back out.
* Selling is legal at price 0 as long as the pile is non-empty: the joker enters your vault
  worth 0 and the card underneath becomes the new price.
* Portfolio size is unlimited; discarded shares are out of the game.

Strategy note: buy cheap, pump the suits you hold, drop a joker or a low card on the suit
your leading rival owns, and remember that selling banks a price forever while the share
you keep is only paper until the bell.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from random import Random

from gd_cards import Card, Deck, Suit
from gd_dice import roll_d6
from gd_gamecore import GMLike

HAND = 4
N_SUITS = 4
BELL_BONUS = 2
SYMBOLS = ("♣", "♦", "♥", "♠")
SUIT_OF_SYMBOL = {s: i for i, s in enumerate(SYMBOLS)}


@dataclass
class BellState:
    """Full game state. Market piles and portfolios are public; hands and vaults are not."""

    hands: list[list[Card]]
    deck: list[Card]
    market: list[list[Card]]  # market[suit] = pile, last card = price
    portfolio: list[list[int]]  # portfolio[player][suit] = number of shares
    vault: list[list[int]]  # vault[player] = ranks banked by selling
    discard: list[Card] = field(default_factory=list)
    turn: int = 0
    first: int = 0
    bell: int = 0  # 0 until the closing bell is rolled, then the die face 1..6
    done: bool = False


class ClosingBell:
    """See the module docstring for the rulesheet."""

    def __init__(self, n_players: int, gm: GMLike | None = None):
        if not 2 <= n_players <= 4:
            raise ValueError("2-4 players")
        self.n_players = n_players
        self.gm = gm

    # -- lifecycle -----------------------------------------------------------------------
    def setup(self, rng: Random) -> BellState:
        deck = Deck(jokers=2).shuffle(rng)
        hands = [list(h) for h in deck.deal(self.n_players, HAND)]
        first = rng.randrange(self.n_players)
        return BellState(
            hands=hands,
            deck=list(deck.cards),
            market=[[] for _ in range(N_SUITS)],
            portfolio=[[0] * N_SUITS for _ in range(self.n_players)],
            vault=[[] for _ in range(self.n_players)],
            turn=first,
            first=first,
        )

    def current_player(self, s: BellState) -> int:
        return s.turn

    # -- actions -------------------------------------------------------------------------
    def legal_actions(self, s: BellState) -> list[tuple]:
        p = s.turn
        acts: list[tuple] = []
        for c in s.hands[p]:
            if c.is_joker:
                acts += [("trade", str(c), sym) for sym in SYMBOLS]
            else:
                acts.append(("trade", str(c)))
        for c in s.hands[p]:
            if not c.is_joker:
                acts.append(("buy", str(c)))
        for su in range(N_SUITS):
            if s.portfolio[p][su] > 0 and s.market[su]:
                acts.append(("sell", SYMBOLS[su]))
        return acts or [("pass",)]

    def step(self, s: BellState, a: tuple, rng: Random) -> BellState:
        if a not in self.legal_actions(s):
            raise ValueError(f"illegal action {a!r}")
        s = copy.deepcopy(s)
        p = s.turn
        kind = a[0]
        if kind == "trade":
            c = self._take(s.hands[p], a[1])
            su = SUIT_OF_SYMBOL[a[2]] if len(a) > 2 else int(c.suit)
            s.market[su].append(c)
        elif kind == "buy":
            c = self._take(s.hands[p], a[1])
            s.portfolio[p][int(c.suit)] += 1
        elif kind == "sell":
            su = SUIT_OF_SYMBOL[a[1]]
            c = s.market[su].pop()
            s.vault[p].append(c.rank)
            s.portfolio[p][su] -= 1
            s.discard.append(c)
        while len(s.hands[p]) < HAND and s.deck:
            s.hands[p].append(s.deck.pop(0))
        if not s.deck and not any(s.hands):
            s.bell = roll_d6(rng).values[0]  # the closing bell
            s.done = True
            return s
        s.turn = (p + 1) % self.n_players
        return s

    @staticmethod
    def _take(hand: list[Card], code: str) -> Card:
        for i, c in enumerate(hand):
            if str(c) == code:
                return hand.pop(i)
        raise ValueError(f"{code} not in hand")

    # -- scoring -------------------------------------------------------------------------
    @staticmethod
    def price(s: BellState, suit: int) -> int:
        return s.market[suit][-1].rank if s.market[suit] else 0

    def _wealth(self, s: BellState, p: int) -> int:
        w = sum(s.vault[p])
        w += sum(n * self.price(s, su) for su, n in enumerate(s.portfolio[p]))
        if 1 <= s.bell <= N_SUITS:
            w += BELL_BONUS * s.portfolio[p][s.bell - 1]
        return w

    def is_terminal(self, s: BellState) -> bool:
        return s.done

    def scores(self, s: BellState) -> list[float]:
        """Wealth plus tie-break fractions: vault rank, then vault size, then turn order."""
        out = []
        for p in range(self.n_players):
            seat = (p - s.first) % self.n_players
            out.append(
                float(self._wealth(s, p))
                + 1e-4 * sum(s.vault[p])
                + 1e-7 * len(s.vault[p])
                - 1e-9 * seat
            )
        return out

    # -- views ---------------------------------------------------------------------------
    def observe(self, s: BellState, p: int) -> tuple:
        return (
            ("hand", tuple(str(c) for c in s.hands[p])),
            ("prices", tuple(self.price(s, su) for su in range(N_SUITS))),
            ("piles", tuple(tuple(str(c) for c in s.market[su]) for su in range(N_SUITS))),
            ("portfolios", tuple(tuple(pf) for pf in s.portfolio)),
            ("my_vault", tuple(s.vault[p])),
            ("vault_sizes", tuple(len(v) for v in s.vault)),
            ("hand_sizes", tuple(len(h) for h in s.hands)),
            ("deck", len(s.deck)),
            ("turn", s.turn),
            ("bell", s.bell),
        )

    def describe(self, s: BellState) -> str:
        prices = " ".join(f"{SYMBOLS[su]}{self.price(s, su)}" for su in range(N_SUITS))
        folios = ", ".join(
            "seat %d[%s]" % (p, "".join(SYMBOLS[su] * n for su, n in enumerate(s.portfolio[p])) or "-")
            for p in range(self.n_players)
        )
        bell = f" bell={s.bell}" if s.bell else ""
        return (
            f"prices {prices} | deck={len(s.deck)} hands={[len(h) for h in s.hands]} | "
            f"portfolios {folios} | vaults={[sum(v) for v in s.vault]} | seat {s.turn} to act{bell}"
        )


GAME = ClosingBell
