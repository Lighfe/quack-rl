# Offline BC and CQL on the rule-bot dataset (November 2026)

Issue: #275. Spec: `docs/specs/2026-11-05-rule-bots-and-rl-proof.md` ("Model-free offline", "Bar
for success").

A dataset of games between the 18 rule-bot settings (3 strategies x draw limits 0/20/40 x points
rounds 4/6, `field_specs("full")` without `bot:random`) was recorded on ruleset v2.3. A behaviour
cloning (BC) policy and a discrete CQL policy were trained on it and saved as the agents
`data/agents/bc/` (seat `agent:bc`) and `data/agents/cql/` (seat `agent:cql`). Each was then
measured against the three preset bots (`PRESET_BOTS` in `src/quack_rl/bots/presets.py`) and
`bot:random`.

**Result in one line:** both agents meet the stage bar. BC wins 51.3%, 48.5% and 37.0% against
the three presets, and CQL wins 39.8%, 43.0% and 27.0%. Both beat `bot:random` in all or nearly all
games.

## Dataset

```
uv run python scripts/build_dataset.py --bots bot:topchip-draw0-pts4,bot:topchip-draw0-pts6,\
bot:topchip-draw20-pts4,bot:topchip-draw20-pts6,bot:topchip-draw40-pts4,bot:topchip-draw40-pts6,\
bot:spendmost-draw0-pts4,bot:spendmost-draw0-pts6,bot:spendmost-draw20-pts4,\
bot:spendmost-draw20-pts6,bot:spendmost-draw40-pts4,bot:spendmost-draw40-pts6,\
bot:blackpurple-draw0-pts4,bot:blackpurple-draw0-pts6,bot:blackpurple-draw20-pts4,\
bot:blackpurple-draw20-pts6,bot:blackpurple-draw40-pts4,bot:blackpurple-draw40-pts6 \
    --games-per-pairing 6 --seed 0 --out data/datasets/rulebots
```

(The `--bots` list is one argument with no spaces; it is split here only to fit the page.)

Every ordered pair (a, b) of distinct specs is recorded, a as the agent, so 18 x 17 = 306 pairs.
Pair k is `build_dataset(a, b, 6, 0 + 6k)`: 6 games, the agent at p1 in the even games and at p2
in the odd ones, so each spec is recorded 3 times at p1 and 3 times at p2 against each other
spec. Each pair is saved as a part, and the parts are joined with `concat_files`.

| item | value |
|---|---|
| ruleset | v2.3 (observation layout 10, 1529 floats per observation, 88 actions) |
| games per pairing (N) | 6 |
| seed | 0 |
| games | 1,836 |
| steps (rows, agent decisions) | 205,236 (about 112 per game) |
| file size of `dataset.npz` | 2,550,880,352 bytes (2.38 GiB) |
| mean return (per game, +1 win, 0 draw, -1 loss) | +0.030 |
| build wall time | 15 min 28 s |
| peak memory of the build | 2.43 GiB (`Maximum resident set size` 2,548,360 kB) |

The mean return is close to 0, as expected: each spec plays each other spec equally often in
both roles, so the results nearly cancel. They do not cancel exactly, because the two directions
of a pair use different chance seeds.

The most frequent actions in the dataset (from `dataset-stats.json`):

| action | count | share |
|---|---:|---:|
| `draw` | 143,938 | 70.1% |
| `stop` | 12,877 | 6.3% |
| `ruby_drop` | 6,652 | 3.2% |
| `play:0` | 5,703 | 2.8% |
| `use_flask` | 3,241 | 1.6% |
| `buy:orange_1` | 2,927 | 1.4% |
| `take_points` | 2,316 | 1.1% |
| `play:1` | 1,771 | 0.9% |

## Training runs

```
uv run --group rl python scripts/train_offline.py --dataset data/datasets/rulebots/dataset.npz \
    --method bc --epochs 10 --seed 0 --eval-games 200 --out data/runs/bc --agent-name bc
uv run --group rl python scripts/train_offline.py --dataset data/datasets/rulebots/dataset.npz \
    --method cql --steps 100000 --alpha 1.0 --seed 0 --eval-games 200 --out data/runs/cql \
    --agent-name cql
```

The build and both runs went inside a memory cap
(`systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 /usr/bin/time -v ...`), one after
the other. The machine was a laptop CPU (8 cores).

| setting | BC | CQL |
|---|---|---|
| network | MLP 1529-256-256-88, ReLU | same |
| epochs / steps | 10 epochs (8,020 batches) | 100,000 steps |
| batch size | 256 | 256 |
| learning rate (Adam) | 1e-3 | 1e-3 |
| alpha (conservative weight) | - | 1.0 |
| gamma | - | 1.0 |
| target net copy | - | every 100 steps |
| seed | 0 | 0 |
| training wall time (`train_seconds`) | 51.6 s | 1,279.6 s (21.3 min) |
| whole command wall time (load, training, 800 evaluation games) | 8 min 14 s | 29 min 5 s |
| peak memory | 3.03 GiB (3,178,304 kB) | 3.04 GiB (3,186,116 kB) |
| sha256 of `model.pt` | `276f5f99f7863801bb5d4802a4fd647107e63bf02617554ef292d2ed4770dc88` | `b9b93f86f62f05b052e77b2d67b325de847f99394b4f909075a4c75610257938` |

The peak memory is mostly the dataset itself: `obs` and `next_obs` are each about 1.17 GiB.

### Loss curve of BC

From `data/runs/bc/metrics.csv`: the mean cross entropy of the stored action over the legal
actions, per epoch.

| epoch | loss |
|---:|---:|
| 1 | 0.2857 |
| 2 | 0.2313 |
| 3 | 0.2159 |
| 4 | 0.2026 |
| 5 | 0.1951 |
| 6 | 0.1888 |
| 7 | 0.1829 |
| 8 | 0.1765 |
| 9 | 0.1708 |
| 10 | 0.1651 |

### Loss curve of CQL

From `data/runs/cql/metrics.csv` (one loss per step, TD error plus alpha times the conservative
term). The loss of one batch is noisy, so the table gives the loss at the step and the mean over
the 1,000 steps that end there.

| step | loss at the step | mean of the last 1,000 steps |
|---:|---:|---:|
| 1 | 0.938 | 0.938 (1 step) |
| 1,000 | 0.301 | 0.417 |
| 5,000 | 0.331 | 0.294 |
| 10,000 | 0.267 | 0.272 |
| 20,000 | 0.239 | 0.251 |
| 30,000 | 0.237 | 0.221 |
| 40,000 | 0.280 | 0.215 |
| 50,000 | 0.183 | 0.469 |
| 60,000 | 0.662 | 0.231 |
| 70,000 | 0.373 | 0.400 |
| 80,000 | 0.328 | 0.281 |
| 90,000 | 0.290 | 0.392 |
| 100,000 | 0.265 | 0.249 |

The CQL loss falls in the first 30,000 steps and then moves between about 0.2 and 0.5 with no
clear trend. This was not looked into; a likely cause is the TD part (the target net is copied
every 100 steps and `gamma = 1`, so a change in the value estimates carries through whole games).

## Win rates

200 games per opponent, after training, from `data/runs/bc/result.json` and
`data/runs/cql/result.json` (`against_presets` and `against_random`). Game i uses the chance seed
`i`, and the agent plays p1 in the even games and p2 in the odd ones. A draw counts as half a
win. The interval is the 95% Wilson interval.

| agent | opponent | wins | draws | losses | win rate | 95% interval |
|---|---|---:|---:|---:|---:|---|
| BC | `bot:topchip-draw20-pts6` | 98 | 9 | 93 | 51.3% | 44.4-58.1% |
| BC | `bot:spendmost-draw20-pts6` | 93 | 8 | 99 | 48.5% | 41.7-55.4% |
| BC | `bot:blackpurple-draw20-pts6` | 69 | 10 | 121 | 37.0% | 30.6-43.9% |
| BC | `bot:random` | 199 | 1 | 0 | 99.8% | 97.7-100.0% |
| CQL | `bot:topchip-draw20-pts6` | 75 | 9 | 116 | 39.8% | 33.2-46.7% |
| CQL | `bot:spendmost-draw20-pts6` | 85 | 2 | 113 | 43.0% | 36.3-49.9% |
| CQL | `bot:blackpurple-draw20-pts6` | 51 | 6 | 143 | 27.0% | 21.3-33.5% |
| CQL | `bot:random` | 200 | 0 | 0 | 100.0% | 98.1-100.0% |

`load_agent("bc", rs)` and `load_agent("cql", rs)` each return an `OfflinePolicy` seat (named
`agent:bc` and `agent:cql`), and each won its one check game against `bot:random`.

## Stage bar

The bar is at least 10% wins against each preset bot.

- **BC meets the bar**: 51.3%, 48.5% and 37.0%; even the lower ends of the intervals (44.4%,
  41.7%, 30.6%) are far above 10%.
- **CQL meets the bar**: 39.8%, 43.0% and 27.0%; the lower ends are 33.2%, 36.3% and 21.3%.

For scale: the online PPO agent (`docs/analysis/2026-11-ppo-online.md`) and the self-play agent
(`docs/analysis/2026-11-selfplay.md`) won 0.0-0.5% against the same presets. The offline agents
learn from the bots' own play, so they start from moves that are already good, while the online
agents had to find them from a reward of -1 in almost every game.

Two notes on what these numbers mean:

- Two of the presets (`topchip-draw20-pts6`, `spendmost-draw20-pts6`) are among the 18 settings in
  the dataset, so the agents saw their moves (as agent and as opponent). The third preset
  (`blackpurple-draw20-pts6`) is in the field too. BC is close to 50% against the first two, as
  an imitation of the field would be against one of its members. Both agents do worst against
  `blackpurple-draw20-pts6`.
- BC is ahead of CQL here. Both runs used one setting each, with no tuning (spec Non-goals); the
  CQL alpha and steps were not searched.

## Repeat

The dataset and the agent folders are not in git (`data/` is ignored). The dataset is seeded by
`--seed` (pair k uses seeds `6k` to `6k + 5`), and the trainings are seeded with `--seed 0` on the
CPU. The runs were not repeated to check that `model.pt` comes out byte for byte the same.
