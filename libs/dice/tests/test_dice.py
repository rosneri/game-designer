from random import Random

import pytest
from gd_dice import DicePool, roll_d6


def test_roll_bounds():
    for _ in range(200):
        r = roll_d6(Random(), 2)
        assert all(1 <= v <= 6 for v in r.values) and 2 <= r.total <= 12


def test_limits():
    with pytest.raises(ValueError):
        DicePool(3)
    assert DicePool(0).roll(Random(0)).values == ()


def test_deterministic():
    assert roll_d6(Random(5), 2) == roll_d6(Random(5), 2)
