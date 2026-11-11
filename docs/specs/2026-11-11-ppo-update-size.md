# PPO update size, and the shortcomings of the screening stage

Date: 2026-11-11. Follows the stage review of #309 (screening, PPO from BC, one long run). The
owner chose none of its options; this spec is a new intake.

## Intent

Stage #309 ran six screenings (S0-S5, about 12 h of laptop time) and chose a long run L = S5.
Every arm stayed near 0 against the preset bots, and the BC arms S3-S5 lost most of their start
(0.19-0.29 at the first checkpoint, 0.02-0.04 at the end). Nobody stopped to ask why. The
training logs (`ppo.csv`) show a likely cause that applies to every arm: the PPO updates are far
too large.

- `approx_kl` (mean over all minibatches of one update) is 0.05 at the start and 0.10-0.16 later,
  in every experiment. 0.01-0.02 is common for PPO.
- The setup is SB3's defaults: `n_steps` 1,024, `batch_size` 64, `n_epochs` 10, so 160 gradient
  steps per update on about 12 games (about 1.5 wins in S1). No `target_kl`, `ent_coef` 0.
- Entropy falls from 0.87 to about 0.15 even in S0, where nearly every game is lost.
- In S0 the critic has nothing to learn about winning: with a reward of almost always -1 it most
  likely learns "how many moves are left" (`explained_variance` about 0.95). The advantages are
  then noise, and advantage normalization scales that noise up.

This stage records what went wrong, makes the PPO update settings part of the experiment config,
and tests two ways to make the updates smaller or better founded, on S1 (the arm with a win
signal). L stays on hold.

## Goals

1. A written account of the shortcomings of stage #309 (part 3 of the screening record).
2. L is on hold, in writing.
3. `n_steps`, `batch_size` and `target_kl` are settings of a PPO experiment config, written in
   every PPO config, used by the run and stored in each run's `config.json`.
4. `ppo.csv` records how many passes (epochs) each update really ran.
5. The monitor notebook shows that number.
6. Screening 3: two S1 variants, S6 and S7, run and recorded (part 4 of the record), with a sense
   check and a suggestion to the owner.

## Non-goals

- The KL penalty toward the BC policy (#306), the long-run budget (#317), saving a run as an
  agent (#307), the monitor for several experiments (#308), the results report (#298).
- Running L, or choosing a new L.
- Variants of S0, S2 or S3-S5. A variant on top of S5 may come in a later stage.
- Other PPO settings: learning rate, `ent_coef`, `n_epochs`, `gamma`, clip range stay at SB3's
  defaults.

## Anti-goals

- Hard numeric stop rules ("escalate if every arm is below X"). The owner wants common sense: a
  written sense check, not thresholds.
- A choice rule that decides for the owner. The engineer suggests; the owner decides after the
  stage, and the stage does not wait for that decision.
- Code defaults for the new settings. Every PPO config states its values.
- A rewrite of parts 1 and 2 of the record. They stay as they are; the new parts are added.

## Part 3 of the record: shortcomings of stage #309

Added to `docs/analysis/2026-11-screening.md`, before any new run. It states, with numbers from
parts 1 and 2 and from the `ppo.csv` files:

- After S0-S2: every score was at the floor (0.0011-0.0181, 1,800 scored games each), and S1
  beat `bot:random` less often than S0 although it trained against it. The stage went on to
  screening 2 instead of asking why.
- After S3-S5: the drop of every BC arm from its first checkpoint, in numbers. The fixed rules
  still chose S5 and wrote L.
- The stage review saw the drop and still offered "run L = S5" as an option.
- The training logs were never read: `approx_kl`, `clip_fraction`, entropy, `explained_variance`
  (the values above, per experiment).
- The owner's part: the owner did not watch the runs in the monitor.
- What changes: the PPO settings become config fields (goal 3), and every screening gets a sense
  check (below).

The same task adds a note to "Next: the long run" in `experiments/README.md`: L is on hold, do
not start it; the reason in one sentence and a link to part 3.

## Sense check after a screening

`experiments/README.md` gets a short section: after each screening, the engineer reads the
learning curves and the PPO metrics (in the monitor or from the CSV files) and writes a short
paragraph in the record. Does the result make sense? Anything that looks implausible (for
example a policy that gets worse while training, or a variant with more signal that scores
below its baseline) goes to the owner before the next run. No thresholds.

## Config fields

`ExperimentConfig` (`src/quack_rl/rl/experiment.py`) gets three fields:

| field | type | meaning |
|---|---|---|
| `n_steps` | int, at least 1 | moves per rollout (MaskablePPO `n_steps`) |
| `batch_size` | int, at least 2 | moves per minibatch (MaskablePPO `batch_size`) |
| `target_kl` | float > 0, or null | MaskablePPO `target_kl`; null means no early stop |

- Required for `kind: "ppo"`: a PPO config without one of them does not load (ValueError that
  names the field). A BC config does not need them.
- `n_steps` must be a multiple of `batch_size` (no partial minibatch).
- `checkpoint_every` and `critic_warmup_steps` must be multiples of the config's `n_steps`
  (today they are checked against the constant `N_STEPS` in `quack_rl.rl.train`).
- `run_ppo_seed` passes the three values to MaskablePPO and writes them in the run's
  `config.json` (today it writes the constants).
- S0-S5 and L get `"n_steps": 1024, "batch_size": 64, "target_kl": null` written in. Their
  meaning does not change.
- `config_diff` names these fields like any other.

`quack_rl/rl/train.py` (the older single-run trainer) and `selfplay.py` keep their constants;
they do not read experiment configs.

## Passes per update in `ppo.csv`

`ppo.csv` gets a new last column `epochs_run`: the number of passes the update ran. SB3's
`train/n_updates` counts passes in total, so `epochs_run` is its difference to the previous
update. Without `target_kl` it is always `n_epochs` (10); with `target_kl` it may be lower.

- A resumed run keeps the column correct across the resume.
- The monitor (`quack_rl.rl.monitor`) still reads the `ppo.csv` files of S0-S5, which have no
  `epochs_run` column. There it is shown as missing, not as an error.
- The notebook `notebooks/rl_monitor.py` plots `epochs_run` with the other PPO metrics.

## Screening 3: S6 and S7

| id | baseline | change | `n_steps` | `batch_size` | `target_kl` | `checkpoint_every` |
|---|---|---|---|---|---|---|
| S6 | S1 | rollout size, at a fixed 16 minibatches per pass | 4,096 | 256 | null | 192,512 |
| S7 | S1 | early stop of the update by `target_kl` | 1,024 | 64 | engineer's choice, 0.02-0.05 | 96,256 |

Everything else as S1: opponents, reward `win_loss`, hidden 256, seeds 0, 1, 2, `steps`
962,560, `n_epochs` 10 (SB3 default), from scratch.

- S6 keeps 160 gradient steps per update (16 minibatches x 10 passes); only the data behind each
  update grows (about 50 games instead of 12). `config_diff` against S1 names `n_steps`,
  `batch_size` and `checkpoint_every`; the `changes` text says that this is one change.
  `checkpoint_every` is 192,512 because 96,256 is not a multiple of 4,096; 192,512 is 47 rollouts,
  so S6 has 5 checkpoints, on every second checkpoint of S1. 962,560 is 235 rollouts.
- S7: the engineer chooses `target_kl` in [0.02, 0.05] and writes the value and the reason in
  the config's `changes` text and in the record, before the run. Note for that choice: SB3 stops
  an update when the KL of a minibatch is above 1.5 x `target_kl`, while the logged `approx_kl`
  is the mean over the whole update.
- Commands as in parts 1 and 2 (`systemd-run ... MemoryMax=4G ... /usr/bin/time -v`,
  `--threads 1`), one after the other.

Part 4 of the record holds, like parts 1 and 2: the commands, the run data, the per-seed rows, the
sha256 of the `final_eval.csv` files, the final tables (greedy rows only are enough), the
scores, and the learning curves (greedy, presets). In addition:

- The win rate against `bot:random` per checkpoint, for S1, S6 and S7.
- The PPO metrics per experiment (S0, S1, S6, S7): `mean_reward`, `approx_kl`,
  `clip_fraction`, entropy, `explained_variance` (and `epochs_run` for S6, S7) at a few points
  of training.
- The sense check (above).
- A suggestion to the owner: does S6 or S7 (or neither) look better than S1, compared with S0,
  S1 and each other, and why. The owner decides; the stage does not wait.

Budget: about 2 h per screening on the laptop, about 4 h in total.

## Decided by the planner

- Record parts 3 and 4 go in the existing record file.
- The new `ppo.csv` column is named `epochs_run`.
- The sense check section in `experiments/README.md` is part of the shortcomings task.
- S6 and S7 are filed as one screening task, run one after the other.
