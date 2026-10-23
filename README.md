# Quack RL

A simplified version of The Quacks of Quedlinburg (rules: `docs/rules/rules-v1.md`), built as a recorded game and a reinforcement learning environment. Design: `docs/specs/2026-10-08-quack-rl-design.md`.

## Rulesets

| Version | Rules document | Notes |
|---|---|---|
| `v1`, `v1.1` | `docs/rules/rules-v1.md`, `rules-v1.1.md` | the first rules; the RL notebooks and the trained policies use `v1.1` |
| `v1.8`, `v1.9` | `docs/rules/rules-v1.8.md`, `rules-v1.9.md` | explosion choice, blue hand and pick step, new red and orange 6 chips |
| `v1.10` | `docs/rules/rules-v1.10.md` | black, yellow and purple chips, shop items with a minimum round. The default before v1.11 |
| `v1.11` | `docs/rules/rules-v1.11.md` | a card at the start of every round (12 cards), the card choice and the restart question, a per-round explosion limit. **The default**: every `--rules` option and `rules` parameter defaults to `v1.11` |
| `v2` | `docs/rules/rules-v2.md` | a shared point board (fields 0 to 50, two laps, at most 100 points), rat tails with a catch-up bonus at round start, a new die. **Not the default**: name it with `--rules v2`; the policy paths refuse it |

Name another version with `--rules v1.1` (CLI and scripts) or `rules="v1.1"` (code). Saved games, runs and datasets name their version and still load. A trained policy exists only for the older observation layouts, so `PolicyBot`, `train`, `finetune`, `selfplay`, offline training and `evaluate` with a policy refuse the default: name an older version for them. The environments and the baseline bots work on `v1.11` and on `v2`.

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

## RL environment

Two environments over the same engine (`quack_rl.rl`). The reward is `reward(final_state, seat)`: +1 for more points, -1 for fewer, 0 for a draw, given once at the end of the game. Both take `reward_fn` to replace it.

    from quack_rl.rl import QuackEnv, QuackParallelEnv

    env = QuackEnv(seat="p1", opponent=None, rules="v1.1")   # Gymnasium, one seat against a bot
    obs, info = env.reset(seed=0)
    obs, reward, terminated, truncated, info = env.step(int(info["action_mask"].argmax()))

    penv = QuackParallelEnv(rules="v1.1")                    # PettingZoo, both seats act
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
  - The phase list holds the card phases, and a card block sits before the map: `card.<kind>` (the card of the round, one entry per card kind including `no_effect`), `deck.<kind>` (cards left in the deck), `restart.available`, and the resolved round-end drops. The pending choice of the opponent is not in it.
  - Board block (`docs/specs/2026-10-22-ruleset-v2.md`): per seat `<who>.board.marker.<k>` (one-hot, `k` in 0..50), `<who>.board.has_50pts` and `<who>.rat_tail`, then `board.tail.<f>` (1 when a rat tail lies after field `f`). All of it is open information. The points entries are bounded 0 to 100. No policy is trained on layout 7; policy entry points refuse it.
  - `observation_bounds(rs)` gives `(low, high)`: finite for flags, fields and ruleset constants, `inf` where there is no real bound (points, money, bag counts); both envs use it in their observation space.
- Actions: `Discrete(n)`, the names are `action_names(rs)` from `quack_rl.engine`. The mask is 1 for legal actions.

## Train from a script

    uv run --group train python scripts/train.py --run NAME [--steps N] [--opponent random|<bot name>]

Options: `--run NAME` (required), `--steps N` (default 20000, decisions of the agent, about 42 per game), `--opponent` (`random` or `draw<percent>-pts<round>-<strategy>`, default `random`), `--rules` (default `v1.11`, which a policy run refuses: pass an older version such as `--rules v1.1`), `--seed` (default 0), `--eval-games` (default 500), `--checkpoint-every N` (default: none), `--runs-dir PATH` (default `data/runs`), `--resume NAME` (instead of `--run`: continue an interrupted run from its newest checkpoint, see `docs/specs/2026-10-14-resume.md`; `--steps`, `--opponent`, `--rules`, `--seed` and `--eval-games` come from its `config.json` and are refused). Runs go to `data/runs/<NAME>` (not committed): `config.json`, `episodes.csv`, `metrics.csv`, `eval.json`, `model.zip` and `checkpoints/`. A name that exists is refused. At the end the script prints the run folder and a table of wins, draws and losses for the baselines and the trained policy.

### Self-play

    uv run --group train python scripts/train_selfplay.py --run NAME [--steps N] [--update-every N]

The learner plays against snapshots of itself (spec: `docs/specs/2026-10-13-self-play.md`). Options: `--run NAME` (required), `--steps N` (default 200000, decisions of the learner), `--update-every N` (default 50000: every N steps a snapshot `checkpoints/step_<n>.zip` is saved and the learner is evaluated), `--rules` (default `v1.11`, which self-play refuses: pass an older version such as `--rules v1.1`), `--seed` (default 0), `--eval-games` (default 500), `--eval-bot NAME` (heuristic bot for the evaluations, repeatable, default `draw20-pts1-points`), `--runs-dir PATH` (default `data/runs`). The opponent of each game is the newest snapshot (0.5), an older one (0.3) or `random` (0.2). The run folder is a normal run folder plus `selfplay.csv`: one row per update with the win rates against `random`, the heuristic bots, each older snapshot and the previous newest snapshot. `PolicyBot.from_run` reads it.

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

### Notebooks

The marimo notebooks are in `archive/notebooks/`. They are not maintained. New notebooks come with ruleset v2.1.
