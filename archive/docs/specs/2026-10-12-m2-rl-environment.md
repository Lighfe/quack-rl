# M2 RL environment: PettingZoo, Gymnasium and a minimal notebook

Date: 2026-10-12. Follows stage #40 (ruleset `v1.1` and a small tournament). Implements the first part of spec `2026-10-08-quack-rl-design.md`, sections 5.1-5.4 and 7.2.

## Purpose

Give the engine a standard RL interface: a PettingZoo `ParallelEnv` for two seats, and a Gymnasium environment where one seat is the agent and a bot plays the other. Add a very small marimo notebook where the owner explores the environment and runs one very simple training. Clear a few housekeeping items on the side.

## Owner's decisions (context, not tasks)

- No more balance work on `v1` and `v1.1`. The game will be reworked as a whole later (the "buy points" design is to be replaced). The sweeps #46 and #47 are closed.
- Reward is +1 for a win, -1 for a loss, 0 for a draw, given at the end of the game. The owner will research the reward later, because points are a strong signal that chess or Go do not have. Switching the reward must be easy (see "Reward").
- The notebook is very minimal.
- Minari (datasets, offline step) is NOT part of this stage. It needs a research task first and becomes its own later stage.
- torch will be used in the long run, also on GPU notebooks (molab). A large download is acceptable. The engine install stays light.

## Decisions

### Package and ruleset

- New package `src/quack_rl/rl/`. The engine, bots and records do not import it.
- Every env takes a ruleset (name or object) as a parameter. The default is `v1.1`. The action space and the encoding are built from the ruleset, so `v1` works as well. The "buy points" items are ordinary shop items: they are in the action space as they are, and nothing special is done for them.

### Observation and actions (spec 5.2-5.4)

- One encoder in `rl/encode.py`, used for both seats, from the point of view of the seat. It gives:
  - a structured dict (readable): round, phase, own and opponent fields (placed chips, field, money, white total, ruby fields ahead, points, status, droplet), the remaining bag composition of the own seat (information state, spec 5.2), and the shop state (purchases and chip colours this round);
  - a flat `float32` vector made from the dict, with a fixed layout that depends only on the ruleset. A function returns the names of the vector entries, for tests and the notebook.
- The observation of the env is `{"observation": <flat vector>, "action_mask": <int8 vector>}` (PettingZoo board-game convention). The dict form is available from the encoder.
- The action space is `Discrete(n)` with the actions of `action_names(rs)` in that order (16 in `v1`). The mask is 1 exactly for the actions in `legal_actions` of the seat.
- Hidden information stays hidden: the draw order and the opponent's current simultaneous choice. The observation never holds them.

### PettingZoo ParallelEnv (`rl/parallel_env.py`)

- Agents are `p1` and `p2`. Every step takes one action per agent. A seat with nothing to do has `Wait` as its only legal action (spec 5.1).
- One env step is one engine decision point to the next. Resolve and Reset are folded into the step whose joint action triggers them.
- The chance source is seeded by `reset(seed=...)`. The same seed and the same actions give the same game.
- The episode ends after the last step of round 9 (the end of the engine game): `terminations` is true for both agents, and the final observation is returned.
- Reward: see "Reward".
- Checked with PettingZoo's `parallel_api_test`.

### Gymnasium single-seat env (`rl/single_env.py`)

- `QuackEnv(seat="p1", opponent=<bot>, rules="v1.1")`. The agent plays one seat. The opponent is any bot of the repo with the `choose(state, seat, legal)` interface (default `RandomBot`). The opponent acts inside the env.
- Steps where the only legal action of the agent is `Wait` are skipped, so the agent sees only real decisions (spec 5.1). The info dict carries `action_mask`, and the observation space is the flat vector. The mask is also available for `MaskablePPO` through `action_masks()`.
- The seat can be `p1`, `p2`, or random per episode, so that an agent trained on one seat can be checked on the other.
- Checked with Gymnasium's `check_env`.

### Reward

- A function in `rl/reward.py`: `reward(final_state, seat) -> float`. It is called once, at the end of the game. The v1 function gives +1 (more points), -1 (fewer points), 0 (draw). Both envs take `reward_fn` as a parameter with this function as default, so a different reward is one argument. No shaping in this stage.

### Tests

- `parallel_api_test` and `check_env` pass, for `v1.1` and for `v1`.
- The action mask equals `legal_actions` at every step of random games on both rulesets.
- A game through the ParallelEnv with scripted actions and chance ends in the same state as the engine with the same actions and chance.
- The single-seat env skips `Wait`-only steps and never offers an illegal action; a game always ends in 9 rounds.
- The flat vector has a fixed length and layout per ruleset; it holds no hidden information (a test changes only the draw order of the remaining bag and expects the same observation).
- The reward function gives +1, -1 and 0 for three states.
- The training smoke test (below) is skipped, with a visible skip reason, when the `train` group is not installed. It is never counted as passed when it did not run.

### Dependencies

- `gymnasium`, `pettingzoo` and `numpy` are added so that the tests run with the default test command `uv run --with pytest pytest`.
- `torch` and `sb3-contrib` (with `stable-baselines3`) are in a separate dependency group `train`. The engine, the CLI and the env tests need neither.
- The environment is documented in the README: how to create the envs, the observation layout, the action list, how to install the `train` group.

### Notebook (`notebooks/rl_env.py`, marimo)

- Built with the project skill `marimo-notebook` (`.agents/skills/marimo-notebook`). Few cells, very minimal.
- Cells:
  1. Create the single-seat env on `v1.1` against `RandomBot`; show the observation (named entries) and the action mask (named actions) after `reset`.
  2. Play a few steps: a slider or button picks a legal action; the notebook shows reward, mask and the next observation. A "random step" button as well.
  3. A very simple training: `MaskablePPO` from `sb3-contrib` for a small number of steps (a setting in the notebook, default a few seconds on a laptop CPU), then an evaluation of the agent against `RandomBot` over a fixed number of games and a bar for the win rate before and after training. No tuning, no claims about strength.
- If `train` is not installed, the training cell shows the install command instead of failing. The first two cells work without it.
- The notebook runs on CPU; no GPU code is needed. It must also run as a script, `marimo run` or `python notebooks/rl_env.py`, for the smoke test.
- A test imports the notebook and runs the first two cells' logic, and (when `train` is installed) a training of at most a few hundred steps, to prove it runs.

### Housekeeping (small, last in the stage)

These are existing or small items that do not touch the RL work. They go last, so that they do not block it:

- #48: the hook-activation check docs name files and headings that do not exist.
- #37: `QA_SANDBOX` is not in `scripts/qa-codex`.
- #38: reference tests for the three ignored fields.
- `docs/team/planner.md:138` still says "entry 3", which nothing defines. Replace it with "the allow entries".
- `uv run ruff check` has 5 errors, and `uv run ruff format --check` would change 1 file (`tests/test_tournament.py`). Make both clean.

The edits to role files (`docs/team/`) are copies of kit files; the same fixes may belong in the agent-graph-kit plugin. The issues say so; the plugin itself is not changed in this stage.

Also first in the stage: #39, baseline name `draw20-pts1-points` in the balance report (existing issue).

## Out of scope

- Minari export, Minari datasets and any offline RL.
- Reward shaping and reward research; tuning, strength claims or a trained agent as a result.
- Balance work, sweeps, bot tuning, a new "buy points" design.
- GPU or molab set-up, server, frontend.
- A frame-stacked or recurrent observation (the observation is the information state, spec 5.2).
