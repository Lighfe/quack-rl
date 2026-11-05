# MaskablePPO against the random bot and a heuristic bot

Issue #194. Aim: check that the RL env works against bots (mask, reward, observation, opponent
handling). No tuning, one seed. Ruleset v2.1, observation layout 8.

## Setup

- `MaskablePPO("MlpPolicy")` of sb3-contrib 2.9.0 (stable-baselines3 2.9.0, torch 2.14.1 on the
  CPU, gymnasium 1.4.0, numpy 2.5.4, Python 3.12.3), defaults except `n_steps=1024`,
  `batch_size=64`. One step is one decision of the agent (about 40 per game).
- `QuackEnv(seat="random", opponent=<bot>)`: the agent sits at a random seat each game. Reward
  +1 / -1 / 0 at the end of the game.
- Evaluation: `PolicyBot` (deterministic), 500 games, chance seed `seed + i`, the agent at p1 for
  even i and p2 for odd i. Win rate counts a draw as one half; the interval is the 95% Wilson
  interval.
- Configs and curves are in `data/runs/ppo-vs-<bot>/` (`config.json`, `metrics.csv`,
  `result.json`, `model.zip`); that folder is not in git.

## Commands

Both runs at the same time, each in a memory cap of 4 GB (peak 0.8 GB each) and with
`OMP_NUM_THREADS=2`, on a machine with 8 cores:

```
OMP_NUM_THREADS=2 systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 \
  /usr/bin/time -v uv run --group rl python scripts/train_ppo.py \
  --opponent bot:random --steps 200000 --seed 0 --eval-games 500 --out data/runs/ppo-vs-random
OMP_NUM_THREADS=2 systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 \
  /usr/bin/time -v uv run --group rl python scripts/train_ppo.py \
  --opponent bot:draw20-pts1-points --steps 200000 --seed 0 --eval-games 500 \
  --out data/runs/ppo-vs-draw20-pts1-points
```

Exit code 0 for both. Wall time 24 min (random) and 32 min (heuristic), of which training took
1316 s and 1336 s; the rest is the evaluation.

## Results (seed 0, 200000 steps, 500 games)

| Trained against | Evaluated against | W / D / L | Win rate | 95% interval |
| --- | --- | --- | --- | --- |
| `bot:random` | `bot:random` | 452 / 27 / 21 | 0.931 | [0.905, 0.950] |
| `bot:draw20-pts1-points` | `bot:draw20-pts1-points` | 1 / 0 / 499 | 0.002 | [0.000, 0.011] |
| `bot:draw20-pts1-points` | `bot:random` | 135 / 39 / 326 | 0.309 | [0.270, 0.351] |

Against the random bot the lower end of the interval (0.905) is above 0.5, so the check passes
at the first budget; the run with 1000000 steps was not needed.

Training curve (mean reward of the games that ended in a rollout of 1024 steps):

- against the random bot: 0.48 (mean of the first 10 points) to 0.89 (mean of the last 40);
  the first point is -0.29
- against the heuristic bot: -0.99 and -0.99 (first 10, last 40); at best -0.71 in one rollout

## Reading

- The env works against the random bot: the policy learns quickly (reward +0.87 after 40000
  steps) and it plays only legal actions (the smoke test and the evaluation check this).
- The heuristic bot `draw20-pts1-points` is very strong against weak play. As a sanity check
  (200 games, seed 0): it beats the random bot 200 to 0, and the random bot loses 200 of 200
  against it. So a constant reward of -1 at the start of training is what the env should give; the
  sparse reward then has no signal (almost every game is lost), and PPO does not leave it. This
  looks like a learning problem (reward shaping, #57; a curriculum or self-play, #86), not an env
  bug: the same env and code learn against the random bot.
- The policy trained against the heuristic bot is worse than a random player against the
  random bot (0.309). This is a policy that learned a bad habit under an all-loss signal; it is
  one seed and no conclusion beyond that.
