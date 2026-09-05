import io
import json
from pathlib import Path

import pytest
from gd_runner import ValidationError, play, sim, validate
from gd_runner.cli import main

REPO = Path(__file__).resolve().parents[3]
WAR = REPO / "games" / "reference-war-plus"


def test_validate_ok():
    info = validate(WAR)
    assert info["slug"] == "reference-war-plus" and info["player_counts"] == [2, 3, 4]
    assert all(len(v) == 3 for v in info["turns"].values())


def test_validate_missing_dir(tmp_path):
    with pytest.raises(ValidationError, match="not a directory"):
        validate(tmp_path / "nope")


def test_validate_reports_bad_spec_and_bad_rules(tmp_path):
    (tmp_path / "spec.json").write_text("{}")
    (tmp_path / "rules.py").write_text("GAME = None")
    with pytest.raises(ValidationError, match="GameSpec"):
        validate(tmp_path)
    (tmp_path / "spec.json").write_text(json.dumps({"slug": "bad-game", "name": "B"}))
    with pytest.raises(ValidationError, match="GAME\\(2\\) failed"):
        validate(tmp_path)


def test_validate_catches_mutating_step(tmp_path):
    (tmp_path / "spec.json").write_text(json.dumps({"slug": "mut-game", "name": "M", "players_max": 2}))
    (tmp_path / "rules.py").write_text(
        "class G:\n"
        "    def __init__(self, n_players, gm=None): self.n_players = n_players\n"
        "    def setup(self, rng): return {'t': 0}\n"
        "    def current_player(self, s): return s['t'] % self.n_players\n"
        "    def legal_actions(self, s): return ['a', 'b']\n"
        "    def step(self, s, a, rng): s['t'] += 1; return s\n"
        "    def is_terminal(self, s): return s['t'] >= 4\n"
        "    def scores(self, s): return [1.0, 0.0]\n"
        "    def observe(self, s, p): return s['t']\n"
        "    def describe(self, s): return str(s)\n"
        "GAME = G\n"
    )
    with pytest.raises(ValidationError, match="mutated"):
        validate(tmp_path)


def test_sim_stats():
    out = sim(WAR, players=3, games=6, agents=["random", "greedy"], seed=5)
    assert out["errors"] == 0 and [s["agent"] for s in out["seats"]] == ["random", "greedy", "random"]
    assert abs(sum(s["win_rate"] for s in out["seats"]) - 1) < 1e-9
    assert out["turns"]["min"] == out["turns"]["max"] == 108
    assert sim(WAR, 3, 6, ["random", "greedy"], 5) == out  # deterministic


def test_play_scripted_human():
    buf = io.StringIO()
    r = play(WAR, players=2, seed=3, input_fn=lambda prompt: "0", out=buf)
    text = buf.getvalue()
    assert r.error is None and "You are seat 0" in text and "[0]" in text and "GAME OVER" in text
    assert "you see:" in text and "seat 1 plays" in text


def test_play_quit():
    calls = iter(["x", "q"])
    buf = io.StringIO()
    with pytest.raises(KeyboardInterrupt):
        play(WAR, players=2, seed=3, input_fn=lambda _: next(calls), out=buf)
    assert "invalid choice" in buf.getvalue()


def test_cli_validate_and_sim(capsys):
    assert main(["validate", str(WAR)]) == 0
    assert "OK reference-war-plus" in capsys.readouterr().out
    assert main(["validate", str(WAR / "missing")]) == 1
    assert "INVALID" in capsys.readouterr().err
    assert main(["sim", str(WAR), "--players", "2", "--games", "2", "--agents", "random"]) == 0
    assert json.loads(capsys.readouterr().out)["games"] == 2


def test_cli_gauntlet_writes_json(tmp_path, capsys, monkeypatch):
    from gd_runner import cli
    from gd_runner.compat import _fallback_gauntlet

    monkeypatch.setattr(cli, "run_gauntlet", lambda d: _fallback_gauntlet(d, {"s2_games": 2}))
    out = tmp_path / "g.json"
    assert main(["gauntlet", str(WAR), "--json", str(out)]) == 0
    data = json.loads(out.read_text())
    assert data["passed"] and [s["stage"] for s in data["stages"]] == ["s0_schema", "s1_import", "s2_playable"]
    assert "GAUNTLET PASSED" in capsys.readouterr().out
    assert main(["gauntlet", str(tmp_path), "--json", str(out)]) == 1  # no spec.json there


def test_cli_play_scripted(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda prompt="": "0")
    assert main(["play", str(WAR), "--players", "2", "--seed", "1"]) == 0
    assert "GAME OVER" in capsys.readouterr().out
