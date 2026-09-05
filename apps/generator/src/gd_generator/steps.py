"""Pipeline steps as small functions over a shared ``IdeaContext``.

Every step writes its prompt/output artifacts under the idea dir and a ``steps/<name>.json`` record, so a
run can be resumed: a step whose record says ``ok`` and whose artifacts still exist is skipped.
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .backends import LLMClient, LLMResult, is_infra_error
from .blocks import parse_file_blocks, parse_json_block, write_blocks
from .config import GeneratorConfig
from .events import EventLog
from .models import FixRecord, IdeaBrief, IdeaResult, JudgeVerdict, StepRecord
from .prompts import Prompts, parse_idea
from .workspace import Workspace


class StepFailed(Exception):
    def __init__(self, stage: str, error: str):
        super().__init__(f"{stage}: {error[-200:]}")
        self.stage, self.error = stage, error


ANSI = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def strip_ansi(text: str) -> str:
    """Tool output reaches prompts and LESSONS.md; colour escapes there are pure noise."""
    return ANSI.sub("", text)


@dataclass
class ToolResult:
    ok: bool
    output: str
    seconds: float


def run_tool(argv: list[str], cwd: Path, timeout: int, env: dict[str, str] | None = None) -> ToolResult:
    t0 = time.monotonic()
    try:
        cp = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False, timeout=timeout, env=env)
        out = strip_ansi((cp.stdout + ("\n" + cp.stderr if cp.stderr else "")).strip())
        return ToolResult(cp.returncode == 0, out, time.monotonic() - t0)
    except subprocess.TimeoutExpired:
        return ToolResult(False, f"TIMEOUT after {timeout}s: {' '.join(map(str, argv))}", time.monotonic() - t0)
    except FileNotFoundError as e:
        return ToolResult(False, f"tool not found: {e}", time.monotonic() - t0)


def gauntlet_summary(data: dict | None, output: str) -> str:
    """Compact text of failing stages from a gauntlet JSON (schema tolerant)."""
    if not data:
        return output[-6000:]
    stages = data.get("stages", data)
    lines = []
    items = stages.items() if isinstance(stages, dict) else enumerate(stages)
    for k, v in items:
        if isinstance(v, dict) and v.get("passed", v.get("ok", True)) is False:
            metrics = v.get("metrics", {k2: v2 for k2, v2 in v.items() if k2 not in ("passed", "ok", "reason", "name")})
            lines.append(f"{v.get('name', k)}: FAIL reason={v.get('reason', v.get('error', ''))} metrics={json.dumps(metrics, default=str)}")
    return "\n".join(lines) or output[-6000:]


@dataclass
class IdeaContext:
    cfg: GeneratorConfig
    llm: LLMClient
    prompts: Prompts
    ws: Workspace
    result: IdeaResult
    idea_dir: Path
    events: EventLog
    idea_text: str = ""
    resume: bool = False
    final: bool = False  # loaded from a previous run and not to be touched
    _t0: dict[str, float] = field(default_factory=dict)

    # ---- artifacts / records
    @property
    def slug(self) -> str:
        assert self.result.slug
        return self.result.slug

    @property
    def game_dir(self) -> Path:
        return self.ws.game_dir(self.slug)

    def save(self, name: str, text: str) -> str:
        (self.idea_dir / name).write_text(text)
        return name

    def record(self, rec: StepRecord) -> StepRecord:
        d = self.idea_dir / "steps"
        d.mkdir(exist_ok=True)
        (d / f"{rec.name}.json").write_text(rec.model_dump_json(indent=1))
        self.result.steps = [s for s in self.result.steps if s.name != rec.name] + [rec]
        self.result.timings[rec.name] = round(rec.seconds, 1)
        self.events.emit("step", idx=self.result.idx, slug=self.result.slug, step=rec.name, status=rec.status,
                         seconds=round(rec.seconds, 1), retries=rec.retries)
        return rec

    def done(self, name: str, *artifacts: Path) -> bool:
        """Resume check: previous record ok and required artifacts still exist."""
        if not self.resume:
            return False
        p = self.idea_dir / "steps" / f"{name}.json"
        if not p.exists():
            return False
        rec = StepRecord.model_validate_json(p.read_text())
        ok = rec.status == "ok" and all(a.exists() for a in artifacts)
        if ok:
            self.result.steps = [s for s in self.result.steps if s.name != name] + [rec]
            self.result.timings[name] = round(rec.seconds, 1)
            self.events.emit("step", idx=self.result.idx, slug=self.result.slug, step=name, status="skipped")
        return ok

    def ask(self, step: str, prompt: str, name: str, *, cwd: Path | None = None, system_append: str | None = None) -> LLMResult:
        self.save(f"{name}.prompt.md", prompt)
        r = self.llm.call(step, prompt, cwd=str(cwd) if cwd else None, system_append=system_append)
        self.save(f"{name}.out.txt", r.text + (f"\n\n--- stderr ---\n{r.stderr}" if r.stderr else ""))
        return r

    def rec_from(self, name: str, r: LLMResult, ok: bool, error: str = "", **artifacts: str) -> StepRecord:
        status = "ok" if ok else ("infra" if r.infra else "failed")
        return self.record(StepRecord(name=name, status=status, backend=r.backend, model=r.model, seconds=r.seconds,
                                      retries=r.retries, error=error[-2000:], artifacts=artifacts))

    def write_answer(self, text: str) -> list[str]:
        written = write_blocks(parse_file_blocks(text), self.ws.root, f"games/{self.slug}/")
        return [p.name for p in written]

    def fail(self, stage: str, error: str) -> None:
        raise StepFailed(stage, error)

    # ---- tools (all run in the repo env, on the workspace game dir)
    def tool(self, argv: list[str]) -> ToolResult:
        return run_tool(argv, self.cfg.root, self.cfg.tool_timeout, self.ws.env())

    def validate(self) -> tuple[bool, str]:
        t = self.tool([*self.cfg.runner_cmd, "validate", str(self.game_dir)])
        return t.ok, t.output

    def pytest(self) -> tuple[bool, str]:
        t = self.tool([*self.cfg.pytest_cmd, str(self.game_dir), "-q", "-x", "--no-header", "-p", "no:cacheprovider"])
        return t.ok, t.output

    def gauntlet(self) -> tuple[bool, str]:
        jp = self.idea_dir / "gauntlet.json"
        t = self.tool([*self.cfg.runner_cmd, "gauntlet", str(self.game_dir), "--json", str(jp)])
        data = None
        if jp.exists():
            try:
                data = json.loads(jp.read_text())
            except json.JSONDecodeError:
                data = None
        self.result.gauntlet = data
        ok = t.ok and (data is None or data.get("passed", True) is not False)
        return ok, gauntlet_summary(data, t.output)


# ---------------------------------------------------------------- steps
def step_idea(ctx: IdeaContext, direction: str, batch_briefs: list[IdeaBrief]) -> IdeaBrief:
    brief_p = ctx.idea_dir / "brief.json"
    if ctx.done("idea", brief_p, ctx.idea_dir / "idea.md"):
        brief = IdeaBrief.model_validate_json(brief_p.read_text())
        ctx.result.brief, ctx.result.slug, ctx.result.name = brief, brief.slug, brief.name
        ctx.idea_text = (ctx.idea_dir / "idea.md").read_text()
        return brief
    r = ctx.ask("idea", ctx.prompts.idea(direction, batch_briefs), "idea")
    if not r.ok:
        ctx.rec_from("idea", r, False, r.stderr or "empty answer")
        ctx.fail("idea", r.stderr or "empty answer")
    brief = parse_idea(r.text, direction)
    ctx.idea_text = r.text
    ctx.save("idea.md", r.text)
    ctx.result.brief, ctx.result.name = brief, brief.name
    ctx.rec_from("idea", r, True, prompt="idea.prompt.md", out="idea.out.txt", idea="idea.md")
    return brief  # slug is finalised by the batch (collision-free) and brief.json written then


def step_code(ctx: IdeaContext) -> None:
    gdir = ctx.game_dir
    if ctx.done("code", gdir / "rules.py", gdir / "spec.json"):
        return
    gdir.mkdir(parents=True, exist_ok=True)
    r = ctx.ask("code", ctx.prompts.code(ctx.idea_text, ctx.slug, gdir), "code", cwd=ctx.ws.root,
                system_append=ctx.prompts.contract())
    written = ctx.write_answer(r.text) if r.text else []
    ok = ctx.ws.files_present(ctx.slug)
    err = "" if ok else f"missing files; written={written}; stderr={r.stderr[-500:]}"
    ctx.rec_from("code", r, ok, err, prompt="code.prompt.md", out="code.out.txt")
    if not ok:
        ctx.fail("code", err)


def repair(ctx: IdeaContext, stage: str, error: str, check: Callable[[], tuple[bool, str]], budget: int,
           extra: str = "") -> bool:
    """Ask the fix model until ``check()`` passes or the budget is spent. Records every attempt."""
    for _ in range(budget):
        n = len(ctx.result.fixes) + 1
        r = ctx.ask("fix", ctx.prompts.fix(ctx.slug, ctx.game_dir, stage, error, extra), f"fix{n}", cwd=ctx.ws.root,
                    system_append=ctx.prompts.contract())
        changed = ctx.write_answer(r.text) if r.text else []
        ok, error2 = check()
        ctx.result.fixes.append(FixRecord(stage=stage, attempt=n, error=error[-600:], fixed=ok, changed=changed))
        ctx.rec_from(f"fix{n}", r, ok, "" if ok else error2, prompt=f"fix{n}.prompt.md", out=f"fix{n}.out.txt")
        ctx.events.emit("fix", idx=ctx.result.idx, slug=ctx.slug, stage=stage, attempt=n, fixed=ok)
        if ok:
            return True
        error = error2
    ctx.result.error = error[-4000:]
    return False


def step_validate(ctx: IdeaContext) -> None:
    if ctx.done("validate"):
        return
    t0 = time.monotonic()
    ok, err = ctx.validate()
    if not ok and not repair(ctx, "validate", err, ctx.validate, ctx.cfg.max_fix_rounds):
        ctx.record(StepRecord(name="validate", status="failed", seconds=time.monotonic() - t0, error=ctx.result.error))
        ctx.fail("validate", ctx.result.error or err)
    ctx.record(StepRecord(name="validate", status="ok", seconds=time.monotonic() - t0))


def step_tests(ctx: IdeaContext) -> None:
    gdir = ctx.game_dir
    if ctx.done("tests", gdir / "test_rules.py"):
        return
    r = ctx.ask("tests", ctx.prompts.tests(ctx.slug, ctx.result.brief.players, gdir), "tests")
    if r.text:
        ctx.write_answer(r.text)
    if not (gdir / "test_rules.py").exists():
        err = f"no test file returned; stderr={r.stderr[-500:]}"
        ctx.rec_from("tests", r, False, err, prompt="tests.prompt.md", out="tests.out.txt")
        ctx.fail("tests", err)
    ok, err = ctx.pytest()
    if not ok:
        ok = repair(ctx, "tests", err, ctx.pytest, ctx.cfg.tests_fix_rounds,
                    extra="The tests were auto-generated and MAY be wrong; fix rules.py or test_rules.py, whichever is at fault.")
    ctx.rec_from("tests", r, ok, "" if ok else (ctx.result.error or err), prompt="tests.prompt.md", out="tests.out.txt")
    if not ok:
        ctx.fail("tests", ctx.result.error or err)


def step_gauntlet(ctx: IdeaContext) -> None:
    jp = ctx.idea_dir / "gauntlet.json"
    if ctx.done("gauntlet", jp):
        ctx.result.gauntlet = json.loads(jp.read_text())
        return
    t0 = time.monotonic()
    ok, err = ctx.gauntlet()
    if not ok and not repair(ctx, "gauntlet", err, ctx.gauntlet, ctx.cfg.max_fix_rounds,
                             extra="Failing gauntlet stages with metrics are listed above. Adjust rules to fix balance/length/decision density while keeping the game's identity."):
        ctx.record(StepRecord(name="gauntlet", status="failed", seconds=time.monotonic() - t0, error=ctx.result.error, artifacts={"json": "gauntlet.json"}))
        ctx.fail("gauntlet", ctx.result.error or err)
    ctx.record(StepRecord(name="gauntlet", status="ok", seconds=time.monotonic() - t0, artifacts={"json": "gauntlet.json"}))


def step_judge(ctx: IdeaContext) -> None:
    jp = ctx.idea_dir / "judge.json"
    if ctx.done("judge", jp):
        ctx.result.judge = JudgeVerdict.model_validate_json(jp.read_text())
        return
    metrics = json.dumps(ctx.result.gauntlet or {}, indent=1, default=str)[:8000]
    r = ctx.ask("judge", ctx.prompts.judge(ctx.idea_text, ctx.game_dir, metrics), "judge")
    j = parse_json_block(r.text) if r.text else None
    if j is None:
        ctx.rec_from("judge", r, False, "no JSON verdict", prompt="judge.prompt.md", out="judge.out.txt")
        ctx.fail("judge", "no JSON verdict")
    try:
        verdict = JudgeVerdict.model_validate({k: v for k, v in j.items() if k in JudgeVerdict.model_fields})
    except ValueError as e:  # pydantic ValidationError
        ctx.rec_from("judge", r, False, f"bad verdict: {e}", prompt="judge.prompt.md", out="judge.out.txt")
        ctx.fail("judge", f"bad verdict: {e}")
    ctx.result.judge = verdict
    jp.write_text(verdict.model_dump_json(indent=1))
    ctx.rec_from("judge", r, True, prompt="judge.prompt.md", out="judge.out.txt", verdict="judge.json")


def step_promote(ctx: IdeaContext) -> Path:
    dst = ctx.ws.promote(ctx.slug, ctx.cfg.catalog_dir, extra={"gauntlet.json": ctx.idea_dir / "gauntlet.json"})
    ctx.result.promoted = True
    ctx.record(StepRecord(name="promote", status="ok", artifacts={"catalog": str(dst)}))
    return dst


def infra_flag(error: str) -> bool:
    return is_infra_error(error)


BUILD_STEPS: list[tuple[str, Callable[[IdeaContext], Any]]] = [
    ("code", step_code), ("validate", step_validate), ("tests", step_tests), ("gauntlet", step_gauntlet), ("judge", step_judge),
]
