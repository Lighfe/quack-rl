# Self-play on the env

Issue #195. Aim: find env bugs (opponent handling, seat swapping, bots in the loop), not a strong
policy. No tuning, one seed. Ruleset v2.1, observation layout 8.

## Setup

- Code: `src/quack_rl/rl/selfplay.py` (`CheckpointPool`, `PoolOpponent`, `run_selfplay`), thin
  wrapper `scripts/train_selfplay.py`. `QuackEnv.reset()` calls `opponent.reset()` when the
  opponent has it; the pool opponent picks one checkpoint at random per episode (the random bot
  while the pool is empty, so in round 1) and plays it as a `PolicyBot`.
- One `MaskablePPO("MlpPolicy")` (sb3-contrib 2.9.0, stable-baselines3 2.9.0, torch 2.14.1 on the
  CPU, gymnasium 1.4.0, numpy 2.5.4, Python 3.12.3) is trained over all rounds; the step counter
  keeps growing. `n_steps=1000`, `batch_size=50` (so 20000 steps are exactly 20 rollouts and the
  run is exactly 100000 steps; #194 used 1024 and 64), other settings the SB3 defaults.
- 5 rounds of 20000 steps, pool size 4, seed 0. After each round the model is saved as
  `checkpoint_<i>.zip` and added to the pool. The agent plays both seats (`seat="random"`).
- Evaluation: the last checkpoint (`PolicyBot`, deterministic), 500 games per opponent, chance seed
  `seed + i`, the agent at p1 for even i and p2 for odd i. A draw counts as one half; the interval
  is the 95% Wilson interval.
- Files are in `data/runs/selfplay/` (`config.json`, `selfplay.csv`, `result.json`, checkpoints);
  not in git.

## Command

```
OMP_NUM_THREADS=2 systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 \
  /usr/bin/time -v uv run --group rl python scripts/train_selfplay.py --seed 0 \
  --out data/runs/selfplay
```

Defaults: `--rounds 5 --steps-per-round 20000 --pool-size 4 --eval-games 500`. Exit code 0. Wall
time 23 min 16 s, of which training took 781 s; peak memory 0.85 GB (maximum resident set size
853684 kB). The full test suite ran at the same time on the same machine for part of the run, so
the times are somewhat too long.

## Results

| Last checkpoint against | W / D / L | Win rate | 95% interval |
| --- | --- | --- | --- |
| `bot:random` | 496 / 4 / 0 | 0.996 | [0.986, 0.999] |
| `bot:draw20-pts1-points` | 1 / 1 / 498 | 0.003 | [0.001, 0.013] |
| first checkpoint (`checkpoint_1`) | 472 / 17 / 11 | 0.961 | [0.940, 0.975] |

The win rate of the last checkpoint against the first checkpoint is 0.961, above 0.5, so the
self-play loop gives a policy that improves over its own start.

Mean episode reward per round (the training opponent changes with the pool, so the numbers are
not comparable between rounds):

| Round | Steps | Mean reward | Pool size |
| --- | --- | --- | --- |
| 1 (random bot) | 20000 | +0.645 | 1 |
| 2 | 40000 | -0.022 | 2 |
| 3 | 60000 | +0.551 | 3 |
| 4 | 80000 | +0.304 | 4 |
| 5 | 100000 | +0.054 | 4 |

## Reading

- No crash, no illegal action in the loop (evaluation raises on an illegal choice), and the
  checkpoints play both seats. The reward falls after round 1 because from round 2 on the
  opponent is a trained policy, not the random bot; this is what self-play should show.
- The last checkpoint beats the random bot (0.996) and loses to the heuristic bot
  `draw20-pts1-points` (0.003), as the #194 policy trained against the random bot and the
  heuristic bot is very strong against weak play. Self-play of 100000 steps does not close that
  gap; that is not an env bug and not the aim here.
- The first-checkpoint condition holds, so no env-bug suspects are listed.
