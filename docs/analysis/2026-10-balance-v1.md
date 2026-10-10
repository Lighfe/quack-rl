# Balance analysis v1: full tournament run

Issue #31. Ruleset `v1` (9 rounds), run on 2026-10-10. Nothing in `v1.toml` or `src/` was changed. The findings below are first pointers, not conclusions: the field is 25 fixed heuristic bots, so every statement is about these bots.

## Setup

- Machine: Intel(R) Core(TM) i7-8650U @ 1.90GHz (4 physical cores, 8 threads), Linux 7.0.0-38-generic, Python 3.12.3
- Code state: commit `9b7b5f3aeace08429589eb5af22e3ad50c14ba40` (nothing under `src/` changed by this issue)
- Field: `--field full`, 25 bots = 24 bots of the balance grid (draw limit 0/20/40 percent x points round 4/7 x strategy blue/green/cleaner/balanced) plus the baseline `draw20-pts1-points`. The bot name is `draw<draw limit>-pts<points round>-<strategy>`: the bot stops brewing when the chance to explode on the next draw is above the draw limit, and buys points items from the points round on (before that it buys by its strategy). `cleaner` buys Orange 1 chips, `blue` Blue chips, `green` Green chips plus droplets, `balanced` a mix, `points` only points items.
- 25 bots give 300 pairings. Every pairing has a fixed seat order (the bot listed first in the field is always p1).

### Commands, seeds, run times

| run | command | seed | games | wall clock |
|---|---|---:|---:|---:|
| seat check | `quack-rl tournament --field full --seat-check --games 200 --seed 2000000 --workers 8 --name seatcheck` | 2000000 | 5,000 | 14.45 s |
| balance-a | `quack-rl tournament --field full --games 400 --seed 0 --workers 8 --keep-records --sample-size 500 --name balance-a` | 0 | 120,000 | 647.4 s (10.8 min) |
| balance-b | `quack-rl tournament --field full --games 400 --seed 1000000 --workers 8 --keep-records --sample-size 500 --name balance-b` | 1000000 | 120,000 | 665.5 s (11.1 min) |

Wall clock is measured around the whole command (`/usr/bin/time`), so it includes the start of `uv run` and the rebuild of the 500 sampled games. The main runs took about 185 games/s, which is slower than the 306 games/s of `docs/speed-measurement.md` (that was a 5-bot field of 10 pairings with 4 workers, no records; here 8 workers on 4 physical cores and all games recorded).

Both main runs were started one after the other, not in parallel. No `--sweep` was used.

### Where the raw runs were and how to recreate them

The raw folders were in `data/tournaments/` (not committed, `/data/` is in `.gitignore`; about 394 MB per main run with all 120,000 game records, 0.7 MB for the seat check):

- `2026-10-10_13-22-15+0200-seatcheck`
- `2026-10-10_13-22-39+0200-balance-a`
- `2026-10-10_13-33-38+0200-balance-b`

To recreate them, run the three commands above at the commit above. Every game has its own seed (`game_seed = run_seed + pairing_index * games + game_index`), so the games are the same again; only the folder time stamp and the run time differ. The drill-down script was a throwaway (see "How the drill-down was computed").

## Checks

- Seat check (`seatcheck`, 25 bots each playing itself, 200 games each): p1 won 50.4% of the 5,000 games, 95% interval [49.1%, 51.8%]; p2 49.6%; draws 0.6%. The interval contains 50%, so the main runs went on (the stop rule did not trigger).
- Sample verification: both main runs ended with `500 sampled games rebuilt from the seed: ok`; the seat check with `20 sampled games rebuilt from the seed: ok`.
- `quack-rl report <folder>` was run on `balance-a` and `balance-b` (and on `seatcheck`). It writes `report.txt` in each folder.
- `quack-rl verify --seed-check` on a record file of each run: `records/shard-0007.jsonl.gz` of `balance-a`: `400 games ok`; the same shard of `balance-b`: `400 games ok`.
- Cross-check of the drill-down script: the total of draws it counted from the records (15,923,558 in A, 15,926,179 in B) equals the sum of `p1_draws + p2_draws` in `results.csv`.

## Ranking of both runs side by side

Win rate over the 24 opponents (a draw counts half), 9,600 games per bot and run, 95% Wilson interval in brackets (taken from `quack-rl report`). Sorted by the mean of both runs.

| bot | rank A | win A | rank B | win B | mean |
|---|--:|--:|--:|--:|--:|
| draw20-pts4-cleaner | 1 | 80.0% [79.2-80.8] | 1 | 80.2% [79.4-81.0] | 80.1 |
| draw20-pts4-balanced | 2 | 78.2% [77.4-79.1] | 3 | 78.5% [77.7-79.3] | 78.3 |
| draw20-pts4-green | 3 | 78.1% [77.2-78.9] | 2 | 78.5% [77.7-79.3] | 78.3 |
| draw0-pts4-cleaner | 4 | 76.5% [75.6-77.3] | 4 | 75.3% [74.4-76.1] | 75.9 |
| draw0-pts4-balanced | 5 | 72.3% [71.4-73.2] | 5 | 72.0% [71.1-72.9] | 72.2 |
| draw20-pts4-blue | 6 | 71.1% [70.2-72.0] | 6 | 71.5% [70.6-72.4] | 71.3 |
| draw40-pts4-green | 7 | 68.8% [67.9-69.8] | 7 | 68.4% [67.5-69.3] | 68.6 |
| draw0-pts4-green | 9 | 66.7% [65.8-67.6] | 8 | 67.6% [66.6-68.5] | 67.2 |
| draw40-pts4-balanced | 8 | 66.7% [65.8-67.7] | 9 | 67.0% [66.0-67.9] | 66.8 |
| draw40-pts4-blue | 10 | 62.0% [61.1-63.0] | 10 | 62.8% [61.8-63.8] | 62.4 |
| draw0-pts4-blue | 11 | 56.7% [55.7-57.7] | 11 | 57.5% [56.5-58.5] | 57.1 |
| draw40-pts4-cleaner | 12 | 50.8% [49.7-51.7] | 12 | 50.5% [49.5-51.5] | 50.6 |
| draw20-pts7-green | 13 | 42.6% [41.6-43.6] | 13 | 42.3% [41.3-43.3] | 42.5 |
| draw0-pts7-green | 15 | 40.8% [39.9-41.8] | 14 | 40.9% [39.9-41.9] | 40.8 |
| draw0-pts7-cleaner | 14 | 41.1% [40.2-42.1] | 16 | 40.4% [39.4-41.4] | 40.8 |
| draw20-pts7-blue | 16 | 40.4% [39.4-41.4] | 15 | 40.7% [39.8-41.7] | 40.5 |
| draw20-pts1-points | 17 | 38.3% [37.3-39.3] | 17 | 37.7% [36.7-38.7] | 38.0 |
| draw0-pts7-balanced | 18 | 37.4% [36.4-38.3] | 18 | 36.6% [35.7-37.6] | 37.0 |
| draw0-pts7-blue | 19 | 35.0% [34.1-36.0] | 19 | 35.3% [34.3-36.2] | 35.1 |
| draw20-pts7-balanced | 20 | 34.6% [33.7-35.6] | 20 | 34.0% [33.1-35.0] | 34.3 |
| draw20-pts7-cleaner | 21 | 30.0% [29.1-30.9] | 21 | 31.3% [30.4-32.3] | 30.6 |
| draw40-pts7-green | 22 | 27.5% [26.7-28.4] | 22 | 27.9% [27.1-28.8] | 27.7 |
| draw40-pts7-blue | 23 | 23.2% [22.4-24.1] | 23 | 23.3% [22.4-24.1] | 23.2 |
| draw40-pts7-balanced | 24 | 18.3% [17.5-19.1] | 24 | 17.8% [17.0-18.5] | 18.1 |
| draw40-pts7-cleaner | 25 | 12.8% [12.1-13.4] | 25 | 12.0% [11.4-12.7] | 12.4 |
top both {'draw0-pts4-cleaner', 'draw20-pts4-balanced', 'draw20-pts4-green', 'draw20-pts4-cleaner', 'draw0-pts4-balanced'} top one set()

Stability: the top group is the top 5 and the bottom group the bottom 5 of 25.

- Top 5 in run A and in run B: the same five bots (`draw20-pts4-cleaner`, `draw20-pts4-balanced`, `draw20-pts4-green`, `draw0-pts4-cleaner`, `draw0-pts4-balanced`).
- Bottom 5 in run A and in run B: the same five bots (`draw20-pts7-cleaner`, `draw40-pts7-green`, `draw40-pts7-blue`, `draw40-pts7-balanced`, `draw40-pts7-cleaner`).
- Bots that are in the top or bottom group in only one run: none. No bot is unstable at this level.
- Only neighbours swap ranks between the runs (2/3, 8/9, 14/15/16), and their intervals overlap: these swaps are noise, not differences. The win rates of the two runs differ by at most 1.3 points for any bot.

The ranking has two blocks: ranks 1 to 12 are exactly the 12 bots with points round 4 (from 80.1% down to 50.6%), ranks 13 to 25 are the 12 bots with points round 7 and the pure-points baseline `draw20-pts1-points` (38.0%, rank 17; 42.5% down to 12.4%). Every `pts4` bot is above every `pts7` bot.

### Main-run seat share is not a seat measurement

In the main runs p1 won 61.0% (A) and 61.0% (B) of the games (73,128 and 73,237 of 120,000; 0.2% draws). This does not say that seat 1 is better: in every pairing the bot listed first in the field is p1, and the field lists the `pts4` bots first. The seat check (above) is the clean measure: 50.4% [49.1%, 51.8%]. To measure the seat in mixed pairings a later run needs both seat orders per pairing (a feature, not part of this issue).

## Item usage, explosion share and game length

Both runs, A / B. Average purchases per game and strategy, only in games the bot seat won (`quack-rl report`, "Item usage of winning bots"):

| item | blue | green | cleaner | balanced | points |
|---|---|---|---|---|---|
| orange_1 | 0 | 0 | 10.75 / 10.80 | 3.21 / 3.20 | 0 |
| blue_1 | 2.03 / 2.02 | 0 | 0 | 0 | 0 |
| blue_2 | 2.53 / 2.52 | 0 | 0 | 0.59 / 0.60 | 0 |
| blue_4 | 0.36 / 0.36 | 0 | 0 | 0 | 0 |
| green_1 | 0 | 1.51 / 1.52 | 0 | 0 | 0 |
| green_2 | 0 | 1.13 / 1.14 | 0 | 0.49 / 0.49 | 0 |
| green_4 | 0 | 0.65 / 0.64 | 0 | 0 | 0 |
| remove_white_1 | 0 | 0 | 0.53 / 0.52 | 0.38 / 0.38 | 0 |
| droplet_1 | 0 | 1.65 / 1.64 | 0 | 1.81 / 1.79 | 0 |
| points_2 | 2.41 / 2.40 | 2.29 / 2.28 | 2.21 / 2.23 | 2.11 / 2.13 | 8.30 / 8.28 |
| points_5 | 2.69 / 2.69 | 2.84 / 2.85 | 2.92 / 2.91 | 2.99 / 2.99 | 1.32 / 1.29 |
| points_10 | 0.71 / 0.71 | 0.73 / 0.73 | 0.69 / 0.69 | 0.68 / 0.68 | 0.04 / 0.04 |
| won games | 27,636 / 27,879 | 31,097 / 31,191 | 27,885 / 27,734 | 29,441 / 29,287 | 3,670 / 3,616 |

Explosion share (exploded potions / potions played) and draws per game (both seats summed), per strategy, A / B:

| strategy | explosion share | draws per game |
|---|---|---|
| blue | 17.4% / 17.3% | 131.0 / 131.0 |
| green | 14.9% / 14.9% | 125.6 / 125.7 |
| cleaner | 24.5% / 24.4% | 149.1 / 149.1 |
| balanced | 16.0% / 16.0% | 127.8 / 127.8 |
| points | 9.1% / 9.4% | 114.3 / 114.4 |
| overall | 17.8% / 17.8% | 132.7 / 132.7 |

By draw limit (from the sweep tables of the reports, run A, all four strategies alike): draw limit 0 gives 0.0% explosions, draw limit 20 about 14 to 22%, draw limit 40 about 31 to 51% (the cleaner is at the top end of both ranges). Points per game of the same bots: 22 to 25 at limit 0, 24 to 25 at 20 (23.6 for cleaner), 18 to 22 at 40.

Ties after the last round: 271 (A) and 293 (B) of 120,000 games, 0.2%.

## Drill-down

### How the drill-down was computed

A throwaway script (not committed, kept in the scratch folder) reads every game of the kept records of one run (all 300 `records/shard-*.jsonl.gz`, so all 120,000 games, not a sample). A bot has 9,600 games in a run (both seats counted). Per bot and seat it takes:

- Ending bag (chips by type): the start bag of `v1` (White 1 x4, White 2 x2, White 3 x1, Orange 1 x1, Green 1 x1) plus every chip bought in the shop (`buy` events of chip items), plus every Orange 1 chip from the bonus die (`die` event with face `orange_1`), minus a White 1 for every `remove_white_1` purchase. Average over the games of the bot. The bag is taken at game end and does not include the droplet or points.
- First three buys: the items of the first three `buy` events of the seat in the game, in order. The table gives the most common items per position and the most common opening of three.
- Draws per round: the number of steps in which the seat chose the action `draw`, divided by 9 rounds, averaged over all games of the bot (it is the same counter as `p1_draws`/`p2_draws` in `results.csv`, and the totals match).
- Median bot: the bot at rank 13 of 25 (the middle of the ranking), `draw20-pts7-green` (42.5% / 42.3%), is the comparison.

Selection: the three strongest and the three weakest bots that are stable in both runs: these are the top 3 and the bottom 3 of the table (the first three of the table: `draw20-pts4-cleaner`, `draw20-pts4-green`, `draw20-pts4-balanced`; the last three: `draw40-pts7-cleaner`, `draw40-pts7-balanced`, `draw40-pts7-blue`). All six are in the top 3 / bottom 3 in both runs, apart from the order inside the group.

The two runs give the same numbers to the second decimal (differences at most 0.04 chips, 0.02 draws per round, 0.1 points). The tables show run A; run B is in the Appendix.

### Average ending bag, draws per round and points (run A)

| bot | rank A / B | white_1 | white_2 | white_3 | orange_1 | blue_1 | blue_2 | blue_4 | green_1 | green_2 | green_4 | bag size | draws/round | buys/game | points |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| draw20-pts4-cleaner | 1 / 1 | 3.87 | 2.00 | 1.00 | 11.47 | 0 | 0 | 0 | 1.00 | 0 | 0 | 19.34 | 9.18 | 16.31 | 29.4 |
| draw20-pts4-green | 3 / 2 | 4.00 | 2.00 | 1.00 | 1.81 | 0 | 0 | 0 | 2.36 | 1.10 | 0.08 | 12.35 | 6.30 | 10.72 | 29.3 |
| draw20-pts4-balanced | 2 / 3 | 3.96 | 2.00 | 1.00 | 4.51 | 0 | 0.58 | 0 | 1.00 | 0.46 | 0 | 13.51 | 6.59 | 11.97 | 29.3 |
| median: draw20-pts7-green | 13 / 13 | 4.00 | 2.00 | 1.00 | 1.95 | 0 | 0 | 0 | 2.76 | 1.27 | 1.64 | 14.62 | 6.76 | 10.83 | 20.5 |
| draw40-pts7-blue | 23 / 23 | 4.00 | 2.00 | 1.00 | 1.73 | 3.07 | 2.98 | 0.89 | 1.00 | 0 | 0 | 16.67 | 8.44 | 10.75 | 16.3 |
| draw40-pts7-balanced | 24 / 24 | 2.83 | 2.00 | 1.00 | 6.40 | 0 | 0.50 | 0 | 1.00 | 0.63 | 0 | 14.36 | 7.75 | 12.67 | 15.2 |
| draw40-pts7-cleaner | 25 / 25 | 2.81 | 2.00 | 1.00 | 14.11 | 0 | 0 | 0 | 1.00 | 0 | 0 | 20.92 | 11.15 | 17.37 | 13.5 |

(`buys/game` counts all shop purchases, points items included; the maximum is 27 = 3 per round x 9 rounds. The Orange 1 count includes the start chip and the bonus-die chips.)

### First three buys (run A)

Share of the games of the bot in which the item was bought at that position; most common items only.

| bot | buy 1 | buy 2 | buy 3 | most common opening |
|---|---|---|---|---|
| draw20-pts4-cleaner | orange_1 100% | orange_1 100% | orange_1 100% | orange_1, orange_1, orange_1 (100%) |
| draw20-pts4-green | green_2 62%, green_1 24%, droplet_1 14% | droplet_1 50%, green_2 37%, green_1 12% | droplet_1 68%, green_1 13%, green_2 11% | green_2, droplet_1, droplet_1 (25%) |
| draw20-pts4-balanced | green_2 33%, blue_2 28%, orange_1 25% | droplet_1 45%, orange_1 27%, blue_2 19% | droplet_1 64%, orange_1 20%, blue_2 10% | green_2, droplet_1, droplet_1 (13%) |
| median: draw20-pts7-green | green_2 62%, green_1 23%, droplet_1 15% | droplet_1 51%, green_2 37%, green_1 12% | droplet_1 67%, green_1 13%, green_2 11% | green_2, droplet_1, droplet_1 (25%) |
| draw40-pts7-blue | blue_2 58%, blue_1 42% | blue_2 69%, blue_1 31% | blue_2 65%, blue_1 32%, blue_4 3% | blue_2, blue_2, blue_2 (24%) |
| draw40-pts7-balanced | droplet_1 28%, blue_2 28%, orange_1 24% | droplet_1 53%, orange_1 27%, blue_2 15% | droplet_1 53%, orange_1 39%, remove_white_1 3% | droplet_1 x3 (13%) |
| draw40-pts7-cleaner | orange_1 100% | orange_1 100% | orange_1 100% | orange_1 x3 (100%) |

The bots choose by a fixed strategy list (the first affordable item of the list), so the opening follows from the list and the money of the first rounds; the variation inside one bot comes from the dice and the cards drawn.

### What the drill-down shows

- Strongest vs median: `draw20-pts4-green` and the median bot `draw20-pts7-green` play the same strategy with the same draw limit and almost the same opening (green_2, then droplets). The difference is the points round. The median bot spends money on Green 4 (1.64 in the bag at the end against 0.08) and ends with 20.5 points; the top bot starts buying points in round 4 and ends with 29.3. Both draw about 6.3 to 6.8 times per round.
- The two cleaner bots (`draw20-pts4-cleaner` best, `draw40-pts7-cleaner` worst) buy the same three Orange 1 chips in every game. They have the biggest bags (19 to 21 chips) and draw 9.2 to 11.2 times per round. The difference between them (80.1% against 12.4%) is only the draw limit and the points round, not the items, and not the buy order.
- The weakest bots are weak because of the late points round, not because of unusual bags: `draw40-pts7-blue` has the normal blue bag (Blue 1 x3, Blue 2 x3, Blue 4 x0.9). The weakest three also draw more (7.8 to 11.2 per round, draw limit 40) and explode more: explosion share 39.9% (blue), 36.7% (balanced) and 53.7% (cleaner), against 13.5% to 19.6% for the three strongest and 14.4% for the median bot (explosion share per bot cell from the sweep tables of the report of run A).
- The first three buys of the strongest and the median bot are almost the same, so the opening is not what separates them.

## Findings that matter for balance

Certainty scale: "stable" = same result in run A and run B (the runs use different seeds); "drill-down" = the kept records support it; "pointer" = a first sign, only from the win rates or the usage tables, to be tested by a sweep. All bots are fixed rules and the field is 12 `pts4` bots, 12 `pts7` bots and the baseline, so what wins here is relative to this field. No rule file is changed; each proposal is a candidate for a later ruleset version (a new file, not an edit of `v1.toml`).

1. **The points round decides the ranking.** All 12 `pts4` bots rank above all 13 other bots (50.6% to 80.1% against 12.4% to 42.5%); with the same strategy and draw limit the move from points round 7 to 4 is worth 22 to 50 win-rate points (e.g. green at limit 20: 78.1% against 42.6%; cleaner at limit 40: 50.8% against 12.8%). The drill-down shows why: `draw20-pts4-green` and the median bot buy the same chips and openings, but the median bot spends on Green 4 (1.64 per bag against 0.08) and ends with 20.5 instead of 29.3 points. The pure-points bot (points from round 1, no chips) is not good either (38.0%, 21.9 points), so there is a best moment between round 1 and round 7 that this run does not locate. Certainty: stable, supported by the drill-down; the position of the optimum is only a pointer (only rounds 1, 4 and 7 were played). Candidate: make early points less attractive or late points more attractive, for example `shop.points_5.price` 13 to 15 and `shop.points_2.price` 6 to 7 (the points items are what a `pts4` bot buys from round 4 on: per won game of the four chip strategies 2.1 to 2.4 Points 2, 2.7 to 3.0 Points 5 and 0.7 Points 10).

2. **No single strategy dominates, but cheap Orange 1 dilution is the strongest chip purchase at the right draw limit.** `draw20-pts4-cleaner` is rank 1 in both runs (80.0% / 80.2%); `draw20-pts4-green` and `draw20-pts4-balanced` are within 2 points (78.1% to 78.5%). The cleaner buys Orange 1 (price 3) in 100% of its first three buys and ends with 11.5 Orange chips in a 19-chip bag, so it draws 9.2 times per round against 6.3 for green. The same strategy is rank 25 (12.4%) at draw limit 40 with points round 7, so the item alone is not dominant. Certainty: the position is stable and supported by the drill-down; "too strong" is only a pointer. Candidate: `shop.orange_1.price` 3 to 4.

3. **The expensive chips are not bought by the best bots.** In the three strongest bots Blue 4 is never in the bag and Green 4 almost never (0.08 in `draw20-pts4-green`, none in the other two), and `remove_white_1` is bought 0.4 to 0.5 times per won game by cleaner and balanced bots only (Blue and Green strategies never buy it). Green 4 (14) and Blue 4 (16) show up mostly in bots from the lower half (Green 4: 1.64 in the median bot; Blue 4: 0.89 in `draw40-pts7-blue`). Points 10 (22) is bought 0.7 times per won game by the four chip strategies, 0.04 by the pure-points bot. Certainty: stable (same usage in both runs); the drill-down supports "the best bots do not use it"; whether the price is the reason is a pointer, because the bots follow a fixed list. Candidate: `shop.green_4.price` 14 to 11 and `shop.blue_4.price` 16 to 12 (so the 4-value chips are an option), `shop.remove_white_1.price` 15 to 10.

4. **The droplet is an early buy of the green and balanced bots.** `droplet_1` (price 10) is the most common second and third buy of `draw20-pts4-green` (50% and 68%) and of `draw20-pts4-balanced` (45% and 64%); the opening "green_2, droplet_1, droplet_1" is the most common one (25%). It is a part of the winning line of two of the three best bots. Certainty: pointer (the bots buy it by their list; the runs do not compare with and without). Candidate: `shop.droplet_1.price` 10 to 12.

5. **At points round 4, draw limit 20 is best for every strategy; 0 and 40 are worse.** For blue, green, cleaner and balanced at points round 4 limit 20 always beats 0 and 40 (at points round 7 it holds for blue, green and balanced; the cleaner is best at limit 0 there, 41.1% against 30.0%): e.g. green 78.1% / 66.7% / 68.8% (limit 20 / 0 / 40), cleaner 80.0% / 76.5% / 50.8%. At limit 40 the explosion share is 31% to 51%. Certainty: stable, drill-down not needed; only three limits tested, so the optimum between 0 and 40 is a pointer. This says more about the explosion limit (7 for the white total) than about a rule fault. Candidate: none now; sweep `draw_limit` first (below), then look at `explosion_limit`.

6. **No seat advantage, no game length problem.** Seat check: p1 wins 50.4% [49.1%, 51.8%] over 5,000 games, the interval contains 50% (one run only; there is no second seat-check run). The games are 114 to 149 draws long (both seats summed, 132.7 on average, i.e. about 7.4 draws per seat and round); ties are 0.2%. Overall explosion share is 17.8%. Candidate: none.

Not found: a chip that nobody buys at all (every chip of the shop is bought by some bot, Blue 4 and Green 4 least), and no bot with a winning rate above 80.2%, so no single bot beats the whole field by a wide margin. Whether 80% is "too strong" depends on the owner's target and the field (12 of the 24 opponents are bots with the late points round).

## Sweep runs the findings suggest (proposals, none is run here)

Each is `quack-rl tournament --field full --games 200 --workers 8 --sweep <parameter>=<values> --name <name>` on a seed of its own, the same field; 200 games per pairing and value would give 60,000 games per value.

| for finding | parameter | values | question |
|---|---|---|---|
| 1 | `points_round` | 2,3,4,5,6 | where is the best moment to start buying points, and how steep is the optimum? |
| 1 | `shop.points_5.price` | 11,13,15,17 | how much does the Points 5 price move the pts4/pts7 gap? |
| 1 | `shop.points_2.price` | 5,6,7,8 | the same for Points 2 (the pure-points bot buys 8.3 of them per won game) |
| 2 | `shop.orange_1.price` | 3,4,5 | how much of the cleaner lead is the Orange 1 price? |
| 3 | `shop.green_4.price` and `shop.blue_4.price` (one run each) | 10,12,14 and 12,14,16 | do the 4-value chips enter the best bots' bags at a lower price? |
| 3 | `shop.remove_white_1.price` | 8,10,12,15 | is removing White 1 worth it at a lower price? |
| 4 | `shop.droplet_1.price` | 8,10,12,14 | how much of the green/balanced lead is the droplet? |
| 5 | `draw_limit` | 10,15,20,25,30 | where is the best draw limit between 0 and 40? |
| 5 | `explosion_limit` | 6,7,8 | how does the explosion threshold move the best draw limit? |

A second round should add both seat orders per pairing (a missing feature, not a request for this issue) so that a seat effect in mixed pairings can be told from the field order.

## Appendix: run B drill-down

Same computation as for run A (ending bag, draws per round, buys per game, points; averages over 9,600 games per bot).

| bot | white_1 | white_2 | white_3 | orange_1 | blue_1 | blue_2 | blue_4 | green_1 | green_2 | green_4 | bag size | draws/round | buys/game | points |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| draw20-pts4-cleaner | 3.88 | 2.00 | 1.00 | 11.51 | 0.00 | 0.00 | 0.00 | 1.00 | 0.00 | 0.00 | 19.38 | 9.19 | 16.35 | 29.4 |
| draw20-pts4-green | 4.00 | 2.00 | 1.00 | 1.80 | 0.00 | 0.00 | 0.00 | 2.35 | 1.09 | 0.09 | 12.33 | 6.29 | 10.71 | 29.4 |
| draw20-pts4-balanced | 3.96 | 2.00 | 1.00 | 4.47 | 0.00 | 0.57 | 0.00 | 1.00 | 0.46 | 0.00 | 13.46 | 6.58 | 11.95 | 29.3 |
| draw20-pts7-green | 4.00 | 2.00 | 1.00 | 1.95 | 0.00 | 0.00 | 0.00 | 2.79 | 1.28 | 1.63 | 14.64 | 6.77 | 10.83 | 20.4 |
| draw40-pts7-blue | 4.00 | 2.00 | 1.00 | 1.72 | 3.08 | 2.99 | 0.89 | 1.00 | 0.00 | 0.00 | 16.68 | 8.43 | 10.74 | 16.2 |
| draw40-pts7-balanced | 2.85 | 2.00 | 1.00 | 6.42 | 0.00 | 0.50 | 0.00 | 1.00 | 0.64 | 0.00 | 14.41 | 7.75 | 12.67 | 15.2 |
| draw40-pts7-cleaner | 2.83 | 2.00 | 1.00 | 14.12 | 0.00 | 0.00 | 0.00 | 1.00 | 0.00 | 0.00 | 20.94 | 11.14 | 17.37 | 13.4 |

The first three buys of run B equal run A within 2 points in every share (for example `draw20-pts4-green`: green_2 62%, green_1 23%, droplet_1 15% at buy 1; droplet_1 50% and 68% at buys 2 and 3), and the most common openings are the same.
