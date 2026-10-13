# M2.5 Observation layout 2 and training feedback Implementation Plan

> **For the workflow:** This plan is turned into GitHub issues (one per task) and run through `docs/process.md`. Do not run it with subagent-driven-development or executing-plans (see `AGENTS.md`). Steps use checkbox syntax as a checklist for the engineer of each issue.

**Goal:** Give the RL environments an observation that follows the agreed principles (board map, both bags, rule scalars, generic derived features), an honest evaluation, visible training progress, and opt-in saving of runs.

**Architecture:** The engine state keeps the landing field of each placed chip. `QuackParallelEnv` keeps the engine step results of a game. The encoder builds a flat, named, bounded vector whose last block is the board map (reshapeable to fields x channels). New modules in `src/quack_rl/rl/` hold the derived features, the opponents, the evaluation, the training function and the run folder. `scripts/train.py` and `notebooks/rl_env.py` are thin callers.

**Tech Stack:** Python 3.12, Gymnasium, PettingZoo, numpy, pytest; SB3 and sb3-contrib (dependency group `train`); marimo and altair (dev group) for the notebook.

**Spec:** `docs/specs/2026-10-12-m2-5-observation-layout-2.md`. It follows `docs/specs/2026-10-12-m2-rl-environment.md`.

## Global Constraints

- Say "observation layout 2", never "v2". "v1" and "v1.1" are rulesets. Ruleset `v1.1` (9 rounds, fields 0..53, explosion limit 7) stays the target; `v1` must keep working.
- The engine, bots and records do not import `quack_rl.rl`. Existing records and `quack-rl verify` stay valid.
- Hidden information never enters the observation: no draw order, no simultaneous choice of the opponent. Both bags are public.
- No rule code is copied into the encoder: use `scoring_field`, `explosion_chance`, the ruleset tables and the components.
- Raw values in the observation, no scaling. Finite bounds only where they are real.
- Nothing is written to disk unless a run name or an explicit "Save"/"Export" action is given. Runs go to `data/runs/<name>/`, never to `data/records` or `data/tournaments`.
- Test command: `uv run --with pytest pytest`. A test skipped for the missing `train` group is never reported as passed.
- Notebooks use the project skill `.agents/skills/marimo-notebook`. Every notebook task has the criterion: after a click the output changes without a manual refresh (checked by a click check, not only by `app.run()`).
- Style: ruff clean (`ruff check`, `ruff format --check`), line length 100, pyright clean as today.

## Review Focus

- Two chips landing on the last field (cap at `track_end`): the later chip fills the map slot and its order is shown. Test it.
- A `remove_chip` shop item removes a chip from `placed`: the stored landing fields must stay in step with `placed`. Test it.
- A seat that exploded: money if it stops is halved; it does not roll the die; the opponent may still roll. Test all three.
- Tie on the scoring field with both seats not exploded: both die flags are 1. Test it.
- An empty bag: the explosion chance is 0 and the vector has no NaN. Test it on a state with an empty bag.
- Ruleset `v1`: layout builds, bounds are valid, `check_env` passes. Test it.
- A model saved with another layout version or other vector names is refused on load. Test it.
- Opening the notebook and running its cells creates no file, and creates no `data/runs` folder. Test it.

## File Structure

- `src/quack_rl/engine/state.py`, `brew.py`, `shop.py`: landing fields (task 1).
- `src/quack_rl/rl/parallel_env.py`, `single_env.py`: step results and episode summary (task 2).
- `src/quack_rl/rl/encode.py`: layout 2, raw part (task 3). Keeps the encoder in one file.
- `src/quack_rl/rl/derive.py` (new): derived features (task 4).
- `src/quack_rl/rl/opponents.py` (new), `src/quack_rl/rl/evaluate.py` (new): task 5.
- `src/quack_rl/rl/train.py` (new): task 6. Imports SB3 inside functions only, so the default install works.
- `src/quack_rl/rl/runs.py` (new): task 7.
- `scripts/train.py` (new): task 8.
- `notebooks/rl_env.py`: tasks 9 and 10.
- `README.md`: section "RL environment" (tasks 3, 4, 8).
- Tests: `tests/test_state_actions.py` or a new `tests/test_placed_fields.py`, `tests/test_rl_encode.py`, `tests/test_rl_single_env.py`, `tests/test_rl_parallel_env.py`, new `tests/test_rl_derive.py`, `tests/test_rl_evaluate.py`, `tests/test_rl_train.py`, `tests/test_rl_runs.py`, `tests/test_rl_notebook.py`.

---

### Task 1: Engine keeps the landing field of each placed chip

**Files:**
- Modify: `src/quack_rl/engine/state.py` (field on `PlayerState`), `src/quack_rl/engine/brew.py:24`, `src/quack_rl/engine/shop.py:20,59`
- Test: `tests/test_placed_fields.py`

**Interfaces:**
- Produces: `PlayerState.placed_fields: list[int]`, same length and order as `placed`; entry i is `p.field` right after chip i was placed (the `to` of its `place` event).

- [ ] **Step 1: Write the failing tests.** Scripted draws on `v1.1`: after each draw, `p.placed_fields[-1] == event["to"]` of the `place` event and `len(placed_fields) == len(placed)`. A test for the cap: draw until two chips land on `track_end`, both entries equal `track_end`. A test for the shop: after a `remove_chip` purchase, `len(placed_fields) == len(placed)` and the removed chip's entry is gone. A test that `placed_fields` is empty after the round reset.
- [ ] **Step 2: Run them and see them fail** (`AttributeError`).
- [ ] **Step 3: Implement.** Add `placed_fields: list[int] = field(default_factory=list)` after `placed`. Append `p.field` after `p.placed.append(chip_id)` in `_draw`. In `shop.py` pop the same index when a chip is removed from `placed`, and clear it where `p.placed = []` is set.
- [ ] **Step 4: Run the whole suite.** Existing records and `verify` tests must still pass without change (the field is state, not part of the record).
- [ ] **Step 5: Commit.**

### Task 2: Env keeps the engine step results and an episode summary

**Files:**
- Modify: `src/quack_rl/rl/parallel_env.py` (`step`, `_fold`, `reset`), `src/quack_rl/rl/single_env.py` (`step`)
- Test: `tests/test_rl_parallel_env.py`, `tests/test_rl_single_env.py`

**Interfaces:**
- Produces: `QuackParallelEnv.trace: list[StepResult]` (all engine steps of the current game in order, including folded phases; cleared by `reset`). `QuackEnv.trace` returns the same list. At the last step `QuackEnv.step` puts `info["episode"]` with the keys `result` (`"win"|"draw"|"loss"` for the agent seat), `points` (`{"own": int, "opponent": int}`), `explosions` (`{"own": int, "opponent": int}`, counted from `explode` events), `decisions` (number of `step` calls of the agent in the game), and `seat`.

- [ ] **Step 1: Write the failing tests.** Scripted game: `len(env.trace)` equals the number of engine steps and the concatenated events equal the events of the same game run with `engine.step` directly. Random games on `v1` and `v1.1`: `info["episode"]` exists only at the last step; `explosions` equals the count of `explode` events per seat; `points` equals the final state points; `result` agrees with `reward`.
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement.** Append every `StepResult` from `step(...)` in `step` and in `_fold`. Count decisions in `QuackEnv`. Build the summary when `done`.
- [ ] **Step 4: Run the suite** (`parallel_api_test` and `check_env` still pass).
- [ ] **Step 5: Commit.**

### Task 3: Observation layout 2, raw part

**Files:**
- Modify: `src/quack_rl/rl/encode.py`, `src/quack_rl/rl/parallel_env.py` (observation space), `src/quack_rl/rl/single_env.py` (observation space), `src/quack_rl/rl/__init__.py`, `README.md` (section "RL environment")
- Test: `tests/test_rl_encode.py`, `tests/test_rl_single_env.py`

**Interfaces:**
- Consumes: `PlayerState.placed_fields` (task 1).
- Produces: `OBSERVATION_LAYOUT: int = 2`; `vector_names(rs) -> list[str]`; `observe(state, rs, seat) -> dict`; `vectorize(obs, rs) -> np.ndarray`; `observation_bounds(rs) -> tuple[np.ndarray, np.ndarray]` (low, high, `float32`, `inf` where no real bound exists, e.g. points); `MAP_CHANNELS: int` and `map_slice(rs) -> slice`. The map is the last block of the vector, field-major: entry for field f and channel c is at `map_slice.start + f * MAP_CHANNELS + c`, so `vec[map_slice(rs)].reshape(rs.track_end + 1, MAP_CHANNELS)` works. Map channels in order: `money`, `ruby`, then for `own` and for `opponent`: one colour flag per colour of the ruleset (in `_colours(rs)` order), `value`, `order`.
- Scalars per seat: `points`, `droplet_halves`, status one-hot, `white_total`, `ruby_fields_ahead`, `money`, `purchases`, `chip_purchases`, chip-colour counts, `shop_done`, `bag.remaining.<chip_id>` and `bag.owned.<chip_id>` for every chip id. Shared: `round`, `rounds`, `explosion_limit`, phase one-hot. Removed: `placed.<chip>` and `field`.

- [ ] **Step 1: Write the failing tests.** (a) Names: unique, `len(names) == len(vector)`, depend only on the ruleset, for `v1` and `v1.1`. (b) Map vs events: in random games, for each `place` event, the map slot at `event["to"]` of the placing seat has that chip's colour flag, value and order (its index among that seat's `place` events in the round, starting at 1); fields with no chip are all zero; the field money and ruby channels equal `rs.money[f]` and `f in rs.rubies`. (c) Last-field cap: two chips on `track_end` show the later chip and its order. (d) Opponent bag: `bag.remaining` and `bag.owned` of the opponent are present and equal `p.bag` and `p.owned(...)`. (e) Hidden information: keep the existing test, and add one that swaps the draw order inside the remaining bag (a different insertion order) and one that changes the opponent's pending choice; both leave the vector unchanged. (f) `explosion_limit` and `rounds` equal the ruleset values, also after `apply_overrides` and `with_rounds`. (g) `vector` lies inside `observation_bounds` at every state of random games. (h) `check_env` passes on `v1` and `v1.1` without the infinite-bounds warning for the bounded entries.
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement** the layout, the bounds and the exports. Set `spaces.Box(low, high, ...)` from `observation_bounds` in both envs. Update `vector_names` users (the notebook test still passes because it uses the function).
- [ ] **Step 4: Update the README** section "RL environment": layout version, entry groups, the reshape of the map, the note on `money`.
- [ ] **Step 5: Run the suite and commit.**

### Task 4: Observation layout 2, derived features

**Files:**
- Create: `src/quack_rl/rl/derive.py`
- Modify: `src/quack_rl/rl/encode.py` (append the entries before the map block), `README.md`
- Test: `tests/test_rl_derive.py`, `tests/test_rl_encode.py`

**Interfaces:**
- Consumes: layout from task 3, `scoring_field`, `explosion_chance`, `Ruleset.money`, `Ruleset.rubies`, `Ruleset.last_round_money_percent`.
- Produces: `derived(state, rs, seat) -> dict[str, float]` with per seat (`own`, `opponent`): `scoring_field`, `ruby_at_scoring_field`, `money_if_stop`, `limit_distance` (`explosion_limit - white_total`), `explosion_chance`, `rolls_die`, `chips_placed`; and shared `point_delta` (own points minus opponent points). `money_if_stop`: money table at the scoring field, `//2` after an explosion, times `last_round_money_percent // 100` in the last round; no die, no round-end bonus. `rolls_die`: 1 when the seat is not exploded and its scoring field equals the best scoring field among non-exploded seats, else 0.

- [ ] **Step 1: Write the failing tests** on built states: `money_if_stop` equals the `amount` of the `money` event when a seat has no die money (compare on a game where the die gives droplet or nothing, or compare with the engine formula for the table value); halving after an explosion; the last-round multiplier; `explosion_chance` equals the helper on the same bag; die flags for lead, tie (both 1), lag, and exploded (own 0, opponent may be 1); empty bag gives chance 0 and no NaN; every derived value inside the bounds.
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement** `derived` with engine helpers only, and add the entries (names and bounds) to the encoder.
- [ ] **Step 4: Update the README, run the suite, commit.**

### Task 5: Evaluation function and opponent helper

**Files:**
- Create: `src/quack_rl/rl/opponents.py`, `src/quack_rl/rl/evaluate.py`
- Modify: `src/quack_rl/rl/__init__.py`
- Test: `tests/test_rl_evaluate.py`

**Interfaces:**
- Produces: `make_opponent(name: str, seed: int | None = None)` where `name` is `"random"` or a heuristic bot name such as `"draw20-pts4-blue"` (`ValueError` with the known forms on a bad name; uses `parse_bot_name` and `HeuristicBot`). `Policy = Callable[[np.ndarray, np.ndarray], int]` (observation, mask to action index). `random_policy(seed: int) -> Policy` (uniform over the mask). `evaluate(policy, opponent, rules="v1.1", games=500, seed=0) -> EvalResult`, a frozen dataclass with `games`, `wins`, `draws`, `losses`, `points_own`, `points_opponent`, `explosions_own` (average per game), and properties `win_rate`, `draw_rate`, `loss_rate`. Game i uses chance seed `seed + i` and the agent seat `p1` for even i and `p2` for odd i. `sb3_policy(model, deterministic: bool) -> Policy` lives in `train.py` (task 6), not here.

- [ ] **Step 1: Write the failing tests.** `make_opponent` accepts `random` and `draw20-pts4-blue`, rejects `draw200-pts4-blue` and `foo`. `evaluate` with `random_policy(0)` against `random`: `wins + draws + losses == games`; the same call twice gives equal results; both seats are used (count via a recording wrapper); a policy that always takes the first legal action is a valid `Policy`. Draws are reported, not folded into wins or losses.
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement** with `QuackEnv` (it already skips Wait-only steps and reseeds a default opponent; for a named opponent build it with `make_opponent` and a seed).
- [ ] **Step 4: Run the suite, commit.**

### Task 6: Training callback, log capture and the `train` function

**Files:**
- Create: `src/quack_rl/rl/train.py`
- Test: `tests/test_rl_train.py`

**Interfaces:**
- Consumes: `info["episode"]` (task 2), `evaluate`, `make_opponent`, `random_policy` (task 5).
- Produces: `TrainingLog` (dataclass with `episodes: list[dict]`, `metrics: list[dict]`; episode row keys: `episode`, `timestep`, `result`, `points_own`, `points_opponent`, `explosions_own`, `decisions`; metric row keys: `timestep` plus the SB3 values that exist: `policy_gradient_loss`, `value_loss`, `entropy_loss`, `approx_kl`, `explained_variance`). `sb3_policy(model, deterministic: bool) -> Policy`. `train(steps: int, rules="v1.1", opponent="random", seed=0, eval_games=500, sink=None) -> TrainResult` (dataclass: `model`, `log`, `baseline_random: EvalResult`, `baseline_untrained: EvalResult` (untrained policy, sampled), `trained_sampled`, `trained_greedy`, each also against `RandomBot` when the opponent is not `random`; `games_played` taken from the log). `RunSink` protocol: `start(config: dict)`, `episode(row: dict)`, `metrics(row: dict)`, `finish(result: TrainResult)`. All SB3 imports happen inside functions; without the `train` group `train()` raises an error that names `uv sync --group train`.

- [ ] **Step 1: Write the failing tests.** Guarded by `pytest.importorskip("sb3_contrib")` with a visible skip reason: `train(256, eval_games=10)` runs; `len(log.episodes) == games_played > 0`; every episode row has the keys above; `metrics` has rows with the SB3 keys; the untrained baseline is sampled (calling it twice with different seeds can differ) and is not the argmax; a sink gets `start`, `episode` rows and `finish` in order. A test that does not need `train`: calling `train` without SB3 installed raises the install message (monkeypatch the import).
- [ ] **Step 2: Run them and see them fail or skip.** Say which ran and which were skipped.
- [ ] **Step 3: Implement** a `BaseCallback` that reads `infos[i]["episode"]` on done, and a logger output format that copies SB3 `record` values into `log.metrics` at each rollout end.
- [ ] **Step 4: Run the suite, commit.**

### Task 7: Run folder, save and load

**Files:**
- Create: `src/quack_rl/rl/runs.py`
- Modify: `src/quack_rl/rl/train.py` (`train(..., run: str | None = None, runs_dir=Path("data/runs"), checkpoint_every: int | None = None)`)
- Test: `tests/test_rl_runs.py`

**Interfaces:**
- Consumes: `RunSink`, `TrainResult`, `OBSERVATION_LAYOUT`, `vector_names`.
- Produces: `RunFolder(path)` implementing `RunSink`; it writes `config.json` (rules, opponent, steps, seed, package version, `layout`, `vector_names`), `episodes.csv`, `metrics.csv` (appended as training runs), `eval.json` (at `finish`), `model.zip` (at `finish`) and `checkpoints/step_<n>.zip`. The folder is created at `start`, never earlier. `save_run(path, result, config)` writes the same files from an in-memory result. `load_run(path) -> LoadedRun` (config, episodes, metrics, eval). `load_model(path, rules)` loads `model.zip` and raises `LayoutMismatch` when `layout` or `vector_names` differ from the current ones. `train(run="name")` uses `RunFolder(runs_dir / name)`; a run name that exists is refused (no overwrite).

- [ ] **Step 1: Write the failing tests** with `tmp_path` as `runs_dir`: a run writes the five kinds of file; the CSV grows during training (check with a sink call order, no SB3 needed); `save_run` then `load_run` round-trips the rows; a changed `layout` or a changed `vector_names` in `config.json` makes `load_model` raise `LayoutMismatch` (model load itself is skipped without SB3); an existing run name raises; with `run=None` nothing is created under `tmp_path`.
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement** with the standard library (`csv`, `json`). Add `data/runs` handling only through the `runs_dir` argument; do not edit `.gitignore` (`/data/` is ignored already).
- [ ] **Step 4: Run the suite, commit.**

### Task 8: `scripts/train.py`

**Files:**
- Create: `scripts/train.py`
- Modify: `README.md` (how to run, where runs go)
- Test: `tests/test_rl_train_script.py`

**Interfaces:**
- Consumes: `train(...)` with `run=`.
- Produces: `uv run --group train python scripts/train.py --run NAME --steps N --opponent random|<bot name> --rules v1.1 --seed 0 --eval-games 500 --checkpoint-every N`. `--run` is required, so the script never trains without writing. It prints the run folder and the evaluation table (wins, draws, losses) at the end. A bad opponent name or an existing run exits with a short message and a non-zero code.

- [ ] **Step 1: Write the failing tests** that import the script's `main(argv)`: a missing `--run` fails; a bad `--opponent` fails with the known forms; with `importorskip("sb3_contrib")`, a run of 256 steps and 10 eval games into `tmp_path` creates the run folder with `model.zip`.
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement** `main(argv: list[str] | None = None) -> int` with `argparse`.
- [ ] **Step 4: Update the README, run the suite, commit.**

### Task 9: Notebook: opponent, honest evaluation, curves, save

**Files:**
- Modify: `notebooks/rl_env.py`, `tests/test_rl_notebook.py`, `README.md` (notebook section)
- Build with `.agents/skills/marimo-notebook`.

**Interfaces:**
- Consumes: `make_opponent`, `evaluate`, `train`, `save_run`, `load_run`.
- Produces: notebook cells: opponent dropdown (`random`, `draw20-pts4-blue`, a free text field); training with steps and games; a text that says "one training step is one decision of the agent, about 42 per game" and shows the games played; a table of wins, draws and losses for the baselines (uniform-random, untrained sampled) and the trained policy (sampled and greedy) against the training opponent and `RandomBot`; altair plots of rolling win rate, average points, explosions per game and the loss curves; a "Save this run" button with a name field that writes through `save_run` to `data/runs/<name>`; a way to load a saved run and plot its curves. The three old live-update problems are not fixed here.

- [ ] **Step 1: Write the failing tests** for the logic functions the cells call (opponent choice, table building, the curve data frames, save path handling), with `importorskip` for the training part.
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement** the cells. Cell outputs depend on their inputs through marimo's reactive model (no output built from a stale object).
- [ ] **Step 4: Click check.** Run the notebook (`uv run --group train marimo run notebooks/rl_env.py` or edit mode), change the opponent dropdown, press Train, press Save: after each click the output changes without a manual refresh. Report what was clicked and seen.
- [ ] **Step 5: No-write check.** Open the notebook, run all cells without pressing Save; `git status --porcelain` and `ls data` show no new file and no `data/runs` folder (a test also checks this with the cell functions).
- [ ] **Step 6: `app.run()` check, suite, commit.**

### Task 10: Notebook: in-memory replay trace and export on request

**Files:**
- Modify: `notebooks/rl_env.py`, `tests/test_rl_notebook.py`
- Uses: `src/quack_rl/cli/render.py` (`render_step`), `src/quack_rl/record` (`GameRecorder`, `HeaderLine`, `SeatInfo`)

**Interfaces:**
- Consumes: `QuackEnv.trace` (task 2), the trained model.
- Produces: a function `play_traced_game(model, opponent, rules, seed, deterministic) -> list[StepResult]` and a function `export_game(trace, path, rules, seed, run_name)` that writes one record with `GameRecorder`: header `mode="sim"`, seats `{"p1": agent, "p2": opponent}` where the agent is `SeatInfo(kind="bot", name=<run name>)`, one `StepLine` per `StepResult`, the footer from the final state. Notebook cells: a seed field and a "Play one game" button that shows the trace as text; an "Export this game" button with a folder field that is enabled only after a game was played.

- [ ] **Step 1: Write the failing tests.** The exported file is read back with `read_games`, `verify_game` returns `[]`, and `verify_seed` returns `[]` for the seed used; playing a traced game writes nothing; export writes exactly one file in the folder given.
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement** the two functions and the cells.
- [ ] **Step 4: Click check and no-write check** as in task 9 (play, then export; after each click the output changes without a manual refresh; before the export click no file exists).
- [ ] **Step 5: Run the suite, commit.**

---

## Self-review

- Spec coverage: principles and layout (tasks 1, 3, 4), episode summary and trace (2), evaluation and opponents (5), training feedback (6), saving and layout check (7), script (8), notebook (9, 10), replay and export (10), tests in each task, "Later" items filed as follow-ups at stage set-up. The README is updated in tasks 3, 4, 8 and 9.
- Type consistency: `Policy`, `EvalResult`, `RunSink`, `TrainResult`, `TrainingLog` and `placed_fields` are named the same in every task that uses them.
- Order and blockers: 2 after 1 is not required (independent); 3 needs 1; 4 needs 3; 5 needs 2 (episode data is not used by `evaluate`, but it uses the env as extended); 6 needs 2 and 5; 7 needs 6; 8 needs 7; 9 needs 4, 5, 6 and 7; 10 needs 2 and 9.
