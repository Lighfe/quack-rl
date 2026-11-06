# PPO online against the preset bots (November 2026)

Issue: #263. Spec: `docs/specs/2026-11-05-rule-bots-and-rl-proof.md` ("Model-free online").

A MaskablePPO policy was trained online on ruleset v2.3 against a mix of the three preset bots
(`PRESET_BOTS` in `src/quack_rl/bots/presets.py`) and saved as the agent `data/agents/ppo-online/`
(seat `agent:ppo-online`).

**Result in one line:** the agent beats `bot:random` (84.0%), but it almost never beats a preset
bot (0.5%, 0.0% and 0.0%). The one-hour run did not reach the stage aim that the agents
sometimes beat the bots.

## Run

```
uv run --group rl python scripts/train_ppo.py \
    --opponent bot:topchip-draw20-pts6,bot:spendmost-draw20-pts6,bot:blackpurple-draw20-pts6 \
    --steps 300000 --eval-games 200 --seed 0 --out data/runs/ppo-online --agent-name ppo-online
```

The run went inside a memory cap
(`systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 /usr/bin/time -v ...`).

| setting | value |
|---|---|
| ruleset | v2.3 (9 rounds, no overrides) |
| steps (agent decisions) | 300,000 (SB3 stops after the rollout at 300,032) |
| seed | 0 |
| `n_steps` (decisions per rollout) | 1024 |
| `batch_size` | 64 |
| other PPO settings | SB3 defaults (`MlpPolicy`, CPU) |
| opponents | `bot:topchip-draw20-pts6`, `bot:spendmost-draw20-pts6`, `bot:blackpurple-draw20-pts6`, one sampled per game, equal weight, generator seeded with `--seed` |
| agent seat | random per game |
| training wall time | 2,079 s (34.6 min) |
| whole command wall time | 43 min 52 s (training plus 800 evaluation games) |
| peak memory | 783 MiB (`Maximum resident set size` 801,748 kB) |
| sha256 of `model.zip` | `3cf4d7155beebec8974f79977a8aa9ccd975a8d2b107ab3a07f3b1e70edb0fcc` |

The machine was a laptop CPU (8 cores), at about 144 training steps per second.

## Learning curve

From `data/runs/ppo-online/metrics.csv`: one point per rollout of 1024 decisions, the mean final
reward of the games that ended in it (+1 win, 0 draw, -1 loss). There are 293 points, and the
table shows every 16th one, the last one, and all 3 points that are not -1. A rollout holds about
9 games.

| steps | mean reward |
|---:|---:|
| 1,024 | -1.000 |
| 17,408 | -1.000 |
| 33,792 | -1.000 |
| 50,176 | -1.000 |
| 66,560 | -1.000 |
| 82,944 | -1.000 |
| 99,328 | -1.000 |
| 110,592 | -0.778 |
| 115,712 | -1.000 |
| 132,096 | -1.000 |
| 148,480 | -1.000 |
| 164,864 | -1.000 |
| 181,248 | -1.000 |
| 197,632 | -1.000 |
| 206,848 | -0.889 |
| 214,016 | -1.000 |
| 215,040 | -0.778 |
| 230,400 | -1.000 |
| 246,784 | -1.000 |
| 263,168 | -1.000 |
| 279,552 | -1.000 |
| 295,936 | -1.000 |
| 300,032 | -1.000 |

290 of the 293 rollouts lost every game. In about 2,600 training games the agent won 2 and drew 1.

## Win rates

200 games per opponent, after training, from `data/runs/ppo-online/result.json`. Game i uses
the chance seed `i`, and the agent plays p1 in the even games and p2 in the odd ones. A draw counts
as half a win. The interval is the 95% Wilson interval.

| opponent | wins | draws | losses | win rate | 95% interval |
|---|---:|---:|---:|---:|---|
| `bot:topchip-draw20-pts6` | 1 | 0 | 199 | 0.5% | 0.1-2.8% |
| `bot:spendmost-draw20-pts6` | 0 | 0 | 200 | 0.0% | 0.0-1.9% |
| `bot:blackpurple-draw20-pts6` | 0 | 0 | 200 | 0.0% | 0.0-1.9% |
| `bot:random` | 165 | 6 | 29 | 84.0% | 78.3-88.4% |

For scale: in the bot baseline (`docs/analysis/2026-11-bot-baseline.md`) the preset bots won
60-68% of all their games, and `bot:random` won 0.0% of its games against the rule bots.

## Below 10% against the presets: what was tried

The win rate against each of the three presets is below 10%. This is what was tried within the
one-hour budget:

- One run of 300,000 steps against the uniform mix of the three presets, with the PPO settings
  above. This used 34.6 minutes of training time, so the run stayed inside the budget. There was
  no second full run.
- Before it, a 2,048-step run against two presets checked the pipeline (the QA check of #263).
  It also lost every training game.

What the curve shows: the reward is only +1, 0 or -1 at the end of the game. Against the presets
the agent almost never wins, so nearly every game ends with -1, and the reward does not show the
agent which choices are better. The policy still learned something, since it beats `bot:random`
84% of the time. The run did not measure where that came from.

These next steps were not tried. Each one needs a change that this issue does not cover, so they
are for the stage review to place:

- a reward with more signal, for example the point margin at the end of the game
- a curriculum: first train against `bot:random` or weaker rule bot settings (`draw0`), then
  against the presets
- warm-starting from the offline agents (#275), or from self-play (#274)
- more steps than one hour allows

## Repeat

The agent folder is not in git (`data/` is ignored). The command above with the same seed gives
the same opponent sequence. The SB3 training on CPU is seeded too, but the run was not repeated
to check that `model.zip` comes out byte for byte the same.
