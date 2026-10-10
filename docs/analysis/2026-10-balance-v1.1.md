# Balance run v1.1: small tournament

Issue #45. Ruleset `v1.1` (9 rounds), run on 2026-10-10. One seat check and one main run on the `small` field. This note describes the setup and the tables of the run; it has no findings.

## Setup

- Machine: Intel(R) Core(TM) i7-8650U @ 1.90GHz (4 physical cores, 8 threads), Ubuntu 24.04.5 LTS, Linux 7.0.0-38-generic, Python 3.12.3
- Code state: commit `3e60cf030d6d5d9ef25de7089db566f51b51a2c6` (clean working tree, `git status --porcelain` empty, during both runs)
- Field: `--field small` = draw limits 10 and 20, points rounds 4 and 6, strategies blue, green, cleaner, balanced (16 bots) plus the baseline `draw20-pts1-points`: 17 bots, 136 pairings, each bot 3,200 games (16 opponents x 200 games). The bot name is `draw<draw limit>-pts<points round>-<strategy>`. Every pairing has a fixed seat order, as in the v1 run: the bot listed first in the field is always p1.

### Commands, seeds, run times

| run | command | seed | games | wall clock |
|---|---|---:|---:|---:|
| seat check | `quack-rl tournament --field small --rules v1.1 --seat-check --games 200 --seed 2000000 --workers 8 --name v1-1-seatcheck` | 2000000 | 3,400 | 10.24 s |
| main run | `quack-rl tournament --field small --rules v1.1 --games 200 --seed 0 --workers 8 --name v1-1-small` | 0 | 27,200 | 77.78 s (1.3 min) |

Both commands were started as `uv run quack-rl ...` from the repo root. Wall clock is measured around the whole command with `/usr/bin/time -f "%e"` (elapsed real time), so it includes the start of `uv run` and the rebuild of the 20 sampled games. The two runs were started one after the other, not in parallel. After each run, `quack-rl report <run folder>` wrote `report.txt` into the run folder.

## Checks

- Seat check (`v1-1-seatcheck`, 17 bots each playing itself, 200 games each, 3,400 games), from the `== Seat check ==` section of its `report.txt`: p1 win rate 50.1%, 95% interval [48.4-51.8%]; p2 win rate 49.9% [48.2-51.6%]; draw share 0.2% of 3,400 games. Verdict line: `Seat check: OK (50% inside the interval of the p1 win rate)`. 50% is inside the interval, so the stop rule did not trigger and the main run was started.
- Sample verification: the seat check ended with `20 sampled games rebuilt from the seed: ok`; the main run ended with `20 sampled games rebuilt from the seed: ok`.

## Ranking

From the `== Ranking ==` section of the main run's `report.txt`, in its order (win rate, then average final points). Win rate over the 16 opponents, a draw counts half, with its 95% Wilson interval in brackets. Average end points is the mean of the bot's final points over its 3,200 games, both seats.

| rank | bot | games | win rate [95% interval] | avg end points |
|--:|---|--:|--:|--:|
| 1 | draw20-pts4-blue | 3,200 | 66.0% [64.3-67.6%] | 27.6 |
| 2 | draw20-pts4-green | 3,200 | 64.5% [62.8-66.1%] | 27.5 |
| 3 | draw20-pts4-balanced | 3,200 | 62.4% [60.7-64.1%] | 27.2 |
| 4 | draw20-pts4-cleaner | 3,200 | 62.0% [60.3-63.7%] | 27.1 |
| 5 | draw10-pts4-green | 3,200 | 52.9% [51.1-54.6%] | 25.8 |
| 6 | draw10-pts4-cleaner | 3,200 | 52.2% [50.4-53.9%] | 25.7 |
| 7 | draw10-pts4-balanced | 3,200 | 52.0% [50.3-53.8%] | 25.6 |
| 8 | draw10-pts6-green | 3,200 | 52.0% [50.2-53.7%] | 24.5 |
| 9 | draw20-pts6-blue | 3,200 | 51.5% [49.8-53.2%] | 24.1 |
| 10 | draw20-pts6-green | 3,200 | 50.4% [48.6-52.1%] | 24.1 |
| 11 | draw10-pts4-blue | 3,200 | 49.5% [47.8-51.3%] | 25.2 |
| 12 | draw10-pts6-blue | 3,200 | 49.2% [47.4-50.9%] | 24.1 |
| 13 | draw10-pts6-cleaner | 3,200 | 45.2% [43.5-47.0%] | 23.1 |
| 14 | draw10-pts6-balanced | 3,200 | 43.5% [41.7-45.2%] | 22.8 |
| 15 | draw20-pts6-balanced | 3,200 | 41.9% [40.2-43.6%] | 22.2 |
| 16 | draw20-pts6-cleaner | 3,200 | 38.3% [36.6-40.0%] | 21.5 |
| 17 | draw20-pts1-points | 3,200 | 16.8% [15.5-18.1%] | 20.4 |

## End bags

Average count of each chip id a bot owns at game end (bag plus placed chips), over all 3,200 games of the bot, both seats, 2 decimals. One column per chip id of the ruleset; all 10 chip ids occur in the end bags of this run. Rows are in the order of the ranking above.

Source: the `end_bags` function of the end bag view of `notebooks/tournament_run.py`, called on `seats.parquet` of the main run (mean of the `bag_<chip id>` columns per bot), rounded to 2 decimals as the notebook does.

| bot | games | white_1 | white_2 | white_3 | orange_1 | blue_1 | blue_2 | blue_4 | green_1 | green_2 | green_4 |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| draw20-pts4-blue | 3,200 | 4.00 | 2.00 | 1.00 | 2.12 | 0.46 | 2.36 | 0.12 | 1.61 | 0.00 | 0.00 |
| draw20-pts4-green | 3,200 | 4.00 | 2.00 | 1.00 | 2.75 | 0.00 | 0.00 | 0.00 | 1.99 | 1.69 | 0.32 |
| draw20-pts4-balanced | 3,200 | 3.78 | 2.00 | 1.00 | 3.16 | 0.00 | 2.23 | 0.00 | 1.23 | 0.00 | 0.00 |
| draw20-pts4-cleaner | 3,200 | 3.82 | 2.00 | 1.00 | 4.64 | 1.43 | 0.38 | 0.00 | 1.24 | 0.45 | 0.00 |
| draw10-pts4-green | 3,200 | 4.00 | 2.00 | 1.00 | 3.01 | 0.00 | 0.00 | 0.00 | 2.29 | 1.53 | 0.18 |
| draw10-pts4-cleaner | 3,200 | 3.91 | 2.00 | 1.00 | 4.66 | 1.69 | 0.31 | 0.00 | 1.46 | 0.29 | 0.00 |
| draw10-pts4-balanced | 3,200 | 3.88 | 2.00 | 1.00 | 3.02 | 0.00 | 2.20 | 0.00 | 1.51 | 0.00 | 0.00 |
| draw10-pts6-green | 3,200 | 4.00 | 2.00 | 1.00 | 3.82 | 0.05 | 0.00 | 0.00 | 2.41 | 2.41 | 1.18 |
| draw20-pts6-blue | 3,200 | 4.00 | 2.00 | 1.00 | 2.49 | 0.69 | 3.26 | 0.99 | 2.15 | 0.00 | 0.00 |
| draw20-pts6-green | 3,200 | 4.00 | 2.00 | 1.00 | 3.70 | 0.12 | 0.00 | 0.00 | 2.38 | 2.14 | 1.48 |
| draw10-pts4-blue | 3,200 | 4.00 | 2.00 | 1.00 | 1.99 | 0.70 | 2.25 | 0.05 | 1.35 | 0.00 | 0.00 |
| draw10-pts6-blue | 3,200 | 4.00 | 2.00 | 1.00 | 2.46 | 0.80 | 3.53 | 0.67 | 2.01 | 0.00 | 0.00 |
| draw10-pts6-cleaner | 3,200 | 3.15 | 2.00 | 1.00 | 6.10 | 2.03 | 0.58 | 0.00 | 1.49 | 0.83 | 0.00 |
| draw10-pts6-balanced | 3,200 | 3.07 | 2.00 | 1.00 | 4.08 | 0.00 | 3.33 | 0.00 | 1.53 | 0.00 | 0.00 |
| draw20-pts6-balanced | 3,200 | 2.72 | 2.00 | 1.00 | 4.12 | 0.00 | 2.97 | 0.00 | 1.37 | 0.00 | 0.00 |
| draw20-pts6-cleaner | 3,200 | 2.80 | 2.00 | 1.00 | 5.85 | 1.67 | 0.47 | 0.00 | 1.41 | 0.83 | 0.00 |
| draw20-pts1-points | 3,200 | 4.00 | 2.00 | 1.00 | 1.44 | 0.00 | 0.00 | 0.00 | 1.00 | 0.00 | 0.00 |

## Raw run and notebook

The two run folders are in `data/tournaments/`. They are not committed (`/data/` is in `.gitignore`):

- seat check: `data/tournaments/2026-10-10_18-32-26+0200-v1-1-seatcheck`
- main run: `data/tournaments/2026-10-10_18-32-45+0200-v1-1-small`

Each folder holds `config.json`, `results.csv`, `seats.parquet` and `report.txt` (no game records, `--keep-records` was not used). To recreate them, run the two commands above at the commit above; every game has its own seed, so the games are the same again, only the folder time stamp and the run time differ.

To open the main run in the notebook (ranking, end bags, money and points per round):

    uv run marimo edit notebooks/tournament_run.py -- --run-folder data/tournaments/2026-10-10_18-32-45+0200-v1-1-small
