# Testing the RL environment: results and verdict

Issue #197. The three runs of the stage (#194 PPO against bots, #195 self-play, #196 offline RL)
in one table, and a verdict on the env. Ruleset v2.1, observation layout 8 (1530 numbers, 88
actions). One seed, no tuning. Details, set-ups and run times are in the three notes:
`2026-10-rl-vs-bots.md`, `2026-10-selfplay.md`, `2026-10-offline-rl.md`. No full run was repeated
for this note.

## Results

All rows: seed 0, 500 evaluation games, chance seed `seed + i`, agent at p1 for even i and p2 for
odd i, a draw counts as one half, 95% Wilson interval.

| Set-up | Opponent | Budget | Win rate | 95% interval |
| --- | --- | --- | --- | --- |
| MaskablePPO trained against `bot:random` (#194) | `bot:random` | 200000 steps | 0.931 | [0.905, 0.950] |
| MaskablePPO trained against `bot:draw20-pts1-points` (#194) | `bot:draw20-pts1-points` | 200000 steps | 0.002 | [0.000, 0.011] |
| MaskablePPO trained against `bot:draw20-pts1-points` (#194) | `bot:random` | 200000 steps | 0.309 | [0.270, 0.351] |
| Self-play, last checkpoint (#195) | `bot:random` | 5 x 20000 steps, pool 4 | 0.996 | [0.986, 0.999] |
| Self-play, last checkpoint (#195) | `bot:draw20-pts1-points` | 5 x 20000 steps, pool 4 | 0.003 | [0.001, 0.013] |
| Self-play, last checkpoint (#195) | first checkpoint | 5 x 20000 steps, pool 4 | 0.961 | [0.940, 0.975] |
| Behaviour bot `draw20-pts1-points` (reference, #196) | `bot:random` | none | 1.000 | [0.992, 1.000] |
| Behaviour cloning (#196) | `bot:random` | 4000 games, 5 epochs | 1.000 | [0.992, 1.000] |
| Behaviour cloning (#196) | `bot:draw20-pts1-points` | 4000 games, 5 epochs | 0.459 | [0.416, 0.503] |
| Discrete CQL (#196) | `bot:random` | 4000 games, 20000 steps | 1.000 | [0.992, 1.000] |
| Discrete CQL (#196) | `bot:draw20-pts1-points` | 4000 games, 20000 steps | 0.464 | [0.421, 0.508] |

## Verdict

The RL environment works on ruleset v2.1 and observation layout 8: three different learners
(online PPO, self-play, offline BC and CQL) ran end to end with exit code 0, no crash and no
illegal action, and every check that has a known right answer came out right. The evidence per
part of the env: **observation**: the 1530-entry layout 8 vector is `float32`, lies inside
`observation_space` in every step of a 20-game masked random rollout (962 steps, 0 outside; 1331
of 1530 upper bounds finite, the 199 others are points, money and bag counts; `points_gap` is the
only entry without a finite lower bound), and carries the information the teacher bot used (BC
and CQL reach 0.46 against their own teacher, 1.000 against the random bot); the layout tests are
`tests/test_rl_layout8.py` and `tests/test_rl_encode.py`. **Action mask**: the mask is non-empty
at every decision of the rollout and all zero at the terminal step; every stored dataset action is
legal under its mask (`test_stored_actions_are_legal` in `tests/test_rl_offline.py`), the PPO
evaluation raises on an illegal choice and did not, and the self-play loop never raised.
**Reward**: +1/-1/0 only at the end of the game; the rollout's terminal rewards were exactly
{-1, 0, +1}, the dataset has reward 0 except on the last step of a game with `terminated` once per
game, and the dataset mean return (0.4975) is what a bot that wins all 2000 games against the
random bot and splits the 2000 mirror games gives. **Opponent handling**: the opponent acts inside
`step`; PPO learned against the random bot (0.931) and the pool opponent of self-play played
earlier checkpoints (last against first: 0.961, the loop improves over its start); against the
strong heuristic bot PPO and self-play lose (0.002, 0.003), which is what a weak policy should
get against a bot that beats the random bot 200 to 0. **Seat handling**: all runs use
`seat="random"` or alternate p1/p2 by game index, and the results are not seat-dependent in any
visible way (BC/CQL near 0.5 against the teacher; the self-play checkpoints play both seats).
**Replay of recorded games**: `tests/test_rl_parallel_env.py` replays the same actions and chance
outcomes through the env and the engine and compares final state and events
(`test_env_matches_engine_with_same_actions_and_chance`, `test_trace_events_equal_direct_engine_events`),
and the dataset build plays 4000 whole bot games through `QuackEnv`. No run produced a result that
contradicts the env being correct.

## Findings

No env bug found. The checks that would have shown one: a PPO win rate against the random bot at
or below 0.5 (got 0.931, lower end 0.905); a crash or illegal action in the self-play loop or the
evaluation (none); a self-play checkpoint not beating its first checkpoint (0.961); a BC policy
not beating the random bot (1.000); BC/CQL far from their teacher (0.46, intervals contain 0.5 or
end just above it); non-finite losses (all finite); an observation outside the space, a non-empty
terminal mask or a reward other than {-1, 0, +1} in the rollout (none). Two oddities that are not
env bugs:

1. **No learning signal against the heuristic bot.** Evidence: `uv run --group rl python
   scripts/train_ppo.py --opponent bot:draw20-pts1-points --steps 200000 --seed 0 --eval-games 500`
   gives a mean training reward of -0.99 (first 10 and last 40 rollout points), win rate 0.002
   against that bot and 0.309 against the random bot (#194). The reward is sparse and nearly every
   game is lost. Proposed fix: reward shaping (#57), a curriculum or self-play from a policy that
   beats the random bot first (#86); not an env change.
2. **Dataset build memory.** Evidence: `uv run python scripts/build_dataset.py --out
   data/datasets/draw20` was killed by the memory caps of 6 GB and 8 GB before #196 changed the
   build to one compact chunk per game (peak now 6.6 GB, 27 min 43 s, 432004 steps of 1530
   floats). Proposed fix, if the default dataset should be cheaper: store the observations as
   `float16`/`uint8` where the entries are flags, or store the map block sparsely. Not needed for
   the env.
