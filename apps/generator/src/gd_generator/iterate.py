"""Improving games that already exist.

Generation produces first drafts; every judge verdict so far has been "iterate". This runs that second pass:
take a finished game, show the model what actually happens at the table, ask for one substantial design change,
and keep it only if the judge scores it higher than the version it replaces.

Each round happens in an isolated workspace, so a failed attempt never touches the catalog. The best version
wins at the end, which may be the one we started with.
"""
from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .backends import LLMClient
from .config import GeneratorConfig
from .events import EventLog
from .harness import Harness
from .models import IdeaBrief, IdeaResult, JudgeVerdict
from .pipeline import load_results
from .prompts import Prompts
from .steps import IdeaContext, StepFailed, game_traces, repair, step_judge
from .workspace import GAME_FILES, Snapshot, Workspace


def recorded_scores(root: Path) -> dict[str, dict[str, Any]]:
    """Latest recorded judge verdict per slug, from every run on disk."""
    out: dict[str, dict[str, Any]] = {}
    for run in sorted((root / "runs").glob("*")):
        if not run.is_dir():
            continue
        for r in load_results(run):
            slug, judge = r.get("slug"), r.get("judge")
            if slug and judge:
                out[slug] = {"total": judge.get("total"), "verdict": judge.get("verdict"),
                             "notes": judge.get("notes", []), "run": run.name, "judge": judge}
    return out


def best_games(cfg: GeneratorConfig, top: int = 3, slugs: list[str] | None = None) -> list[str]:
    """The highest-scoring games still in the catalog, best first."""
    have = {p.name for p in cfg.catalog_dir.glob("*") if (p / "rules.py").exists()}
    if slugs:
        missing = [s for s in slugs if s not in have]
        if missing:
            raise ValueError(f"not in the catalog: {', '.join(missing)}")
        return slugs
    scored = [(v["total"], s) for s, v in recorded_scores(cfg.root).items()
              if s in have and s != cfg.reference_game and isinstance(v["total"], int)]
    return [s for _, s in sorted(scored, reverse=True)[:top]]


@dataclass
class Round:
    n: int
    total: int | None = None
    kept: bool = False
    error: str = ""
    changed: list[str] = field(default_factory=list)
    seconds: float = 0.0


@dataclass
class IterationResult:
    slug: str
    baseline: int | None = None
    best: int | None = None
    rounds: list[Round] = field(default_factory=list)
    promoted: bool = False
    error: str = ""

    @property
    def improved(self) -> bool:
        return (self.best is not None and self.baseline is not None and self.best > self.baseline)

    def as_dict(self) -> dict[str, Any]:
        return {"slug": self.slug, "baseline": self.baseline, "best": self.best, "improved": self.improved,
                "promoted": self.promoted, "error": self.error,
                "rounds": [{"n": r.n, "total": r.total, "kept": r.kept, "changed": r.changed,
                            "error": r.error[-300:], "seconds": round(r.seconds, 1)} for r in self.rounds]}


def _brief_from_spec(game_dir: Path) -> IdeaBrief:
    try:
        d = json.loads((game_dir / "spec.json").read_text())
    except (OSError, json.JSONDecodeError):
        return IdeaBrief(slug=game_dir.name)
    return IdeaBrief(name=d.get("name", ""), slug=d.get("slug", game_dir.name),
                     players=(int(d.get("players_min", 2)), int(d.get("players_max", 4))),
                     mechanics=[str(m).lower() for m in d.get("mechanics", [])])


def _snapshot_game(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for f in GAME_FILES:
        if (src / f).exists():
            shutil.copy2(src / f, dst / f)


def _judge_now(ctx: IdeaContext, tag: str) -> JudgeVerdict | None:
    """Judge the workspace copy as it currently stands, reusing the normal judge step."""
    for stale in ("judge.json", "gauntlet.json"):
        (ctx.idea_dir / stale).unlink(missing_ok=True)
    ctx.result.judge = None
    ok, err = ctx.gauntlet()
    if not ok:
        ctx.result.error = err
        return None
    try:
        step_judge(ctx)
    except StepFailed:
        return None
    j = ctx.result.judge
    if j:
        (ctx.idea_dir / f"judge-{tag}.json").write_text(j.model_dump_json(indent=1))
    return j


def iterate_game(cfg: GeneratorConfig, slug: str, run_dir: Path, rounds: int, llm: LLMClient,
                 prompts: Prompts, snap: Snapshot, events: EventLog) -> IterationResult:
    res = IterationResult(slug=slug)
    idea_dir = run_dir / slug
    idea_dir.mkdir(parents=True, exist_ok=True)
    ws = Workspace(idea_dir).create(snap)
    game_dir = ws.game_dir(slug)
    _snapshot_game(cfg.catalog_dir / slug, game_dir)

    result = IdeaResult(idx=0, seed=0, slug=slug, name=slug, brief=_brief_from_spec(game_dir))
    ctx = IdeaContext(cfg=cfg, llm=llm, prompts=prompts, ws=ws, result=result, idea_dir=idea_dir, events=events)

    base = _judge_now(ctx, "baseline")
    if base is None:
        res.error = f"the game as it stands does not pass: {ctx.result.error[-300:]}"
        events.emit("iterate_baseline_failed", slug=slug, error=res.error)
        return res
    res.baseline = res.best = base.total
    best_dir = idea_dir / "best"
    _snapshot_game(game_dir, best_dir)
    best_metrics = ctx.result.gauntlet
    events.emit("iterate_baseline", slug=slug, total=base.total)

    verdict = base
    for n in range(1, rounds + 1):
        t0 = time.monotonic()
        rnd = Round(n=n)
        res.rounds.append(rnd)
        prompt = prompts.iterate(slug, game_dir, verdict,
                                 metrics=json.dumps(ctx.result.gauntlet or {}, indent=1, default=str)[:8000],
                                 trace=game_traces(ctx))
        r = ctx.ask("iterate", prompt, f"iterate{n}", cwd=ws.root, system_append=prompts.contract())
        rnd.changed = ctx.write_answer(r.text) if r.text else []
        if not rnd.changed:
            rnd.error = r.stderr[-300:] or "no files returned"
            rnd.seconds = time.monotonic() - t0
            _snapshot_game(best_dir, game_dir)   # nothing applied; carry on from the best version
            events.emit("iterate_round", slug=slug, round=n, kept=False, error=rnd.error)
            continue

        ok, err = ctx.validate()
        if ok:
            ok, err = ctx.gauntlet_and_tests()
            if not ok:
                ok = repair(ctx, "iterate", err, ctx.gauntlet_and_tests, cfg.max_fix_rounds,
                            extra="This is a redesign round: keep the new mechanic, make it satisfy the checks.")
        if not ok:
            rnd.error = (ctx.result.error or err)[-600:]
            rnd.seconds = time.monotonic() - t0
            _snapshot_game(best_dir, game_dir)
            events.emit("iterate_round", slug=slug, round=n, kept=False, error=rnd.error[-200:])
            continue

        j = _judge_now(ctx, f"r{n}")
        rnd.total = j.total if j else None
        if j and res.best is not None and j.total > res.best:
            res.best, rnd.kept, verdict = j.total, True, j
            _snapshot_game(game_dir, best_dir)
            best_metrics = ctx.result.gauntlet
        else:
            _snapshot_game(best_dir, game_dir)   # worse or unjudgeable: go back to the best version
        rnd.seconds = time.monotonic() - t0
        events.emit("iterate_round", slug=slug, round=n, total=rnd.total, kept=rnd.kept)

    if res.improved and cfg.promote:
        if best_metrics:
            (idea_dir / "gauntlet.json").write_text(json.dumps(best_metrics, indent=2, default=str))
        _snapshot_game(best_dir, game_dir)
        ws.promote(slug, cfg.catalog_dir, extra={"gauntlet.json": idea_dir / "gauntlet.json"})
        res.promoted = True
    (idea_dir / "iteration.json").write_text(json.dumps(res.as_dict(), indent=2))
    events.emit("iterate_done", slug=slug, baseline=res.baseline, best=res.best, promoted=res.promoted)
    return res


def iterate(cfg: GeneratorConfig, run_dir: Path, slugs: list[str], rounds: int = 2,
            llm: LLMClient | None = None) -> list[IterationResult]:
    run_dir = Path(run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    snap = Snapshot.take(cfg, run_dir)
    harness = Harness(cfg.harness_file)
    prompts = Prompts(snap, cfg.root, cfg.reference_game, harness=harness.text_for)
    llm = llm or LLMClient(cfg)
    events = EventLog(run_dir / "events.jsonl")
    events.emit("iterate_start", games=slugs, rounds=rounds)
    out = [iterate_game(cfg, s, run_dir, rounds, llm, prompts, snap, events) for s in slugs]
    (run_dir / "iterations.json").write_text(json.dumps([r.as_dict() for r in out], indent=2))
    return out


__all__ = ["IterationResult", "Round", "best_games", "iterate", "iterate_game", "recorded_scores"]
