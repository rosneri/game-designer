import json
import os
import shutil
from pathlib import Path

import pytest
from gd_gamecore import load_spec
from gd_gauntlet import STAGES, GauntletConfig, GauntletResult, find_config_file, run_gauntlet
from gd_gauntlet.stages import dominance, fingerprint, jaccard, tension_of

DUMMY = Path(__file__).parent / "dummy_game"
FAST = GauntletConfig(playable_games=4, balance_games=60, skill_games=40, mcts_games=1, mcts_sims=5)


def copy_game(tmp: Path, slug: str, **spec_overrides) -> Path:
    d = tmp / slug
    d.mkdir()
    shutil.copy(DUMMY / "rules.py", d / "rules.py")
    spec = json.loads((DUMMY / "spec.json").read_text()) | {"slug": slug} | spec_overrides
    (d / "spec.json").write_text(json.dumps(spec))
    return d


def test_dummy_passes_fast_config():
    r = run_gauntlet(DUMMY, FAST)
    assert r.passed, r.summary()
    assert [s.name for s in r.stages] == [f.__name__ for f in STAGES]
    assert r.failed_stage is None and r.summary().startswith("PASS")
    d = r.to_dict()
    assert d["passed"] and len(d["stages"]) == len(STAGES)
    s4 = d["stages"][4]["metrics"]
    assert s4["p2"]["greedy_win_rate"] > 0.6
    assert 0.0 < s4["p2"]["dominance"] <= 1.0 and 0.0 < s4["skill_dominance"] <= 1.0
    json.dumps(d)  # serialisable


def test_dominance_scale():
    assert dominance(0.5, 2) == 0.0 and dominance(1.0, 2) == 1.0
    assert dominance(0.25, 4) == 0.0 and round(dominance(0.625, 4), 3) == 0.5


def test_greedy_treadmill_fails_s4():
    """The dummy game is a pure 'play the highest-scoring card' treadmill: a tight cap must reject it."""
    cfg = FAST.model_copy(update={"max_skill_dominance": 0.2})
    r = run_gauntlet(DUMMY, cfg, stop_on_fail=False)
    s4 = next(s for s in r.stages if s.name == "s4_skill")
    assert not s4.passed and "greedy dominance" in s4.reason
    assert s4.metrics["skill_dominance"] > 0.2


@pytest.mark.skipif(not os.environ.get("GD_SLOW"), reason="set GD_SLOW=1 for the full default gauntlet")
def test_dummy_passes_default_config():
    r = run_gauntlet(DUMMY, GauntletConfig())
    assert r.passed, r.summary()
    assert r.seconds < 90


def test_deterministic():
    a, b = run_gauntlet(DUMMY, FAST).to_dict(), run_gauntlet(DUMMY, FAST).to_dict()
    for d in (a, b, *a["stages"], *b["stages"]):
        d.pop("seconds")
    assert a == b


def test_missing_spec_fails_s0(tmp_path):
    r = run_gauntlet(tmp_path, FAST)
    assert not r.passed and r.failed_stage == "s0_schema" and "FAIL" in r.summary()


def test_bad_spec_and_bad_rules(tmp_path):
    d = copy_game(tmp_path, "bad-spec")
    (d / "spec.json").write_text('{"slug": "x"}')
    assert run_gauntlet(d, FAST).failed_stage == "s0_schema"
    d2 = copy_game(tmp_path, "bad-rules")
    (d2 / "rules.py").write_text("x = 1\n")
    r = run_gauntlet(d2, FAST, stop_on_fail=False)
    assert r.failed_stage == "s1_import" and len(r.stages) == 2  # cannot continue without GAME


def test_broken_step_fails_s2(tmp_path):
    d = copy_game(tmp_path, "broken-step")
    src = (d / "rules.py").read_text().replace("s.turn += 1", "s.turn += 1\n        if s.turn > 5: raise RuntimeError('boom')")
    (d / "rules.py").write_text(src)
    r = run_gauntlet(d, FAST)
    assert r.failed_stage == "s2_playable" and "boom" in r.stages[-1].reason
    assert r.stages[-1].metrics["p2"]["error_rate"] == 1.0


def test_stop_on_fail_false_runs_all(tmp_path):
    d = copy_game(tmp_path, "short-game")
    src = (d / "rules.py").read_text().replace("ROUNDS = 45", "ROUNDS = 2")
    (d / "rules.py").write_text(src)
    r = run_gauntlet(d, FAST, stop_on_fail=False)
    assert not r.passed and len(r.stages) == len(STAGES)
    assert r.failed_stage in ("s3_balance", "s4_skill", "s6_length")
    assert not next(s for s in r.stages if s.name == "s6_length").passed


def test_novelty_against_siblings(tmp_path):
    a = copy_game(tmp_path, "twin-a")
    copy_game(tmp_path, "twin-b")
    copy_game(tmp_path, "far-away", mechanics=["trick-taking", "bidding"], components={"jokers": 2, "dice": 0})
    r = run_gauntlet(a, FAST, stop_on_fail=False)
    s7 = next(st for st in r.stages if st.name == "s7_novelty")
    assert not s7.passed
    assert s7.metrics["nearest"] == "twin-b" and s7.metrics["similarity"] == 1.0
    assert r.failed_stage == "s7_novelty"


def test_fingerprint_jaccard():
    from gd_gamecore import load_spec
    s = load_spec(DUMMY)
    f = fingerprint(s)
    assert "mech:dice-rolling" in f and jaccard(f, f) == 1.0
    g = fingerprint(s.model_copy(update={"mechanics": []}))
    assert 0 < jaccard(f, g) < 1


def test_config_toml_override(tmp_path, monkeypatch):
    (tmp_path / "gauntlet.toml").write_text("[gauntlet]\nbalance_games = 7\nminutes_band = [1.0, 2.0]\n")
    game = tmp_path / "games" / "g"
    game.mkdir(parents=True)
    assert find_config_file(game) == tmp_path / "gauntlet.toml"
    cfg = GauntletConfig.load(game)
    assert cfg.balance_games == 7 and cfg.minutes_band == (1.0, 2.0) and cfg.skill_games == GauntletConfig().skill_games
    monkeypatch.chdir(tmp_path)
    assert GauntletConfig.load().balance_games == 7


def test_result_summary_empty():
    r = GauntletResult("x")
    assert not r.passed and r.failed_stage is None


def test_tension_of_reads_a_score_trace():
    # seat 1 leads all game and wins: no drama at all
    runaway = [[0, 5], [0, 6], [1, 7], [2, 9]]
    t = tension_of(runaway)
    assert t["lead_changes"] == 0 and t["decided_at"] == 0.0 and t["comeback"] == 0.0
    # the winner is behind until the final turn: still losing at the three-quarter mark
    comeback = [[1, 0], [2, 0], [3, 0], [4, 0], [5, 0], [6, 0], [7, 0], [7, 9]]
    t = tension_of(comeback)
    assert t["decided_at"] == 0.875 and t["comeback"] == 1.0 and t["lead_changes"] == 1
    # ties count as shared leadership, so a tie-break at the end is a lead change
    assert tension_of([[0, 0], [1, 0], [1, 1], [1, 2]])["lead_changes"] == 3
    assert tension_of([[0, 0]]) is None          # too short to say anything
    assert tension_of([]) is None


def test_s8_tension_fails_a_runaway_and_passes_a_swingy_game(tmp_path):
    from gd_gauntlet import GauntletConfig
    from gd_gauntlet.stages import Context, s8_tension

    class Runaway:
        """Seat 0 scores every turn; nobody else ever does."""

        def __init__(self, n_players, gm=None):
            self.n_players = n_players

        def setup(self, rng):
            return {"t": 0, "s": [0.0] * self.n_players}

        def current_player(self, s):
            return s["t"] % self.n_players

        def legal_actions(self, s):
            return [("go",), ("wait",)]

        def step(self, s, a, rng):
            s = {"t": s["t"] + 1, "s": list(s["s"])}
            if (s["t"] - 1) % self.n_players == 0:
                s["s"][0] += 1
            return s

        def is_terminal(self, s):
            return s["t"] >= 40

        def scores(self, s):
            return list(s["s"])

        def observe(self, s, p):
            return (s["t"],)

        def describe(self, s):
            return f"t={s['t']}"

    class Swingy(Runaway):
        """Every seat takes the lead in turn, so the standings never settle."""

        def step(self, s, a, rng):
            s = {"t": s["t"] + 1, "s": list(s["s"])}
            s["s"][(s["t"] - 1) % self.n_players] += s["t"]
            return s

    cfg = GauntletConfig(tension_games=3, seed=0)
    spec = load_spec(DUMMY / "spec.json")
    for cls, expected in ((Runaway, False), (Swingy, True)):
        ctx = Context(game_dir=tmp_path, cfg=cfg, spec=spec, game_cls=cls)
        res = s8_tension(ctx)
        assert res.passed is expected, (cls.__name__, res.reason, res.metrics)
    ctx = Context(game_dir=tmp_path, cfg=cfg, spec=spec, game_cls=Runaway)
    assert "lead changes" in s8_tension(ctx).reason
