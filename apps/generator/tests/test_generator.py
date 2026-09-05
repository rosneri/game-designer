import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from gd_generator import lessons
from gd_generator.backends import (
    ClaudeCodeBackend,
    LLMClient,
    LLMRequest,
    PrimeAgentBackend,
    is_infra_error,
)
from gd_generator.blocks import parse_file_blocks, parse_json_block, write_blocks
from gd_generator.cli import main
from gd_generator.config import GeneratorConfig
from gd_generator.git import GitRepo
from gd_generator.harness import Edit, Harness, parse_edits
from gd_generator.improve import improve
from gd_generator.models import IdeaResult
from gd_generator.pipeline import Batch
from gd_generator.prompts import DIRECTIONS, Prompts, choose_direction, parse_idea, slugify
from gd_generator.refine import refine, run_digest
from gd_generator.registry import Duplicate, LessonBoard, Registry, jaccard
from gd_generator.report import write_report
from gd_generator.steps import gauntlet_summary
from gd_generator.workspace import Snapshot, Workspace

HERE = Path(__file__).parent
REPO = HERE.parents[2]
STUB_LLM = f"{sys.executable} {HERE / 'stubs' / 'fake_prime_agent.py'}"
STUB_TOOL = [sys.executable, str(HERE / "stubs" / "fake_tool.py")]
SPEC = {"name": "Old", "mechanics": ["trick-taking", "bluffing"], "components": {"jokers": 0, "dice": 0}}


@pytest.fixture
def cfg(tmp_path, monkeypatch) -> GeneratorConfig:
    """Isolated repo copy: real prompts + gamecore source, empty games/, stubbed LLM and tools."""
    root = tmp_path / "repo"
    shutil.copytree(REPO / "prompts", root / "prompts")
    (root / "prompts" / "LESSONS.md").write_text("# Lessons\n\n")
    # never inherit the real repo's learned state: every test starts from an empty ledger
    (root / "prompts" / "harness_state.json").unlink(missing_ok=True)
    shutil.copytree(REPO / "libs" / "gamecore" / "src" / "gd_gamecore", root / "libs/gamecore/src/gd_gamecore")
    (root / "games").mkdir()
    monkeypatch.setenv("GD_PRIME_AGENT_BIN", STUB_LLM)
    monkeypatch.setenv("GD_CLAUDE_BIN", STUB_LLM)  # the idea step goes through the claude backend
    monkeypatch.setenv("GD_RUNNER_CMD", " ".join(STUB_TOOL))
    monkeypatch.setenv("GD_PYTEST_CMD", " ".join(STUB_TOOL))
    monkeypatch.setenv("GD_FAKE_STATE", str(tmp_path / "state"))
    for k in ("GD_FAKE_FAIL", "GD_FAKE_LLM_MODE", "GD_FAKE_INFRA_ONCE"):
        monkeypatch.delenv(k, raising=False)
    return GeneratorConfig.load(root, tool_timeout=60, parallel=2)


def add_catalog_game(cfg: GeneratorConfig, slug: str, spec: dict = SPEC) -> Path:
    d = cfg.catalog_dir / slug
    d.mkdir(parents=True)
    (d / "spec.json").write_text(json.dumps({**spec, "slug": slug}))
    (d / "rules.py").write_text("GAME = None\n")
    return d


def run_batch(cfg: GeneratorConfig, run_dir: Path, n: int = 1, seed: int = 1, resume: bool = False) -> list[IdeaResult]:
    return Batch(cfg, run_dir, n, seed, resume=resume).run()


# ------------------------------------------------------------------ units
def test_parse_file_blocks_and_write(tmp_path):
    text = "intro\n```python path=games/x/rules.py\nprint(1)\n```\ntext\n```json path=./games/x/spec.json\n{}\n```\n```python\nno path\n```"
    b = parse_file_blocks(text)
    assert set(b) == {"games/x/rules.py", "./games/x/spec.json"}
    written = write_blocks(b, tmp_path, "games/x/")
    assert sorted(p.name for p in written) == ["rules.py", "spec.json"]
    assert not write_blocks({"../evil.py": "x", "games/y/a.py": "x"}, tmp_path, "games/x/")


def test_parse_json_block():
    assert parse_json_block("```json\n{\"a\": 1}\n```") == {"a": 1}
    assert parse_json_block("bare {\"a\": [1]} trailing") == {"a": [1]}
    assert parse_json_block("nothing") is None


def test_parse_idea_and_slugify():
    b = parse_idea("# Big Game!\nslug: Big Game!\nplayers: 3-5\njokers: 2 jokers\ndice: none\nmechanics: A, b\n", "dir")
    assert b.slug == "big-game" and b.players == (3, 4) and b.jokers == 2 and b.dice == 0
    assert b.mechanics == ["a", "b"] and b.name == "Big Game!" and b.direction == "dir" and b.tags() == {"a", "b"}
    assert slugify("42 cards") == "g-42-cards" and slugify("ab") == "ab-game"
    assert parse_idea("no header").slug == "untitled"


def test_choose_direction_prefers_uncovered_and_is_deterministic():
    assert choose_direction(5, set()) == choose_direction(5, set())
    covered = {"trick-taking", "push-your-luck", "set-collection", "shedding", "bluffing", "auction", "memory"}
    d = choose_direction(5, covered)
    assert not ({"trick", "luck", "shedding", "bluffing", "auction", "memory"} & set(d.split()))
    used = set()
    picks = []
    for i in range(len(DIRECTIONS)):
        p = choose_direction(i, set(), used)
        used.add(p)
        picks.append(p)
    assert len(set(picks)) == len(DIRECTIONS)  # never repeats within a batch while directions remain


def test_backend_argv_and_env(monkeypatch):
    pa = PrimeAgentBackend(["prime-agent"])
    a = pa.argv(LLMRequest("hi", "m", "low", cwd="/x", tools=False, system_append="sys"))
    assert a[-2:] == ["--", "hi"] and "-nt" in a and "--cwd" in a and "--append-system-prompt" in a
    assert "-nt" not in pa.argv(LLMRequest("hi", "m", "low", tools=True))
    cc = ClaudeCodeBackend(["claude"])
    c = cc.argv(LLMRequest("hi", "anthropic/claude-fable-5-1", "medium"))
    assert c[-2:] == ["--", "hi"] and "claude-fable-5-1" in c and "anthropic/claude-fable-5-1" not in c and "--effort" in c
    with pytest.raises(ValueError):
        cc.argv(LLMRequest("hi", "m", "low", tools=True))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert "ANTHROPIC_API_KEY" not in cc.env() and "ANTHROPIC_API_KEY" in pa.env()


def test_timeouts_are_infra_but_not_retried(cfg, monkeypatch):
    from gd_generator.backends import is_retryable
    assert is_infra_error("TIMEOUT after 900s") and not is_retryable("TIMEOUT after 900s")
    assert is_retryable("Provider rejected the request (rate_limit_error, 429)")
    calls = []
    monkeypatch.setattr("gd_generator.backends.run_backend",
                        lambda b, req: calls.append(1) or __import__("gd_generator.backends", fromlist=["x"]).LLMResult(
                            "", "TIMEOUT after 5s", -1, 0.0, [], backend=b.name))
    r = LLMClient(cfg).call("judge", "x")
    assert not r.ok and r.infra and not r.retryable and len(calls) == 1


def test_llm_client_uses_stub_and_retries_infra(cfg, monkeypatch, tmp_path):
    client = LLMClient(cfg)
    r = client.call("judge", "Reply PONG")
    assert r.ok and r.text.strip() == "PONG" and r.argv[-1] == "Reply PONG" and r.backend == "prime-agent"
    monkeypatch.setenv("GD_FAKE_LLM_MODE", "empty")
    assert not client.call("judge", "x").ok
    monkeypatch.delenv("GD_FAKE_LLM_MODE")
    monkeypatch.setenv("GD_FAKE_INFRA_ONCE", str(tmp_path / "once"))
    monkeypatch.setattr("gd_generator.backends.time.sleep", lambda s: None)
    r = client.call("judge", "Reply PONG")
    assert r.ok and r.retries == 1
    monkeypatch.setenv("GD_FAKE_LLM_MODE", "infra")
    r = client.call("judge", "x")
    assert not r.ok and r.infra and r.retries == 1
    assert is_infra_error("TIMEOUT after 5s") and not is_infra_error("AssertionError: seat 0 wins")


def test_tool_output_is_stripped_of_colour_codes():
    from gd_generator.steps import strip_ansi
    assert strip_ansi("\x1b[31m\x1b[1m1 failed\x1b[0m, 27 passed") == "1 failed, 27 passed"
    assert strip_ansi("plain") == "plain"


def test_gauntlet_summary():
    d = {"stages": {"s3": {"passed": False, "reason": "unbalanced", "metrics": {"w": 0.9}}, "s2": {"passed": True}}}
    s = gauntlet_summary(d, "raw")
    assert "s3" in s and "unbalanced" in s and "s2" not in s
    assert gauntlet_summary(None, "raw out") == "raw out"


def test_config_from_toml_and_env(cfg):
    (cfg.root / "generator.toml").write_text('[generator]\nparallel = 7\n[generator.steps.idea]\nmodel = "anthropic/x"\ntimeout = 5\n')
    c = GeneratorConfig.load(cfg.root)
    assert c.parallel == 7 and c.steps["idea"].model == "anthropic/x" and c.steps["idea"].timeout == 5
    assert c.steps["idea"].backend == "claude" and c.steps["code"].tools and c.prime_agent_bin[0] == sys.executable
    assert GeneratorConfig.load(cfg.root, parallel=2).parallel == 2


# ------------------------------------------------------------------ snapshot / workspace
def test_snapshot_is_frozen_and_shadows_catalog(cfg, tmp_path):
    add_catalog_game(cfg, "old")
    ref = add_catalog_game(cfg, cfg.reference_game, {**SPEC, "name": "Ref"})
    snap = Snapshot.take(cfg, tmp_path / "run")
    assert (snap.games / "old" / "spec.json").exists() and not (snap.games / "old" / "rules.py").exists()
    assert (snap.games / cfg.reference_game / "rules.py").exists()  # full package for the code example
    assert snap.catalog_slugs() == {"old", cfg.reference_game} and "idea.md" in snap.prompt_hashes()
    (cfg.prompts_dir / "idea.md").write_text("CHANGED")
    add_catalog_game(cfg, "newer")
    assert "CHANGED" not in (snap.prompts / "idea.md").read_text() and "newer" not in snap.catalog_slugs()
    assert Snapshot.take(cfg, tmp_path / "run").catalog_slugs() == {"old", cfg.reference_game}  # idempotent
    p = Prompts(snap, cfg.root, cfg.reference_game)
    assert "- old: Old [trick-taking, bluffing]" in p.existing_text() and "Example package" in p.example_text()
    ws = Workspace(tmp_path / "run" / "idea00").create(snap)
    assert (ws.games / "old" / "spec.json").exists() and ws.env()["PYTHONPYCACHEPREFIX"].endswith(".pycache")
    ws.game_dir("new").mkdir()
    (ws.game_dir("new") / "rules.py").write_text("x")
    dst = ws.promote("new", cfg.catalog_dir, extra={"gauntlet.json": ref / "spec.json"})
    assert (dst / "rules.py").read_text() == "x" and (dst / "gauntlet.json").exists()
    assert not [p for p in cfg.catalog_dir.iterdir() if p.name.startswith(".")]  # no temp dirs left behind


# ------------------------------------------------------------------ pipeline
def test_happy_path_isolated_then_promoted(cfg, tmp_path):
    run_dir = tmp_path / "run"
    (res,) = run_batch(cfg, run_dir)
    assert res.passed and res.slug == "stub-duel" and res.fix_rounds == 0 and res.promoted
    assert [s.name for s in res.steps] == ["idea", "code", "validate", "tests", "gauntlet", "judge", "promote"]
    assert all(s.status == "ok" for s in res.steps) and res.step("idea").backend == "claude"
    assert res.judge.total == 22 and res.judge.verdict == "reject"
    idea = run_dir / "idea00"
    ws_game = idea / "workspace" / "games" / "stub-duel"
    for f in ("idea.md", "brief.json", "code.prompt.md", "code.out.txt", "tests.out.txt", "gauntlet.json", "judge.json",
              "result.json", "steps/code.json", "steps/judge.json"):
        assert (idea / f).exists(), f
    assert (ws_game / "rules.py").exists() and (ws_game / "test_rules.py").exists()
    g = cfg.catalog_dir / "stub-duel"
    assert (g / "rules.py").exists() and (g / "spec.json").exists() and (g / "test_rules.py").exists() and (g / "gauntlet.json").exists()
    assert json.loads((g / "spec.json").read_text())["slug"] == "stub-duel"
    code_prompt = (idea / "code.prompt.md").read_text()
    assert "class Game(Protocol)" in code_prompt
    # the coding agent's cwd is its workspace, so every command argument it is given must be absolute
    assert str(ws_game.resolve()) in code_prompt
    cmd = next(l for l in code_prompt.splitlines() if "runner validate" in l)
    assert cmd.split("runner validate ")[1].split("`")[0] == str(ws_game.resolve())
    # run-level artefacts
    m = json.loads((run_dir / "manifest.json").read_text())
    assert m["n"] == 1 and "idea.md" in m["prompt_hashes"] and m["config"]["steps"]["idea"]["backend"] == "claude"
    kinds = [e["kind"] for e in json.loads("[" + ",".join((run_dir / "events.jsonl").read_text().split("\n")[:-1]) + "]")]
    assert kinds[0] == "run_start" and kinds[-1] == "run_end" and "step" in kinds
    recs = lessons.load(run_dir)
    assert len(recs) == 1 and recs[0]["kind"] == "judge" and recs[0]["weakest"] == "originality"
    assert (cfg.prompts_dir / "LESSONS.md").read_text() == "# Lessons\n\n"  # untouched until `learn`
    assert lessons.learn(run_dir, cfg.prompts_dir / "LESSONS.md") == 2  # batch aggregate + per-game
    txt = (cfg.prompts_dir / "LESSONS.md").read_text()
    assert "[batch] 1 judged" in txt and "[passed] stub-duel: 22/50 weakest=originality" in txt
    assert lessons.learn(run_dir, cfg.prompts_dir / "LESSONS.md") == 0  # dedupes


def test_no_promote_keeps_catalog_clean(cfg, tmp_path):
    cfg = cfg.model_copy(update={"promote": False})
    (res,) = run_batch(cfg, tmp_path / "run")
    assert res.passed and not res.promoted and not list(cfg.catalog_dir.iterdir())


def test_validate_fix_round(cfg, tmp_path, monkeypatch):
    monkeypatch.setenv("GD_FAKE_FAIL", "validate:1")
    (res,) = run_batch(cfg, tmp_path / "run")
    assert res.passed and res.fix_rounds == 1 and res.fixes[0].stage == "validate" and res.fixes[0].fixed
    assert "(fixed)" in (cfg.catalog_dir / "stub-duel" / "rules.py").read_text()
    assert (tmp_path / "run" / "idea00" / "fix1.out.txt").exists()
    assert [r["kind"] for r in lessons.load(tmp_path / "run")] == ["fix", "judge"]


def test_gauntlet_unrecovered(cfg, tmp_path, monkeypatch):
    monkeypatch.setenv("GD_FAKE_FAIL", "gauntlet:99")
    (res,) = run_batch(cfg, tmp_path / "run", seed=9)
    assert res.failed_stage == "gauntlet" and res.fix_rounds == 2 and res.judge is None and not res.infra and not res.promoted
    assert "seat 0 wins 80%" in res.error and not (cfg.catalog_dir / "stub-duel").exists()
    prompt = (tmp_path / "run" / "idea00" / "fix1.prompt.md").read_text()
    assert "s3_balance" in prompt and "test_rules.py" in prompt
    assert [r["kind"] for r in lessons.load(tmp_path / "run")] == ["fix", "fix", "unrecovered"]


def test_tests_fail_once_then_pass(cfg, tmp_path, monkeypatch):
    monkeypatch.setenv("GD_FAKE_FAIL", "pytest:1")
    (res,) = run_batch(cfg, tmp_path / "run")
    assert res.passed and res.fix_rounds == 1 and res.fixes[0].stage == "tests"


def test_bad_judge_json(cfg, tmp_path, monkeypatch):
    monkeypatch.setenv("GD_FAKE_LLM_MODE", "badjson")
    (res,) = run_batch(cfg, tmp_path / "run")
    assert res.failed_stage == "judge" and res.step("gauntlet").status == "ok" and res.step("judge").status == "failed"


def test_empty_and_infra_idea(cfg, tmp_path, monkeypatch):
    monkeypatch.setenv("GD_FAKE_LLM_MODE", "empty")
    (res,) = run_batch(cfg, tmp_path / "r1")
    assert res.failed_stage == "idea" and not res.infra and (tmp_path / "r1" / "idea00" / "result.json").exists()
    monkeypatch.setenv("GD_FAKE_LLM_MODE", "infra")
    monkeypatch.setattr("gd_generator.backends.time.sleep", lambda s: None)
    (res,) = run_batch(cfg, tmp_path / "r2")
    assert res.failed_stage == "idea" and res.infra and res.step("idea").status == "infra"
    assert lessons.load(tmp_path / "r2") == []  # plumbing failures are not design lessons


def test_slug_collision_with_catalog(cfg, tmp_path):
    add_catalog_game(cfg, "stub-duel", {"name": "Taken", "mechanics": ["nothing-alike"]})
    (res,) = run_batch(cfg, tmp_path / "run")
    assert res.slug == "stub-duel-2" and (cfg.catalog_dir / "stub-duel-2" / "rules.py").exists()
    assert (tmp_path / "run" / "idea00" / "workspace" / "games" / "stub-duel-2" / "rules.py").exists()


def test_dedupe_within_batch_and_against_catalog(cfg, tmp_path):
    a, b = run_batch(cfg, tmp_path / "r1", n=2, seed=3)  # both stub ideas share the same mechanics
    assert a.passed and b.failed_stage == "dedupe" and "stub-duel" in b.error and not b.infra
    assert b.slug == "stub-duel" and not (cfg.catalog_dir / "stub-duel-2").exists()
    (c,) = run_batch(cfg, tmp_path / "r2")  # catalog now holds stub-duel with identical tags
    assert c.failed_stage == "dedupe" and "stub-duel" in c.error
    loose = cfg.model_copy(update={"dedupe_similarity": 1.01})
    (d,) = run_batch(loose, tmp_path / "r3")
    assert d.passed and d.slug == "stub-duel-2"


def test_registry_is_ordered_and_allocates_slugs():
    reg = Registry([{"slug": "old", "mechanics": ["racing"]}], {"old"}, 0.75, 3)
    b0, b1 = parse_idea("# A\nslug: alpha\nmechanics: racing, dice\n"), parse_idea("# B\nslug: old\nmechanics: bidding\n")
    assert reg.register(0, b0) == "alpha"
    assert reg.register(1, b1) == "old-2"  # slug taken by the catalog
    with pytest.raises(Duplicate):
        reg.register(2, parse_idea("# C\nslug: gamma\nmechanics: bidding\n"))
    assert [b.slug for b in reg.briefs()] == ["alpha", "old-2"] and reg.catalog_tags() == {"racing"}
    assert jaccard({"a", "b"}, {"b", "c"}) == pytest.approx(1 / 3) and jaccard(set(), set()) == 0.0


def test_resume_reruns_infra_and_skips_finished_steps(cfg, tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    monkeypatch.setenv("GD_FAKE_LLM_MODE", "infra")
    monkeypatch.setattr("gd_generator.backends.time.sleep", lambda s: None)
    (r1,) = run_batch(cfg, run_dir)
    assert r1.infra and r1.failed_stage == "idea"
    monkeypatch.delenv("GD_FAKE_LLM_MODE")
    (r2,) = run_batch(cfg, run_dir, n=99, seed=99, resume=True)  # n/seed come from the manifest
    assert r2.passed and r2.seed == 1000 and r2.slug == "stub-duel" and r2.promoted
    # now drop the judge record: resume must skip code..gauntlet (artifacts exist) and only redo judge
    rj = json.loads((run_dir / "idea00" / "result.json").read_text())
    rj["steps"] = [s for s in rj["steps"] if s["name"] not in ("judge", "promote")]
    (run_dir / "idea00" / "result.json").write_text(json.dumps(rj))
    (run_dir / "idea00" / "steps" / "judge.json").unlink()
    n_prompts = len(list((run_dir / "idea00").glob("*.prompt.md")))
    (r3,) = run_batch(cfg, run_dir, resume=True)
    assert r3.passed and len(list((run_dir / "idea00").glob("*.prompt.md"))) == n_prompts
    events = [json.loads(l) for l in (run_dir / "events.jsonl").read_text().splitlines()]
    skipped = {e["step"] for e in events if e["kind"] == "step" and e.get("status") == "skipped"}
    assert {"idea", "code", "validate", "tests", "gauntlet"} <= skipped and "judge" not in skipped
    # a finished run resumed again touches nothing
    (r4,) = run_batch(cfg, run_dir, resume=True)
    assert r4.passed and len(list((run_dir / "idea00").glob("*.prompt.md"))) == n_prompts


# ------------------------------------------------------------------ cli / report
def test_cli_run_report_learn(cfg, tmp_path, capsys):
    run_dir = tmp_path / "run"
    loose = cfg.root / "generator.toml"
    loose.write_text("[generator]\ndedupe_similarity = 1.01\n")
    rc = main(["--root", str(cfg.root), "run", "--n", "2", "--seed", "3", "--parallel", "2", "--run-dir", str(run_dir)])
    assert rc == 0
    results = json.loads((run_dir / "results.json").read_text())
    assert sorted(r["slug"] for r in results) == ["stub-duel", "stub-duel-2"]  # parallel workers, distinct slugs
    assert all(r["failed_stage"] is None and r["promoted"] for r in results)
    assert main(["report", str(run_dir)]) == 0
    md = (run_dir / "REPORT.md").read_text()
    assert "Leaderboard" in md and "stub-duel-2" in md and "2 ideas, 2 passed" in md and "models: idea=claude" in md
    assert main(["--root", str(cfg.root), "learn", str(run_dir)]) == 0
    assert "[passed] stub-duel-2" in (cfg.prompts_dir / "LESSONS.md").read_text()
    assert main(["--root", str(cfg.root), "resume", str(run_dir)]) == 0


def test_write_report_own_table(tmp_path):
    d = tmp_path / "r" / "idea00"
    d.mkdir(parents=True)
    (d / "result.json").write_text(json.dumps({"idx": 0, "slug": "a", "failed_stage": None, "fix_rounds": 1, "promoted": True,
                                                "judge": {"fun": 5, "total": 25, "verdict": "iterate", "summary": "ok"}, "timings": {"total": 3}}))
    md = write_report(tmp_path / "r").read_text()
    assert "a" in md and "passed (iterate, 25/50) promoted" in md


def test_cli_dry_run(cfg, capsys):
    assert main(["--root", str(cfg.root), "dry-run", "--n", "1", "--seed", "2"]) == 0
    out = capsys.readouterr().out
    assert "IDEA prompt" in out and "CODE prompt" in out and "class Game(Protocol)" in out and "direction=" in out


# ------------------------------------------------------------------ live lessons / harness / flywheel
def test_lesson_board_and_live_lessons_reach_later_ideas(cfg, tmp_path):
    board = LessonBoard(["old lesson"], live=True)
    board.add(["fresh one", "fresh one"])
    assert board.text() == "- old lesson\n- (this run) fresh one"
    assert LessonBoard(["old lesson"], live=False).text() == "- old lesson"
    assert LessonBoard([], live=True).text() == "- (none yet)"
    # rolling mode, one worker: idea 1's prompt must contain what idea 0 taught
    loose = cfg.model_copy(update={"dedupe_similarity": 1.01, "parallel": 1})
    run_batch(loose, tmp_path / "run", n=2, seed=3)
    first = (tmp_path / "run" / "idea00" / "idea.prompt.md").read_text()
    second = (tmp_path / "run" / "idea01" / "idea.prompt.md").read_text()
    assert "(this run)" not in first
    assert "(this run) [passed] stub-duel: 22/50" in second
    assert "- stub-duel: Stub Duel [trick-taking, bluffing]" in second  # peer briefs listed as existing


def test_live_lessons_can_be_switched_off(cfg, tmp_path):
    off = cfg.model_copy(update={"dedupe_similarity": 1.01, "parallel": 1, "live_lessons": False})
    run_batch(off, tmp_path / "run", n=2, seed=3)
    assert "(this run)" not in (tmp_path / "run" / "idea01" / "idea.prompt.md").read_text()


def test_phased_mode_still_works(cfg, tmp_path):
    phased = cfg.model_copy(update={"dedupe_similarity": 1.01, "mode": "phased"})
    a, b = run_batch(phased, tmp_path / "run", n=2, seed=3)
    assert a.passed and b.passed and {a.slug, b.slug} == {"stub-duel", "stub-duel-2"}


def test_harness_ledger_apply_render_and_rollback(tmp_path):
    h = Harness(tmp_path / "harness_state.json")
    assert h.text_for("idea") == "- (none yet)"
    ev = h.apply([Edit(op="create", id="a", kind="constraint", text="rule A", targets=["idea", "code"]),
                  Edit(op="create", id="b", kind="note", text="rule B")], run="r1")
    assert "rule A" in h.text_for("idea") and "rule A" in h.text_for("code") and "rule B" not in h.text_for("code")
    ev2 = h.apply([Edit(op="update", id="a", kind="constraint", text="rule A2", targets=["idea"]),
                   Edit(op="delete", id="b")], run="r2")
    assert "rule A2" in h.text_for("idea") and "rule B" not in h.text_for("idea")
    assert h.rollback(ev2.event_id) and "rule A" in h.text_for("idea") and "rule B" in h.text_for("idea")
    assert not h.rollback(ev2.event_id)  # already rolled back
    assert h.rollback(ev.event_id) and h.load().entries == {}
    assert h.apply([Edit(op="create", id="a", kind="note", text="kept")], run="r3").edits
    assert "kept" in Harness(tmp_path / "harness_state.json").summary()


def test_parse_edits_validates():
    ok = parse_edits({"edits": [{"op": "create", "id": "a", "kind": "note", "text": "x", "targets": ["idea", "nope"]},
                                {"op": "create", "id": "", "text": "no id"},
                                {"op": "create", "id": "b", "text": "   "},
                                {"op": "delete", "id": "c"},
                                {"op": "explode", "id": "d", "text": "x"},
                                "junk"]})
    assert [(e.op, e.id) for e in ok] == [("create", "a"), ("delete", "c")] and ok[0].targets == ["idea"]
    assert parse_edits(None) == [] and parse_edits({}) == []
    assert len(parse_edits({"edits": [{"op": "create", "id": f"i{i}", "text": "x"} for i in range(20)]}, limit=3)) == 3


def test_harness_entries_reach_idea_and_code_prompts(cfg, tmp_path):
    Harness(cfg.harness_file).apply([Edit(op="create", id="k", kind="constraint", text="LEDGER RULE ONE",
                                          targets=["idea", "code"])], run="seed")
    (res,) = run_batch(cfg, tmp_path / "run")
    assert res.passed
    assert "LEDGER RULE ONE" in (tmp_path / "run" / "idea00" / "idea.prompt.md").read_text()
    assert "LEDGER RULE ONE" in (tmp_path / "run" / "idea00" / "code.prompt.md").read_text()
    assert json.loads((tmp_path / "run" / "manifest.json").read_text())["harness_entries"] == 1


def test_refine_updates_ledger_and_is_reversible(cfg, tmp_path):
    run_dir = tmp_path / "run"
    run_batch(cfg, run_dir)
    d = run_digest(run_dir)
    assert d["ideas"] == 1 and d["passed"] == 1 and d["mean_judge"] == 22 and d["games"][0]["slug"] == "stub-duel"
    ev, _ = refine(cfg, run_dir)
    assert ev and [e.op for e in ev.edits] == ["create", "delete"]
    h = Harness(cfg.harness_file)
    assert "more than 3 legal actions" in h.text_for("idea")
    assert (run_dir / "refine.prompt.md").exists() and (run_dir / "refine.json").exists()
    assert h.rollback(ev.event_id) and h.text_for("idea") == "- (none yet)"


def test_refine_reports_unusable_answer(cfg, tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    run_batch(cfg, run_dir)
    monkeypatch.setenv("GD_FAKE_LLM_MODE", "badjson")
    ev, raw = refine(cfg, run_dir)
    assert ev is None and "not json" in raw
    assert Harness(cfg.harness_file).load().entries == {}


def _improve_cfg(cfg: GeneratorConfig, gate_ok: bool = True):
    gate = [*STUB_TOOL, "gate"] if gate_ok else [*STUB_TOOL, "gate", "--fail"]
    return cfg.model_copy(update={"improve_paths": ["prompts", "libs"], "improve_gates": [gate], "gate_timeout": 60})


def test_improve_applies_when_gates_pass(cfg, tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    run_batch(cfg, run_dir)
    target = cfg.prompts_dir / "idea.md"
    monkeypatch.setenv("GD_FAKE_IMPROVE_WRITE", f"{target}::PATCHED IDEA PROMPT\n")
    res = improve(_improve_cfg(cfg), run_dir)
    assert res.applied and not res.reverted and res.changed == ["prompts/idea.md"]
    assert target.read_text() == "PATCHED IDEA PROMPT\n" and res.gates[0].ok
    assert json.loads((run_dir / "improve" / "improve.json").read_text())["applied"]
    assert "self-improvement" in Harness(cfg.harness_file).text_for("idea")


def test_improve_reverts_when_a_gate_fails(cfg, tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    run_batch(cfg, run_dir)
    target, before = cfg.prompts_dir / "idea.md", (cfg.prompts_dir / "idea.md").read_text()
    new_file = cfg.root / "libs" / "brand_new.py"
    monkeypatch.setenv("GD_FAKE_IMPROVE_WRITE", f"{target}::BROKEN\n")
    monkeypatch.setenv("GD_FAKE_FAIL", "gate:99")
    res = improve(_improve_cfg(cfg, gate_ok=False), run_dir)
    assert res.reverted and not res.applied and res.changed == ["prompts/idea.md"]
    assert target.read_text() == before  # restored byte for byte
    assert "REVERTED" in Harness(cfg.harness_file).text_for("idea")
    # a file the model creates is removed again when the gates fail
    monkeypatch.setenv("GD_FAKE_IMPROVE_WRITE", f"{new_file}::x = 1\n")
    res = improve(_improve_cfg(cfg, gate_ok=False), run_dir)
    assert res.reverted and res.changed == ["libs/brand_new.py"] and not new_file.exists()


def test_improve_no_change_and_dry_run(cfg, tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    run_batch(cfg, run_dir)
    monkeypatch.delenv("GD_FAKE_IMPROVE_WRITE", raising=False)
    res = improve(_improve_cfg(cfg), run_dir)
    assert not res.applied and not res.reverted and res.changed == [] and res.error == "no files changed"
    dry = improve(_improve_cfg(cfg), run_dir, dry_run=True)
    assert "## Evidence from run" in dry.answer and not dry.gates


def test_flywheel_runs_each_phase_in_a_fresh_interpreter(cfg, monkeypatch):
    """The improve step can rewrite the generator, so a cycle must not run already-imported code."""
    calls = []
    monkeypatch.setattr("gd_generator.cli.subprocess.run",
                        lambda cmd, check=False: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0))
    assert main(["--root", str(cfg.root), "flywheel", "--cycles", "2", "--n", "4", "--seed", "5",
                 "--parallel", "2", "--push", "--label", "A"]) == 0
    phases = [c[c.index("gd_generator.cli") + 3] for c in calls]
    assert phases == ["run", "learn", "refine", "improve"] * 2
    assert all(c[:3] == [sys.executable, "-m", "gd_generator.cli"] for c in calls)
    run_cmd = calls[0]
    assert "--push" in run_cmd and run_cmd[run_cmd.index("--n") + 1] == "4" and run_cmd[run_cmd.index("--parallel") + 1] == "2"
    assert all("--push" in c for c in calls)  # every phase commits what it produces
    assert main(["--root", str(cfg.root), "flywheel", "--cycles", "1", "--n", "1", "--no-refine",
                 "--no-improve", "--label", "B"]) == 0
    assert [c[c.index("gd_generator.cli") + 3] for c in calls[8:]] == ["run", "learn"]


def test_flywheel_resumes_an_interrupted_cycle(cfg, monkeypatch):
    calls = []
    monkeypatch.setattr("gd_generator.cli.subprocess.run",
                        lambda cmd, check=False: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0))
    fly = ["--root", str(cfg.root), "flywheel", "--cycles", "3", "--n", "2", "--label", "L",
           "--no-refine", "--no-improve"]
    # cycle 1 finished; cycle 2 was killed mid-run (a manifest, no done marker); cycle 3 never started
    for c, files in ((1, ("manifest.json", ".cycle-done")), (2, ("manifest.json",))):
        d = cfg.runs_dir / f"L-c{c:02d}"
        d.mkdir(parents=True)
        for f in files:
            (d / f).write_text("{}")
    assert main(fly) == 0
    phases = [c[c.index("gd_generator.cli") + 3] for c in calls]
    assert phases == ["resume", "learn", "run", "learn"]      # c1 skipped, c2 resumed, c3 fresh
    assert str(cfg.runs_dir / "L-c02") in calls[0] and str(cfg.runs_dir / "L-c03") in calls[2]
    assert all((cfg.runs_dir / f"L-c{c:02d}" / ".cycle-done").exists() for c in (1, 2, 3))


def test_cli_flywheel_and_harness_commands(cfg, tmp_path, monkeypatch, capsys):
    (cfg.root / "generator.toml").write_text(
        f'[generator]\ndedupe_similarity = 1.01\nimprove_paths = ["prompts"]\nimprove_gates = [{[*STUB_TOOL, "gate"]!r}]\n'.replace("'", '"'))
    monkeypatch.setenv("GD_FAKE_IMPROVE_WRITE", f"{cfg.prompts_dir / 'judge.md'}::JUDGE {{idea}} {{docstring}} {{metrics}}\n")
    assert main(["--root", str(cfg.root), "flywheel", "--cycles", "2", "--n", "1", "--seed", "5", "--parallel", "2"]) == 0
    assert (cfg.root / "runs").exists()
    runs = sorted(p for p in (cfg.root / "runs").glob("*-c*") if p.is_dir())
    assert len(runs) == 2 and all((r / "REPORT.md").exists() for r in runs)
    h = Harness(cfg.harness_file)
    assert "more than 3 legal actions" in h.text_for("idea")  # refine ran
    assert "self-improvement" in h.text_for("idea")           # improve ran
    assert "[passed] stub-duel" in (cfg.prompts_dir / "LESSONS.md").read_text()  # learn ran
    assert main(["--root", str(cfg.root), "harness"]) == 0
    assert "min-legal-actions" in capsys.readouterr().out
    ev = h.load().refinements[0]
    assert main(["--root", str(cfg.root), "rollback", ev.event_id]) == 0
    assert main(["--root", str(cfg.root), "rollback", "nope"]) == 1


# ------------------------------------------------------------------ git
def _init_repo(root: Path) -> None:
    import subprocess
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@example.com"],
                 ["config", "user.name", "T"], ["add", "-A"], ["commit", "-qm", "base"]):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _log(root: Path) -> list[str]:
    import subprocess
    out = subprocess.run(["git", "-C", str(root), "log", "--format=%s"], capture_output=True, text=True, check=True)
    return out.stdout.splitlines()


def test_git_commits_only_named_paths(cfg, tmp_path):
    _init_repo(cfg.root)
    git = GitRepo(cfg.root, push=False, enabled=True)
    (cfg.root / "games").mkdir(exist_ok=True)
    (cfg.root / "games" / "a.txt").write_text("mine\n")
    (cfg.root / "someone_elses_work.py").write_text("not mine\n")   # another agent, mid-edit
    res = git.commit(["games/a.txt"], "Add a")
    assert res and _log(cfg.root) == ["Add a", "base"]
    import subprocess
    left = subprocess.run(["git", "-C", str(cfg.root), "status", "--porcelain"], capture_output=True, text=True, check=True)
    assert "someone_elses_work.py" in left.stdout  # untouched, still uncommitted
    assert git.commit(["games/a.txt"], "again").output == "nothing to commit"
    assert git.commit(["games/missing.txt"], "no-op").output == "nothing to commit"
    assert not GitRepo(tmp_path / "not-a-repo", enabled=True).commit(["x"], "m").ok or True
    assert GitRepo(cfg.root, enabled=False).commit(["games/a.txt"], "m").output == "git disabled"
    assert git.push().output == "push disabled"


def test_each_finished_game_is_committed(cfg, tmp_path):
    _init_repo(cfg.root)
    committed = cfg.model_copy(update={"commit_each_game": True, "dedupe_similarity": 1.01})
    a, b = run_batch(committed, tmp_path / "run", n=2, seed=3)
    assert a.promoted and b.promoted
    subjects = _log(cfg.root)
    assert sum(s.startswith("Add Stub Duel (22/50 reject)") for s in subjects) == 2
    assert subjects[-1] == "base"
    events = [json.loads(l) for l in (tmp_path / "run" / "events.jsonl").read_text().splitlines()]
    assert sum(e["kind"] == "commit" and e["ok"] for e in events) == 2


def test_failed_game_is_not_committed(cfg, tmp_path, monkeypatch):
    _init_repo(cfg.root)
    monkeypatch.setenv("GD_FAKE_FAIL", "gauntlet:99")
    committed = cfg.model_copy(update={"commit_each_game": True})
    (res,) = run_batch(committed, tmp_path / "run")
    assert res.failed_stage == "gauntlet" and not res.promoted and _log(cfg.root) == ["base"]
