# Self-play, first run

Issue #78. One self-play run with the loop of #76 (spec `docs/specs/2026-10-13-self-play.md`), run on 2026-10-14 on the engineer's machine (Intel i7-8650U, CPU only, Python 3.12.3), code at commit `d3bcb00` (the loop is unchanged since). The run folder `data/runs/selfplay-1` is not committed (`data/` is ignored).

## Setup

- Command: `uv run --group train python scripts/train_selfplay.py --run selfplay-1 --steps 200000 --update-every 50000` (rules `v1.1`, seed 0, 500 evaluation games, default `eval_bots` = `draw20-pts1-points`). Started in the background and polled (a foreground command stops after 10 minutes). File times of the run folder: `config.json` 18:21, snapshots 18:25 to 18:55, `selfplay.csv` 19:01, `eval.json` 19:03, on 2026-10-14.
- Steps: 200,000 decisions of the learner, 5,127 games, 4 updates (snapshots `step_50000.zip` to `step_200000.zip`). The estimate of #76 was 143 steps/s, so about 23 minutes of training; the steps were chosen from it, 4 updates fit the 90-minute budget, so `update_every` stays 50,000.
- Wall clock of the whole command: 2,486 s (41.4 min), including the evaluations at the 4 updates and the final evaluations.

## Files in this folder

The run folder `data/runs/selfplay-1` is ignored by git, so the material the numbers come from is copied to `docs/analysis/2026-10-selfplay-first-run/` (no secrets in it):

- `config.json`, `selfplay.csv`, `eval.json`: copies of the files of the run folder (`selfplay.csv` is also quoted in the table of the updates below).
- `tournament-config.json`: the `config.json` of the tournament run (seats, games, seed, rules).
- `tournament-summary.csv`: wins, draws and losses of every pairing of that tournament, counted from its `results.csv` (10,500 games, not committed).

## Where the numbers come from

- `eval.json` and `selfplay.csv`: win rates and the sampled and greedy evaluation against `random` (`evaluate`, `seed=0`, 500 games, the seat alternates). `selfplay.csv` holds win rates only.
- Tournament of #70 for wins, draws and losses, one tournament, `--games 500 --seed 0 --rules v1.1`, seats `policy:<run folder>` (greedy `PolicyBot`). Field in this order: the learner (`policy:data/runs/selfplay-1`), the untrained network, the snapshots 150,000, 100,000, 50,000 (scratch run folders: `config.json` of the run plus the snapshot as `model.zip`), `bot:random`, `bot:draw20-pts1-points`. Command: `uv run quack-rl tournament --bots "<field>" --games 500 --seed 0 --rules v1.1 --workers 4 --name sp1-final --sample-size 0`. The scratch folders have absolute paths of the engineer's machine, the summary file uses short names.
- Seat caveat: in a tournament the first bot of a pair is p1 in all 500 games (no alternation). Each row below is read as "first bot as p1". The games are not those of `evaluate`, so the rates differ from `selfplay.csv`.
- The untrained network: `MaskablePPO` with `seed=0` and the same construction as at the start of the run, saved as a scratch run folder. Its sampled row against `random` equals `baseline_untrained` of `eval.json` (213 wins).

## Results

Final learner (step 200,000), 500 games per row, seed 0, win rate = wins / games.

| agent | against | games | wins | draws | losses | win rate | source |
|---|---|--:|--:|--:|--:|--:|---|
| learner, greedy, p1 | `random` | 500 | 101 | 2 | 397 | 0.202 | tournament |
| learner, greedy | `random` | 500 | 93 | 68 | 339 | 0.186 | `eval.json` `trained_greedy`, `selfplay.csv` |
| learner, sampled | `random` | 500 | 365 | 45 | 90 | 0.730 | `eval.json` `trained_sampled` |
| learner, greedy, p1 | `draw20-pts1-points` | 500 | 0 | 0 | 500 | 0.000 | tournament (`selfplay.csv`: 0.0) |
| learner, sampled | `draw20-pts1-points` | 500 | 0 | 0 | 500 | 0.000 | `evaluate` |
| learner, greedy, p1 | snapshot 150,000 | 500 | 260 | 10 | 230 | 0.520 | tournament (`selfplay.csv`: 0.424) |
| learner, greedy, p1 | snapshot 100,000 | 500 | 318 | 0 | 182 | 0.636 | tournament (`selfplay.csv`: 0.652) |
| learner, greedy, p1 | snapshot 50,000 | 500 | 310 | 0 | 190 | 0.620 | tournament (`selfplay.csv`: 0.652) |

Baseline: no number of a policy trained against a fixed strong bot (stage #69) is known, so the baseline is the untrained network (same rows, all from the tournament, untrained network as p1, greedy):

| agent | against | games | wins | draws | losses | win rate | source |
|---|---|--:|--:|--:|--:|--:|---|
| untrained, greedy, p1 | `random` | 500 | 85 | 0 | 415 | 0.170 | tournament |
| untrained, sampled | `random` | 500 | 213 | 86 | 201 | 0.426 | `eval.json` `baseline_untrained` |
| untrained, greedy, p1 | `draw20-pts1-points` | 500 | 0 | 0 | 500 | 0.000 | tournament |
| untrained, sampled | `draw20-pts1-points` | 500 | 0 | 0 | 500 | 0.000 | `evaluate` |
| untrained, greedy, p1 | snapshot 150,000 | 500 | 52 | 0 | 448 | 0.104 | tournament |
| untrained, greedy, p1 | snapshot 100,000 | 500 | 97 | 0 | 403 | 0.194 | tournament |
| untrained, greedy, p1 | snapshot 50,000 | 500 | 88 | 0 | 412 | 0.176 | tournament |
| learner, greedy, p1 | untrained, greedy | 500 | 460 | 0 | 40 | 0.920 | tournament |

Snapshots as p1 against the two bots (tournament, 500 games, greedy):

| snapshot | against `random` | against `draw20-pts1-points` |
|---|--:|--:|
| 50,000 | 268 / 7 / 225 (0.536) | 0 / 0 / 500 (0.000) |
| 100,000 | 260 / 1 / 239 (0.520) | 0 / 0 / 500 (0.000) |
| 150,000 | 89 / 10 / 401 (0.178) | 0 / 0 / 500 (0.000) |

Snapshot against snapshot (tournament, wins / draws / losses of the first as p1): 100,000 against 50,000: 214 / 85 / 201 (0.428); 150,000 against 50,000: 292 / 0 / 208 (0.584); 150,000 against 100,000: 320 / 0 / 180 (0.640).

The learner at each update, from `selfplay.csv` (win rate of the greedy learner of that update, 500 games, copied):

| update | vs `random` | vs `draw20-pts1-points` | vs older snapshots | vs previous newest |
|--:|--:|--:|---|--:|
| 50,000 | 0.322 | 0.000 | | |
| 100,000 | 0.322 | 0.000 | 50k: 0.152 | 0.152 |
| 150,000 | 0.186 | 0.000 | 50k: 0.652, 100k: 0.652 | 0.652 |
| 200,000 | 0.186 | 0.000 | 50k: 0.652, 100k: 0.652, 150k: 0.424 | 0.424 |

## Does the learner beat `random`?

It depends on how the policy acts. The sampled policy (the one that trained) beats `random` clearly: 0.730 against 0.426 for the untrained network. The greedy policy (most likely action, used by `PolicyBot`, the tournament and `selfplay.csv`) loses to `random`: 0.186 (`selfplay.csv`) and 0.202 (tournament). In the tournament the greedy snapshots of 50,000 and 100,000 steps still beat `random` (0.536 and 0.520) and the later ones do not (0.178, 0.202), so the greedy read-out got worse against `random` while the learner got better against its own snapshots. The untrained network is also poor when greedy (0.170 in the tournament), so greedy play is a poor read-out of a policy of this size here.

## Does the learner beat the strong heuristic bot?

No. `draw20-pts1-points` won all 500 games against the final learner, sampled and greedy, against every snapshot and against the untrained network. There is no sign of progress against it at any update.

## Progress and cycling against snapshots

Progress: the final learner beats all three older snapshots in the tournament (0.620 against 50,000, 0.636 against 100,000, 0.520 against 150,000), and the snapshots beat each other in order (150,000 against 100,000: 0.640; 150,000 against 50,000: 0.584; 100,000 against 50,000: 0.428 with 85 draws, about level). It beats the untrained network 0.920. So against snapshots there is progress, but the step from 150,000 to 200,000 is small (0.520), and none of it carries over to `random` in the greedy read-out or to the strong bot.

Cycling: the numbers do not show it. A win rate against a fixed snapshot should go up and down over the updates. In `selfplay.csv` the learners of 100,000, 150,000 and 200,000 steps against the snapshot of 50,000 give 0.152, 0.652, 0.652: one jump up, then flat. Against the snapshot of 100,000 the learners of 150,000 and 200,000 give 0.652, 0.652: flat. Against 150,000 there is one value (0.424). In the tournament the learners of 100,000, 150,000 and 200,000 against the snapshot of 50,000 give 0.428, 0.584, 0.620: rising. The sequence 0.152, 0.652, 0.424 that an earlier version of this report called cycling mixes different opponents (the previous newest snapshot changes at each update), so it is not a cycle. There is also no rock-paper-scissors triple: the order 200,000 over 150,000 over 100,000 over 50,000 is consistent in the tournament. With 4 updates and one seed a weak cycle could still be hidden, but this run shows none.

## Time per step against the estimate of #76

#76 measured 143 steps/s with a `PolicyBot` opponent. The first 178 s of the run gave 625 games, about 147 steps/s, which agrees. The whole command took 2,486 s for 200,000 steps, about 80 steps/s, because the evaluations (500 games against `random`, the bot and every snapshot, at each of the 4 updates, plus the final ones) are inside that time. They were not timed separately.

## Conclusion

The environment supports online RL in the narrow sense: the sampled policy learns from self-play and wins 73% against `random` from 43% untrained, and later learners beat the early snapshots (no cycling seen). There is no signal against the strong bot (0 of 500 wins), and the greedy read-out that the loop uses for its numbers is misleading (it loses to `random`, 0.20 in the tournament). The result against the strong bot is negative. The next experiment should evaluate the sampled policy (or fix the greedy read-out) and add the strong bot to the opponent pool, so that the learner meets an opponent that is hard to beat; this is the content of #86.
