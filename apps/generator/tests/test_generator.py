import json
import shutil
import sys
from pathlib import Path

import pytest
from gd_generator import llm
from gd_generator.blocks import parse_file_blocks, parse_json_block, write_blocks
from gd_generator.cli import main
from gd_generator.pipeline import (
    Config,
    append_lessons,
    gauntlet_summary,
    idea_prompt,
    parse_idea,
    reserve_slug,
    reset_reservations,
    run_one,
    slugify,
)
from gd_generator.report import write_report

HERE = Path(__file__).parent
REPO = HERE.parents[2]
STUB_LLM = f"{sys.executable} {HERE / 'stubs' / 'fake_prime_agent.py'}"
STUB_TOOL = [sys.executable, str(HERE / "stubs" / "fake_tool.py")]


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """Isolated repo copy: real prompts + gamecore source, empty games/, stubbed LLM and tools."""
    reset_reservations()
    root = tmp_path / "repo"
    shutil.copytree(REPO / "prompts", root / "prompts")
    (root / "prompts" / "LESSONS.md").write_text("# Lessons\n\n")
    shutil.copytree(REPO / "libs" / "gamecore" / "src" / "gd_gamecore", root / "libs/gamecore/src/gd_gamecore")
    (root / "games").mkdir()
    monkeypatch.setenv("GD_PRIME_AGENT_BIN", STUB_LLM)
    monkeypatch.setenv("GD_CLAUDE_BIN", STUB_LLM)  # the idea step goes through the claude backend
    monkeypatch.setenv("GD_RUNNER_CMD", " ".join(STUB_TOOL))
    monkeypatch.setenv("GD_PYTEST_CMD", " ".join(STUB_TOOL))
    monkeypatch.setenv("GD_FAKE_STATE", str(tmp_path / "state"))
    monkeypatch.delenv("GD_FAKE_FAIL", raising=False)
    monkeypatch.delenv("GD_FAKE_LLM_MODE", raising=False)
    return Config(root=root, runner_cmd=STUB_TOOL, pytest_cmd=STUB_TOOL, tool_timeout=60)


# ------------------------------------------------------------------ units
def test_parse_file_blocks_and_write(tmp_path):
    text = "intro\n```python path=games/x/rules.py\nprint(1)\n```\ntext\n```json path=./games/x/spec.json\n{}\n```\n```python\nno path\n```"
    b = parse_file_blocks(text)
    assert set(b) == {"games/x/rules.py", "./games/x/spec.json"}
    assert b["games/x/rules.py"] == "print(1)\n"
    written = write_blocks(b, tmp_path, "games/x/")
    assert sorted(p.name for p in written) == ["rules.py", "spec.json"]
    assert not write_blocks({"../evil.py": "x", "games/y/a.py": "x"}, tmp_path, "games/x/")


def test_parse_json_block():
    assert parse_json_block("```json\n{\"a\": 1}\n```") == {"a": 1}
    assert parse_json_block("bare {\"a\": [1]} trailing") == {"a": [1]}
    assert parse_json_block("nothing") is None


def test_parse_idea_and_slugify():
    d = parse_idea("# Big Game!\nslug: Big Game!\nplayers: 3-5\njokers: 2 jokers\ndice: none\nmechanics: A, b\n")
    assert d["slug"] == "big-game" and d["players"] == (3, 4) and d["jokers"] == 2 and d["dice"] == 0
    assert d["mechanics"] == ["a", "b"] and d["name"] == "Big Game!"
    assert slugify("42 cards") == "g-42-cards" and slugify("ab") == "ab-game"
    assert parse_idea("no header")["slug"] == "untitled"


def test_reserve_slug(tmp_path):
    reset_reservations()
    (tmp_path / "war").mkdir()
    assert reserve_slug("war", tmp_path) == "war-2"
    assert reserve_slug("war", tmp_path) == "war-3"  # reserved by a concurrent worker
    assert reserve_slug("peace", tmp_path) == "peace"


def test_build_argv():
    a = llm.build_argv("hi", "m", "low", cwd="/x", tools=False, system_append="sys")
    assert a[-2:] == ["--", "hi"] and "-nt" in a and "--cwd" in a and "--append-system-prompt" in a
    assert "-nt" not in llm.build_argv("hi", "m", "low", tools=True)
    c = llm.build_argv("hi", "anthropic/claude-fable-5-1", "medium", backend="claude")
    assert c[-2:] == ["--", "hi"] and "claude-fable-5-1" in c and "anthropic/claude-fable-5-1" not in c
    with pytest.raises(ValueError):
        llm.build_argv("hi", "m", "low", backend="claude", tools=True)


def test_llm_call_uses_stub(monkeypatch):
    monkeypatch.setenv("GD_PRIME_AGENT_BIN", STUB_LLM)
    r = llm.call("Reply PONG", "judge")
    assert r.ok and r.text.strip() == "PONG" and r.argv[-1] == "Reply PONG"
    monkeypatch.setenv("GD_FAKE_LLM_MODE", "empty")
    assert not llm.call("x", "judge").ok


def test_gauntlet_summary():
    d = {"stages": {"s3": {"passed": False, "reason": "unbalanced", "metrics": {"w": 0.9}}, "s2": {"passed": True}}}
    s = gauntlet_summary(d, "raw")
    assert "s3" in s and "unbalanced" in s and "s2" not in s
    assert gauntlet_summary(None, "raw out") == "raw out"


def test_append_lessons_dedupes(tmp_path):
    cfg = Config(root=tmp_path)
    (tmp_path / "prompts").mkdir()
    assert append_lessons(cfg, ["a", "- a", "b"]) == 2
    assert append_lessons(cfg, ["a"]) == 0
    assert (tmp_path / "prompts" / "LESSONS.md").read_text() == "- a\n- b\n"


def test_idea_prompt_has_direction_and_existing(repo):
    (repo.games / "old").mkdir()
    (repo.games / "old" / "spec.json").write_text(json.dumps({"name": "Old", "mechanics": ["x"]}))
    p = idea_prompt(repo, 7)
    assert "Seed direction" in p and "- old: Old [x]" in p and idea_prompt(repo, 7) == p


# ------------------------------------------------------------------ pipeline
def test_run_one_happy_path(repo, tmp_path):
    run_dir = tmp_path / "run"
    res = run_one(run_dir, 0, 1, repo)
    assert res["failed_stage"] is None
    assert res["passed"] == ["idea", "code", "validate", "tests", "gauntlet", "judge"]
    assert res["slug"] == "stub-duel" and res["fix_rounds"] == 0
    assert res["judge"]["total"] == 22 and res["judge"]["verdict"] == "reject"
    g = repo.games / "stub-duel"
    assert (g / "rules.py").exists() and (g / "spec.json").exists() and (g / "test_rules.py").exists()
    assert json.loads((g / "spec.json").read_text())["slug"] == "stub-duel"
    out = run_dir / "stub-duel"
    for f in ("idea.md", "code.out.txt", "code.prompt.md", "tests.out.txt", "gauntlet.json", "judge.json", "result.json"):
        assert (out / f).exists(), f
    assert "verbatim" in (out / "code.prompt.md").read_text() and "class Game(Protocol)" in (out / "code.prompt.md").read_text()
    lessons = (repo.prompts / "LESSONS.md").read_text()
    assert "[passed] stub-duel: weakest=originality" in lessons


def test_run_one_validate_fix_round(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("GD_FAKE_FAIL", "validate:1")
    res = run_one(tmp_path / "run", 0, 1, repo)
    assert res["failed_stage"] is None and res["fix_rounds"] == 1
    assert res["fixes"][0]["stage"] == "validate" and res["fixes"][0]["fixed"]
    assert "(fixed)" in (repo.games / "stub-duel" / "rules.py").read_text()
    assert (tmp_path / "run" / "stub-duel" / "fix1.out.txt").exists()
    assert "[validate] stub-duel: failed" in (repo.prompts / "LESSONS.md").read_text()


def test_run_one_gauntlet_unrecovered(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("GD_FAKE_FAIL", "gauntlet:99")
    res = run_one(tmp_path / "run", 3, 9, repo)
    assert res["failed_stage"] == "gauntlet" and res["fix_rounds"] == 2 and res["judge"] is None
    assert "seat 0 wins 80%" in res["error"]
    assert "unrecovered after 2 fixes" in (repo.prompts / "LESSONS.md").read_text()
    prompt = (tmp_path / "run" / "stub-duel" / "fix1.prompt.md").read_text()
    assert "s3_balance" in prompt and "test_rules.py" in prompt


def test_run_one_tests_fail_once_then_pass(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("GD_FAKE_FAIL", "pytest:1")
    res = run_one(tmp_path / "run", 0, 1, repo)
    assert res["failed_stage"] is None and res["fix_rounds"] == 1 and res["fixes"][0]["stage"] == "tests"


def test_run_one_bad_judge_json(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("GD_FAKE_LLM_MODE", "badjson")
    res = run_one(tmp_path / "run", 0, 1, repo)
    assert res["failed_stage"] == "judge" and "gauntlet" in res["passed"]


def test_slug_collision_appends_2(repo, tmp_path):
    (repo.games / "stub-duel").mkdir()
    res = run_one(tmp_path / "run", 0, 1, repo)
    assert res["slug"] == "stub-duel-2" and (repo.games / "stub-duel-2" / "rules.py").exists()
    assert (tmp_path / "run" / "stub-duel-2" / "result.json").exists()


def test_run_one_empty_idea(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("GD_FAKE_LLM_MODE", "empty")
    res = run_one(tmp_path / "run", 0, 1, repo)
    assert res["failed_stage"] == "idea" and (tmp_path / "run" / "idea00" / "result.json").exists()


# ------------------------------------------------------------------ cli / report
def test_cli_run_and_report(repo, tmp_path, capsys):
    run_dir = tmp_path / "run"
    rc = main(["--root", str(repo.root), "run", "--n", "2", "--seed", "3", "--parallel", "2", "--run-dir", str(run_dir)])
    assert rc == 0
    results = json.loads((run_dir / "results.json").read_text())
    assert sorted(r["slug"] for r in results) == ["stub-duel", "stub-duel-2"]  # parallel workers, distinct slugs
    assert all(r["failed_stage"] is None for r in results)
    assert main(["report", str(run_dir)]) == 0
    md = (run_dir / "REPORT.md").read_text()
    assert "Leaderboard" in md and "stub-duel-2" in md and "2 ideas, 2 passed" in md


def test_write_report_own_table(tmp_path):
    d = tmp_path / "r" / "a"
    d.mkdir(parents=True)
    (d / "result.json").write_text(json.dumps({"idx": 0, "slug": "a", "passed": [], "failed_stage": None, "fix_rounds": 1,
                                                "judge": {"fun": 5, "total": 25, "verdict": "iterate", "summary": "ok"}, "timings": {"total": 3}}))
    md = write_report(tmp_path / "r").read_text()
    assert "| a | 25 |" in md or "a" in md
    assert "passed (iterate, 25/50)" in md


def test_cli_dry_run(capsys):
    assert main(["--root", str(REPO), "dry-run", "--n", "1", "--seed", "2"]) == 0
    out = capsys.readouterr().out
    assert "IDEA prompt" in out and "CODE prompt" in out and "class Game(Protocol)" in out
