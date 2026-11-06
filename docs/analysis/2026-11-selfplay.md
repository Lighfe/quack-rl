# Self-play against the preset bots (November 2026)

Issue: #274. Spec: `docs/specs/2026-11-05-rule-bots-and-rl-proof.md` ("Self-play").

A MaskablePPO policy was trained on ruleset v2.3 by self-play, against a pool of its own earlier
checkpoints, and saved as the agent `data/agents/selfplay/` (seat `agent:selfplay`). It was then
measured against the three preset bots (`PRESET_BOTS` in `src/quack_rl/bots/presets.py`),
`bot:random` and its own first checkpoint.

**Result in one line:** the agent beats `bot:random` (78.3%) and its first checkpoint (57.5%),
but it lost all 600 games against the preset bots (0.0% against each). The one-hour run did not
reach the stage aim that the agents sometimes beat the bots.

## Run

```
uv run --group rl python scripts/train_selfplay.py --rounds 12 --steps-per-round 20000 \
    --pool-size 4 --seed 0 --eval-games 200 --out data/runs/selfplay --agent-name selfplay
```

The run went inside a memory cap
(`systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 /usr/bin/time -v ...`). It ran in
one part (not resumed).

| setting | value |
|---|---|
| ruleset | v2.3 (9 rounds, no overrides) |
| rounds | 12 |
| steps per round (agent decisions) | 20,000 (240,000 in all) |
| pool size | 4 (the last 4 checkpoints) |
| seed | 0 |
| `n_steps` (decisions per rollout) | 1000 |
| `batch_size` | 50 |
| eval games | 200 per opponent |
| other PPO settings | SB3 defaults (`MlpPolicy`, CPU) |
| agent seat | random per game |
| training wall time (`train_seconds`) | 2,108.9 s (35.1 min) |
| whole command wall time | 41 min 58 s (training plus 1,000 evaluation games) |
| peak memory | 838 MiB (`Maximum resident set size` 857,952 kB) |
| sha256 of `model.zip` | `3ff6d2e5ffac102f5b222f17d8b9200806620ee22bd06eda71288a3afd8466af` |

The machine was a laptop CPU (8 cores). Round 1 (against `bot:random`) took about 140 s and each
later round about 175 s, so about 115 training steps per second against the pool.

## Per-round curve

From `data/runs/selfplay/selfplay.csv`: the mean final reward (+1 win, 0 draw, -1 loss) of the
games that ended in the round. This curve is measured against the pool (round 1 against
`bot:random`, since the pool is still empty then), so it shows how the agent does against its own
recent checkpoints, not its strength against the bots.

| round | steps | mean reward | pool size |
|---:|---:|---:|---:|
| 1 | 20,000 | +0.726 | 1 |
| 2 | 40,000 | +0.531 | 2 |
| 3 | 60,000 | +0.266 | 3 |
| 4 | 80,000 | +0.344 | 4 |
| 5 | 100,000 | +0.515 | 4 |
| 6 | 120,000 | -0.059 | 4 |
| 7 | 140,000 | -0.223 | 4 |
| 8 | 160,000 | -0.443 | 4 |
| 9 | 180,000 | -0.465 | 4 |
| 10 | 200,000 | -0.005 | 4 |
| 11 | 220,000 | +0.279 | 4 |
| 12 | 240,000 | -0.153 | 4 |

## Win rates

200 games per opponent, after training, from `data/runs/selfplay/result.json`. Game i uses the
chance seed `i`, and the agent plays p1 in the even games and p2 in the odd ones. A draw counts as
half a win. The interval is the 95% Wilson interval.

| opponent | wins | draws | losses | win rate | 95% interval |
|---|---:|---:|---:|---:|---|
| `bot:topchip-draw20-pts6` | 0 | 0 | 200 | 0.0% | 0.0-1.9% |
| `bot:spendmost-draw20-pts6` | 0 | 0 | 200 | 0.0% | 0.0-1.9% |
| `bot:blackpurple-draw20-pts6` | 0 | 0 | 200 | 0.0% | 0.0-1.9% |
| `bot:random` | 148 | 17 | 35 | 78.3% | 72.0-83.4% |
| first checkpoint (`checkpoint_1`) | 102 | 26 | 72 | 57.5% | 50.6-64.1% |

For scale: the PPO agent trained online against the presets (`docs/analysis/2026-11-ppo-online.md`)
won 0.5%, 0.0% and 0.0% against them and 84.0% against `bot:random`.

## Below 10% against the presets: what was tried

The win rate against each of the three presets is below 10% (0.0%). This is what was tried within
the one-hour budget:

- One self-play run of 12 rounds x 20,000 steps with a pool of 4 checkpoints and the PPO settings
  above. This used 35.1 minutes of training time, inside the budget. There was no second full
  run.
- Before it, the small check of 2 rounds x 1,000 steps (the QA check of this issue) tested the
  pipeline.

What the curve shows: self-play gives the agent opponents of its own level, so it gets wins and
losses to learn from (the reward is not stuck at -1 as against the presets). The agent did get
better than its first checkpoint (57.5%), but the pool only holds weak earlier versions of itself.
It never meets the strategies of the rule bots, and what it learned does not carry over to them.

These next steps were not tried. Each needs a change outside this issue, so they are for the stage
review to place:

- mixing the preset bots into the pool, so part of the games are against them
- a reward with more signal, for example the point margin at the end of the game
- more steps than one hour allows, or a tuned run (#86)

## Repeat

The agent folder is not in git (`data/` is ignored). The command above seeds the PPO model and the
pool opponent with `--seed`. The SB3 training on CPU is seeded too, but the run was not
repeated to check that `model.zip` comes out byte for byte the same.
