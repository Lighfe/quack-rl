# RL experiment setup: a faster engine, controlled PPO and BC experiments, a live run monitor

Date: 2026-11-07. Source: owner intake after the stage review of #277 (M2.24).

## Intent

Stage #277 trained five agents on ruleset v2.3. BC and CQL win 32-48% against each preset bot.
PPO online and self-play won 0 of 600 games against the presets, and the planner 5 of 300. Each
online agent had one run of about 35 minutes. PPO online played only against the presets, won 2
of about 2,600 training games, and so got almost no reward signal.

This stage does not try to win. It prepares clear, repeatable experiments that the owner runs
after the stage, one at a time, each at most 6 hours of wall time on the laptop. Each experiment
changes exactly one thing against a shared baseline. The owner watches a run live in a marimo
notebook: the training curves, and the win rate of the newest checkpoint against the bots.

The work must stay grounded in established RL practice: budgets in environment steps, several
seeds per experiment, one fixed evaluation protocol, and a record of which data each run used.

Long-term vision of the owner (not in this stage): explain and interpret the decisions and
policies of all models, and turn the planner into real model-based RL (search plus learning).
Choices in this stage keep that possible: small networks, named observation features, saved
models that can be loaded and inspected.

## Goals

1. The game engine copies a game state faster. Every game gives exactly the same result for a
   given seed as before.
2. The PPO training script supports long, resumable runs that the owner starts by hand.
3. One experiment command runs one experiment: 3 seeds side by side, each with its own evaluator.
4. Six experiments are defined as config files, ready to run (table below).
5. BC has two new variants (label smoothing, entropy bonus); PPO can start from BC weights.
6. A marimo notebook shows a running or finished experiment live.
7. Every dataset and every run records where its data came from.
8. Each experiment has a short trial run in the stage that proves it works end to end. The BC
   experiments (B1, B2) are cheap and run fully in the stage.

## Non-goals

- Claims about which approach works. No results report, no final tournament in this stage.
  The report comes in a later stage, after the owner's long runs.
- Self-play with the presets in its pool (#86 stays parked).
- More varied bot datasets (random moves mixed in, higher shop temperature): parked.
- The planner as model-based RL: parked.
- Interpretability research: parked.
- Changes to the CQL method, the observation layout or the rules.

## Anti-goals

- An experiment that changes more than one thing against its baseline.
- A run whose budget is set in hours. Budgets are environment steps; wall time is only measured.
- A run that does not record its dataset, its config or its seeds.
- Training results that depend on the engine speed-up (any change of a game for a given seed).
- QA or trial runs that save agents into `data/agents/` (they appear in the browser's opponent
  list, as `agent:selfplay-qa` did after #274).

## The experiments

All PPO experiments use the same opponents, reward, network, PPO settings and step budget as P0,
except the one thing in the "changes" column.

| id | name | changes against the baseline | baseline |
|---|---|---|---|
| P0 | PPO baseline | nothing: today's setup (opponents: uniform mix of the three presets; reward +1/0/-1 at game end) with the new step budget and the shared network | (control) |
| P1 | PPO, mixed opponents | opponents: a fixed mix of `bot:random`, weak rule-bot settings and the three presets | P0 |
| P2 | PPO, point-margin reward | reward at game end: own points minus the opponent's points, scaled to [-1, 1] | P0 |
| P3 | PPO from BC | the actor starts from the weights of the better of B1 and B2 (see "PPO from BC") | P0 |
| B1 | BC, label smoothing | the BC target puts a small share of the probability on the other legal actions | today's BC |
| B2 | BC, entropy bonus | the BC loss gets a small bonus for the entropy of the policy over the legal actions | today's BC |

"Today's BC" is rerun as the BC control B0 (the #275 settings, seeds 0, 1, 2), so B1 and B2
compare against the same seeds and the same evaluation. It costs minutes, so it runs in the stage.

Order: P0 first. Then P1 and P2, one by one. B1 and B2 run in the stage. P3 after B1 and B2.

"Better of B1 and B2": the higher mean win rate over the three presets in the fixed evaluation,
with the greedy and the sampled play both reported. If neither beats today's BC, P3 starts from
today's BC trained into the shared network, and the record says so.

## Shared network

Today the PPO policy is the SB3 `MlpPolicy` default and BC is a 256x256 ReLU MLP
(`make_mlp` in `src/quack_rl/rl/offline.py`). P3 can only load BC weights if the actor has the
same shape. So all PPO experiments (P0 to P3) use one shared network: actor and critic each with
two hidden layers of 256 units and ReLU, as BC. P0 is a new baseline, so this changes no
comparison inside the stage. (Planner's call.)

## PPO from BC

- The actor gets the BC weights. The critic starts random.
- Critic warm-up: for a fixed number of steps at the start, only the critic is trained and the
  actor is frozen. This is part of P3, not a separate experiment: without it a random critic is
  known to undo the BC policy in the first updates.
- No penalty for moving away from BC (kept out to keep P3 to one change).

## Budget, seeds, evaluation

- Each experiment: 3 seeds (0, 1, 2), run side by side, at most 6 hours of wall time in total.
- The step budget per run is a fixed number of environment steps, the same for P0 to P3. It is
  set after the engine speed-up is measured, so that 3 runs plus 3 evaluators fit in 6 hours on
  the laptop (8 cores) within a memory cap. The measurement and the number go into the
  experiment configs. For scale: at today's 144 steps per second, 6 hours is about 3 million steps.
- Live evaluation: a separate evaluator process per run watches the run folder. For each new
  checkpoint it plays a fixed set of games (for example 50 per opponent) against each preset and
  `bot:random`, with fixed seeds and seats swapped, and appends the win rates with the 95% Wilson
  interval to a file in the run folder. It runs in its own process so it does not slow training.
- Final evaluation: when a run ends, its last checkpoint plays the fixed evaluation with the
  tournament form of #276 (200 games per preset and `bot:random`, seats swapped, seed 2026).
- BC experiments and agents from BC are evaluated twice: sampled play and greedy play (always the
  most likely legal action). This shows whether a flatter policy stops at random.

## What a run writes

Into its run folder, while it runs:

- the config (experiment id, seed, step budget, opponents, reward, network, PPO settings,
  dataset id and hash when one is used, library versions, git commit)
- PPO numbers after each update: steps, mean final reward of the games that ended, policy loss,
  value loss, entropy, approximate KL, clip fraction, explained variance, wall time
- checkpoints at fixed step counts
- the evaluator's file (one row per checkpoint and opponent)
- optional (a flag of the script): the training games as seeds and actions, so the observations
  can be rebuilt with the deterministic engine and used for offline training later

A run can resume from its newest checkpoint after an interruption.

## Data provenance

- Each dataset folder gets a manifest: the bot specs, games per pairing, seeds, ruleset and
  layout, the command, and the hash of the data file.
- Each run's config names the dataset (or none) and its hash.

## Agents root

The training scripts (`scripts/train_ppo.py`, `scripts/train_selfplay.py`,
`scripts/train_offline.py`) and the experiment command take the agents root as an argument.
Trial and QA runs save outside `data/agents/`. Only the owner's chosen agents go into
`data/agents/`.

## The notebook

A marimo notebook (`notebooks/rl_monitor.py`; the older notebooks are in `archive/notebooks/`)
that the owner starts next to the experiment command:

- pick a run folder or an experiment (all its seeds)
- the PPO numbers over the steps, and for BC the loss per epoch
- the win rate per opponent over the checkpoints, with the intervals
- the 3 seeds of an experiment together, and the baseline P0 next to it
- it refreshes by itself as new rows arrive, with no manual refresh: live updates are part of the
  design from the start (earlier notebooks needed a manual refresh)

## Constraints

- Ruleset v2.3, observation layout 10.
- The owner's laptop, CPU, 8 cores; runs inside a memory cap.
- Long runs are started by the owner after the stage, not in a Claude Code session.
- No secrets in commits, issues or reports.

## Calls made (by the planner, not the owner)

- The shared 256x256 ReLU network for all PPO experiments.
- The critic warm-up inside P3; no penalty for moving away from BC.
- A separate evaluator process per run.
- 3 seeds per experiment, seeds 0, 1, 2.
- The rule for "better of B1 and B2", and the BC control B0.
- The notebook path `notebooks/rl_monitor.py`.
- Training games saved as seeds and actions, not as observations (about 12 GB per million steps
  otherwise).

## Left to the builder

- The exact copy method of the engine, as long as games stay identical for every seed.
- The checkpoint interval, the games per opponent in the live evaluation, the critic warm-up
  length, the label smoothing and entropy weights, the scale of the point-margin reward.
- The weak bot settings in P1's mix and their shares.
- The file formats of the run outputs, and the config format of an experiment.
