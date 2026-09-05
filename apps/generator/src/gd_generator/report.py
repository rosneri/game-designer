"""Write runs/<run>/REPORT.md from per-game result.json files."""
from __future__ import annotations

import json
from pathlib import Path

DIMS = ("fun", "clarity", "originality", "depth", "component_fit")


def load_results(run_dir: Path) -> list[dict]:
    out = []
    for p in sorted(run_dir.glob("*/result.json")):
        try:
            out.append(json.loads(p.read_text()))
        except json.JSONDecodeError:
            continue
    return out


def _own_table(rows: list[dict]) -> str:
    head = "| # | slug | total | " + " | ".join(DIMS) + " | verdict | failed | fixes |\n|" + "---|" * (len(DIMS) + 7)
    lines = [head]
    for i, r in enumerate(rows, 1):
        j = r.get("judge") or {}
        lines.append(f"| {i} | {r.get('slug') or '?'} | {j.get('total', '-')} | " + " | ".join(str(j.get(d, "-")) for d in DIMS)
                     + f" | {j.get('verdict', '-')} | {r.get('failed_stage') or '-'} | {r.get('fix_rounds', 0)} |")
    return "\n".join(lines)


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


def leaderboard(rows: list[dict]) -> str:
    rows = sorted(rows, key=lambda r: (-(r.get("judge") or {}).get("total", -1), r.get("failed_stage") is not None, r.get("slug") or ""))
    try:
        from gd_report import leaderboard_md  # type: ignore
        return leaderboard_md(_gauntlet_rows(rows))
    except Exception:  # noqa: BLE001 - optional dependency / signature drift
        return _own_table(rows)


def one_liner(r: dict) -> str:
    j = r.get("judge") or {}
    status = f"FAILED at {r['failed_stage']}" if r.get("failed_stage") else f"passed ({j.get('verdict', '?')}, {j.get('total', '?')}/50)"
    summ = j.get("summary") or (r.get("error") or "").strip().splitlines()[-1:] or [""]
    summ = summ if isinstance(summ, str) else summ[0]
    slug = r.get("slug") or f"idea{r.get('idx', 0):02d}"
    total = r.get("timings", {}).get("total", "?")
    return f"- **{slug}** ({r.get('name', '')}): {status}; fixes={r.get('fix_rounds', 0)}; {total}s. {summ[:160]}"


def write_report(run_dir: str | Path) -> Path:
    run_dir = Path(run_dir)
    rows = load_results(run_dir)
    n_pass = sum(1 for r in rows if not r.get("failed_stage"))
    md = [f"# Run report: {run_dir.name}", "", f"{len(rows)} ideas, {n_pass} passed all stages.", "",
          "## Leaderboard", "", leaderboard(rows), "", "## Games", ""] + [one_liner(r) for r in rows] + [""]
    out = run_dir / "REPORT.md"
    out.write_text("\n".join(md))
    return out
