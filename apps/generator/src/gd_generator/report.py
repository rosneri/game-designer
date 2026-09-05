"""Write runs/<run>/REPORT.md from per-idea result.json files."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .pipeline import load_results

DIMS = ("fun", "clarity", "originality", "depth", "component_fit")


def _gauntlet_rows(rows: list[dict]) -> list[dict]:
    """Reshape generator results into what ``gd_report.leaderboard_md`` expects (GauntletResult.to_dict shape)."""
    out = []
    for r in rows:
        g = r.get("gauntlet") or {}
        j = r.get("judge") or {}
        out.append({"slug": r.get("slug") or f"idea{r.get('idx', 0):02d}", "name": r.get("name") or "-",
                    "passed": not r.get("failed_stage"), "failed_stage": r.get("failed_stage") or g.get("failed_stage"),
                    "stages": g.get("stages", []), "judge_score": j.get("total")})
    return out


def _own_table(rows: list[dict]) -> str:
    head = "| # | slug | total | " + " | ".join(DIMS) + " | verdict | failed | fixes |\n|" + "---|" * (len(DIMS) + 7)
    lines = [head]
    for i, r in enumerate(rows, 1):
        j = r.get("judge") or {}
        lines.append(f"| {i} | {r.get('slug') or '?'} | {j.get('total', '-')} | " + " | ".join(str(j.get(d, "-")) for d in DIMS)
                     + f" | {j.get('verdict', '-')} | {r.get('failed_stage') or '-'} | {r.get('fix_rounds', 0)} |")
    return "\n".join(lines)


def leaderboard(rows: list[dict]) -> str:
    rows = sorted(rows, key=lambda r: (-(r.get("judge") or {}).get("total", -1), r.get("failed_stage") is not None, r.get("slug") or ""))
    try:
        from gd_report import leaderboard_md  # type: ignore
        return leaderboard_md(_gauntlet_rows(rows))
    except Exception:  # noqa: BLE001 - optional dependency / signature drift
        return _own_table(rows)


def one_liner(r: dict) -> str:
    j = r.get("judge") or {}
    if r.get("failed_stage"):
        status = f"FAILED at {r['failed_stage']}" + (" (infra)" if r.get("infra") else "")
    else:
        status = f"passed ({j.get('verdict', '?')}, {j.get('total', '?')}/50)" + (" promoted" if r.get("promoted") else "")
    summ = j.get("summary") or (r.get("error") or "").strip().splitlines()[-1:] or [""]
    summ = summ if isinstance(summ, str) else summ[0]
    slug = r.get("slug") or f"idea{r.get('idx', 0):02d}"
    total = r.get("timings", {}).get("total", "?")
    return f"- **{slug}** ({r.get('name', '')}): {status}; fixes={r.get('fix_rounds', 0)}; {total}s. {summ[:160]}"


def manifest_text(run_dir: Path) -> str:
    p = run_dir / "manifest.json"
    if not p.exists():
        return ""
    m: dict[str, Any] = json.loads(p.read_text())
    steps = m.get("config", {}).get("steps", {})
    routes = ", ".join(f"{k}={v.get('backend')}:{v.get('model', '').split('/')[-1]}" for k, v in steps.items())
    return (f"run `{m.get('run_id')}` created {m.get('created')} · n={m.get('n')} seed={m.get('seed')} · git {m.get('git_sha') or '-'}\n\n"
            f"models: {routes}\n\nprompts: " + ", ".join(f"{k}@{v}" for k, v in m.get("prompt_hashes", {}).items())
            + f"\n\ncatalog at start: {len(m.get('catalog', []))} games\n")


def write_report(run_dir: str | Path) -> Path:
    run_dir = Path(run_dir)
    rows = load_results(run_dir)
    n_pass = sum(1 for r in rows if not r.get("failed_stage"))
    n_infra = sum(1 for r in rows if r.get("infra"))
    md = [f"# Run report: {run_dir.name}", "", manifest_text(run_dir),
          f"{len(rows)} ideas, {n_pass} passed all stages" + (f", {n_infra} infra failures" if n_infra else "") + ".", "",
          "## Leaderboard", "", leaderboard(rows), "", "## Games", ""] + [one_liner(r) for r in rows] + [""]
    out = run_dir / "REPORT.md"
    out.write_text("\n".join(md))
    return out
