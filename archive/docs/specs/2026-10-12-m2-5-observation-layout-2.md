# M2.5 Observation layout 2 and training feedback

Date: 2026-10-12. Follows stage #56 (`2026-10-12-m2-rl-environment.md`), which stays as the record of that stage. This spec replaces its section "Observation and actions" for the observation (the action space, the mask and the reward do not change) and extends its notebook section.

## Purpose

Make the observation of the RL environments a principled description of what a seat may know, and give the owner honest evaluation and visible training progress. Stage #56 was a tooling smoke test. This stage is not about a strong agent, and it makes no claim that the new observation is "better" than the old one: the old layout is discarded.

"v1" and "v1.1" are rulesets. The new observation is called "observation layout 2". Ruleset `v1.1` (9 rounds, fields 0..53, explosion limit 7) stays the target.

## Success

1. The principles for the observation (below) are agreed and written down.
2. The observation follows them, the evaluation is honest, curves and opt-in saving work, and a training run provably runs. There is no comparison with the old layout.

## Owner's decisions (context, not tasks)

- The environment serves state-of-the-art and simple RL models alike. It does not invent good models. Normalisation, recurrent policies, embeddings and similar choices are the model's business, not the environment's.
- Notebooks are for exploring. Dedicated experiments are run with scripts.
- Observation scope: the current state only. No memory of earlier rounds beyond what the current state shows. Against a fixed bot the policy learns the average behaviour of that bot during training. What is lost is adapting to the opponent inside one game. Round summaries or an event history for a recurrent policy are possible later extensions.
- No A/B comparison of layouts.
- Out of scope: reward research (#57), Minari and offline RL (#58), balance work, a recurrent policy, self-play (see "Later"), and the three live-update problems of `notebooks/rl_env.py` (see "Notebook").

## Principles of the observation

1. **Information state.** The observation holds everything the seat may know and that matters for its decision, as a snapshot. A policy without memory can then decide from it. Example: the effect of the next chip depends on the previous chip (`place_bonus(chip, previous)`), so the last placed chip must be visible.
2. **Hidden information stays hidden.** The draw order and the simultaneous choice of the opponent never appear. Public knowledge does appear: both bags (the opponent's bag is public).
3. **Egocentric view.** Every entry is "own" or "opponent" from the point of view of the seat.
4. **Raw facts first.** The board and the bags are given as facts, in their natural units.
5. **Derived features: generic rules only.** A derived feature is a function of what the observation already holds. It adds convenience and no new information. It is allowed only for a generic rule of the game (fields, the money table, rubies, the explosion limit, the die, points). It is not allowed for a specific rule (what one colour or chip does). Specific effects, for example the round-end droplet bonus of the last chips, are learned from the raw board. Derived features use the engine helpers (`scoring_field`, `explosion_chance`, the ruleset tables) and never copy rule code into the encoder.
6. **Ruleset parameters that decide meaning are observation entries.** The explosion limit and the total number of rounds can vary per game, so they are entries.
7. **Named, fixed layout.** Every entry has a name (`vector_names`). The layout depends only on the ruleset. A layout version constant changes whenever the layout changes.
8. **Raw values, honest bounds.** No scaling in the environment. The observation space has finite bounds where they are real (flags, fields, counts) and is unbounded where they are not (points).

## Observation layout 2

The flat `float32` vector stays the standard output, as `{"observation": <vector>, "action_mask": <int8 vector>}`. The readable dict form from the encoder stays and is extended in the same way.

### Board map

One block for each field `0..track_end` (54 in `v1.1`):

- the money the field gives, and a ruby flag (from the ruleset);
- for the own seat and the opponent separately: the colour of the chip lying there (one-hot, all zero for no chip), its value, and its placement order in this round (1 for the first chip, 0 for none).

A chip lies on its landing field, the field the engine puts it on. The map shows the position of every placed chip, the distance each one moved (the gap to the previous chip) and the order. If more than one chip lands on the last field (the engine caps at `track_end`), the later chip fills the slot and the order channel shows it.

The map part of the vector is laid out so that it can be reshaped to (fields, channels). This is documented in the README. No second observation space exists.

### Landing fields in the engine state

The state keeps the landing field of each placed chip next to `placed` (the `place` event already has `from` and `to`). The encoder does not replay placements. This is a small engine change with tests. Records and `verify` must stay valid.

### Scalars per seat (own and opponent)

- Kept: points, `droplet_halves`, status (one-hot), `white_total`, `ruby_fields_ahead`, the shop state (purchases, chip purchases, chip colours, shop done), and `money`. `money` is the budget in the Shop phase and the value of the last Resolve otherwise. The entry description says so.
- Dropped: `placed.<chip>` counts (replaced by the map) and `field` (the scoring field replaces it).
- Shared: round, the total number of rounds, phase (one-hot), and the explosion limit.

### Bags

For both seats, two vectors with one entry per chip id: the chips still remaining in the bag, and the complete amounts (every chip the player owns, bag plus placed: `PlayerState.owned()`). The opponent's bag is new.

### Derived features (a task after the raw part)

For both seats, with "stop now" meaning the seat stops with its current chips:

1. the scoring field, and whether a ruby lies there;
2. the money it would get if it stops now: the money table at the scoring field, halved after an explosion, with the last-round multiplier. The bonus die and the round-end bonus are not included;
3. the distance of the white total to the explosion limit;
4. the explosion chance of the next draw;
5. whether the seat would roll the bonus die if both seats stopped now. The die goes to every non-exploded seat that has the best scoring field, so a tie means both roll, and an exploded seat does not roll. Both flags (own and opponent) are entries, because denying the die has value;
6. the number of chips placed this round.

Plus one entry shared by both seats: the point difference to the opponent.

Not included, with the reason: the round-end droplet bonus (a specific rule, learned from the board) and the buy options (the Shop mask already shows what is legal).

### Hidden information test

The existing test stays valid: a change in the draw order of the remaining bag, or in the opponent's pending choice, does not change the observation.

## Evaluation

One function in the package, used by the notebook and the script:

- It plays N games of an agent against an opponent. The default is 500 games, which is about +-4 points of noise on a win rate. Seeds are fixed and seats alternate.
- It returns wins, draws and losses, the average points of both seats, and explosions per game.
- The "before" baselines are a uniform-random agent and the untrained policy with sampled actions. The argmax of an untrained network is not a baseline. "After" shows the trained policy sampled and greedy.
- The result is given against the training opponent and against `RandomBot`.
- One training step is one decision of the agent (about 42 decisions per game, not a game). The notebook and the script say this and show the number of games played in training.

## Opponents

One helper turns a name into an opponent: `random`, or a heuristic bot name such as `draw20-pts4-blue`, through the existing bot parsing. The default stays `RandomBot`. The notebook gets a dropdown, the script a `--opponent` flag.

## Training feedback

- A callback records one row per finished game (result, points of both seats, explosions, decisions). Another hook captures the SB3 training numbers (policy loss, value loss, entropy, `approx_kl`, `explained_variance`).
- The env keeps the engine step results during a game and adds an episode summary to the info at the last step. Explosions are counted from the `explode` events.
- One `train` function in the package takes the ruleset, the opponent, the steps, the seed and an optional run name. Without a run name it keeps everything in memory.
- The notebook plots rolling win rate, average points, explosions per game and the loss curves.

## Saving

Dedicated experiments write into `data/runs/<name>/` as they go. `/data/` is git-ignored already. The folder is separate from `data/records` and `data/tournaments` and is created only when a run with a name starts.

A run folder holds:

- `config.json`: ruleset, opponent, steps, seed, versions, the layout version and the vector names;
- the episode rows and the training numbers (CSV);
- the evaluation results;
- `model.zip`, and checkpoints in the script.

Loading a model refuses when the layout version or the vector names differ. The notebook writes nothing by default. Its "Save this run" button writes the same files to the folder the owner names, and the notebook can load a saved run to show its curves.

## Script

`scripts/train.py` takes `--run <name> --steps N --opponent <bot> --rules <version>` (and a seed). It writes the run folder as it trains. No sweeps, no resume, no hyperparameter search.

## Replay

- The notebook shows one game of the trained model as an in-memory trace, using the existing text rendering of steps. It writes no file by itself.
- "Export this game" writes one record with the existing `GameRecorder` into a folder the owner names, only when the owner presses it. The agent seat is a bot named after the run. The record format does not change, and `quack-rl verify` can check the exported game.

## Notebook

- Built with the project skill `.agents/skills/marimo-notebook`.
- Opponent dropdown, honest evaluation, curves, "Save this run", the replay trace and its export.
- Every notebook task has this acceptance criterion: after a click, the output changes without a manual refresh. It is checked by a click check, not only by `app.run()`, because `app.run()` does not catch missing updates.
- The three live-update problems of the existing cells (action dropdown, "Step with the action", the "2. Steps" table) are not fixed as a side job.
- Without the `train` group the training cells show the install command. The first cells work without it.

## Tests

- Layout: fixed length and names per ruleset, `check_env` without the infinite-bounds warning, the mask equals `legal_actions`, the hidden-information test.
- Map: chip positions, order and gaps match the `place` events of scripted games on `v1` and `v1.1`.
- Derived features: each equals the engine helper it uses on scripted states, including the tie case of the die.
- The engine change leaves records valid (`verify` passes on existing fixtures).
- Evaluation: the same seeds give the same result; the baselines are not the argmax of the network.
- Saving: a run folder round-trips; loading refuses a changed layout; opening the notebook and running its cells write no file.
- The training test is skipped, with a visible reason, without the `train` group, and is never counted as passed.

## Order of work

1. Engine: landing fields in the state.
2. Env: engine step results and the episode summary.
3. Observation layout 2, raw part (map, bags, rule scalars, bounds, layout version, README).
4. Observation layout 2, derived part.
5. Evaluation function and opponent helper.
6. Training callback, log capture and the `train` function.
7. Run folder: save and load.
8. `scripts/train.py`.
9. Notebook: opponent, evaluation, curves, save.
10. Notebook: replay trace and export.

## Later (not in this stage)

- Self-play: a trained policy as an opponent, and the training loop that updates it (`QuackParallelEnv` exists for it).
- A formal mapping from colour to effect (a spellbook), so that a colour no longer holds its effect directly.
- Round summaries or an event history in the observation, for a recurrent policy.
- Reward research (#57), Minari and offline RL (#58).
