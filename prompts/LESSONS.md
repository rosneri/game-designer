# Lessons

Appended by the generator after every run. One bullet per lesson. Newest last.

- [gauntlet] loom: failed with `s6_length: FAIL reason=estimated 2-4 min does not overlap [8, 35] metrics={"p2": {"mean_turns": 18, "est_minutes": 1.8},`; fix worked: rules.py, spec.json
- [passed] loom: weakest=fun (6/10); verdict=iterate; note: 3-player balance is skewed (seat 0 wins far more than seat 2); adjust turn/start-player rotation or scoring to compensate for draft-order di
- [passed] switchback: weakest=depth (5/10); verdict=iterate; note: 4-player win rates are uneven (seat 1 at 0.213 vs seat 0 at 0.293), suggesting turn-order/positional advantage needs balancing, e.g. rotatin
- [tests] closing-bell: failed with `1 failed, 9 passed in 0.24s`; fix worked: test_rules.py
- [passed] closing-bell: weakest=depth (5/10); verdict=iterate; note: Add a stronger reason to sell early (e.g. price decay or interest on vault) since 4-player greedy win rate near 45% suggests optimal play ma
- [tests] dead-drop: failed with `1 failed, 9 passed in 0.18s`; fix worked: test_rules.py
- [gauntlet] dead-drop: failed with `s4_skill: FAIL reason=greedy win rate >= 0.97 at every player count (no luck) metrics={"p2": {"greedy_win_rate": 1.0, "m`; fix worked: rules.py, spec.json
- [passed] dead-drop: weakest=fun (6/10); verdict=iterate; note: Ledger placement is fully forced and deterministic once a card is chosen, so most of the game is 'pick best card to place' — add more meanin
- [passed] ferryman: weakest=fun (6/10); verdict=iterate; note: Games run ~60-80 turns (22-26 min) which feels long for the decision depth; consider trimming hand limit or deck size to tighten pacing
- [passed] undertow: weakest=depth (5/10); verdict=iterate; note: Greedy win rates of 89% (2p) and 80% (3p) vs random-ish baseline suggest the optimal push/bank threshold dominates too hard; add variance or
- [tests] tumble: failed with `1 failed, 9 passed in 0.22s`; fix worked: test_rules.py
- [passed] tumble: weakest=depth (4/10); verdict=iterate; note: No-follow-suit removes most tactical tension since off-suit cards can never win but still safely dump; add a penalty or incentive for playin
- [passed] reckoner: weakest=fun (6/10); verdict=iterate; note: Greedy win rates near 78-98% are too high; genuinely skillful play should be more clearly rewarded—rebalance capture values or add more mean
- [passed] chicane: weakest=fun (6/10); verdict=iterate; note: Lay is nearly always dominant (guaranteed +1, no risk) while Drive risks wasted throttle — rebalance so Drive's variance pays off more, e.g.
- [tests] overburden: failed with `1 failed, 9 passed in 0.27s`; fix worked: test_rules.py
- [passed] overburden: weakest=fun (6/10); verdict=iterate; note: Estimated 33-37 minutes for a 4x4 grid game is too long; tighten pacing by shrinking deck used or adding faster win conditions.
