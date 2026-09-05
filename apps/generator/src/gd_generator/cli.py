"""``generator`` CLI: run | resume | flywheel | refine | improve | learn | rollback | harness | report | dry-run."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import lessons
from .config import GeneratorConfig
from .harness import Harness
from .improve import improve
from .models import IdeaResult
from .pipeline import Batch
from .prompts import Prompts, choose_direction
from .refine import refine
from .report import write_report
from .workspace import Snapshot


def _cfg(args) -> GeneratorConfig:
    over = {k: getattr(args, k, None) for k in ("parallel", "mode", "max_fix")}
    over["max_fix_rounds"] = over.pop("max_fix")
    if getattr(args, "no_promote", False):
        over["promote"] = False
    if getattr(args, "no_live_lessons", False):
        over["live_lessons"] = False
    return GeneratorConfig.load(args.root, getattr(args, "config", None), **over)


def _progress(r: IdeaResult) -> None:
    st = r.failed_stage or "passed"
    if r.infra:
        st += " (infra)"
    print(f"[{r.idx:02d}] {r.slug}: {st} fixes={r.fix_rounds} judge={r.judge.total if r.judge else None}", file=sys.stderr)


def _new_run_dir(cfg: GeneratorConfig, given: str | None = None) -> Path:
    return Path(given) if given else cfg.runs_dir / time.strftime("%Y%m%d-%H%M%S")


def _batch(cfg: GeneratorConfig, run_dir: Path, n: int, seed: int, resume: bool = False) -> list[IdeaResult]:
    print(f"run dir: {run_dir}", file=sys.stderr)
    results = Batch(cfg, run_dir, n, seed, resume=resume).run(on_result=_progress)
    print(write_report(run_dir), file=sys.stderr)
    return results


def cmd_run(args) -> int:
    cfg = _cfg(args)
    results = _batch(cfg, _new_run_dir(cfg, args.run_dir), args.n, args.seed)
    return 0 if any(r.passed for r in results) else 1


def cmd_resume(args) -> int:
    cfg = _cfg(args)
    results = _batch(cfg, Path(args.run_dir), 0, 0, resume=True)
    return 0 if any(r.passed for r in results) else 1


def cmd_refine(args) -> int:
    cfg = _cfg(args)
    ev, raw = refine(cfg, Path(args.run_dir), instructions=args.instructions or "")
    if ev is None:
        print(f"no ledger edits: {raw[:400]}", file=sys.stderr)
        return 1
    for e in ev.edits:
        print(f"{e.op:6} {e.id} [{e.kind}] {e.text[:100]}")
    print(f"event {ev.event_id} (undo with: generator rollback {ev.event_id})", file=sys.stderr)
    return 0


def cmd_improve(args) -> int:
    cfg = _cfg(args)
    res = improve(cfg, Path(args.run_dir), instructions=args.instructions or "", dry_run=args.dry_run)
    if args.dry_run:
        print(res.answer)
        return 0
    for g in res.gates:
        print(f"gate {'PASS' if g.ok else 'FAIL'} ({g.seconds:.0f}s): {' '.join(g.argv)}", file=sys.stderr)
    verb = "applied" if res.applied else ("reverted" if res.reverted else "no change")
    print(f"{verb}: {', '.join(res.changed) or '-'}", file=sys.stderr)
    if res.error and not res.applied:
        print(res.error[-1500:], file=sys.stderr)
    return 0 if res.applied else 1


def cmd_learn(args) -> int:
    cfg = _cfg(args)
    n = lessons.learn(Path(args.run_dir), cfg.prompts_dir / "LESSONS.md")
    print(f"added {n} lessons to {cfg.prompts_dir / 'LESSONS.md'}")
    return 0


def cmd_flywheel(args) -> int:
    """run -> learn -> refine -> improve -> repeat. Each cycle starts from the previous cycle's harness."""
    cfg = _cfg(args)
    stop = time.monotonic() + args.max_hours * 3600 if args.max_hours else None
    for cycle in range(1, args.cycles + 1):
        run_dir = cfg.runs_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-c{cycle}"
        print(f"\n=== cycle {cycle}/{args.cycles}: generating {args.n} games ===", file=sys.stderr)
        cfg = _cfg(args)  # reload: an earlier cycle may have rewritten generator.toml or the code
        results = _batch(cfg, run_dir, args.n, args.seed + cycle, resume=False)
        passed = sum(r.passed for r in results)
        best = max((r.judge.total for r in results if r.judge), default=None)
        print(f"cycle {cycle}: {passed}/{len(results)} passed, best judge {best}", file=sys.stderr)
        lessons.learn(run_dir, cfg.prompts_dir / "LESSONS.md")
        if not args.no_refine:
            ev, _ = refine(cfg, run_dir, trigger="auto")
            print(f"refine: {len(ev.edits) if ev else 0} ledger edits", file=sys.stderr)
        if not args.no_improve:
            res = improve(cfg, run_dir)
            verb = "applied" if res.applied else ("reverted" if res.reverted else "no change")
            print(f"improve: {verb} {', '.join(res.changed[:6]) or '-'}", file=sys.stderr)
        if stop and time.monotonic() > stop:
            print(f"time budget reached after cycle {cycle}", file=sys.stderr)
            break
    return 0


def cmd_rollback(args) -> int:
    cfg = _cfg(args)
    ok = Harness(cfg.harness_file).rollback(args.event_id)
    print(f"{'rolled back' if ok else 'no such live refinement'}: {args.event_id}", file=sys.stderr)
    return 0 if ok else 1


def cmd_harness(args) -> int:
    print(Harness(_cfg(args).harness_file).summary())
    return 0


def cmd_report(args) -> int:
    print(write_report(Path(args.run_dir)))
    return 0


def cmd_dry_run(args) -> int:
    cfg = _cfg(args)
    run_dir = cfg.runs_dir / ".dry-run"
    snap = Snapshot.take(cfg, run_dir)
    harness = Harness(cfg.harness_file)
    prompts = Prompts(snap, cfg.root, cfg.reference_game, harness=harness.text_for)
    tags = {t for g in snap.catalog() for t in g.get("mechanics", [])}
    used: set[str] = set()
    for i in range(args.n):
        seed = args.seed * 1000 + i
        d = choose_direction(seed, tags, used)
        used.add(d)
        print(f"\n{'=' * 30} IDEA prompt (seed={seed}, direction={d!r}) {'=' * 30}\n")
        print(prompts.idea(d))
        print(f"\n{'=' * 30} CODE prompt {'=' * 30}\n")
        print(prompts.code("<idea.md goes here>", "example-slug", run_dir / "idea00/workspace/games/example-slug"))
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="generator", description=__doc__)
    ap.add_argument("--root", default=".", help="repo root (default: cwd)")
    ap.add_argument("--config", default=None, help="generator.toml (default: <root>/generator.toml if present)")
    ap.add_argument("--max-fix", type=int, default=None, dest="max_fix")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_batch_flags(p):
        p.add_argument("--parallel", type=int, default=None, help="concurrent ideas (default 3)")
        p.add_argument("--mode", choices=["rolling", "phased"], default=None,
                       help="rolling: each idea learns from games already finished (default); phased: all ideas first")
        p.add_argument("--no-promote", action="store_true", help="keep survivors in the run dir only")
        p.add_argument("--no-live-lessons", action="store_true", help="do not feed this run's lessons back mid-run")

    p = sub.add_parser("run", help="generate N games")
    p.add_argument("--n", type=int, default=1)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--run-dir", default=None)
    add_batch_flags(p)
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("resume", help="finish an interrupted run (re-runs infra failures and unfinished ideas)")
    p.add_argument("run_dir")
    add_batch_flags(p)
    p.set_defaults(fn=cmd_resume)

    p = sub.add_parser("flywheel", help="run -> learn -> refine -> improve, repeatedly")
    p.add_argument("--cycles", type=int, default=3)
    p.add_argument("--n", type=int, default=5, help="games per cycle")
    p.add_argument("--seed", type=int, default=100)
    p.add_argument("--max-hours", type=float, default=None, help="stop after the cycle that crosses this budget")
    p.add_argument("--no-refine", action="store_true")
    p.add_argument("--no-improve", action="store_true")
    add_batch_flags(p)
    p.set_defaults(fn=cmd_flywheel)

    p = sub.add_parser("refine", help="review a run and update the learned-rules ledger")
    p.add_argument("run_dir")
    p.add_argument("--instructions", default=None)
    p.set_defaults(fn=cmd_refine)

    p = sub.add_parser("improve", help="let the harness patch its own code, behind gates")
    p.add_argument("run_dir")
    p.add_argument("--instructions", default=None)
    p.add_argument("--dry-run", action="store_true", help="print the prompt without calling the model")
    p.set_defaults(fn=cmd_improve)

    p = sub.add_parser("learn", help="fold a finished run's lessons into prompts/LESSONS.md")
    p.add_argument("run_dir")
    p.set_defaults(fn=cmd_learn)

    p = sub.add_parser("rollback", help="undo one refinement event")
    p.add_argument("event_id")
    p.set_defaults(fn=cmd_rollback)

    p = sub.add_parser("harness", help="print the learned-rules ledger")
    p.set_defaults(fn=cmd_harness)

    p = sub.add_parser("report", help="write REPORT.md for a run dir")
    p.add_argument("run_dir")
    p.set_defaults(fn=cmd_report)

    p = sub.add_parser("dry-run", help="print prompts without calling any model")
    p.add_argument("--n", type=int, default=1)
    p.add_argument("--seed", type=int, default=1)
    p.set_defaults(fn=cmd_dry_run)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
