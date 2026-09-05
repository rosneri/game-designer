from random import Random

from gd_cards import Card, Deck, Suit, standard_deck


def test_deck_sizes():
    assert len(standard_deck()) == 52
    assert len(standard_deck(2)) == 54
    assert len(set(standard_deck(2))) == 54


def test_shuffle_deterministic():
    a = Deck().shuffle(Random(1)).cards
    b = Deck().shuffle(Random(1)).cards
    assert a == b and a != standard_deck()


def test_deal_and_draw():
    d = Deck().shuffle(Random(3))
    hands = d.deal(4, 5)
    assert [len(h) for h in hands] == [5] * 4 and len(d) == 32


def test_parse_roundtrip():
    for c in standard_deck(2):
        assert Card.parse(str(c)) == c
    assert Card.parse("10H") == Card(10, Suit.HEARTS)
    assert Card(1, Suit.SPADES).high_value() == 14
