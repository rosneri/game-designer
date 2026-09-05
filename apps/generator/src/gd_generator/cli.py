"""``generator`` CLI: run | resume | flywheel | refine | improve | learn | rollback | harness | report | dry-run."""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

from . import lessons
from .config import GeneratorConfig
from .git import GitRepo
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
    if getattr(args, "commit", False):
        over["commit_each_game"] = True
    if getattr(args, "push", False):
        over["commit_each_game"], over["push_commits"] = True, True
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


def _git(cfg: GeneratorConfig) -> GitRepo:
    return GitRepo(cfg.root, cfg.git_remote, cfg.git_branch, push=cfg.push_commits, enabled=cfg.commit_each_game)


def cmd_refine(args) -> int:
    cfg = _cfg(args)
    run_dir = Path(args.run_dir)
    ev, raw = refine(cfg, run_dir, trigger=args.trigger, instructions=args.instructions or "")
    if ev is None:
        print(f"no ledger edits: {raw[:400]}", file=sys.stderr)
        return 1
    for e in ev.edits:
        print(f"{e.op:6} {e.id} [{e.kind}] {e.text[:100]}")
    print(f"event {ev.event_id} (undo with: generator rollback {ev.event_id})", file=sys.stderr)
    summary = "; ".join(f"{e.op} {e.id}" for e in ev.edits)
    res = _git(cfg).commit_and_push(["prompts/harness_state.json"],
                                    f"Refine ledger after {run_dir.name} ({len(ev.edits)} edits)\n\n{summary}\n\n"
                                    f"Undo with: generator rollback {ev.event_id}")
    print(f"commit: {res.output[-120:]}", file=sys.stderr)
    return 0


def cmd_improve(args) -> int:
    cfg = _cfg(args)
    run_dir = Path(args.run_dir)
    res = improve(cfg, run_dir, instructions=args.instructions or "", dry_run=args.dry_run)
    if args.dry_run:
        print(res.answer)
        return 0
    for g in res.gates:
        print(f"gate {'PASS' if g.ok else 'FAIL'} ({g.seconds:.0f}s): {' '.join(g.argv)}", file=sys.stderr)
    verb = "applied" if res.applied else ("reverted" if res.reverted else "no change")
    print(f"{verb}: {', '.join(res.changed) or '-'}", file=sys.stderr)
    if res.error and not res.applied:
        print(res.error[-1500:], file=sys.stderr)
    if res.applied and res.changed:
        why = next((l for l in res.answer.strip().splitlines() if l.strip() and not l.startswith("#")), "")[:200]
        out = _git(cfg).commit_and_push(res.changed, f"Self-improve after {run_dir.name}\n\n{why}\n\n"
                                                     f"Gates passed: {len(res.gates)}.")
        print(f"commit: {out.output[-120:]}", file=sys.stderr)
    return 0 if res.applied else 1


def cmd_learn(args) -> int:
    cfg = _cfg(args)
    run_dir = Path(args.run_dir)
    n = lessons.learn(run_dir, cfg.prompts_dir / "LESSONS.md")
    print(f"added {n} lessons to {cfg.prompts_dir / 'LESSONS.md'}")
    _git(cfg).commit_and_push(["prompts/LESSONS.md"], f"Fold {n} lessons from {run_dir.name} into LESSONS.md")
    return 0


def _phase(args, *argv: str) -> int:
    """Run one flywheel phase in a fresh interpreter.

    The improve step may rewrite the generator itself, and an already-imported module would not notice. A
    subprocess per phase means every cycle runs the code as it stands on disk right now.
    """
    cmd = [sys.executable, "-m", "gd_generator.cli", "--root", str(args.root)]
    if getattr(args, "config", None):
        cmd += ["--config", str(args.config)]
    cmd += list(argv)
    print(f"$ {' '.join(cmd[3:])}", file=sys.stderr)
    return subprocess.run(cmd, check=False).returncode


def cmd_flywheel(args) -> int:
    """run -> learn -> refine -> improve -> repeat. Each cycle starts from the previous cycle's harness.

    Cycle directories are named from ``--label``, so re-running the same command after an interruption skips
    finished cycles and resumes a half-finished one instead of starting over.
    """
    stop = time.monotonic() + args.max_hours * 3600 if args.max_hours else None
    label = args.label or time.strftime("%Y%m%d-%H%M%S")
    git_flags = ["--push"] if args.push else (["--commit"] if args.commit else [])
    batch_flags = [*git_flags, "--parallel", str(args.parallel or 3)]
    if args.mode:
        batch_flags += ["--mode", args.mode]
    if args.no_live_lessons:
        batch_flags.append("--no-live-lessons")
    print(f"flywheel {label}: {args.cycles} cycles x {args.n} games", file=sys.stderr)
    for cycle in range(1, args.cycles + 1):
        cfg = _cfg(args)  # reload: an earlier cycle may have rewritten generator.toml
        run_dir = cfg.runs_dir / f"{label}-c{cycle:02d}"
        done = run_dir / ".cycle-done"
        if done.exists():
            print(f"=== cycle {cycle}/{args.cycles}: already complete, skipping ===", file=sys.stderr)
            continue
        started = (run_dir / "manifest.json").exists()
        print(f"\n=== cycle {cycle}/{args.cycles}: {'resuming' if started else 'generating'} {args.n} games ===",
              file=sys.stderr)
        if started:
            _phase(args, "resume", str(run_dir), *batch_flags)
        else:
            _phase(args, "run", "--n", str(args.n), "--seed", str(args.seed + cycle), "--run-dir", str(run_dir),
                   *batch_flags)
        _phase(args, "learn", str(run_dir), *git_flags)
        if not args.no_refine:
            _phase(args, "refine", str(run_dir), *git_flags)
        if not args.no_improve:
            _phase(args, "improve", str(run_dir), *git_flags)
        done.parent.mkdir(parents=True, exist_ok=True)   # a phase may have failed before creating it
        done.write_text(time.strftime("%Y-%m-%dT%H:%M:%S\n"))
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

    def _add_git_flags(p):
        p.add_argument("--commit", action="store_true", help="commit what this produces")
        p.add_argument("--push", action="store_true", help="commit and push it")

    def add_batch_flags(p):
        p.add_argument("--parallel", type=int, default=None, help="concurrent ideas (default 3)")
        p.add_argument("--mode", choices=["rolling", "phased"], default=None,
                       help="rolling: each idea learns from games already finished (default); phased: all ideas first")
        p.add_argument("--no-promote", action="store_true", help="keep survivors in the run dir only")
        p.add_argument("--no-live-lessons", action="store_true", help="do not feed this run's lessons back mid-run")
        _add_git_flags(p)

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
    p.add_argument("--label", default=None,
                   help="names the cycle run dirs; reuse it to continue an interrupted flywheel")
    p.add_argument("--no-refine", action="store_true")
    p.add_argument("--no-improve", action="store_true")
    add_batch_flags(p)
    p.set_defaults(fn=cmd_flywheel)

    p = sub.add_parser("refine", help="review a run and update the learned-rules ledger")
    p.add_argument("run_dir")
    p.add_argument("--instructions", default=None)
    p.add_argument("--trigger", choices=["manual", "auto"], default="manual")
    _add_git_flags(p)
    p.set_defaults(fn=cmd_refine)

    p = sub.add_parser("improve", help="let the harness patch its own code, behind gates")
    p.add_argument("run_dir")
    p.add_argument("--instructions", default=None)
    p.add_argument("--dry-run", action="store_true", help="print the prompt without calling the model")
    _add_git_flags(p)
    p.set_defaults(fn=cmd_improve)

    p = sub.add_parser("learn", help="fold a finished run's lessons into prompts/LESSONS.md")
    p.add_argument("run_dir")
    _add_git_flags(p)
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
