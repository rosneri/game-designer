"""Refinement: review a finished run and update the continual-harness ledger.

This is the cheap half of the flywheel. It never edits the prompt templates (the immutable base) or any code;
it proposes a small batch of create/update/delete entries that are rendered into later prompts, and records
before/after state so ``generator rollback`` can undo the batch.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .backends import LLMClient
from .blocks import parse_json_block
from .config import GeneratorConfig
from .harness import Harness, Refinement, parse_edits
from .lessons import load as load_lessons
from .pipeline import load_results


def run_digest(run_dir: Path) -> dict[str, Any]:
    """Everything a reviewer needs about one run, small enough to fit in a prompt."""
    run_dir = Path(run_dir)
    rows = load_results(run_dir)
    games: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for r in rows:
        j = r.get("judge") or {}
        g = r.get("gauntlet") or {}
        st = {s.get("name"): s.get("metrics", {}) for s in g.get("stages", []) if isinstance(s, dict)}
        if r.get("failed_stage"):
            failures.append({"slug": r.get("slug"), "stage": r["failed_stage"], "infra": r.get("infra", False),
                             "fixes": r.get("fix_rounds", 0), "error": (r.get("error") or "")[-300:]})
            continue
        games.append({"slug": r.get("slug"), "mechanics": (r.get("brief") or {}).get("mechanics", []),
                      "total": j.get("total"), "verdict": j.get("verdict"),
                      "scores": {k: j.get(k) for k in ("fun", "clarity", "originality", "depth", "component_fit")},
                      "notes": (j.get("notes") or [])[:3], "fixes": r.get("fix_rounds", 0),
                      "skill": st.get("s4_skill", {}), "decisions": st.get("s5_decisions", {}),
                      "length": st.get("s6_length", {}).get("est_minutes_range"),
                      "balance": st.get("s3_balance", {}), "novelty": st.get("s7_novelty", {}).get("similarity")})
    judged = [g for g in games if isinstance(g.get("total"), int)]
    return {"run": run_dir.name, "ideas": len(rows), "passed": len(games), "failures": failures, "games": games,
            "mean_judge": round(sum(g["total"] for g in judged) / len(judged), 1) if judged else None,
            "lessons": load_lessons(run_dir)[-40:]}


def refine(cfg: GeneratorConfig, run_dir: Path, llm: LLMClient | None = None, trigger: str = "manual",
           instructions: str = "") -> tuple[Refinement | None, str]:
    """Ask the refine model for ledger edits, validate them, apply. Returns (event, raw answer)."""
    run_dir = Path(run_dir)
    llm = llm or LLMClient(cfg)
    harness = Harness(cfg.harness_file)
    prompt = (cfg.prompts_dir / "refine.md").read_text().format(
        run=run_dir.name, digest=json.dumps(run_digest(run_dir), indent=1, default=str)[:24000],
        entries=harness.summary(), limit=cfg.max_refine_edits, instructions=instructions or "(none)")
    (run_dir / "refine.prompt.md").write_text(prompt)
    r = llm.call("refine", prompt)
    (run_dir / "refine.out.txt").write_text(r.text + (f"\n\n--- stderr ---\n{r.stderr}" if r.stderr else ""))
    if not r.ok:
        return None, r.stderr or "empty answer"
    edits = parse_edits(parse_json_block(r.text), limit=cfg.max_refine_edits)
    if not edits:
        return None, r.text
    ev = harness.apply(edits, run=run_dir.name, trigger=trigger)
    (run_dir / "refine.json").write_text(ev.model_dump_json(indent=1))
    return ev, r.text
