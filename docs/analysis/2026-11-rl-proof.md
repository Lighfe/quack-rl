# Final tournament: RL proof of concept on v2.3 (November 2026)

Issue: #276. Spec: `docs/specs/2026-11-05-rule-bots-and-rl-proof.md` ("Bar for success").

One final tournament measured every agent of the stage against each preset bot
(`PRESET_BOTS` in `src/quack_rl/bots/presets.py`) and `bot:random`, with the seats swapped in
every second game. The bar: each agent wins at least 10% of its games against each preset bot.

**Result in one line:** BC and CQL meet the bar (32-48% against each preset). PPO online,
self-play and the planner miss it (0-3% against each preset), though all three beat `bot:random`.

## Runs

Two runs, both on ruleset v2.3 (9 rounds, no overrides), `--swap-seats` (game g with odd g has the
agent at `p2`), the same `--vs` list and seed 2026. The planner has its own run at 100 games per
pairing, because it is slow (about 40 s per game).

Model-free agents, 200 games per pairing (16 pairings, 3,200 games):

```
uv run --group rl quack-rl tournament \
    --bots agent:ppo-online,agent:selfplay,agent:bc,agent:cql \
    --vs bot:topchip-draw20-pts6,bot:spendmost-draw20-pts6,bot:blackpurple-draw20-pts6,bot:random \
    --swap-seats --games 200 --seed 2026 --workers 4 --name rl-proof-modelfree
```

Planner, 100 games per pairing (4 pairings, 400 games):

```
uv run --group rl quack-rl tournament --bots agent:planner \
    --vs bot:topchip-draw20-pts6,bot:spendmost-draw20-pts6,bot:blackpurple-draw20-pts6,bot:random \
    --swap-seats --games 100 --seed 2026 --workers 2 --name rl-proof-planner-w2
```

Each run went inside a memory cap
(`systemd-run --user --scope -p MemoryMax=6G -p MemorySwapMax=0 /usr/bin/time -v ...`), with no
other run of this issue next to it.

| run folder (`data/tournaments/`) | games | wall time | peak memory (largest process) | sample rebuild | clock caps |
|---|---:|---:|---:|---|---:|
| `2026-11-06_16-19-33+0100-rl-proof-modelfree` | 3,200 | 16 min 07 s | 860 MiB (880,204 kB) | 20 of 20 ok | - |
| `2026-11-06_18-58-22+0100-rl-proof-planner-w2` | 400 | 2 h 06 min | 99 MiB (101,196 kB) | 20 of 20 ok | 0 |

A first planner run with 3 workers (`2026-11-06_16-35-53+0100-rl-proof-planner`) logged 20
`planner decision stopped by the clock` warnings, so some of its games are not reproducible. It is
not used here. The run above repeated it with 2 workers and had no clock cap. Its W/D/L counts
were the same as the first run's.

## Agents

From `config.json` `agents` of the run folders.

| seat | kind | weights sha256 |
|---|---|---|
| `agent:ppo-online` | ppo | `3cf4d7155beebec8974f79977a8aa9ccd975a8d2b107ab3a07f3b1e70edb0fcc` |
| `agent:selfplay` | ppo | `3ff6d2e5ffac102f5b222f17d8b9200806620ee22bd06eda71288a3afd8466af` |
| `agent:bc` | bc | `276f5f99f7863801bb5d4802a4fd647107e63bf02617554ef292d2ed4770dc88` |
| `agent:cql` | cql | `b9b93f86f62f05b052e77b2d67b325de847f99394b4f909075a4c75610257938` |
| `agent:planner` | planner | none (no weights: 40 simulations, rollout `bot:topchip-draw20-pts6`, `max_seconds` 2.0) |

## Results

W/D/L from the agent's view, over both seats. Win rate = (wins + draws/2) / games, with the 95%
Wilson interval (`quack_rl.report.wilson`). Games per cell: 200, and 100 for the planner.

| agent | vs `topchip-draw20-pts6` | vs `spendmost-draw20-pts6` | vs `blackpurple-draw20-pts6` | vs `random` | bar |
|---|---|---|---|---|---|
| ppo-online | 0/0/200, 0.0% [0.0-1.9%] | 0/0/200, 0.0% [0.0-1.9%] | 0/0/200, 0.0% [0.0-1.9%] | 174/2/24, 87.5% [82.2-91.4%] | missed |
| selfplay | 0/0/200, 0.0% [0.0-1.9%] | 0/0/200, 0.0% [0.0-1.9%] | 0/0/200, 0.0% [0.0-1.9%] | 163/0/37, 81.5% [75.5-86.3%] | missed |
| bc | 96/0/104, 48.0% [41.2-54.9%] | 83/0/117, 41.5% [34.9-48.4%] | 74/0/126, 37.0% [30.6-43.9%] | 200/0/0, 100.0% [98.1-100.0%] | **met** |
| cql | 94/1/105, 47.2% [40.4-54.2%] | 85/0/115, 42.5% [35.9-49.4%] | 63/2/135, 32.0% [25.9-38.8%] | 200/0/0, 100.0% [98.1-100.0%] | **met** |
| planner | 3/0/97, 3.0% [1.0-8.5%] | 2/0/98, 2.0% [0.6-7.0%] | 0/0/100, 0.0% [0.0-3.7%] | 100/0/0, 100.0% [96.3-100.0%] | missed |

## Against the bar

- **BC: meets the bar.** At least 37.0% against each preset; even the lower end of the
  interval (30.6%) is above 10%.
- **CQL: meets the bar.** At least 32.0% against each preset (lower end 25.9%).
- **PPO online: misses the bar.** No win in 600 games against the presets. What was tried: one
  online PPO run of 300,000 steps (about 35 minutes of training) against a uniform mix of the three
  presets, with SB3 default settings and only the end-of-game reward (+1/0/-1). Against the presets
  nearly every training game ended with -1, so the reward hardly told the agent which choices were
  better. Background: `docs/analysis/2026-11-ppo-online.md`.
- **Self-play: misses the bar.** No win in 600 games against the presets. What was tried: one
  self-play run of 12 rounds x 20,000 steps against a pool of its own 4 latest checkpoints (about
  35 minutes of training). It learned to beat `bot:random` and its first checkpoint, but it never
  played the rule bots in training, and what it learned does not carry over to them. Background:
  `docs/analysis/2026-11-selfplay.md`.
- **Planner: misses the bar.** 5 wins in 300 games against the presets. What was tried (#273):
  flat Monte Carlo search with determinization at 40 simulations per decision inside a 2 s cap.
  Within that cap, 16-game tests against `bot:topchip-draw20-pts6` also tried 50 and 60
  simulations (1 win each) and UCB1 at the root (one-level MCTS) at 40 and 60 simulations (no
  win). None reached 10%. At 40 simulations the noise of the rollouts is larger than the effect of
  one choice. Without the cap, 160 simulations won 4 of 12 games, but its slowest decision took
  6.67 s. A cheaper state copy (#285) could make room for more simulations inside 2 s.

The missed bars are reported, not fixed: more training or tuning is a non-goal of the spec.

## Repeat

The two commands above, with the agents in `data/agents/` that match the weights hashes. Both runs
rebuild a random sample of 20 games from their seeds at the end
(`20 sampled games rebuilt from the seed: ok`). Run the planner with at most two or three pairings
in parallel and nothing heavy next to it, so that no decision hits the 2 s clock cap.
