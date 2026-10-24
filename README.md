# Quack RL

A simplified version of The Quacks of Quedlinburg (rules: `docs/rules/rules-v2.1.md`), built as a recorded game and a reinforcement learning environment. Design: `docs/specs/2026-10-08-quack-rl-design.md`. What is left after the retirement before v2, the archived ruleset v2 and the old code, is in `archive/` (`archive/README.md`).

## Rulesets

| Version | Rules document | Notes |
|---|---|---|
| `v2.1` | `docs/rules/rules-v2.1.md` | the only ruleset and **the default** (in progress: it has the numbers of the archived v2 and the stage changes it in place): a shared point board (fields 0 to 50, two laps, at most 100 points), rat tails with a catch-up bonus at round start, a new die, a card at the start of every round |

Name it with `--rules v2.1` (CLI) or `rules="v2.1"` (code); it is also what you get without naming a version. The older rulesets (v1 to v1.11), their rules documents and their saved data are history under `archive/`. Ruleset v2 is archived too (files listed in `archive/README.md`): `--rules v2` is an error.

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

The game is played with ruleset `v2.1`, the only ruleset and the default. `--rules v2` is an error: v2 is archived.

Keys: `d` draw, `s` stop, `0` done shopping, `1`-`9`/`a`-`c` buy. Your key is not shown.

## RL environment

Two environments over the same engine (`quack_rl.rl`). The reward is `reward(final_state, seat)`: +1 for more points, -1 for fewer, 0 for a draw, given once at the end of the game. Both take `reward_fn` to replace it.

    from quack_rl.rl import QuackEnv, QuackParallelEnv

    env = QuackEnv(seat="p1", opponent=None, rules="v2.1")   # Gymnasium, one seat against a bot
    obs, info = env.reset(seed=0)
    obs, reward, terminated, truncated, info = env.step(int(info["action_mask"].argmax()))

    penv = QuackParallelEnv(rules="v2.1")                    # PettingZoo, both seats act
    obs, infos = penv.reset(seed=0)                          # obs[seat]["observation"], ["action_mask"]

- `QuackEnv`: `seat` is `"p1"`, `"p2"` or `"random"` (per episode). `opponent` is any bot with `choose(state, seat, legal)`; `None` is `RandomBot`. The opponent acts inside `step`, and steps where the agent can only `Wait` are skipped. `info["action_mask"]` and `env.action_masks()` (for `MaskablePPO`) give the legal actions; at the terminal step the mask is all zero (no legal action).
- Observation: a flat `float32` vector of the agent's view, called observation layout 7 (`BOARD_LAYOUT = 7` in `quack_rl.rl`; layouts 2 to 6 are archived in `archive/src/quack_rl/rl/encode.py`). No hidden information: the draw order of the bag and the opponent's pending choice never appear; both bags and the placed chips are public. The entry names, in order, are `vector_names(rs)`; the layout depends only on the ruleset. The groups, in order:
  - shared: `round`, `rounds` (total number of rounds), `explosion_limit`, phase (one-hot)
  - own seat, then the opponent: status (one-hot), chip colours bought this round, `money`, `white_total`, `ruby_fields_ahead`, `points`, `droplet_halves`, `purchases`, `chip_purchases`, `shop_done`, and per chip id `bag.remaining.<id>` (still in the bag) and `bag.owned.<id>` (bag plus placed chips)
  - the derived features (below), then the board map as the last block
  - Derived features (`derived(state, rs, seat)` in `quack_rl.rl.derive`), per seat as `own.<name>` and `opponent.<name>`: `scoring_field`, `ruby_at_scoring_field`, `money_if_stop` (money table at the scoring field, 0 in the last round; no bonus die, no round-end bonus), `limit_distance` (explosion limit minus white total, negative after an explosion), `explosion_chance` (of the next draw, same function as the heuristic bot; 0 for an empty bag), `rolls_die` (1 when the seat is not exploded and its scoring field is the best among non-exploded seats; a tie gives both seats 1), `chips_placed`; plus the shared `point_delta` (own points minus opponent points). They use the engine helpers and the ruleset tables, no rule code is copied.
  - Rule of thumb: generic rules (fields, the money table, rubies, the explosion limit, the die, points) are derived; specific rules (what one colour or chip does, the round-end droplet bonus, the buy options) are not. The model learns those from the board and the Shop mask.
  - `money` is the budget in the Shop phase and the value of the last Resolve otherwise. Values are raw, not scaled.
  - The map has one row per field `0..track_end` and `map_channels(rs)` channels (23): `money`, `points` (the points for scoring on that field) and `ruby` of the field, then for `own` and for `opponent` one flag per colour, `value` and `order` of the chip that lies on the field (all zero without a chip; `order` is 1 for the first chip of the round; if several chips land on the last field the later one fills it). Reshape it with `vec[map_slice(rs)].reshape(rs.track_end + 1, map_channels(rs))`.
  - The phase list holds the card phases, and a card block sits before the map: `card.<kind>` (the card of the round, one entry per card kind), `deck.<kind>` (cards left in the deck), `restart.available`, and the resolved round-end drops. The pending choice of the opponent is not in it.
  - Board block (`docs/specs/2026-10-22-ruleset-v2.md`): per seat `<who>.board.marker.<k>` (one-hot, `k` in 0..50), `<who>.board.has_50pts` and `<who>.rat_tail`, then `board.tail.<f>` (1 when a rat tail lies after field `f`). All of it is open information. The points entries are bounded 0 to 100. No policy is trained on layout 7; policy entry points refuse it.
  - `observation_bounds(rs)` gives `(low, high)`: finite for flags, fields and ruleset constants, `inf` where there is no real bound (points, money, bag counts); both envs use it in their observation space.
- Actions: `Discrete(n)`, the names are `action_names(rs)` from `quack_rl.engine`. The mask is 1 for legal actions.

## Training

There is no training in the repo now. The training stack (trainers, self-play, offline and replay code, the dataset builder, the evaluator and `PolicyBot`) is in `archive/` with its tests and scripts, and nothing imports it. Training is rebuilt on ruleset v2.1.

## Simulate, replay, verify

    uv run quack-rl simulate --games 1000
    uv run quack-rl simulate --games 1000 --rounds 4   # shorter games (default 9)
    uv run quack-rl replay <record file>.jsonl
    uv run quack-rl verify <record file>.jsonl --seed-check

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
| `rubies` | int64 | ruby count of the seat in the final state, after the `bag_*` columns |

Rows follow the order of `results.csv`, and inside a game first `p1`, then `p2`. Join key to `results.csv`: (`pairing`, `sweep_value`, `game`, `seed`); `seed` alone is also unique in a run.

Missing values: there are none. The engine gives each seat a `money` event in every round (rules 4.3), so every money and points cell is set. The writer never fills in a value (no null, no 0): a missing round value stops the run with an error.

Load it:

    import polars as pl
    seats = pl.read_parquet("data/tournaments/<run folder>/seats.parquet")
    # or: import pandas as pd; seats = pd.read_parquet(".../seats.parquet")

### Notebooks

There are no notebooks now. The old marimo notebooks are in `archive/notebooks/` and are not maintained. New notebooks come with ruleset v2.1.
