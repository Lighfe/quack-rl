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

L is S11 (chosen after screening 5) with a longer budget. S11's update stops early
(`target_kl` 0.03, about 3 passes per update instead of 10), so it is faster than the 194.2 steps
per second above, which were measured for 10 passes. The rate is re-measured from S11 (4 seeds,
8 processes, `train_seconds` in `done.json` and `wall_seconds` in `ppo.csv`):

| item | value |
|---|---|
| rate per training, whole run (slowest seed, seed 1) | 962,560 / 3,765.5 s = 255.6 steps per second |
| rate per training, slowest quarter of any seed (seed 1, last quarter) | 240.1 steps per second |
| final evaluation and start-up (S11's whole run 4,237 s minus 3,765.5 s) | 471 s |

`steps` = 4,235,264 (22 x 192,512), `checkpoint_every` = 192,512 (2 x 96,256 = 188 x 1,024).

```
steps_long / rate + final evaluation time
  = 4,235,264 / 255.6 + 471  =  16,570 + 471  =  17,041 s (4.7 h)  <=  18,360 s
  at the slowest quarter rate:
  = 4,235,264 / 240.1 + 471  =  17,640 + 471  =  18,111 s (5.0 h)  <=  18,360 s
```

- The budget is set by the slowest quarter rate, since the number of passes per update can
  change over a longer run. One more checkpoint interval, 4,427,776 steps, gives
  4,427,776 / 240.1 + 471 = 18,912 s > 18,360 s.
- `checkpoint_every` is a multiple of S11's 96,256, so L's checkpoints at 192,512 ... 962,560
  fall on S11's checkpoint steps. Same config and seeds: L's first 962,560 steps should repeat
  S11 (checked for the first 3,072 steps of seed 0: `ppo.csv` equal except `wall_seconds`), so
  the part beyond 962,560 is what L adds.
- The evaluators keep up: a checkpoint comes every 192,512 / 255.6 = 753 s.

### The long run

Run it (all steps logged to `data/experiments/run_long.log`):

```
scripts/run_long.sh                 # checks, trial, L, reproducibility check, agents
scripts/run_long.sh --skip-trial    # without the trial
scripts/run_long.sh --resume        # after an interruption
```

- Before anything runs it checks that B2's `model.pt` of seeds 0-3 exist and that the agent
  names are free, so the agents can be saved after the run.
- The whole script runs under `systemd-inhibit` (no suspend, idle sleep or lid-switch sleep).
- A trial of 8,192 steps with all 4 seeds goes to `/tmp/quack-trial-l` (memory check as in
  screening 5) and saves one agent into a temporary root, to check the save step.
- After L it compares L's `ppo.csv` up to 962,560 with S11's per seed and logs the result. A
  resumed run restarts the opponent mix and the env generators, so it differs after the resume.
- Then it saves the final checkpoint of each seed as an agent:
  `data/agents/long-s11-seed<k>/` (seat `agent:long-s11-seed<k>`). `AGENTS_ROOT` and
  `AGENT_PREFIX` change the folder and the names.

`scripts/save_run_agent.py RUN_DIR --agent-name NAME --agents-root PATH [--step N]` saves any
finished seed folder (PPO: a checkpoint, default the final one; BC: `model.pt`) as an agent.

### Decision rule for L (written before the run)

- **Agents.** The agents are the final checkpoints, chosen before the run. A best checkpoint
  picked from `eval.csv` (50 games per opponent and mode) would be picked on noise.
- **Does more training help?** For each seed, the greedy preset win rate at the last checkpoint
  is compared with the one at 962,560 (S11's end; both from `eval.csv`), and the 4-seed mean
  of L's `final_eval.csv` score with S11's 0.5585. L helps when the mean is higher and at least
  3 of 4 seeds are not lower at the last checkpoint than at 962,560.
- **Decline.** If the preset curve (mean over seeds x presets) drops below its value at
  962,560 for the last 3 checkpoints, the result goes to the owner before any further run.
- The sense check (see "Sense check after a screening") is written as usual.

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

**Result (2026-11-11):** S8 is not better than S7. Score 0.1464 against 0.1714 (a fails); its
preset curve is at or above S7's at 2 of 10 checkpoints (b fails); largest seed share 37% (c
holds). The owner kept S7's settings and dropped S8. S9-S11 take `target_kl` 0.03 only.

## Screening 5: S9, S10, S11

`experiments/S9.json`, `S10.json`, `S11.json` are S3, S4, S5 (BC start from B0, B1, B2, reward
`margin`, the three presets, critic warmup 51,200) with two changes: `target_kl` 0.03 (S7's
early stop) and a fourth seed. Seeds 0, 1, 2 are paired with S3-S5. Seed 3 is new: PPO seed 3
starts from BC seed 3, so B0, B1 and B2 get seed 3 as well (`experiments/B*.json`; seeds 0-2 of
the BC runs are not run again). 4 seeds give 4 trainings and 4 evaluators, 8 processes on the
8 cores.

Run it:

```
scripts/run_s9_s11.sh                         # BC seed 3, trial, S9, S10, S11
scripts/run_s9_s11.sh --skip-bc --skip-trial  # the full runs only
scripts/run_s9_s11.sh --resume                # passes --resume to the PPO runs
```

- First BC seed 3 of B0, B1, B2, one arm at a time (a BC process loads the whole 2.5 GB
  dataset), under `BC_MEM_MAX` (default 8G).
- Then a trial of S9 with all 4 seeds and 8,192 steps to `/tmp/quack-trial-s9`, under
  `PPO_MEM_MAX` (default 6G; the 4G of the earlier screenings was for 6 processes). If the peak
  memory of the whole trial run is above 85% of the cap, the script stops before the full runs.
- `data/experiments/run_s9_s11.log` gets start, end, exit code, wall time, the peak RSS of the
  largest process and the peak memory of the whole run (`memory.peak` of the systemd scope).
  The cap is on the whole run, so that second number is the one to compare with the cap.

### Decision rule (written before the run)

Committed together with the configs, before S9-S11 ran. The question is whether the early stop
keeps the BC start from getting worse in PPO, and which BC start is best with it.

- **Decline.** For each arm, the preset curve (mean greedy `win_rate` over seeds x presets in
  `eval.csv`) at the last checkpoint is not below the first one (96,256). S3-S5 fell from
  0.19-0.29 to 0.02-0.04. Also reported: the BC start level of each seed (the greedy preset win
  rate in `final_eval.csv` of B0/B1/B2), so the curve can be read against where PPO started.
- **Against its baseline.** S9, S10 and S11 are compared with S3, S4 and S5 on the paired seeds
  0, 1, 2 only: score, and how many of the 10 checkpoints are at or above the baseline's.
- **Best arm.** The arm with the highest score over all 4 seeds, provided its decline check holds
  and no single seed gives more than half of its score (with 4 seeds an even share is a
  quarter). If no arm passes the decline check, there is no best arm, and the result goes to
  the owner.
- The comparison table lists the gradient steps of each arm (as in screening 4), and the score
  of each arm on seeds 0-2 as well as on 0-3.
- S7 (0.1714) is shown for orientation only. S9-S11 differ from S7 in the start, the reward and
  the opponents, so a gap between them has no single cause.

L stays on hold. What follows S9-S11 is the owner's decision.

**Result (2026-11-12):** all three arms beat their baselines at 10 of 10 checkpoints (seeds
0-2). Score over seeds 0-3: S9 0.522, S10 0.421, S11 0.559. S10 fails the decline check (0.473
at the first checkpoint, 0.372 at the last); S9 and S11 pass, and no seed gives more than 42%
of an arm's score. Best arm: S11 (B2 start), also the one with the smallest seed spread (sd
0.060) and the largest gain over its BC start (+0.100). S11 over S9 is not clear (paired
difference +0.037, SE 0.040). Gradient steps: about 50,000 per seed for S9-S11 against 150,400
for S3-S5, so the early stop and less training are not separated. The owner chose S11 for L.

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

This command saves no agent. Agents go into `data/agents/` only by the owner's choice: through
`scripts/save_run_agent.py RUN_DIR --agent-name NAME --agents-root PATH [--step N]` for a
finished seed folder (#307; `--agents-root` has no default), `scripts/run_long.sh` for the long
run, or `--agent-name` and `--agents-root` of `scripts/train_ppo.py` and
`scripts/train_offline.py`.
