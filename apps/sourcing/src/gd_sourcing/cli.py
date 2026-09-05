"""``sourcing bgg <properties|families|build>`` — download BoardGameGeek taxonomies into data/bgg/."""
from __future__ import annotations

import argparse
from pathlib import Path

from . import bgg


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="sourcing")
    sub = ap.add_subparsers(dest="source", required=True)
    b = sub.add_parser("bgg", help="BoardGameGeek categories / mechanics / subdomains / families")
    b.add_argument("what", choices=[*bgg.KINDS, "build"])
    b.add_argument("--out", type=Path, default=Path("data/bgg"))
    b.add_argument("--min", type=int, default=1)
    b.add_argument("--max", type=int, default=None)
    b.add_argument("--workers", type=int, default=8)
    b.add_argument("--rate", type=float, default=12.0, help="initial requests/second (adapts on 429)")
    a = ap.parse_args(argv)
    if a.what in bgg.KINDS:
        bgg.scan(a.out, a.what, a.min, a.max or bgg.DEFAULT_MAX[a.what], a.workers, a.rate)
    bgg.build(a.out)
