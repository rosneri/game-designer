"""Lessons as data. Each run appends structured records to ``runs/<run>/lessons.jsonl``; ``learn`` folds a
finished run into ``prompts/LESSONS.md`` between batches. A running batch only ever reads its snapshot."""
from __future__ import annotations

import json
import threading
from collections import Counter
from pathlib import Path
from typing import Any

from .backends import is_infra_error
from .models import IdeaResult

_lock = threading.Lock()


def records_from(result: IdeaResult, run_id: str) -> list[dict[str, Any]]:
    slug = result.slug or f"idea{result.idx:02d}"
    out: list[dict[str, Any]] = []
    for fx in result.fixes:
        if is_infra_error(fx.error):
            continue
        cls = fx.error.strip().splitlines()[-1][:160] if fx.error.strip() else "unknown"
        out.append({"run": run_id, "slug": slug, "kind": "fix", "stage": fx.stage, "fixed": fx.fixed,
                    "error": cls, "changed": fx.changed})
    if result.failed_stage:
        if result.infra or is_infra_error(result.error):
            return out  # plumbing failed; nothing to learn about game design
        out.append({"run": run_id, "slug": slug, "kind": "unrecovered", "stage": result.failed_stage,
                    "fix_rounds": result.fix_rounds, "error": result.error[-200:]})
    elif result.judge:
        j = result.judge
        dims = {k: getattr(j, k) for k in ("fun", "clarity", "originality", "depth", "component_fit")}
        weakest = min(dims, key=dims.get)
        metrics = _key_metrics(result.gauntlet)
        out.append({"run": run_id, "slug": slug, "kind": "judge", "total": j.total, "verdict": j.verdict,
                    "weakest": weakest, "weakest_score": dims[weakest], "notes": j.notes[:3],
                    "rejected": result.rejected, **metrics})
    return out


def _key_metrics(g: dict[str, Any] | None) -> dict[str, Any]:
    if not g:
        return {}
    st = {s.get("name"): s.get("metrics", {}) for s in g.get("stages", []) if isinstance(s, dict)}
    out: dict[str, Any] = {}
    sk = st.get("s4_skill", {})
    greedy = [v.get("greedy_win_rate") for k, v in sk.items() if k.startswith("p") and isinstance(v, dict)]
    if greedy:
        out["greedy_max"] = max(x for x in greedy if x is not None)
    dec = st.get("s5_decisions", {})
    if "mean_legal_actions" in dec:
        out["mean_legal"] = dec["mean_legal_actions"]
        out["forced_share"] = dec.get("forced_share")
    ln = st.get("s6_length", {})
    if "est_minutes_range" in ln:
        out["minutes"] = ln["est_minutes_range"]
    return out


def append(run_dir: Path, records: list[dict[str, Any]]) -> int:
    if not records:
        return 0
    with _lock, (Path(run_dir) / "lessons.jsonl").open("a") as f:
        for r in records:
            f.write(json.dumps(r, default=str) + "\n")
    return len(records)


def load(run_dir: Path) -> list[dict[str, Any]]:
    p = Path(run_dir) / "lessons.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []


def bullets(records: list[dict[str, Any]], aggregate: bool = True) -> list[str]:
    """Human-readable lessons for the idea prompt; aggregated first, then per-game specifics."""
    out: list[str] = []
    if not aggregate:
        return _per_game(records)
    stages = Counter(r["stage"] for r in records if r["kind"] in ("fix", "unrecovered"))
    if stages:
        out.append("[batch] failures by stage: " + ", ".join(f"{s}={n}" for s, n in stages.most_common()))
    judged = [r for r in records if r["kind"] == "judge"]
    if judged:
        weak = Counter(r["weakest"] for r in judged)
        greedy = [r["greedy_max"] for r in judged if r.get("greedy_max") is not None]
        legal = [r["mean_legal"] for r in judged if r.get("mean_legal") is not None]
        line = f"[batch] {len(judged)} judged, mean total {sum(r['total'] for r in judged) / len(judged):.1f}/50; weakest dims: " + \
               ", ".join(f"{k}={n}" for k, n in weak.most_common(3))
        if greedy:
            line += f"; greedy max win rate median {sorted(greedy)[len(greedy) // 2]:.2f}"
        if legal:
            line += f"; legal actions/turn median {sorted(legal)[len(legal) // 2]:.1f}"
        out.append(line)
    return out + _per_game(records)


def _per_game(records: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for r in records:
        if r["kind"] == "fix":
            out.append(f"[{r['stage']}] {r['slug']}: failed with `{r['error'][:120]}`; fix {'worked' if r['fixed'] else 'FAILED'}: {', '.join(r['changed']) or 'no files'}")
        elif r["kind"] == "unrecovered":
            out.append(f"[{r['stage']}] {r['slug']}: unrecovered after {r['fix_rounds']} fixes: {r['error'][-120:]}")
        elif r["kind"] == "judge":
            note = (r.get("notes") or [""])[0][:140]
            tag = "rejected" if r.get("rejected") else "passed"
            out.append(f"[{tag}] {r['slug']}: {r['total']}/50 weakest={r['weakest']} ({r['weakest_score']}/10); verdict={r['verdict']}; note: {note}")
    return out


def learn(run_dir: Path, lessons_md: Path, max_bullets: int = 60) -> int:
    """Fold one finished run into LESSONS.md (dedupes; keeps the file bounded). Returns bullets added."""
    run_dir, lessons_md = Path(run_dir), Path(lessons_md)
    new = bullets(load(run_dir))
    head = "# Lessons\n\nAppended by `generator learn <run>` after each batch. One bullet per lesson. Newest last.\n"
    old = [l for l in lessons_md.read_text().splitlines() if l.startswith("- ")] if lessons_md.exists() else []
    seen = set(old)
    add = [f"- {b}" for b in new if f"- {b}" not in seen]
    merged = (old + add)[-max_bullets:]
    lessons_md.write_text(head + "\n" + "\n".join(merged) + "\n")
    return len(add)
