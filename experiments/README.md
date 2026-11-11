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

> **L is on hold. Do not start it.** Every BC arm of screening 2 got worse while training (S5
> fell from 0.2578 at the first checkpoint to 0.0444 at the last), so a longer run of S5 has no
> sound basis. See
> [part 3 of the screening record](../docs/analysis/2026-11-screening.md#part-3-shortcomings-of-stage-309)
> (#318).

Next: the long run. `experiments/L.json` is S5 (chosen in part 2 of
`docs/analysis/2026-11-screening.md`, #314) with the long-run budget above:

```
systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 /usr/bin/time -v \
    uv run --group rl python scripts/run_experiment.py \
    --config experiments/L.json --out data/experiments --threads 1
```

## Screening 4: S8

`experiments/S8.json` is S7 (`target_kl` 0.03) with `n_steps` 2,048 and `batch_size` 128
instead of 1,024 and 64: half of S6's rollout size, on top of S7's early stop. A pass still has
16 minibatches. Seeds 0, 1, 2, paired with S7's. `checkpoint_every` 96,256 is 47 rollouts of
2,048, so S8 has S7's 10 checkpoints. Why: S7 is the best arm so far (score 0.1714) but noisy
(seed 2 gives about 77% of its score, all three seeds dropped at 577,536); S6 (`n_steps` 4,096)
roughly halved the KL and slowed the decline, but was not enough on its own. See parts 3 and 4 of
`docs/analysis/2026-11-screening.md`.

Run it (trial of seed 0 with 8,192 steps to `/tmp/quack-trial-s8`, then the full run to
`data/experiments`; each in the memory cap wrapper above; start, end, exit code and peak RSS of
each run go to `data/experiments/run_s8.log`):

```
scripts/run_s8.sh                 # trial, then full run
scripts/run_s8.sh --skip-trial    # full run only
scripts/run_s8.sh --resume        # passes --resume to run_experiment.py
```

### Decision rule (written before the run)

This rule was committed together with `experiments/S8.json`, before S8 ran. S8 counts as better
than S7 when all three hold:

- **(a) Score.** S8's score is higher than S7's 0.1714 (score as in part 1 of the screening
  record: mean greedy `win_rate` over 3 seeds x 3 presets in `final_eval.csv`).
- **(b) Curve.** S8's preset curve (mean greedy `win_rate` over the 9 seed x preset rows of
  `eval.csv` per checkpoint) is not below S7's at most of the 10 checkpoints: S8 >= S7 at 6 or
  more of them.
- **(c) Seeds.** No single seed gives more than about two thirds of S8's score: the largest
  per-seed score (mean over the three presets) is at most 2/3 of the sum of the three. S7 fails
  this (0.3975 of 0.5141, 77%).

The comparison table in the screening record also lists the **gradient steps** of S1, S6, S7 and
S8 over the budget, so that a gain cannot be mistaken for less training: per seed, the sum over
the rows of `ppo.csv` of `epochs_run` x (`n_steps` / `batch_size`) (16 for all four arms). S1 has
no `epochs_run` column; it ran 10 passes per update (940 x 160 = 150,400). For S7 and S8 the sum
is an upper bound, since the pass in which the stop comes is cut short.

The sense check after S8 (see "Sense check after a screening") is written as usual, whatever the
rule says.

### Next step after S8 (text only, no configs yet)

The BC reruns S9, S10, S11 are S3, S4, S5 (BC starts from B0, B1, B2) with the update settings of
the winner, and wait for the owner's decision after S8:

- if S8 is better than S7 by the rule above: S8's settings, `n_steps` 2,048, `batch_size` 128,
  `target_kl` 0.03;
- if not: S7's settings, `target_kl` 0.03 only (`n_steps` 1,024, `batch_size` 64).

Both are possible with S3-S5's other settings: `critic_warmup_steps` 51,200 is 25 rollouts of
2,048 (and 50 of 1,024), and `checkpoint_every` 96,256 is a multiple of both rollout sizes.

## Sense check after a screening

After each screening, the engineer reads the learning curves and the PPO metrics, in the monitor
(`notebooks/rl_monitor.py`, see "Watch a run") or from the CSV files (`eval.csv`, `ppo.csv`), and
writes a short paragraph in the screening record: does the result make sense?

Anything that looks implausible goes to the owner before the next run. Examples: a policy that
gets worse while training, or a variant with more signal that scores below its baseline. The
check is a judgment, not a list of limits.

The sense check is engineer and QA work:

- The engineer writes it in the record, after each screening and before the next run.
- QA reads the same curves and metrics on its own and states in its result whether it agrees. It
  names anything implausible that the engineer's check missed or played down.
- A missing sense check, or one that contradicts the numbers in the record, is a QA failure.

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
