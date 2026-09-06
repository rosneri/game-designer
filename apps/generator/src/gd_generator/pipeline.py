"""Batch orchestration.

Default mode is **rolling**: a worker pool runs each idea end to end (idea -> code -> validate -> tests ->
gauntlet -> judge -> promote) and publishes its lessons the moment it finishes, so ideas that start later see
what earlier games taught. ``phased`` keeps the older two-phase behaviour (all ideas first, then all builds).

Every run works against a frozen snapshot of prompts and catalog, and every idea builds in its own workspace;
the only shared mutable state is the registry (slugs/dedupe) and the lesson board.
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import lessons as lessons_mod
from .backends import LLMClient
from .config import GeneratorConfig
from .events import EventLog
from .git import GitRepo
from .harness import Harness
from .models import IdeaBrief, IdeaResult, RunManifest
from .prompts import Prompts, choose_direction
from .registry import Duplicate, LessonBoard, Registry, jaccard
from .steps import BUILD_STEPS, IdeaContext, StepFailed, infra_flag, step_idea, step_promote
from .workspace import Snapshot, Workspace, git_sha


class Batch:
    def __init__(self, cfg: GeneratorConfig, run_dir: Path, n: int, seed: int, resume: bool = False):
        # absolute: the coding agent works from its own workspace, so every path we hand it must resolve there
        self.cfg, self.run_dir, self.n, self.seed, self.resume = cfg, Path(run_dir).resolve(), n, seed, resume
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.snap = Snapshot.take(cfg, self.run_dir)
        self.harness = Harness(cfg.harness_file)
        self.events = EventLog(self.run_dir / "events.jsonl")
        self.manifest = self._manifest()
        self.board = LessonBoard(self.snap.lesson_bullets(), live=cfg.live_lessons)
        self.registry = Registry(self.snap.catalog(), self._taken_slugs(), cfg.dedupe_similarity, self.n)
        self.prompts = Prompts(self.snap, cfg.root, cfg.reference_game, lessons=self.board.text,
                               harness=self.harness.text_for, peers=self.registry.briefs)
        self.llm = LLMClient(cfg)
        self.git = GitRepo(cfg.root, cfg.git_remote, cfg.git_branch, push=cfg.push_commits,
                           enabled=cfg.commit_each_game)
        self.results: dict[int, IdeaResult] = {}
        self._used_directions: set[str] = set()

    # ---------------------------------------------------------------- setup
    def _taken_slugs(self) -> set[str]:
        live = {p.name for p in self.cfg.catalog_dir.glob("*") if p.is_dir()} if self.cfg.catalog_dir.exists() else set()
        return self.snap.catalog_slugs() | live

    def _manifest(self) -> RunManifest:
        p = self.run_dir / "manifest.json"
        if p.exists() and self.resume:
            m = RunManifest.model_validate_json(p.read_text())
            self.n, self.seed = m.n, m.seed
            return m
        hashes = self.snap.prompt_hashes()
        m = RunManifest(run_id=self.run_dir.name, created=datetime.now(UTC).isoformat(timespec="seconds"), n=self.n,
                        seed=self.seed, config=self.cfg.manifest_dict(), prompt_hashes=hashes,
                        lessons_hash=hashes.get("LESSONS.md", ""), catalog=sorted(self.snap.catalog_slugs()),
                        git_sha=git_sha(self.cfg.root), harness_entries=len(self.harness.load().entries))
        p.write_text(m.model_dump_json(indent=1))
        return m

    def idea_dir(self, idx: int) -> Path:
        d = self.run_dir / f"idea{idx:02d}"
        d.mkdir(exist_ok=True)
        return d

    def _load_result(self, idx: int) -> IdeaResult | None:
        p = self.idea_dir(idx) / "result.json"
        if self.resume and p.exists():
            try:
                return IdeaResult.model_validate_json(p.read_text())
            except ValueError:
                return None
        return None

    def ctx(self, idx: int) -> IdeaContext:
        idea_dir = self.idea_dir(idx)
        loaded = self._load_result(idx)
        res = loaded or IdeaResult(idx=idx, seed=self.seed * 1000 + idx)
        # On resume a finished idea (judged, or a real design failure) is final. Infra failures, dedupe culls
        # and crashes are re-run from their last good step.
        final = bool(loaded) and (loaded.passed and loaded.step("judge") is not None
                                  or (loaded.failed_stage not in (None, "dedupe", "crash") and not loaded.infra))
        if not final:
            res.failed_stage, res.error, res.infra = None, "", False
        return IdeaContext(cfg=self.cfg, llm=self.llm, prompts=self.prompts, ws=Workspace(idea_dir).create(self.snap),
                           result=res, idea_dir=idea_dir, events=self.events, resume=self.resume, final=final)

    def save(self, ctx: IdeaContext) -> IdeaResult:
        (ctx.idea_dir / "result.json").write_text(json.dumps(ctx.result.summary_dict(), indent=2, default=str))
        self.results[ctx.result.idx] = ctx.result
        return ctx.result

    def direction_for(self, ctx: IdeaContext) -> str:
        d = choose_direction(ctx.result.seed, self.registry.catalog_tags() | {t for b in self.registry.briefs() for t in b.tags()},
                             self._used_directions)
        self._used_directions.add(d)
        return d

    # ---------------------------------------------------------------- one idea
    def idea_phase(self, ctx: IdeaContext) -> bool:
        """Generate + register one brief. Returns True when the idea may be built."""
        idx = ctx.result.idx
        if ctx.final:
            if ctx.result.brief:
                self.registry.reserve(idx, ctx.result.brief)
            else:
                self.registry.skip(idx)
            return False
        try:
            brief = step_idea(ctx, self.direction_for(ctx), self.registry.briefs())
        except StepFailed as e:
            self.registry.skip(idx)
            ctx.result.failed_stage, ctx.result.error, ctx.result.infra = e.stage, e.error[-4000:], infra_flag(e.error)
            return False
        except Exception as e:  # noqa: BLE001 - never kill the pool
            self.registry.skip(idx)
            ctx.result.failed_stage, ctx.result.error = "crash", f"{type(e).__name__}: {e}"
            return False
        if ctx.resume and ctx.result.slug:  # already registered in an earlier attempt
            brief.slug = ctx.result.slug
            self.registry.reserve(idx, brief)
        else:
            try:
                self.registry.register(idx, brief)
            except Duplicate as d:
                ctx.result.slug = brief.slug
                ctx.result.failed_stage, ctx.result.error = "dedupe", str(d)
                self.events.emit("dedupe", idx=idx, slug=brief.slug, against=d.against, similarity=round(d.similarity, 2))
                return False
        ctx.result.slug = brief.slug
        (ctx.idea_dir / "brief.json").write_text(brief.model_dump_json(indent=1))
        return True

    def build_phase(self, ctx: IdeaContext) -> None:
        try:
            ctx.idea_text = ctx.idea_text or (ctx.idea_dir / "idea.md").read_text()
            for _, fn in BUILD_STEPS:
                fn(ctx)
            j = ctx.result.judge
            if j and self.cfg.min_judge_total and j.total < self.cfg.min_judge_total:
                # it survived the gauntlet but is not worth keeping: the catalog is what later ideas are
                # told to beat, so letting weak games in lowers the bar for everything after them.
                ctx.result.rejected = True
                self.events.emit("rejected", idx=ctx.result.idx, slug=ctx.result.slug, total=j.total,
                                 threshold=self.cfg.min_judge_total)
            elif self.cfg.promote:
                step_promote(ctx)
        except StepFailed as e:
            ctx.result.failed_stage, ctx.result.error, ctx.result.infra = e.stage, e.error[-4000:], infra_flag(e.error)
        except Exception as e:  # noqa: BLE001
            ctx.result.failed_stage, ctx.result.error = "crash", f"{type(e).__name__}: {e}"

    def finish(self, ctx: IdeaContext) -> IdeaResult:
        """Publish one idea's lessons immediately, so later ideas in this run can use them."""
        r = ctx.result
        records = lessons_mod.records_from(r, self.manifest.run_id)
        if not ctx.final:
            lessons_mod.append(self.run_dir, records)
            self.board.add(lessons_mod.bullets(records, aggregate=False))
        self.events.emit("idea_done", idx=r.idx, slug=r.slug, failed_stage=r.failed_stage, infra=r.infra,
                         fixes=r.fix_rounds, judge=r.judge.total if r.judge else None, promoted=r.promoted)
        self.save(ctx)
        self.commit_game(r)
        return r

    def commit_game(self, r: IdeaResult) -> None:
        """One commit per finished game. Only the game's own files are staged."""
        if not (self.cfg.commit_each_game and r.promoted and r.slug):
            return
        rel = f"games/{r.slug}"
        judge = f"{r.judge.total}/50 {r.judge.verdict}" if r.judge else "unjudged"
        mech = ", ".join((r.brief.mechanics if r.brief else [])[:4])
        msg = (f"Add {r.name or r.slug} ({judge})\n\n{mech}\n\n"
               f"Generated by run {self.manifest.run_id}, idea {r.idx}, seed {r.seed}; "
               f"{r.fix_rounds} fix round(s).")
        res = self.git.commit_and_push([rel], msg)
        self.events.emit("commit", idx=r.idx, slug=r.slug, ok=res.ok, detail=res.output[-200:])

    def one(self, ctx: IdeaContext) -> IdeaResult:
        t0 = time.monotonic()
        if self.idea_phase(ctx):
            self.build_phase(ctx)
            ctx.result.timings["total"] = round(ctx.result.timings.get("total", 0.0) + time.monotonic() - t0, 1)
        return self.finish(ctx)

    # ---------------------------------------------------------------- run
    def run(self, on_result=None) -> list[IdeaResult]:
        self.events.emit("run_start", run=self.manifest.run_id, n=self.n, seed=self.seed, resume=self.resume,
                         mode=self.cfg.mode, parallel=self.cfg.parallel, live_lessons=self.cfg.live_lessons)
        contexts = [self.ctx(i) for i in range(self.n)]
        workers = max(1, self.cfg.parallel)
        if self.cfg.mode == "phased":
            with ThreadPoolExecutor(max_workers=workers) as ex:
                buildable = [c for c, ok in zip(contexts, ex.map(self.idea_phase, contexts)) if ok]
            for c in contexts:
                if c not in buildable and (r := self.finish(c)) and on_result:
                    on_result(r)
            with ThreadPoolExecutor(max_workers=workers) as ex:
                for c in buildable:
                    ex.submit(lambda c=c: (self.build_phase(c), self.finish(c)))
            for c in buildable:
                if on_result:
                    on_result(self.results[c.result.idx])
        else:
            with ThreadPoolExecutor(max_workers=workers) as ex:
                for r in ex.map(self.one, contexts):
                    if on_result:
                        on_result(r)
        rows = [self.results[i].summary_dict() for i in sorted(self.results)]
        (self.run_dir / "results.json").write_text(json.dumps(rows, indent=2, default=str))
        self.events.emit("run_end", run=self.manifest.run_id, passed=sum(r.passed for r in self.results.values()))
        return [self.results[i] for i in sorted(self.results)]


# run-level directories that never hold an idea result
NON_IDEA_DIRS = {"snapshot", "improve"}


def load_results(run_dir: Path) -> list[dict[str, Any]]:
    """Every idea result of a run, oldest layout included (dirs used to be named after the slug)."""
    out = []
    for p in sorted(Path(run_dir).glob("*/result.json")):
        if p.parent.name in NON_IDEA_DIRS:
            continue
        try:
            out.append(json.loads(p.read_text()))
        except json.JSONDecodeError:
            continue
    return sorted(out, key=lambda r: r.get("idx", 0))


__all__ = ["Batch", "IdeaBrief", "jaccard", "load_results"]
