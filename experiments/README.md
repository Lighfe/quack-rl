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

Open the monitor notebook next to the command (the notebook comes in #294):

```
uv run --group rl --group monitor marimo run notebooks/rl_monitor.py
```

## Agents

This command saves no agent. Agents go into `data/agents/` only by the owner's choice: today
through `--agent-name` and `--agents-root` of `scripts/train_ppo.py` and
`scripts/train_offline.py`. Saving a run of an experiment as an agent is #307.
