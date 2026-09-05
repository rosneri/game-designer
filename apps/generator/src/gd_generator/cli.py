"""``generator`` CLI: run | report | dry-run."""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .pipeline import Config, code_prompt, idea_prompt, run_one
from .report import write_report


def _cfg(args) -> Config:
    return Config(root=Path(args.root).resolve(), max_fix_rounds=args.max_fix)


def cmd_run(args) -> int:
    cfg = _cfg(args)
    run_dir = Path(args.run_dir) if args.run_dir else cfg.root / "runs" / time.strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"run dir: {run_dir}", file=sys.stderr)
    results = []
    with ThreadPoolExecutor(max_workers=max(1, args.parallel)) as ex:
        futs = {ex.submit(run_one, run_dir, i, args.seed * 1000 + i, cfg): i for i in range(args.n)}
        for f in as_completed(futs):
            r = f.result()
            results.append(r)
            st = r.get("failed_stage") or "passed"
            print(f"[{r['idx']:02d}] {r.get('slug')}: {st} fixes={r['fix_rounds']} judge={(r.get('judge') or {}).get('total')}", file=sys.stderr)
    (run_dir / "results.json").write_text(json.dumps(sorted(results, key=lambda r: r["idx"]), indent=2, default=str))
    print(write_report(run_dir), file=sys.stderr)
    return 0 if any(not r.get("failed_stage") for r in results) else 1


def cmd_report(args) -> int:
    print(write_report(Path(args.run_dir)))
    return 0


def cmd_dry_run(args) -> int:
    cfg = _cfg(args)
    for i in range(args.n):
        seed = args.seed * 1000 + i
        print(f"\n{'=' * 30} IDEA prompt (seed={seed}, model idea) {'=' * 30}\n")
        print(idea_prompt(cfg, seed))
        print(f"\n{'=' * 30} CODE prompt (model code) {'=' * 30}\n")
        print(code_prompt(cfg, "<idea.md goes here>", "example-slug"))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="generator", description=__doc__)
    ap.add_argument("--root", default=".", help="repo root (default: cwd)")
    ap.add_argument("--max-fix", type=int, default=2)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run", help="generate N games")
    p.add_argument("--n", type=int, default=1)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--parallel", type=int, default=3)
    p.add_argument("--run-dir", default=None)
    p.set_defaults(fn=cmd_run)
    p = sub.add_parser("report", help="write REPORT.md for a run dir")
    p.add_argument("run_dir")
    p.set_defaults(fn=cmd_report)
    p = sub.add_parser("dry-run", help="print prompts without calling prime-agent")
    p.add_argument("--n", type=int, default=1)
    p.add_argument("--seed", type=int, default=1)
    p.set_defaults(fn=cmd_dry_run)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
