# Experiments

One JSON config per experiment lives in this folder (`experiments/<id>.json`, read by
`load_config` in `src/quack_rl/rl/experiment.py`). One command runs one experiment: for each seed
one training process and one evaluator process side by side, then the final evaluation of each
seed and a summary table.

## Run an experiment

```
systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 /usr/bin/time -v \
    uv run --group rl python scripts/run_experiment.py \
    --config experiments/<id>.json --out data/experiments --threads 1
```

- The first line is the memory cap wrapper. It stops the run instead of filling the memory of the
  laptop; `/usr/bin/time -v` prints the peak memory (`Maximum resident set size`) at the end. If
  the cap stops a run, resume it (see below) with a larger cap only after you checked the peak.
- The run folder of seed k is `data/experiments/<id>/seed<k>/`. It gets `config.json`, the
  training numbers (`ppo.csv` or `bc.csv`), `checkpoints/`, `eval.csv` (the evaluator, one row per
  checkpoint, opponent and mode), `done.json` when the training has finished and
  `final_eval.csv` (the last checkpoint, `final_eval_games` games per opponent and mode, seed
  `final_eval_seed`).
- At the end the command prints one table: seed, opponent, mode (greedy, sampled) and the win
  rate with its 95% interval.
- `--seeds 0,1` runs only some of the config's seeds (default: all of them). A seed that is not
  in the config's `seeds` is an error.
- `--steps N` overrides the step budget of a ppo config, for a short trial run. Use another
  `--out` folder for trial runs, since the budget is stored in each `config.json`.
- `--threads N` sets `OMP_NUM_THREADS` and `MKL_NUM_THREADS` for each child process (default 1).
  3 seeds give 3 trainings and 3 evaluators; with `--threads 1` each uses one core, so the 6
  processes fit on the 8 cores without oversubscribing them. Raise it only when you run fewer
  seeds.
- `--eval-poll SECONDS` sets how often an evaluator looks for a new checkpoint (default 30).

When a child process fails, the command stops the others and exits with code 1, naming the seed
and the process (training or evaluator). Ctrl-C or SIGTERM stops all children.

## Step budget

An experiment is 3 trainings and 3 evaluators side by side, then the final evaluation, on the
laptop (8 cores, CPU, 15 GB RAM). Its time is planned from the measured step rate:
`steps / rate + final evaluation time`. Two bounds (spec
`docs/specs/2026-11-09-screening-and-bc-start.md`, "Budgets"):

- screening (S0-S5): at most 1.5 h = 5,400 s, with at least 6 checkpoints
- long run (L): at most 6 h minus 15% = 6 h x 0.85 = 18,360 s

### Measurement

Measured with S0, 3 seeds, 20,000 steps, after the env speed-up of #310 (#312, commit
`7728906`):

```
systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 /usr/bin/time -v \
    uv run --group rl python scripts/run_experiment.py \
    --config experiments/S0.json --out <trial folder> --steps 20000 --threads 1
```

| item | value |
|---|---|
| steps per training (the run ends at the first rollout end past 20,000) | 20,480 |
| training time per seed (`train_seconds` in `done.json`, the `wall_seconds` of the last `ppo.csv` row) | 106.024 s, 105.264 s, 105.022 s (sum 316.31 s) |
| rate per training | 3 x 20,480 / 316.31 s = 194.2 steps per second |
| final evaluation (3 seeds side by side, 200 games x 4 opponents x 2 modes each; from the last evaluator's end to the last `final_eval.csv`) | 328 s |
| one evaluator pass over a checkpoint (50 games x 4 opponents x 2 modes; from the checkpoint file to its rows in `eval.csv`, the slowest seed, poll wait included) | 94 s (seeds: 94 s, 91 s, 84 s) |
| whole command | 532.5 s (8:52.50), exit code 0, `Maximum resident set size` 832,724 kB (the largest single process) |

Before #310 the rate was 89.0 steps per second (P0, #295).

### Screening budget (S0-S5)

`steps` = 962,560 (10 x 96,256), `checkpoint_every` = 96,256 (94 x 1,024).

```
steps / rate + final evaluation time
  = 962,560 / 194.2 + 328
  = 4,956.5 + 328
  = 5,284.5 s  <=  5,400 s

steps / checkpoint_every = 962,560 / 96,256 = 10  >=  6
```

- The largest that fits: one more checkpoint interval, 1,058,816 steps, gives
  1,058,816 / 194.2 + 328 = 5,452.2 + 328 = 5,780.2 s > 5,400 s.
- With the evaluator's pass over the last checkpoint (94 s) the total is 5,378.5 s, still below
  5,400 s.
- The evaluators keep up: a checkpoint comes every 96,256 / 194.2 = 495.7 s, and one evaluator
  pass takes 94 s.

### Long-run budget (L)

`steps` = 3,481,600 (20 x 174,080), `checkpoint_every` = 174,080 (170 x 1,024).

```
steps_long / rate + final evaluation time
  = 3,481,600 / 194.2 + 328
  = 17,927.9 + 328
  = 18,255.9 s  <=  18,360 s
```

- The largest that fits: one more checkpoint interval, 3,655,680 steps, gives
  3,655,680 / 194.2 + 328 = 18,824.3 + 328 = 19,152.3 s > 18,360 s.
- With the evaluator's pass over the last checkpoint (94 s) the total is 18,349.9 s, still below
  18,360 s.
- The evaluators keep up: a checkpoint comes every 174,080 / 194.2 = 896.4 s, and one evaluator
  pass takes 94 s.

### Next: the long run

Next: the long run. `experiments/L.json` is S5 (chosen in part 2 of
`docs/analysis/2026-11-screening.md`, #314) with the long-run budget above:

```
systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 /usr/bin/time -v \
    uv run --group rl python scripts/run_experiment.py \
    --config experiments/L.json --out data/experiments --threads 1
```

## Resume after an interruption

Run the same command again with `--resume` and the same `--steps` (or none, as before):

```
systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 /usr/bin/time -v \
    uv run --group rl python scripts/run_experiment.py \
    --config experiments/<id>.json --out data/experiments --threads 1 --resume
```

- A PPO seed continues from its newest complete checkpoint. The config, the seed and the budget
  must be the ones in its `config.json`; otherwise the training stops with an error naming what
  differs.
- A seed with `done.json` is not trained again. Its evaluator still runs (it skips the
  checkpoints that `eval.csv` already has) and its final evaluation is done again.
- A BC run cannot resume (it takes minutes). The command stops with a message naming the folder
  of an unfinished BC seed: delete that folder and run again.
- Without `--resume`, a seed folder that already has a `config.json` stops the command before
  anything starts.

## Watch a run

Open the monitor notebook next to the command:

```
uv run --group rl --group monitor marimo run notebooks/rl_monitor.py
```

- It shows the picked experiment and, optionally, a baseline experiment side by side: the
  training numbers of each seed (PPO over steps, BC per epoch), the win rate per opponent over
  the checkpoints with its 95% band (greedy and sampled apart), and the final evaluation.
- It reloads the run folders every 30 seconds by itself (the interval can be changed at the top).
  It only reads them.
- `-- --root <folder> --experiment <id> --baseline <id>` after the command sets the defaults of
  the root folder (default `data/experiments`) and of the two dropdowns.

## Agents

This command saves no agent. Agents go into `data/agents/` only by the owner's choice: today
through `--agent-name` and `--agents-root` of `scripts/train_ppo.py` and
`scripts/train_offline.py`. Saving a run of an experiment as an agent is #307.
