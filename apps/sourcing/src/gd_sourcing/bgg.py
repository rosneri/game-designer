"""BoardGameGeek taxonomy download: categories, mechanics, subdomains and families.

boardgamegeek.com (HTML, sitemaps, XML API) sits behind a Cloudflare challenge / needs an API token, but
``api.geekdo.com`` serves any taxonomy item by id anonymously, so we enumerate ids:

* categories / mechanics are ``objecttype=property`` ids (all below ~6000; the range also holds
  video-game / RPG properties, which ``build`` filters out by subtype)
* subdomains and families are ``objecttype=family`` ids (dense up to ~120k, shared with RPG series,
  card sets, video-game characters, ...; again filtered by subtype)

Raw hits are appended to ``data/bgg/raw/<kind>.jsonl`` and resolved ids to ``<kind>.done`` so a scan can be
resumed. The API rate-limits (429 + Retry-After), so requests go through an adaptive limiter and an id is
only marked done once it resolved to a 200 or a 404.
"""
from __future__ import annotations

import html
import json
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

UA = "game-designer sourcing (contact neri.coder@gmail.com)"
API = "https://api.geekdo.com/api/geekitems?objecttype={ot}&objectid={id}&nosession=1"
KEEP = ("objectid", "name", "subtype", "href", "description", "linkcounts", "itemstate")
KINDS = {"properties": "property", "families": "family"}
DEFAULT_MAX = {"properties": 6000, "families": 120500}
SUBTYPE_GROUP = {"boardgamecategory": "categories", "boardgamemechanic": "mechanics",
                 "boardgamesubdomain": "subdomains", "boardgamefamily": "families"}


class Unresolved(Exception):
    """The id could not be resolved (rate limit / network); it must be retried later."""


class RateLimiter:
    """Token bucket shared by worker threads. Halves the rate on 429, creeps back up on success."""

    def __init__(self, rate: float, min_rate: float = 1.0, max_rate: float | None = None):
        self.rate, self.min_rate, self.max_rate = rate, min_rate, max_rate or rate
        self._lock = threading.Lock()
        self._next = time.monotonic()
        self._paused_until = 0.0
        self._ok_streak = 0

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                start = max(now, self._next, self._paused_until)
                self._next = start + 1.0 / self.rate
            if start > now:
                time.sleep(start - now)
            return

    def throttled(self, retry_after: float) -> None:
        with self._lock:
            self._paused_until = max(self._paused_until, time.monotonic() + retry_after)
            self.rate = max(self.min_rate, self.rate / 2)
            self._ok_streak = 0

    def success(self) -> None:
        with self._lock:
            self._ok_streak += 1
            if self._ok_streak >= 300:
                self._ok_streak = 0
                self.rate = min(self.max_rate, self.rate * 1.25)


def fetch(ot: str, oid: int, limiter: RateLimiter | None = None, attempts: int = 8) -> dict | None:
    """Return the trimmed item, None for a 404/empty item, or raise ``Unresolved``."""
    url = API.format(ot=ot, id=oid)
    for attempt in range(attempts):
        if limiter:
            limiter.acquire()
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30) as r:
                body = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                if limiter:
                    limiter.success()
                return None
            wait = float(e.headers.get("Retry-After") or 0) if e.code == 429 else 0.0
            if limiter:
                limiter.throttled(wait or 5.0)
            else:
                time.sleep(wait or 2.0 * (attempt + 1))
            continue
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            time.sleep(2.0 * (attempt + 1))
            continue
        if limiter:
            limiter.success()
        item = body.get("item") if isinstance(body, dict) else None
        return {k: item.get(k) for k in KEEP} if item else None
    raise Unresolved(f"{ot}/{oid}")


def scan(out_dir: Path, kind: str, lo: int, hi: int, workers: int = 8, rate: float = 12.0,
         fetch_fn: Callable[..., dict | None] = fetch, log: Callable[[str], None] = lambda s: print(s, file=sys.stderr)) -> int:
    """Resolve every id in [lo, hi] not yet in ``<kind>.done``; return the number of new hits."""
    ot = KINDS[kind]
    raw = out_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    path, done_path = raw / f"{kind}.jsonl", raw / f"{kind}.done"
    seen = {int(x) for x in done_path.read_text().split()} if done_path.exists() else set()
    todo = [i for i in range(lo, hi + 1) if i not in seen]
    log(f"{kind}: {len(todo)} ids to resolve ({lo}-{hi}), {workers} workers, {rate}/s")
    limiter = RateLimiter(rate)
    hits = unresolved = 0
    t0 = time.monotonic()
    with path.open("a") as out, done_path.open("a") as done, ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(fetch_fn, ot, i, limiter): i for i in todo}
        for n, fut in enumerate(as_completed(futs), 1):
            try:
                item = fut.result()
            except Unresolved:
                unresolved += 1
                continue
            if item:
                hits += 1
                out.write(json.dumps(item, ensure_ascii=False) + "\n")
            done.write(f"{futs[fut]}\n")
            if n % 500 == 0:
                out.flush(); done.flush()
                log(f"  {n}/{len(todo)} resolved, {hits} hits, {unresolved} unresolved, "
                    f"{limiter.rate:.1f}/s, {time.monotonic() - t0:.0f}s")
    log(f"{kind}: {hits} new hits, {unresolved} unresolved (rerun to retry)")
    return hits


_TAG = re.compile(r"<[^>]+>")


def clean_desc(s: str | None) -> str:
    s = re.sub(r"\s+", " ", html.unescape(_TAG.sub(" ", s or ""))).strip()
    return re.sub(r"\s+([.,;:!?)])", r"\1", s)


def load_raw(out_dir: Path, kind: str) -> dict[int, dict]:
    p = out_dir / "raw" / f"{kind}.jsonl"
    items: dict[int, dict] = {}
    if p.exists():
        for line in p.read_text().splitlines():
            if line.strip():
                d = json.loads(line)
                items[int(d["objectid"])] = d
    return items


def build(out_dir: Path, log: Callable[[str], None] = lambda s: print(s, file=sys.stderr)) -> dict[str, list[dict]]:
    """Derive ``<group>.json`` (sorted by game count) and ``families_by_prefix.json`` from the raw scans."""
    groups: dict[str, list[dict]] = {g: [] for g in SUBTYPE_GROUP.values()}
    for kind in KINDS:
        for d in load_raw(out_dir, kind).values():
            g = SUBTYPE_GROUP.get(d.get("subtype") or "")
            if not g or d.get("itemstate") not in (None, "approved"):
                continue
            groups[g].append({
                "id": int(d["objectid"]),
                "name": d["name"],
                "games": int((d.get("linkcounts") or {}).get("boardgame") or 0),
                "url": "https://boardgamegeek.com" + (d.get("href") or ""),
                "description": clean_desc(d.get("description")),
            })
    for g, rows in groups.items():
        rows.sort(key=lambda r: (-r["games"], r["name"]))
        (out_dir / f"{g}.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n")
        log(f"{g}: {len(rows)}")
    by_prefix: dict[str, list[dict]] = {}
    for r in groups["families"]:
        prefix = r["name"].split(":", 1)[0].strip() if ":" in r["name"] else "(other)"
        by_prefix.setdefault(prefix, []).append(r)
    ordered = dict(sorted(by_prefix.items(), key=lambda kv: (-len(kv[1]), kv[0])))
    (out_dir / "families_by_prefix.json").write_text(json.dumps(ordered, indent=1, ensure_ascii=False) + "\n")
    if ordered:
        log("family prefixes: " + ", ".join(f"{k} ({len(v)})" for k, v in list(ordered.items())[:30]))
    return groups
