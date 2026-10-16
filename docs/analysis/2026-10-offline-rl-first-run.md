# Offline RL, first run

Issue #90. One policy trained by masked behaviour cloning on the dataset of #89 only (no game played in training), then two 500-game tournaments, run on 2026-10-16. Method: `docs/analysis/2026-10-offline-rl-research.md` (Parquet, masked cross-entropy, plain PyTorch, no new dependency). Code: `src/quack_rl/rl/offline.py`, `scripts/train_offline.py`. The run folder `data/runs/offline-bc-1` and the dataset are not committed (`data/` is ignored); the material is copied to `docs/analysis/2026-10-offline-rl-first-run/`.

## Headline

The policy, playing first (p1) against `draw20-pts4-green`, 500 games, seed 0, rules `v1.1`: 236 wins, 1 draw, 263 losses, win rate 0.472 (236 / 500). The win rate is above 10% (0.472, above). Source: `tournament-p1-summary.csv`, `result.json`. No retry was needed; this is the only attempt.

## Results

Win rate = wins / games, a draw is not a win. 500 games per row, seed 0, greedy `PolicyBot`.

| policy seat | against | games | wins | draws | losses | win rate | source |
|---|---|--:|--:|--:|--:|--:|---|
| p1 (headline) | `draw20-pts4-green` | 500 | 236 | 1 | 263 | 0.472 | `tournament-p1-summary.csv` |
| p1 | `random` | 500 | 500 | 0 | 0 | 1.000 | `tournament-p1-summary.csv` |
| p1 | `draw20-pts1-points` | 500 | 447 | 4 | 49 | 0.894 | `tournament-p1-summary.csv` |
| p2 (context) | `draw20-pts4-green` | 500 | 232 | 4 | 264 | 0.464 | `tournament-p2-summary.csv` (row "green as p1 against the policy") |
| p2 | `random` | 500 | 500 | 0 | 0 | 1.000 | `tournament-p2-summary.csv` |
| p2 | `draw20-pts1-points` | 500 | 427 | 2 | 71 | 0.854 | `tournament-p2-summary.csv` |

Reference rows of the same tournaments (bots only): `draw20-pts4-green` as p1 against `draw20-pts1-points`: 0.896 (p1 tournament), 0.920 (p2 tournament); against `random`: 1.000. So the policy plays at about the level of the bot it imitates most closely, and clearly above `draw20-pts1-points` (the baseline bot) in both seats. The p2 rows are context only; the target is judged on the headline row. Both tournaments also played the bot pairs (3,000 games each), see the summary files.

## What the dataset contained

`data/datasets/full.parquet`: 5,000 games, 413,471 rows (decisions of the recording seat), seed 0, default bot mix of #89 (`full.json`, unchanged). Recording seat's result per game from the reward sum (win above 0, loss below 0, draw 0). Numbers from `dataset-stats.py` (columns `episode`, `reward`, `bot` only), output `dataset-stats.csv`:

| recorded bot | games | share | wins | draws | losses | win rate |
|---|--:|--:|--:|--:|--:|--:|
| `draw10-pts4-balanced` | 780 | 15.6% | 367 | 34 | 379 | 0.4705 |
| `draw20-pts4-balanced` | 854 | 17.1% | 480 | 22 | 352 | 0.5621 |
| `draw20-pts4-blue` | 825 | 16.5% | 498 | 33 | 294 | 0.6036 |
| `draw20-pts4-cleaner` | 864 | 17.3% | 499 | 22 | 343 | 0.5775 |
| `draw20-pts4-green` | 853 | 17.1% | 520 | 36 | 297 | 0.6096 |
| `random` | 824 | 16.5% | 69 | 22 | 733 | 0.0837 |
| all | 5,000 | 100% | 2,433 | 169 | 2,398 | 0.4866 |

The policy learns from all of these games alike, including the 16.5% of `random` games and the lost games (no weighting by result; return-aware variants are out of scope).

## Training

- Model: policy network of a `MaskablePPO` built from the observation size 848 and `Discrete(15)` (two layers of 256 units, tanh), no environment; saved as `model.zip`, so `load_model` and `PolicyBot.from_run` work unchanged. Loss: `logits.masked_fill(mask == 0, -1e9)`, then cross-entropy. Adam, learning rate 0.001, batch 256 rows drawn at random, 30,000 gradient steps (about 18.6 epochs), seed 0, CPU. The final logged loss is about 0.11 and the training accuracy about 0.95 (`metrics.csv`, means over 100 steps; no held-out split was made).
- Files: `config.json`, `metrics.csv` (step, loss, accuracy), the dataset stats, `result.json`, the tournament summaries and configs (made from `results.csv` by `tournament-summary.py`; the 3,000-row `results.csv` files are not committed).
- Steps: no tuning. The step count was picked from a 2,000-step probe (13 s) so that the full run fits in a few minutes; the probe run was deleted and not evaluated.

## Time, machine, memory

All heavy runs ran inside `systemd-run --user --scope -p MemoryMax=<cap> -p MemorySwapMax=0`; none hit the cap. Peak = maximum resident set size from `/usr/bin/time -v` run inside the scope (the largest single process, not the scope total).

| run | cap | wall clock | peak | exit |
|---|---|--:|--:|--:|
| training, 30,000 steps | 4G | 193.8 s (load 7.7 s, train 183.8 s) | 2,175,080 kB | 0 |
| tournament p1, 3,000 games | 2G, CPUQuota 400% | 889 s | 767,720 kB | 0 |
| tournament p2, 3,000 games | 2G, CPUQuota 400% | 946 s | 812,320 kB | 0 |
| full test command | 4G, CPUQuota 400% | 217 s | 1,047,036 kB | 0 |

Machine: Intel Core i7-8650U, 8 logical cores, 15 GB RAM, Python 3.12.3, torch 2.14.1, CPU only.

Commands (repo root):

- `systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 /usr/bin/time -v uv run --group train python scripts/train_offline.py --dataset data/datasets/full.parquet --run offline-bc-1 --steps 30000 --seed 0`
- `systemd-run --user --scope -p MemoryMax=2G -p MemorySwapMax=0 -p CPUQuota=400% /usr/bin/time -v uv run --group train quack-rl tournament --bots "policy:data/runs/offline-bc-1,bot:draw20-pts4-green,bot:random,bot:draw20-pts1-points" --games 500 --seed 0 --rules v1.1 --workers 4 --name off1-p1 --sample-size 0`
- the same with the field `bot:draw20-pts4-green,bot:random,bot:draw20-pts1-points,policy:data/runs/offline-bc-1` and `--name off1-p2`
- `uv run python docs/analysis/2026-10-offline-rl-first-run/dataset-stats.py data/datasets/full.parquet docs/analysis/2026-10-offline-rl-first-run/dataset-stats.csv`

Seat caveat: in a tournament the first bot of a pair is p1 in all 500 games. A policy as p2 is read from the rows with the bot first.

## Conclusion

Behaviour cloning on 5,000 bot games gives a policy that wins 47% of games against `draw20-pts4-green` (target: above 10%), 89% against `draw20-pts1-points` and all games against `random`, in about 3 minutes of CPU training, which is far better than the online self-play run (0 of 500 against the strong bot). One seed and one run: the numbers show the first attempt, not a spread. The policy was cloned from bots that include `draw20-pts4-green` itself, so matching that bot's level is the expected result, not a surprise.
