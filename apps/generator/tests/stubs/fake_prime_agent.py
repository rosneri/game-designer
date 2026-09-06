"""Fake prime-agent / claude: answers by prompt type. Optional env GD_FAKE_LLM_MODE=empty|badjson|infra.
GD_FAKE_INFRA_ONCE=<path>: fail with an infra error only on the first call (marker file).
GD_FAKE_IMPROVE_WRITE=<path>::<text>: what the improve step should write (simulates an agent editing the repo).
GD_FAKE_JUDGE_SEQ="4,6,3": the `fun` score for successive judge calls, so an iteration can get better or worse.
"""
import os
import re
import sys

prompt = sys.argv[-1]
mode = os.environ.get("GD_FAKE_LLM_MODE", "")
if mode == "empty":
    sys.exit(0)
if mode == "infra":
    print("Provider rejected the request (invalid_request_error, 400): Your credit balance is too low", file=sys.stderr)
    sys.exit(1)
once = os.environ.get("GD_FAKE_INFRA_ONCE")
if once and not os.path.exists(once):
    open(once, "w").close()
    print("Provider rejected the request (rate_limit_error, 429): overloaded", file=sys.stderr)
    sys.exit(1)

IDEA = '# Stub Duel\nslug: stub-duel\nplayers: 2-3\njokers: 1\ndice: 0\nmechanics: trick-taking, bluffing\nhidden_information: true\nturn_order: clockwise\n\n## Pitch\nTwo players flip cards; highest wins the round.\n\n## Rules\nDeal 5 cards each. On your turn play one card face up. After all played, highest card wins a point. Most points wins.\n\n## Design plan\n- State: hands, played, scores, current\n- Actions: ("play", card)\n'
RULES = 'from __future__ import annotations\nimport copy\nfrom random import Random\n\n\nclass StubDuel:\n    """Stub Duel rulesheet.\n\n    Each player is dealt 5 cards (ranks 2-14). Players alternate playing one card; the higher\n    card wins one point. After 5 rounds the player with most points wins.\n    """\n\n    def __init__(self, n_players: int, gm=None):\n        self.n_players = n_players\n        self.gm = gm\n\n    def setup(self, rng: Random):\n        deck = list(range(2, 15)) * 4\n        rng.shuffle(deck)\n        hands = [sorted(deck[i * 5:(i + 1) * 5]) for i in range(self.n_players)]\n        return {"hands": hands, "table": [], "scores": [0] * self.n_players, "cur": 0}\n\n    def current_player(self, s):\n        return s["cur"]\n\n    def legal_actions(self, s):\n        return [("play", c) for c in sorted(set(s["hands"][s["cur"]]))]\n\n    def step(self, s, a, rng: Random):\n        s = copy.deepcopy(s)\n        s["hands"][s["cur"]].remove(a[1])\n        s["table"].append((s["cur"], a[1]))\n        s["cur"] = (s["cur"] + 1) % self.n_players\n        if len(s["table"]) == self.n_players:\n            w = max(s["table"], key=lambda t: t[1])[0]\n            s["scores"][w] += 1\n            s["table"] = []\n        return s\n\n    def is_terminal(self, s):\n        return all(not h for h in s["hands"]) and not s["table"]\n\n    def scores(self, s):\n        return [float(x) for x in s["scores"]]\n\n    def observe(self, s, p):\n        return (tuple(s["hands"][p]), tuple(s["table"]), tuple(s["scores"]), s["cur"])\n\n    def describe(self, s):\n        return f"scores={s[\'scores\']} table={s[\'table\']}"\n\n\nGAME = StubDuel\n'
SPEC = '{"slug": "SLUG", "name": "Stub Duel", "tagline": "flip and win", "players_min": 2, "players_max": 3,\n "components": {"jokers": 1, "dice": 0, "uses_full_deck": true, "extra": []}, "mechanics": ["trick-taking", "bluffing"],\n "core_loop": "play a card", "win_condition": "most points", "est_minutes": [5, 10],\n "gm": {"enabled": false, "role": "", "decisions": []}, "hidden_information": true, "turn_order": "clockwise"}\n'
TESTS = 'from pathlib import Path\nfrom random import Random\nfrom gd_gamecore import load_game_module\n\nGAME = load_game_module(Path(__file__).parent).GAME\n\n\ndef test_setup():\n    g = GAME(2)\n    s = g.setup(Random(1))\n    assert len(g.legal_actions(s)) > 0\n'
JUDGE = 'Here is my verdict.\n```json\n{"fun": 4, "clarity": 8, "originality": 2, "depth": 3, "component_fit": 5, "verdict": "reject",\n "notes": ["add decisions", "use the joker", "shorten"], "summary": "A bare-bones war variant."}\n```\n'
REFINE = 'Reviewed the batch.\n```json\n{"edits": [{"op": "create", "id": "min-legal-actions", "kind": "constraint", "targets": ["idea"],\n "text": "Every player count must average more than 3 legal actions per turn.", "reason": "shallow games passed"},\n {"op": "delete", "id": "gone", "reason": "obsolete"}]}\n```\n'


def block(lang, path, body):
    return f"```{lang} path={path}\n{body}```\n"


if "veteran card-game designer" in prompt:
    print(IDEA)
elif "Implement the following card game" in prompt:
    slug = re.search(r"games/([a-z0-9-]+)/rules\.py", prompt).group(1)
    print("Here are the files.\n" + block("json", f"games/{slug}/spec.json", SPEC.replace("SLUG", slug))
          + block("python", f"games/{slug}/rules.py", RULES))
elif "fails a check" in prompt:
    slug = re.search(r"games/([a-z0-9-]+)/ fails", prompt).group(1)
    print("Fixed.\n" + block("python", f"games/{slug}/rules.py", RULES.replace("Stub Duel rulesheet", "Stub Duel rulesheet (fixed)")))
elif "Write pytest tests" in prompt:
    slug = re.search(r"games/([a-z0-9-]+)/test_rules\.py", prompt).group(1)
    print(block("python", f"games/{slug}/test_rules.py", TESTS))
elif "board-game reviewer" in prompt:
    if mode == "badjson":
        print("not json at all")
    else:
        seq = [x for x in os.environ.get("GD_FAKE_JUDGE_SEQ", "").split(",") if x]
        if seq:
            state = os.environ.get("GD_FAKE_STATE", "/tmp/gd_fake_state")
            os.makedirs(state, exist_ok=True)
            cf = os.path.join(state, "judge.count")
            n = 1
            if os.path.exists(cf):
                with open(cf) as f:
                    n = int(f.read()) + 1
            with open(cf, "w") as f:
                f.write(str(n))
            print(JUDGE.replace('"fun": 4', f'"fun": {seq[min(n, len(seq)) - 1]}'))
        else:
            print(JUDGE)
elif "redesigning an existing card game" in prompt:
    slug = re.search(r"games/([a-z0-9-]+)/rules\.py", prompt).group(1)
    print("I added a catch-up lever.\n" + block("python", f"games/{slug}/rules.py",
          RULES.replace("Stub Duel rulesheet", "Stub Duel rulesheet (redesigned)")))
elif "learned-rules ledger" in prompt:
    print("not json at all" if mode == "badjson" else REFINE)
elif "improving a self-improving card-game generator" in prompt:
    spec = os.environ.get("GD_FAKE_IMPROVE_WRITE", "")
    if spec:
        path, _, text = spec.partition("::")
        with open(path, "w") as f:
            f.write(text)
        print(f"I edited {path}.")
    else:
        print("The evidence does not support a change; I changed nothing.")
else:
    print("PONG")
