from random import Random

from gd_gamecore import GMLike
from gd_gm import ScriptedGM


def test_scripted_gm():
    gm = ScriptedGM(Random(1))
    assert isinstance(gm, GMLike)
    assert gm.decide("pick", ["a", "b"], {}) in ("a", "b")
    assert gm.narrate("hi", {}).startswith("[GM]")
