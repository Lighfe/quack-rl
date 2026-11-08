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

An experiment (3 trainings and 3 evaluators side by side, then the final evaluation) must end
in at most 6 hours on the laptop (8 cores, CPU, 15 GB RAM). The budget leaves 15% of that free,
so the limit is 6 h x 0.85 = 18,360 seconds.

Measured with P0, 3 seeds, 20,000 steps (#295):

```
systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 /usr/bin/time -v \
    uv run --group rl python scripts/run_experiment.py \
    --config experiments/P0.json --out <trial folder> --steps 20000 --threads 1
```

| item | value |
|---|---|
| steps per training (the run ends at the first rollout end past 20,000) | 20,480 |
| training time per seed (`wall_seconds` of the last `ppo.csv` row) | 231.4 s, 229.0 s, 229.9 s |
| rate per training | 3 x 20,480 / 690.3 s = 89.0 steps per second |
| final evaluation (3 seeds side by side, 200 games x 4 opponents x 2 modes each) | 1,076 s |
| evaluator after the last checkpoint (50 games x 4 opponents x 2 modes) | 279 s |
| whole command | 1,590 s, exit code 0, `Maximum resident set size` 818,768 kB (the largest single process) |

Chosen budget: `steps` = 1,433,600 (14 x 102,400) in P0 to P3, with `checkpoint_every` = 102,400.

```
steps / rate + final evaluation time
  = 1,433,600 / 89.0 + 1,076
  = 16,108 + 1,076
  = 17,184 s  <=  18,360 s
```

With the evaluator's last checkpoint (279 s) the total is 17,463 s, still below 18,360 s. One
evaluation of a checkpoint takes about 280 s, and a checkpoint comes about every 1,150 s
(102,400 / 89.0), so the evaluators keep up during the run.

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
