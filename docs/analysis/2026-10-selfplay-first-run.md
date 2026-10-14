# Self-play, first run

Issue #78. One self-play run with the loop of #76 (spec `docs/specs/2026-10-13-self-play.md`), run on 2026-10-14 on the engineer's machine (Intel i7-8650U, CPU only, Python 3.12.3), code at commit `d3bcb00` (the loop is unchanged since). The run folder `data/runs/selfplay-1` is not committed (`data/` is ignored).

## Setup

- Command: `uv run --group train python scripts/train_selfplay.py --run selfplay-1 --steps 200000 --update-every 50000` (rules `v1.1`, seed 0, 500 evaluation games, default `eval_bots` = `draw20-pts1-points`). Started in the background and polled.
- Steps: 200,000 decisions of the learner, 5,127 games, 4 updates (snapshots `step_50000.zip` to `step_200000.zip`). The estimate of #76 was 143 steps/s, so about 23 minutes of training; the steps were chosen from it, 4 updates fit the 90-minute budget, so `update_every` stays 50,000.
- Wall clock of the whole command: 2,486 s (41.4 min), including the evaluations at the 4 updates and the final evaluations.

## Where the numbers come from

- `selfplay.csv` and `eval.json` of the run folder: win rates and the sampled and greedy evaluation against `random`. `selfplay.csv` holds win rates only (the learner is evaluated greedily, `evaluate`, `seed=0`, 500 games, the seat alternates).
- Tournament of #70 for wins, draws and losses: the learner is the seat `policy:data/runs/selfplay-1` (greedy `PolicyBot`), the snapshots are scratch run folders (`config.json` of the run plus the snapshot as `model.zip`). Each opponent was played in two tournaments of 250 games, the learner as p1 (`--seed 0`, `--name sp1-learner-p1`, seats fixed by field order) and as p2 (`--seed 250`, one tournament per opponent), so 500 games per row, 250 in each seat. Commands: `uv run quack-rl tournament --bots "<seat A>,<seat B>" --games 250 --seed <0|250> --rules v1.1 --sample-size 0`. The games are not the same as those of `evaluate`, so the rates differ a little from `selfplay.csv`.
- The untrained network: `MaskablePPO` with `seed=0` as at the start of the run, evaluated with `evaluate` (`seed=0`, 500 games). Its sampled row against `random` equals `baseline_untrained` of `eval.json` (213 wins).

## Results

Final learner (step 200,000), 500 games per row, win rate = wins / games.

| agent | against | games | wins | draws | losses | win rate | source |
|---|---|--:|--:|--:|--:|--:|---|
| learner, greedy | `random` | 500 | 108 | 4 | 388 | 0.216 | tournament |
| learner, greedy | `random` | 500 | 93 | 68 | 339 | 0.186 | `eval.json` `trained_greedy`, `selfplay.csv` |
| learner, sampled | `random` | 500 | 365 | 45 | 90 | 0.730 | `eval.json` `trained_sampled` |
| learner, greedy | `draw20-pts1-points` | 500 | 0 | 0 | 500 | 0.000 | tournament (`selfplay.csv`: 0.0) |
| learner, sampled | `draw20-pts1-points` | 500 | 0 | 0 | 500 | 0.000 | `evaluate` |
| learner, greedy | snapshot 50,000 | 500 | 300 | 0 | 200 | 0.600 | tournament (`selfplay.csv`: 0.652) |
| learner, greedy | snapshot 100,000 | 500 | 304 | 0 | 196 | 0.608 | tournament (`selfplay.csv`: 0.652) |
| learner, greedy | snapshot 150,000 | 500 | 250 | 13 | 237 | 0.500 | tournament (`selfplay.csv`: 0.424) |

Baseline: no number of a policy trained against a fixed strong bot (stage #69) is known, so the baseline is the untrained network.

| agent | against | games | wins | draws | losses | win rate | source |
|---|---|--:|--:|--:|--:|--:|---|
| untrained, sampled | `random` | 500 | 213 | 86 | 201 | 0.426 | `eval.json` `baseline_untrained` |
| untrained, greedy | `random` | 500 | 28 | 81 | 391 | 0.056 | `evaluate` |
| untrained, sampled | `draw20-pts1-points` | 500 | 0 | 0 | 500 | 0.000 | `evaluate` |
| untrained, greedy | `draw20-pts1-points` | 500 | 0 | 0 | 500 | 0.000 | `evaluate` |

The learner at each update, from `selfplay.csv` (win rate of the greedy learner of that update, 500 games):

| update | vs `random` | vs `draw20-pts1-points` | vs older snapshots | vs previous newest |
|--:|--:|--:|---|--:|
| 50,000 | 0.322 | 0.000 | | |
| 100,000 | 0.322 | 0.000 | 50k: 0.152 | 0.152 |
| 150,000 | 0.186 | 0.000 | 50k: 0.652, 100k: 0.652 | 0.652 |
| 200,000 | 0.186 | 0.000 | 50k: 0.652, 100k: 0.652, 150k: 0.424 | 0.424 |

## Does the learner beat `random`?

It depends on how the policy acts. The sampled policy (the one that trained) beats `random` clearly: 0.730 against 0.426 for the untrained network. The greedy policy (most likely action, used by `PolicyBot`, the tournament and `selfplay.csv`) loses to `random`: 0.186 to 0.216. The untrained network is even worse when greedy (0.056), so greedy play is a poor read-out of a policy of this size here. The self-play numbers of `selfplay.csv` therefore measure a different, weaker agent than the one that was trained.

## Does the learner beat the strong heuristic bot?

No. `draw20-pts1-points` won all 500 games against the final learner, sampled and greedy, and also against the untrained network. There is no sign of progress against it at any update.

## Progress and cycling against snapshots

The final learner beats the snapshots of 50,000 and 100,000 steps (0.60 and 0.61 in the tournament, 0.652 in `selfplay.csv`) and is level with the snapshot of 150,000 (0.50 and 0.42). Progress is weak: the newest snapshot is not clearly ahead of the one before. The win rate against a snapshot is not stable. The learner of 100,000 steps lost to the snapshot of 50,000 (0.152), while the learners of 150,000 and 200,000 won against it (0.652); against the previous newest snapshot the rate went 0.152, 0.652, 0.424. This up and down is the pattern of cycling, but with 4 updates and one seed it cannot be told from noise. The snapshots of 50,000 and 100,000 also gave identical rates in `selfplay.csv` (0.322 against `random`, 0.652 against the same snapshots), which suggests that the greedy policy changed little between them.

## Time per step against the estimate of #76

#76 measured 143 steps/s with a `PolicyBot` opponent. The first 178 s of the run gave 625 games, about 147 steps/s, which agrees. The whole command took 2,486 s for 200,000 steps, about 80 steps/s, because the evaluations (500 games against `random`, the bot and every snapshot, at each of the 4 updates, plus the final ones) are inside that time. They were not timed separately.

## Conclusion

The environment supports online RL in the narrow sense: the sampled policy learns from self-play and wins 73% against `random` from 43% untrained, and later learners beat the early snapshots. There is no signal against the strong bot (0 of 500 wins), and the greedy read-out that the loop uses for its numbers is misleading (it loses to `random`). The result against the strong bot is negative. The next experiment should evaluate the sampled policy (or fix the greedy read-out) and add the strong bot to the opponent pool, so that the learner meets an opponent that is hard to beat; this is the content of #86.
