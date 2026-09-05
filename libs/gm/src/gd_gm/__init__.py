"""Game master implementations.

* :class:`ScriptedGM` — deterministic; used by the gauntlet. Picks options with the game rng
  or by a simple rule, and returns canned narration.
* :class:`LLMGM` — Anthropic-backed; used when a human plays. Requires ANTHROPIC_API_KEY.
"""
from __future__ import annotations

import json
import os
from random import Random
from typing import Any


class ScriptedGM:
    def __init__(self, rng: Random | None = None, policy: str = "random"):
        self.rng = rng or Random(0)
        self.policy = policy
        self.log: list[dict[str, Any]] = []

    def decide(self, prompt: str, options: list[str], context: dict[str, Any]) -> str:
        if not options:
            raise ValueError("GM.decide needs options")
        choice = options[0] if self.policy == "first" else self.rng.choice(options)
        self.log.append({"prompt": prompt, "options": options, "choice": choice})
        return choice

    def narrate(self, prompt: str, context: dict[str, Any]) -> str:
        return f"[GM] {prompt}"


class LLMGM:
    def __init__(self, role: str, model: str = "claude-sonnet-5", api_key: str | None = None):
        from anthropic import Anthropic  # local import: optional at runtime

        self.client = Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
        self.model = model
        self.role = role
        self.history: list[dict[str, str]] = []

    def _ask(self, text: str) -> str:
        self.history.append({"role": "user", "content": text})
        msg = self.client.messages.create(
            model=self.model, max_tokens=400, system=self.role, messages=self.history[-20:]
        )
        out = "".join(getattr(b, "text", "") for b in msg.content).strip()
        self.history.append({"role": "assistant", "content": out})
        return out

    def decide(self, prompt: str, options: list[str], context: dict[str, Any]) -> str:
        text = (
            f"{prompt}\n\nContext: {json.dumps(context, default=str)[:3000]}\n\n"
            f"Choose exactly one option and reply with only its text:\n" + "\n".join(f"- {o}" for o in options)
        )
        ans = self._ask(text)
        for o in options:
            if o.lower() in ans.lower():
                return o
        return options[0]

    def narrate(self, prompt: str, context: dict[str, Any]) -> str:
        return self._ask(f"{prompt}\n\nContext: {json.dumps(context, default=str)[:3000]}\n\nReply in 1-3 sentences.")


__all__ = ["LLMGM", "ScriptedGM"]
