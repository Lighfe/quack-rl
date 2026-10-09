# M2.1: bots and balance report

Parent spec: `docs/specs/2026-10-08-quack-rl-design.md` (sections 4.3 and 10). This spec covers the first stage of milestone M2. The RL environment (issue #17) is a later stage.

## Purpose

Bots that play better than `RandomBot`, and a tournament with a balance report. The bots are a tool for balance testing, not for fun or for RL training. The owner wants to see how the game reacts when stop rules, buying habits and prices change.

## Bots

A bot has three parameters: a draw limit, a points round and a strategy. It implements the `quack_rl.runner.Seat` protocol and writes its parameters to the record header, as `RandomBot` does.

### Draw rule

The bot sends Stop when the chance to explode on the next draw is above its draw limit, and Draw otherwise.

- Chance = number of chips in the bag that would push the white total over `explosion_limit`, divided by the bag size. The bag content is public (spec section 5.2), so the bot needs no simulation.
- Three draw limits: careful 15%, medium 30%, greedy 50%. These are start values. The tournament sweeps them in small steps.

### Shop rule

Each shop phase, up to `max_purchases` purchases:

1. From the points round onwards: buy points items first, the biggest affordable one first.
2. With the money left: buy by the strategy's priority list.
3. Stop when nothing is affordable or the purchases are used up.

Ties between equal items are broken by a seeded RNG. Two start values for the points round: 3 and 8. The points round applies to all strategies and is swept by the tournament.

### Strategies

A strategy is data (a priority list and a few weights), not a class.

| Strategy | Idea |
|---|---|
| blue | prefers blue chips and high-value chips |
| green | buys green chips and droplets |
| cleaner | buys `remove_white_1` more often, and adds chips. No droplets: removing white makes the bag better, so each added chip is drawn more often |
| balanced | buys a bit of everything |

### Baseline

A points-only bot: strategy `points` (never buys chips), points round 1, draw limit 30%. Its theoretical maximum is derived by calculation and confirmed by simulation runs. The report compares both.

### Names

A bot name shows all parameters, for example `draw30-pts3-blue`. The seat spec is `bot:<name>` in `play` and `simulate`. The field of the stage: 3 draw limits x 2 points rounds x 4 strategies = 24 bots, plus the baseline = 25.

## Sandbox: ruleset overrides

The owner explores prices and numbers before deciding on a rule change. A decided change becomes a new version file (for example `v1.1.toml`). Exploring does not.

- A function next to `with_rounds` in `src/quack_rl/rules/load.py` takes a ruleset and a map of overrides, for example `shop.droplet_1.price=8`, and returns a changed copy. It rejects unknown keys and validates the result again.
- `play` and `simulate` take the overrides with `--set key=value`.
- The record header stores the base version and the overrides. `verify` rebuilds the ruleset from them and replays the game.
- `v1.toml` stays untouched.

## Tournament

- Input: bots, games per pairing, seed, base version, overrides, sweeps. A sweep is one parameter with a list of values (draw limit, points round, or any override).
- Every pair of bots plays once. Seats are not swapped, because the game has no first-player advantage. One separate run with identical bots on both seats is the seat sanity check.
- The opponents of a sweep are the full field.
- Games per pairing is a parameter. About 120,000 games in a run is normal.
- Runs on several cores, one process per pairing. The first task is a speed measurement.
- Measured with random bots: 5.4 ms and 21.5 KB per game (about 0.9 KB gzipped). 120,000 games take about 11 minutes on one core.

### Storage

```
data/tournaments/<timestamp>-<name>/
  config.json      bots, games per pairing, seed, base version, overrides, sweeps
  results.csv      one row per game: bots, winner, points, explosions
  report.txt       the balance report
  records/         only with --keep-records, gzipped shards
```

By default the run keeps only config and results. The seed recreates any game, and a random sample of games is verified. `--keep-records` writes the records (about 110 MB gzipped for 120,000 games).

## Balance report

Terminal text plus the file. It reads `results.csv` and recomputes nothing from the games.

1. Bot ranking by win rate and average points.
2. Sweeps for each of the 4 strategies: draw limit, points round, and both together as one table (draw limit as rows, points round as columns). Each cell: win rate, share of exploded potions, average final points.
3. Item usage of winning bots.
4. Explosion share and game length.
5. Seat sanity check: p1 and p2 win about 50% with identical bots.
6. Baseline against its theoretical maximum.

Every win rate shows the number of games and a confidence interval. Win rate is the main number, average points the second.

## Issues

1. Ruleset overrides (#16)
2. Bot core (#24)
3. Four shop strategies (new)
4. Tournament runner (#25)
5. Balance report (new)

Blockers: the strategies issue is blocked by the bot core. The runner is blocked by overrides and strategies. The report is blocked by the runner.

## Out of scope

- The RL environment (issue #17), Minari.
- A bot tournament against a reference bot or between strategies chosen by the owner (later).
- Rule changes. A price decision creates a new ruleset version after this stage.
