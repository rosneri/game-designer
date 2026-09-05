"""Batch-shared, thread-safe state: slug allocation, brief registration/dedupe, live lessons.

Registration is *ordered by idea index* even though ideas are generated in parallel, so which of two similar
briefs survives depends on the seed, not on thread timing.
"""
from __future__ import annotations

import threading
from typing import Any

from .models import IdeaBrief


class Duplicate(Exception):
    def __init__(self, against: str, similarity: float, tags: set[str]):
        super().__init__(f"mechanics overlap {similarity:.2f} with {against}: {sorted(tags)}")
        self.against, self.similarity = against, similarity


def jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a or b else 0.0


class Registry:
    def __init__(self, catalog: list[dict[str, Any]], taken: set[str], threshold: float, n: int):
        self.threshold = threshold
        self._catalog = [(g["slug"], {str(t).lower() for t in g.get("mechanics", [])}) for g in catalog]
        self._taken = set(taken)
        self._briefs: list[IdeaBrief] = []
        self._next = 0
        self._n = n
        self._cv = threading.Condition()

    # -- ordering ---------------------------------------------------------
    def _wait_turn(self, idx: int) -> None:
        with self._cv:
            while self._next < idx:
                self._cv.wait(timeout=0.05)

    def _advance(self, idx: int) -> None:
        with self._cv:
            self._next = max(self._next, idx + 1)
            self._cv.notify_all()

    def skip(self, idx: int) -> None:
        """An idea failed before registration; let later ideas proceed."""
        self._advance(idx)

    # -- registration -----------------------------------------------------
    def register(self, idx: int, brief: IdeaBrief) -> str:
        """Assign a collision-free slug and reject near-duplicates. Returns the final slug."""
        self._wait_turn(idx)
        try:
            with self._cv:
                tags = brief.tags()
                known = self._catalog + [(b.slug, b.tags()) for b in self._briefs]
                worst = max(((jaccard(tags, t), s) for s, t in known), default=(0.0, ""))
                if worst[0] >= self.threshold:
                    raise Duplicate(worst[1], worst[0], tags)
                cand, i = brief.slug, 1
                while cand in self._taken:
                    i += 1
                    cand = f"{brief.slug[:37]}-{i}"
                self._taken.add(cand)
                brief.slug = cand
                self._briefs.append(brief)
                return cand
        finally:
            self._advance(idx)

    def reserve(self, idx: int, brief: IdeaBrief) -> str:
        """Re-register an idea resumed from disk: keep its slug, keep it out of everyone else's way."""
        self._wait_turn(idx)
        with self._cv:
            self._taken.add(brief.slug)
            self._briefs.append(brief)
        self._advance(idx)
        return brief.slug

    def briefs(self) -> list[IdeaBrief]:
        with self._cv:
            return list(self._briefs)

    def catalog_tags(self) -> set[str]:
        return {t for _, tags in self._catalog for t in tags}


class LessonBoard:
    """Lessons accumulated during a run. Read by every later idea prompt, so the batch learns game by game."""

    def __init__(self, base: list[str], live: bool = True):
        self._base, self._live, self._rows = list(base), live, []
        self._lock = threading.Lock()

    def add(self, bullets: list[str]) -> None:
        with self._lock:
            for b in bullets:
                if b not in self._rows:
                    self._rows.append(b)

    def text(self, limit: int = 40) -> str:
        with self._lock:
            rows = self._base + ([f"(this run) {r}" for r in self._rows] if self._live else [])
        return "\n".join(f"- {r.lstrip('- ')}" for r in rows[-limit:]) or "- (none yet)"
