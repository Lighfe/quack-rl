# Offline RL on the env: behaviour cloning and discrete CQL

Issue #196. Aim: find env bugs (transitions, masks, rewards, terminal handling) with an offline
pipeline, not a strong policy. No tuning, one seed. Ruleset v2.1, observation layout 8
(1530 numbers, 88 actions). Libraries: torch 2.14.1 (CPU), numpy 2.5.4, gymnasium 1.4.0,
Python 3.12.3.

## Setup

- Dataset (`src/quack_rl/rl/dataset.py`): one row per decision of the agent seat, as `QuackEnv`
  shows it (Wait-only steps skipped, their reward summed in). Arrays: `obs`, `action`, `reward`,
  `next_obs`, `terminated`, `mask`, `next_mask`, `episode`. Game i: chance seed `seed + i`, the
  agent at p1 for even i and p2 for odd i, both bots built with `seed + i`.
- Default dataset: 2000 games of `bot:draw20-pts1-points` against `bot:random` (seed 0) plus 2000
  games of the same bot against itself (seed 2000), in one file.
- BC (`train_bc`): MLP 1530-256-256-88, cross entropy over the logits of the legal actions, Adam
  lr 1e-3, batch 256, 5 epochs, seed 0.
- CQL (`train_cql`): same MLP as Q network, `gamma = 1`, double-DQN target (online net picks the
  next action among `next_mask`, a target net copied every 100 steps values it), no bootstrap when
  `terminated`, loss = MSE TD error + `alpha * (logsumexp(Q masked) - Q(s, a))`, `alpha = 1`,
  Adam lr 1e-3, batch 256, 20000 steps, seed 0.
- Evaluation: `evaluate`, 500 games, chance seed `seed + i`, win rate counts a draw as one half,
  95% Wilson interval. Policies play the legal action with the highest logit / Q value.

## Commands

Small scale first (all exit code 0): build 20 games (6.6 s, peak 0.10 GB), BC 1 epoch and CQL
50 steps with 10 eval games (11.6 s and 12.7 s including start-up, peak 0.80 GB):

```
uv run python scripts/build_dataset.py --agent bot:draw20-pts1-points --opponent bot:random \
  --games 20 --seed 0 --out data/small
uv run --group rl python scripts/train_offline.py --dataset data/small/dataset.npz \
  --method bc --epochs 1 --seed 0 --eval-games 10 --out data/small/bc
uv run --group rl python scripts/train_offline.py --dataset data/small/dataset.npz \
  --method cql --steps 50 --seed 0 --eval-games 10 --out data/small/cql
```

Full run, each in a memory cap (`systemd-run --user --scope -p MemoryMax=<cap> -p MemorySwapMax=0
/usr/bin/time -v ...`):

```
uv run python scripts/build_dataset.py --out data/datasets/draw20            # cap 8G
uv run --group rl python scripts/train_offline.py --dataset data/datasets/draw20/dataset.npz \
  --method bc --epochs 5 --seed 0 --eval-games 500 --out data/runs/bc       # cap 9G
uv run --group rl python scripts/train_offline.py --dataset data/datasets/draw20/dataset.npz \
  --method cql --steps 20000 --seed 0 --eval-games 500 --out data/runs/cql  # cap 9G
```

| Job | Exit | Wall time | Peak memory |
| --- | --- | --- | --- |
| dataset build (4000 games) | 0 | 27 min 43 s | 6.6 GB |
| BC (5 epochs, 2 x 500 eval games) | 0 | 9 min 42 s (training 59 s) | 5.9 GB |
| CQL (20000 steps, 2 x 500 eval games) | 0 | 12 min 19 s (training 227 s) | 5.9 GB |

The first two build attempts were killed by the cap (6 GB, then 8 GB): the lists of per-step
arrays and their copy needed more than 4 times the final size. The build now keeps one compact
chunk per game, fills the final arrays game by game, and the default script saves its two parts
and joins them array by array (`concat_files`). The peak of 6.6 GB is the final `Dataset.load`
that computes the stats; the files are 5.4 GB (432004 steps of 1530 floats, twice).

## Dataset stats

4000 games, 432004 steps (108 steps per game), mean return 0.4975 (the bot wins all 2000 games
against `bot:random`, return +1, and the 2000 mirror games average about 0, as they should).
The action histogram (88 entries) is in `dataset-stats.json`; the main entries: action 1: 272458
(63%), action 2: 30121, action 3: 36000, action 17: 17396, action 18: 8080; 31 of the 88
actions never appear. Every stored action is legal under its mask (checked in the tests).

## Results (seed 0, 500 games each)

| Policy | Against | W / D / L | Win rate | 95% interval |
| --- | --- | --- | --- | --- |
| behaviour bot `draw20-pts1-points` (reference) | `bot:random` | 500 / 0 / 0 | 1.000 | [0.992, 1.000] |
| BC | `bot:random` | 500 / 0 / 0 | 1.000 | [0.992, 1.000] |
| BC | `bot:draw20-pts1-points` | 215 / 29 / 256 | 0.459 | [0.416, 0.503] |
| CQL | `bot:random` | 500 / 0 / 0 | 1.000 | [0.992, 1.000] |
| CQL | `bot:draw20-pts1-points` | 222 / 20 / 258 | 0.464 | [0.421, 0.508] |

The BC win rate against `bot:random` (1.000) is above 0.5: the check passes. Loss curves
(`metrics.csv`): BC per epoch 0.095, 0.047, 0.034, 0.027, 0.024. CQL (TD error plus the
conservative term) 0.95 at step 1, 0.12 at 2500, 0.07 at 7500, 0.03 at 20000; all values are
finite.

## Reading

- The pipeline works end to end. Rewards are 0 except at the last step of a game; `terminated`
  is set once per game; the terminal `next_mask` is all zero and the CQL target does not use it;
  the cloned policy plays only legal actions and beats the random bot like its teacher does.
- Both policies are about even with the behaviour bot (0.46, intervals contain 0.5 or end just
  above it), as a copy of a bot should be against that bot. This says the stored transitions
  carry the information the bot used, so the observation, mask and action index fit together.
- CQL shows no gain over BC here. It was not expected to: the dataset has no failure data of a
  better policy, and nothing was tuned.
- No env or dataset bug showed up. Dataset files and runs are in `data/` (not in git).
