# Screening, PPO from BC, and one long run

Date: 2026-11-09. Follows the stage review of #296 (RL experiment setup) and the owner's note on
it (https://github.com/Lighfe/quack-rl/issues/296#issuecomment-6744495591).

## Intent

The goal is a proof of concept, not a perfect model. Each idea (opponent mix, point-margin reward,
PPO starting from BC) gets one fair, short look at the same budget. The best setup then gets
one long run. That replaces four long runs (P0-P3, about 20 h) by short screenings that the
engineer runs in the stage, and one long run that the owner starts after the stage.

The stage also fixes an error of the last stage. #295 chose P3's BC start by the BC models' own
greedy win rate. But label smoothing (B1) and the entropy bonus (B2) are meant to give PPO a
better start, so the measure is what PPO learns from each BC start. A BC model's own score is
never compared with a PPO run, and it decides nothing here.

## Goals

1. The `QuackEnv` step gets faster, so PPO gets more steps per hour. Games stay identical for
   every seed.
2. `init_from_bc` can name one BC model per PPO seed: PPO seed k starts from BC seed k.
3. The step rate is measured again. The screening budget and the long-run budget are set from it.
4. Screening 1: PPO with the three variants of today (baseline, mixed opponents, point-margin
   reward) at the screening budget. The best is X.
5. Screening 2: X started from each BC model (B0, B1, B2) at the same budget, compared with each
   other, with X from scratch shown as a reference.
6. The config of the one long run: the best of screening 2 and X from scratch, at the long-run
   budget. The owner runs it after the stage.
7. A short screening record with the tables and the two choices.

## Non-goals

- The results report (#298), saving a run as an agent (#307), the monitor for several
  experiments (#308): a later stage, after the long run.
- More BC variants, a KL penalty towards BC (#306), new reward or opponent ideas.
- Planner simulations within the 2 s cap (#297), doc and kit fixes (option C of the review).
- Tuning: no hyperparameter search inside a variant.

## Anti-goals

- Any choice made by a BC model's own win rate.
- A screening arm that differs from its baseline in more than one thing.
- A rule for a choice that is written after the numbers are seen. The rules below are fixed now.
- Game changes from the speed-up: a game for a given seed must stay the same, move by move.
- Screening runs or trial runs that write into `data/agents/`.

## The experiments

New config files in `experiments/`. They replace P0-P3, which are deleted (no long runs of them
exist). B0-B2 stay: their `model.pt` files are the BC starts. The setting of each variant is
taken from today's P0-P3, unchanged; only `steps` and `checkpoint_every` change (and
`init_from_bc` for the BC arms).

| id | what | baseline | differs from the baseline in |
|---|---|---|---|
| S0 | PPO, today's P0 setup | (control) | - |
| S1 | PPO, mixed opponents (today's P1) | S0 | `opponents` |
| S2 | PPO, point-margin reward (today's P2) | S0 | `reward` |
| S3 | X started from B0, critic warm-up 51,200 steps | X | `init_from_bc`, `critic_warmup_steps` |
| S4 | X started from B1 | S3 | `init_from_bc` |
| S5 | X started from B2 | S3 | `init_from_bc` |
| L | the long run: the chosen setup at the long-run budget | the chosen S config | `steps`, `checkpoint_every` |

S0-S5 have the same `steps` and `checkpoint_every`. S3-S5 use the paired form
`data/experiments/B<n>/seed{seed}/model.pt` (goal 2). S3-S5 can only be written after X is
known.

## Choice rules (fixed before any screening run)

Score of a PPO experiment: the mean greedy final win rate against the three presets, over its
3 seeds (9 values from `final_eval.csv`).

- **X:** the highest score of S0, S1, S2. If two are within 0.01 of each other, the simpler one
  wins in the order S0, S1, S2. (Planner's call.)
- **Best BC arm:** the highest score of S3, S4, S5. Within 0.01: the order S3 (B0), S5 (B2),
  S4 (B1). (Planner's call: plain BC first, then the flatter but still playable B2.)
- **Long run:** the best BC arm if its score is higher than X's score by more than 0.01,
  otherwise X from scratch. (Planner's call.)

The record also gives, for each experiment, the sampled final win rate and the learning curve
(the greedy win rate against the presets at each checkpoint, from `eval.csv`, mean over seeds).
These are reported, but they do not decide.

## Budgets

The rule of the last stage stays: an experiment (3 trainings and 3 evaluators side by side, then
the final evaluation) is measured, and its time is planned from the measured rate. Budgets are
environment steps. Wall time is only measured.

- **Long run (L):** the most steps such that `steps / rate + final evaluation time` is at most
  18,360 s (6 h minus 15%), a multiple of `checkpoint_every`.
- **Screening (S0-S5):** the most steps such that one screening experiment ends in at most
  1.5 h (5,400 s) by the same sum, with at least 6 checkpoints, so the learning curve has points.
  (Planner's call: 6 screening experiments then take at most 9 h of the engineer's run time.)
- The measurement is done after the speed-up, as in "Step budget" of `experiments/README.md`,
  and the README section is updated.

## Speed-up of the env step

#285 made the state copy faster (the planner's rollouts doubled), but not the env step: about
145-150 steps per second before and after. The engineer of #285 found the time is spent in the
observation and mask encoding and in the opponent bot.

- Profile `QuackEnv.step` and make the slow parts faster. The approach is the builder's call.
- Bar: `scripts/measure_speed.py --env-steps 20000`, before and after, on the same machine.
  There is no target number. If no clear gain is possible, the profile is recorded and the
  budgets come from the measured rate anyway.
- Games and observations stay identical for every seed (a test compares them before and after).

## Paired BC start

- `init_from_bc` may hold the text `{seed}`. Each seed's training replaces it with its own seed
  number, so seed k loads `.../seed<k>/model.pt`. Without `{seed}` it works as today.
- The resolved path and its sha256 are written into each seed's `config.json`, as today.
- `--resume` checks the resolved file, as today.

## The screening record

`docs/analysis/2026-11-screening.md`: the commands, the budget, the tables (greedy and sampled
final win rate per seed and opponent, the score per experiment), the learning curves as tables,
and the two choices with the rule applied in numbers. No claims beyond the numbers; the full
report is #298.

## Constraints

- Laptop: 8 cores, CPU, 15 GB RAM. Every run under the memory cap wrapper of
  `experiments/README.md`.
- The `data/experiments/B<n>/seed<k>/model.pt` files and the dataset are local, git-ignored data.
  The engineer runs on this machine.
- The old spec's rule "Better of B1 and B2" (`docs/specs/2026-11-07-rl-experiment-setup.md`)
  gets a note that this spec replaces it, and why.

## Left to the builder

- How to make the env step faster.
- The run folder for the screenings (for example `data/experiments`).
- The order of the screening commands within a task, and whether seeds run side by side.
