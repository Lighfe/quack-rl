# Quack RL

A simplified version of The Quacks of Quedlinburg (rules: `docs/rules/rules-v1.md`), built as a recorded game and a reinforcement learning environment. Design: `docs/specs/2026-10-08-quack-rl-design.md`.

## Set-up

Requires [uv](https://docs.astral.sh/uv/).

    uv sync
    uv run quack-rl --help

## Tests

    uv run --with pytest pytest
    HYPOTHESIS_PROFILE=deep uv run --with pytest pytest   # slower, more random games

## Play

    uv run quack-rl play                          # you (p1) vs the random bot
    uv run quack-rl play --p2 human               # hot seat on one keyboard
    uv run quack-rl play --no-bag-assist          # hide the bag contents
    uv run quack-rl play --rounds 4               # a shorter game (default 9)

Keys: `d` draw, `s` stop, `0` done shopping, `1`-`9`/`a`-`c` buy. Your key is not shown.

## Simulate, replay, verify

    uv run quack-rl simulate --games 1000
    uv run quack-rl simulate --games 1000 --rounds 4   # shorter games (default 9)
    uv run quack-rl replay data/records/v1/play/<file>.jsonl
    uv run quack-rl verify data/records/v1/sim/<run>/shard-0001.jsonl --seed-check

Records go to `data/records/` (not committed).

## Tournament run folder

    uv run quack-rl tournament --field small --games 100 --workers 4
    uv run quack-rl report data/tournaments/<run folder>

Each tournament run writes its own folder under `data/tournaments/` (not committed):

- `config.json` - the inputs of the run, the seed scheme and the engine version
- `results.csv` - one row per game: pairing, seats, seed, winner, points, explosions, purchases, draws
- `seats.parquet` - one row per game and seat: money and points per round and the end bag (see below)
- `report.txt` - the balance report, written by `quack-rl report <run folder>`
- `records/` - gzipped game records, only with `--keep-records`

Named fields (`--field`): `full` (25 bots) and `small` (17 bots: draw limit 10/20, points round 4/6, strategies blue, green, cleaner, balanced, plus the baseline `draw20-pts1-points`).

### `seats.parquet`

Apache Parquet, written with pyarrow, zstd compression. Columns in this order:

| column | type | content |
|---|---|---|
| `pairing` | string | as in `results.csv` |
| `sweep_value` | string | as in `results.csv` (`""` without a sweep) |
| `game` | int64 | as in `results.csv` |
| `seed` | int64 | as in `results.csv` |
| `seat` | string | `p1` or `p2` |
| `bot` | string | bot name of that seat, as in the `p1`/`p2` column of `results.csv` |
| `money_r1` .. `money_r<rounds>` | int64 | money of the seat when its shop phase of round k starts (the amount of its `money` event: after the die and the last-round bonus) |
| `points_r1` .. `points_r<rounds>` | int64 | points total of the seat at the end of round k (after the shop) |
| `bag_<chip id>` | int64 | count of that chip id the seat owns at game end (bag plus placed chips), one column for every chip id of the ruleset, in ruleset order, zeros included |

Rows follow the order of `results.csv`, and inside a game first `p1`, then `p2`. Join key to `results.csv`: (`pairing`, `sweep_value`, `game`, `seed`); `seed` alone is also unique in a run.

Missing values: there are none. The engine gives each seat a `money` event in every round (rules 4.3), so every money and points cell is set. The writer never fills in a value (no null, no 0): a missing round value stops the run with an error.

Load it:

    import polars as pl
    seats = pl.read_parquet("data/tournaments/<run folder>/seats.parquet")
    # or: import pandas as pd; seats = pd.read_parquet(".../seats.parquet")
