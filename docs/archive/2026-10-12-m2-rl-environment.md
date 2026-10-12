# M2 RL environment Implementation Plan

> **For agentic workers:** This repo does NOT use subagent-driven-development or executing-plans (see `AGENTS.md`). Each task below becomes one issue in `docs/task-template.md` format and runs through `docs/process.md`. Steps use checkbox syntax.

**Goal:** A PettingZoo `ParallelEnv` and a Gymnasium single-seat env over the engine, and a minimal marimo notebook to explore the env and run one very simple training.

**Architecture:** A new package `src/quack_rl/rl/` that only imports the engine, the ruleset loader and the bots. One encoder turns a `GameState` into a seat-view dict and a flat vector. The ParallelEnv wraps `engine.step`. The Gymnasium env wraps the ParallelEnv logic with a bot on the other seat and skips `Wait`-only steps.

**Tech Stack:** Python 3.12, numpy, gymnasium, pettingzoo; `sb3-contrib` and torch only in the dependency group `train`; marimo (already a dev dependency).

**Spec:** `docs/specs/2026-10-12-m2-rl-environment.md` (and sections 5.1-5.4, 7.2 of `docs/specs/2026-10-08-quack-rl-design.md`)

## Global Constraints

- Ruleset default is `v1.1`; `v1` must work too. Action space and vector layout come from the ruleset only.
- The engine, bots, records and CLI do not import `quack_rl.rl`.
- Hidden information never enters the observation: draw order and the opponent's current simultaneous choice.
- Reward is +1 / -1 / 0 at the end of the game, from one function `reward(final_state, seat) -> float`, passed to the envs as `reward_fn`.
- Test command: `uv run --with pytest pytest`. A skipped test is reported as skipped, never as passed.
- Default dependencies add `gymnasium`, `pettingzoo`, `numpy`. `torch` and `sb3-contrib` only in group `train`.
- New code is clean under `uv run ruff check` and `uv run ruff format --check`.
- No Minari, no reward shaping, no balance work, no GPU code.

## Review Focus

- A seat that exploded or stopped must get `Wait` only, in the mask and in the env (no illegal action ever offered).
- A ruleset without `max_purchases` (`v1.1`) and one with it (`v1`) both build a valid action space.
- `reset(seed=s)` twice gives the same game; different seeds differ.
- Stepping after the episode ended raises a clear error (or follows the API's rule), not a crash in the engine.
- The agent seat is `p2` or random: observations are still from the agent's view.
- The training cell must not fail the notebook when `train` is not installed.

## File structure

- Create `src/quack_rl/rl/__init__.py`: exports `QuackParallelEnv`, `QuackEnv`, `reward`.
- Create `src/quack_rl/rl/encode.py`: `observe(state, rs, seat) -> dict`, `vectorize(obs, rs) -> np.ndarray`, `vector_names(rs) -> list[str]`, `action_mask(state, rs, seat) -> np.ndarray`.
- Create `src/quack_rl/rl/reward.py`: `reward(final_state, seat) -> float`.
- Create `src/quack_rl/rl/parallel_env.py`: `QuackParallelEnv`.
- Create `src/quack_rl/rl/single_env.py`: `QuackEnv`.
- Create `notebooks/rl_env.py`: the marimo notebook.
- Tests: `tests/test_rl_encode.py`, `tests/test_rl_parallel_env.py`, `tests/test_rl_single_env.py`, `tests/test_rl_notebook.py`.
- Modify `pyproject.toml` (dependencies, group `train`), `README.md` (section "RL environment").

## Tasks (each becomes one issue; sub-issues of the stage in this order)

### Task 0: Baseline name in the balance report (existing issue #39)

Link #39 as the first sub-issue. No new text.

### Task 1: Encoder, action mask and reward

**Files:** Create `rl/__init__.py`, `rl/encode.py`, `rl/reward.py`, `tests/test_rl_encode.py`; modify `pyproject.toml` (add `numpy`, `gymnasium`, `pettingzoo`).

**Interfaces:**
- Produces: `observe(state: GameState, rs: Ruleset, seat: str) -> dict[str, Any]` (own and opponent fields, round, phase, own remaining bag composition per chip id, shop state of the round); `vector_names(rs) -> list[str]`; `vectorize(obs: dict, rs) -> np.ndarray` (`float32`, length `len(vector_names(rs))`); `action_mask(state, rs, seat) -> np.ndarray` (`int8`, length `len(action_names(rs))`, 1 exactly for `legal_actions`); `reward(final_state, seat) -> float`.

- [ ] Write failing tests: mask equals `legal_actions` for random games on `v1` and `v1.1` at every step; vector length and names are stable per ruleset; changing only the draw order of the remaining bag does not change the observation; `observe(state, rs, "p2")` swaps own and opponent compared with `"p1"`; `reward` gives +1, -1, 0 for three final states
- [ ] Run them and see them fail
- [ ] Implement the encoder, mask and reward
- [ ] Run `uv run --with pytest pytest tests/test_rl_encode.py` and the full suite
- [ ] Commit

### Task 2: PettingZoo ParallelEnv

**Files:** Create `rl/parallel_env.py`, `tests/test_rl_parallel_env.py`; modify `rl/__init__.py`.

**Interfaces:**
- Consumes: Task 1 functions; `engine.new_game`, `engine.step`, `engine.RngChance`, `rules.load_ruleset`.
- Produces: `QuackParallelEnv(rules: str | Ruleset = "v1.1", reward_fn=reward)` with `possible_agents = ["p1", "p2"]`, `reset(seed=None, options=None) -> (obs, infos)`, `step(actions: dict[str, int]) -> (obs, rewards, terminations, truncations, infos)`. `obs[agent] = {"observation": vector, "action_mask": mask}`. Rewards are 0 until the last step, then `reward_fn(final_state, seat)`.

- [ ] Write failing tests: `pettingzoo.test.parallel_api_test` for `v1.1` and `v1`; same seed and same actions give the same game; scripted actions and chance end in the same state as the engine with the same input; a seat with nothing to do has only `Wait` in its mask; the episode ends after round 9 with `terminations` true for both seats; a step after the end raises a clear error
- [ ] Run them and see them fail
- [ ] Implement the env: map the action index to the action name, call `engine.step` with a seeded `RngChance`, fold automatic Resolve/Reset steps into the step that triggers them
- [ ] Run the new tests and the full suite
- [ ] Commit

### Task 3: Gymnasium single-seat env and README

**Files:** Create `rl/single_env.py`, `tests/test_rl_single_env.py`; modify `rl/__init__.py`, `README.md`.

**Interfaces:**
- Consumes: Task 2 env; the bot interface `choose(state, seat, legal) -> str`.
- Produces: `QuackEnv(seat: str = "p1" | "p2" | "random", opponent=None, rules="v1.1", reward_fn=reward)` (`opponent=None` means `RandomBot`). `observation_space = Box(float32, (n,))`, `action_space = Discrete(n_actions)`. `reset(seed, options) -> (obs, info)`, `step(a) -> (obs, reward, terminated, truncated, info)`, `info["action_mask"]`, `action_masks() -> np.ndarray` (for `MaskablePPO`).

- [ ] Write failing tests: `gymnasium.utils.env_checker.check_env` passes for `v1.1` and `v1`; no step is `Wait`-only for the agent; the mask never offers an illegal action; a game always ends after 9 rounds; `seat="p2"` and `"random"` give observations from the agent's view; a heuristic bot as opponent works
- [ ] Run them and see them fail
- [ ] Implement the env on top of the ParallelEnv logic: the opponent acts inside `step`; skip steps where the agent's only legal action is `Wait`
- [ ] README section "RL environment": how to create both envs, the observation layout (point to `vector_names`), the action list, the reward, how to install the `train` group
- [ ] Run the full suite
- [ ] Commit

### Task 4: Minimal marimo notebook with a very simple training

**Files:** Create `notebooks/rl_env.py`, `tests/test_rl_notebook.py`; modify `pyproject.toml` (group `train`: `torch`, `stable-baselines3`, `sb3-contrib`), `README.md` (one line how to open the notebook).

**Interfaces:** Consumes `QuackEnv` and `RandomBot`. Produces no importable API.

- [ ] Read `.agents/skills/marimo-notebook/SKILL.md` before writing the notebook
- [ ] Write a failing test that imports the notebook module and runs its first two cells' logic (env creation, named observation and mask after `reset`, one step), and a test for the training cell (a few hundred steps with `MaskablePPO`) guarded by `pytest.importorskip("sb3_contrib")`, so it shows as skipped when `train` is missing
- [ ] Implement three cells: (1) reset and show the named observation and named mask; (2) a step cell with a legal-action picker and a random-step button, showing reward, mask and next observation; (3) `MaskablePPO` for a number of steps set in a number input (default a few seconds on CPU), then the win rate against `RandomBot` before and after as a bar
- [ ] If `sb3_contrib` is not installed, cell 3 shows the install command instead of failing; cells 1 and 2 work without it
- [ ] Run `uv run --group train pytest tests/test_rl_notebook.py` and report how many tests ran and how many were skipped; run the notebook once with `marimo run` or as a script and report the result
- [ ] Commit

### Task 5: Housekeeping (last in the stage, independent of the RL work)

Link the existing issues #48, #37, #38. File two new issues:

- **Planner.md "entry 3"**: in `docs/team/planner.md` (line 138 at the time of writing) replace "When the owner has set entry 3 and asks for a retry" with "When the owner has set the allow entries and asks for a retry". Check that no other file in `docs/` uses "entry 3" in that sense. Source: the stage review of #40. The role file is a copy of a kit file; the same fix likely belongs in the agent-graph-kit plugin.
- **Ruff clean**: `uv run ruff check` and `uv run ruff format --check` report nothing. Fix the 5 errors (E501, I001, F401, F841, B905) and format `tests/test_tournament.py`. No change of behaviour; the full suite passes. This issue is blocked by Task 4, so the new RL code is included in the check.

## Order and blockers

1. #39 (existing)
2. Task 1: encoder, mask, reward
3. Task 2: ParallelEnv (blocked by Task 1)
4. Task 3: Gymnasium env and README (blocked by Task 2)
5. Task 4: notebook (blocked by Task 3)
6. #48, #37, #38, planner.md "entry 3" (no blockers; last in the order)
7. Ruff clean (blocked by Task 4)

## Self-review

- Spec coverage: encoder and information state (Task 1); ParallelEnv with `Wait`, seed, end after round 9 (Task 2); Gymnasium env with skip, opponent, seat choice, mask (Task 3); reward function (Task 1, parameter in Tasks 2 and 3); dependencies and `train` group (Tasks 1 and 4); README (Tasks 3 and 4); notebook with three cells and fallback (Task 4); housekeeping and #39 (Tasks 0 and 5). The three required test families of the spec (API tests, mask equals legal actions, engine equivalence) are in Tasks 1 and 2.
- Placeholders: none. Code is left to the engineer, as in earlier plans of this repo; interfaces are exact.
- Names are consistent: `observe`, `vectorize`, `vector_names`, `action_mask`, `reward`, `QuackParallelEnv`, `QuackEnv`.
