from gd_gamecore import GameSpec
from gd_report import leaderboard_md, rulesheet_md

SPEC = GameSpec(slug="test-game", name="Test Game", tagline="Fast and loose.", players_min=2, players_max=4,
                components={"jokers": 1, "dice": 2, "extra": ["pen and paper"]},
                mechanics=["bidding", "push-your-luck"], core_loop="Bid, then roll.", win_condition="Most points.",
                gm={"enabled": True, "role": "You are the auctioneer.", "decisions": ["tie-breaks"]})


def test_rulesheet():
    md = rulesheet_md(SPEC, """
        Deal five cards.

        Play until the deck runs out.
    """)
    assert md.startswith("# Test Game\n")
    for needle in ("2-4 players", "1 joker", "2 six-sided dice", "pen and paper", "## Game master", "tie-breaks",
                   "Bid, then roll.", "Most points.", "## Full rules", "Deal five cards.\n\nPlay until", "bidding"):
        assert needle in md, needle
    assert "## Full rules" not in rulesheet_md(SPEC, "")


def _result(slug, passed, failed=None, greedy=0.7, judge=None):
    stages = [
        {"name": "s3_balance", "passed": True, "metrics": {"p2": {"draw_rate": 0.05}, "p3": {"draw_rate": 0.1}}},
        {"name": "s4_skill", "passed": True, "metrics": {"p2": {"greedy_win_rate": greedy}, "p3": {"greedy_win_rate": None}}},
        {"name": "s5_decisions", "passed": True, "metrics": {"mean_legal_actions": 3.2}},
        {"name": "s6_length", "passed": True, "metrics": {"p2": {"mean_turns": 90}, "p3": {"mean_turns": 130}}},
    ]
    return {"slug": slug, "name": slug.title(), "passed": passed, "failed_stage": failed, "stages": stages,
            "game_dir": f"games/{slug}", **({"judge": {"score": judge}} if judge is not None else {})}


def test_leaderboard():
    md = leaderboard_md([_result("b-game", False, "s4_skill", greedy=0.4), _result("a-game", True, judge=7.5),
                         _result("c-game", True, judge=8.5)])
    lines = md.strip().split("\n")
    assert lines[0].startswith("| slug | name | passed | failed_stage")
    assert len(lines) == 5
    assert lines[2] == "| c-game | C-Game | ✅ | - | 4/4 | 90/130 | 0.70/- | 0.05/0.10 | 3.2 | 8.5 |"
    assert lines[3].startswith("| a-game")
    assert "| b-game | B-Game | ❌ | s4_skill |" in lines[4] and "0.40/-" in lines[4]


def test_leaderboard_minimal_dict():
    md = leaderboard_md([{"game_dir": "/x/games/only-dir", "passed": False, "failed_stage": "s0_schema", "stages": []}])
    assert "| only-dir | - | ❌ | s0_schema | 0/8 | - | - | - | - | - |" in md
