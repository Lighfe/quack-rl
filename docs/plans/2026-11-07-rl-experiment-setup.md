# RL experiment setup Implementation Plan

> **For agentic workers:** this plan becomes GitHub issues in `docs/task-template.md` format and runs through the loop of `docs/process.md` (PM, engineer, QA). Do not use the superpowers skills subagent-driven-development or executing-plans (see `AGENTS.md`). Steps use checkbox (`- [ ]`) syntax.

**Goal:** a faster engine copy, one experiment command that runs 3 seeds of one config with live evaluators, six ready experiment configs (P0-P3, B1-B2 plus the BC control B0), and a live marimo monitor.

**Architecture:** an experiment is one JSON config in `experiments/`. `scripts/run_experiment.py` starts, per seed, one training process (`quack_rl.rl.ppo_run` or `quack_rl.rl.bc_run`) and one evaluator process (`quack_rl.rl.live_eval`) that watches the run folder. The notebook `notebooks/rl_monitor.py` reads the run folders through `quack_rl.rl.monitor`.

**Tech Stack:** Python, MaskablePPO (sb3-contrib), torch, pydantic, polars, marimo, altair; `uv run --group rl`.

**Spec:** `docs/specs/2026-11-07-rl-experiment-setup.md`

## Global Constraints

- Ruleset v2.3, observation layout 10.
- Budgets are environment steps (agent decisions), never hours; wall time is only measured.
- Each experiment changes exactly one thing against its baseline (table "The experiments" in the spec).
- 3 seeds per experiment: 0, 1, 2. One experiment at most 6 hours of wall time on the laptop (8 cores, CPU) for 3 runs plus 3 evaluators.
- Final evaluation: 200 games per opponent (the three `PRESET_BOTS` and `bot:random`), seats swapped, seed 2026.
- Shared PPO network: actor and critic each two hidden layers of 256 units, ReLU.
- Trial and QA runs never write into `data/agents/`.
- Game results for a given seed never change (engine speed-up).
- Test command `uv run --with pytest pytest`; long tests marked `slow`.

## Review Focus

- A run killed in the middle of a checkpoint save: resume uses the newest complete checkpoint only (test in Task 4).
- The evaluator started before the first checkpoint exists, or after the run has ended: it waits, then evaluates every checkpoint once, and exits after `done.json` (test in Task 6).
- Resume of a run whose config file differs from the stored `config.json`: exits with an error that names the differing keys (test in Task 4).
- Label smoothing that puts probability on illegal actions: the smoothed target covers only the legal actions (test in Task 8).
- The notebook opened on an empty or half-written run folder (a CSV with a header only, or a cut-off last line): it shows "no data yet", not an error (test in Task 10).

---

### Task 1: Faster game-state copy (existing issue #285)

**Files:**
- Modify: `src/quack_rl/engine/state.py` (`PlayerState`, `GameState`)
- Test: `tests/test_state_copy.py`
- Modify: `scripts/measure_speed.py` (add an env-step measurement)

**Interfaces:**
- Produces: `PlayerState.__deepcopy__(memo) -> PlayerState`, `GameState.__deepcopy__(memo) -> GameState`; `engine.step` keeps calling `copy.deepcopy`.

- [ ] **Step 1: Failing test** `test_copy_equals_deepcopy_over_seeded_games`: for 20 seeded games (`bot:topchip-draw20-pts6` both seats), at every 10th step, `copy.deepcopy(state)` `==` a reference copy `pickle.loads(pickle.dumps(state))`. `test_copy_is_independent`: change every list, dict and field of the copy; the original is unchanged. `test_every_field_is_copied` (Step 3) fails before the change.
- [ ] **Step 2:** run, expect `test_every_field_is_copied` to FAIL.
- [ ] **Step 3:** implement `__deepcopy__` with explicit copies of each list and dict field (strings and ints are shared). New fields added later must be copied too: `test_every_field_is_copied` iterates `dataclasses.fields`, checks that `__deepcopy__` is defined on both classes, and fails on a mutable field whose copy is the same object as the original.
- [ ] **Step 4:** `test_golden_v2_3.py` and `test_engine_v2_3_games.py` pass unchanged (same games per seed).
- [ ] **Step 5:** `scripts/measure_speed.py --env-steps N` prints QuackEnv steps per second against `bot:topchip-draw20-pts6` (random actions from the mask, fixed seed). Engineer DONE gives the before and after numbers, and the rollout time of one game before and after (at least 2 times faster, as #285 says).
- [ ] **Step 6:** commit.

### Task 2: Agents root argument and dataset manifest

**Files:**
- Modify: `scripts/train_ppo.py`, `scripts/train_selfplay.py`, `scripts/train_offline.py`, `scripts/build_dataset.py`, `src/quack_rl/rl/dataset.py`
- Test: `tests/test_rl_agents_root.py`, `tests/test_rl_dataset_manifest.py`

**Interfaces:**
- Produces: `--agents-root PATH` (default `data/agents`) on the three training scripts, passed to `ensure_new_agent(..., root=)` and `write_agent(..., root=)`. `write_dataset_manifest(folder: Path, *, bots: list[str], games_per_pairing: int, seed: int, rules: str, command: list[str]) -> Path` writes `manifest.json` with those keys plus `layout` and `sha256` of `dataset.npz`. `dataset_sha256(path: Path) -> str`.

- [ ] **Step 1: Failing tests**: each script with `--agents-root tmp_path` and `--agent-name x` writes `tmp_path/x/agent.json` and nothing under `data/agents` (run the script `main` with a monkeypatched `sys.argv`, tiny steps); `build_dataset.py` writes `manifest.json` whose `sha256` equals `dataset_sha256` of the npz.
- [ ] **Step 2:** run, expect FAIL.
- [ ] **Step 3:** implement.
- [ ] **Step 4:** run, expect PASS.
- [ ] **Step 5:** commit.

### Task 3: Experiment config

**Files:**
- Create: `src/quack_rl/rl/experiment.py`
- Test: `tests/test_rl_experiment_config.py`

**Interfaces:**
- Produces (pydantic models, `extra="forbid"`):
  - `OpponentShare(spec: str, weight: int = 1)`
  - `BCSettings(dataset: str, epochs: int = 10, label_smoothing: float = 0.0, entropy_coef: float = 0.0)`
  - `ExperimentConfig(id: str, kind: Literal["ppo", "bc"], baseline: str | None, changes: str, seeds: list[int] = [0, 1, 2], steps: int | None, opponents: list[OpponentShare] = [], reward: Literal["win_loss", "margin"] = "win_loss", hidden: int = 256, checkpoint_every: int | None, live_eval_games: int = 50, final_eval_games: int = 200, final_eval_seed: int = 2026, init_from_bc: str | None = None, critic_warmup_steps: int = 0, save_games: bool = False, bc: BCSettings | None = None)`
  - `load_config(path: Path) -> ExperimentConfig`; `config_diff(a: ExperimentConfig, b: ExperimentConfig) -> list[str]` (the names of the keys that differ).
  - `EVAL_OPPONENTS: tuple[str, ...] = (*PRESET_BOTS, "bot:random")`

- [ ] **Step 1: Failing tests**: a `kind="ppo"` config without `steps` or without `opponents` raises; a `kind="bc"` config without `bc` raises; an unknown key raises; `config_diff` of P0 and a copy with `reward="margin"` is `["reward"]`.
- [ ] **Step 2-4:** fail, implement, pass.
- [ ] **Step 5:** commit.

### Task 4: PPO run with logging, checkpoints and resume

**Files:**
- Create: `src/quack_rl/rl/ppo_run.py`
- Modify: `src/quack_rl/rl/reward.py` (add `margin_reward`)
- Test: `tests/test_rl_ppo_run.py`, `tests/test_rl_reward.py`

**Interfaces:**
- Consumes: `ExperimentConfig`, `config_diff` (Task 3); `OpponentMix` (`src/quack_rl/rl/opponents.py`, a spec repeated `weight` times); `QuackEnv(reward_fn=...)`.
- Produces:
  - `margin_reward(final_state: GameState, seat: str) -> float`: own points minus the best other seat's points, divided by `MARGIN_SCALE` and clipped to [-1, 1]. `MARGIN_SCALE` is the builder's call, stated in a docstring with the observed spread of final margins. `REWARDS = {"win_loss": reward, "margin": margin_reward}`.
  - `POLICY_KWARGS(hidden) -> dict`: `net_arch=dict(pi=[hidden, hidden], vf=[hidden, hidden])`, `activation_fn=torch.nn.ReLU`.
  - `run_ppo_seed(config: ExperimentConfig, seed: int, out: Path, *, resume: bool = False, steps_override: int | None = None) -> Path`. The run folder `out` gets: `config.json` (config, seed, git commit, library versions, dataset hash when one is used), `ppo.csv` (one row per rollout: `steps, mean_reward, games, policy_loss, value_loss, entropy, approx_kl, clip_fraction, explained_variance, wall_seconds`), `checkpoints/step_<n>.zip` every `checkpoint_every` steps and at the end, `done.json` (`steps`, `train_seconds`) when finished.
  - `newest_complete_checkpoint(out: Path) -> Path | None` (a save goes to a temp name and is renamed).

- [ ] **Step 1: Failing tests** (`slow` where training runs): a run of 2,048 steps with `checkpoint_every=1024` writes 2 checkpoints, 2 `ppo.csv` rows with all columns filled, and `done.json`; `resume=True` after deleting `done.json` and the last checkpoint continues from step 1,024 and ends at 2,048; a leftover `checkpoints/step_3072.tmp.zip` is ignored; resume with a changed `reward` exits with an error naming `reward`; the policy has two 256-unit ReLU layers in both actor and critic; `margin_reward` is 0 for equal points, positive when ahead, and within [-1, 1] for a 1,000-point margin.
- [ ] **Step 2-4:** fail, implement, pass. PPO numbers come from the SB3 logger values (`train/policy_gradient_loss`, `train/value_loss`, `train/entropy_loss`, `train/approx_kl`, `train/clip_fraction`, `train/explained_variance`) read in a callback.
- [ ] **Step 5:** commit.

### Task 5: Save training games as seeds and actions

**Files:**
- Modify: `src/quack_rl/rl/ppo_run.py`, `src/quack_rl/rl/single_env.py` (expose the chance seed and the joint actions of the episode)
- Create: `src/quack_rl/rl/game_log.py`
- Test: `tests/test_rl_game_log.py`

**Interfaces:**
- Consumes: `run_ppo_seed` (Task 4), `ExperimentConfig.save_games`.
- Produces: with `save_games=True`, `games.jsonl` in the run folder, one line per finished game: `{"step": <run step at game end>, "chance_seed": int, "agent_seat": "p1"|"p2", "opponent": spec, "actions": [[p1_action, p2_action], ...]}`. `rebuild_dataset(games_file: Path, rules: str = "v2.3") -> Dataset` replays each game with the engine and the chance seed and returns the agent's transitions in the `Dataset` form of `src/quack_rl/rl/dataset.py`.

- [ ] **Step 1: Failing tests**: a short run with `save_games=True` writes one line per finished game; `rebuild_dataset` gives the same `obs`, `action`, `reward` rows as a `Dataset` recorded live for the same games (record live in the test with the env); a game whose replay diverges (edited action) raises ValueError naming the line.
- [ ] **Step 2-4:** fail, implement, pass.
- [ ] **Step 5:** commit.

### Task 6: Live evaluator and final evaluation

**Files:**
- Create: `src/quack_rl/rl/live_eval.py`
- Modify: `src/quack_rl/rl/policy_bot.py`, `src/quack_rl/rl/offline.py` (sampled mode)
- Test: `tests/test_rl_live_eval.py`

**Interfaces:**
- Consumes: `evaluate` and `wilson_interval` (`src/quack_rl/rl/evaluate.py`), `EVAL_OPPONENTS` (Task 3), `newest_complete_checkpoint` (Task 4).
- Produces:
  - `PolicyBot(model, rules, name, mode: Literal["greedy", "sampled"] = "greedy", seed: int | None = None)`, and the same `mode` and `seed` on `OfflinePolicy`. Sampled draws from the masked softmax with a seeded generator.
  - `watch_run(run_dir: Path, *, games: int, seed: int, modes: tuple[str, ...], poll_seconds: float = 30.0) -> None`: evaluates every complete checkpoint once (`checkpoints/step_<n>.zip` for PPO, `checkpoints/epoch_<n>.pt` for BC), appends rows to `eval.csv` (`step, opponent, mode, games, wins, draws, losses, win_rate, ci_low, ci_high`), and returns after `done.json` exists and every checkpoint has rows. On restart it skips checkpoints already in `eval.csv`.
  - `final_eval(run_dir: Path, *, games: int = 200, seed: int = 2026, modes: tuple[str, ...]) -> Path`: the last checkpoint against `EVAL_OPPONENTS`, seats swapped (as `evaluate` does), writes `final_eval.csv` with the same columns.
  - CLI: `python -m quack_rl.rl.live_eval RUN_DIR [--games 50] [--seed 0] [--modes greedy,sampled] [--final]`.

- [ ] **Step 1: Failing tests**: with a fake run folder (two saved tiny PPO models and no `done.json`), `watch_run` in a thread evaluates both, then a third checkpoint and `done.json` appear and it evaluates the third and returns; started on an empty folder it waits and does not fail; a restart writes no duplicate rows; sampled mode with the same seed gives the same games, greedy mode equals today's `PolicyBot` choice.
- [ ] **Step 2-4:** fail, implement, pass.
- [ ] **Step 5:** commit.

### Task 7: The experiment command

**Files:**
- Create: `scripts/run_experiment.py`, `experiments/README.md`
- Test: `tests/test_run_experiment.py`

**Interfaces:**
- Consumes: `load_config` (Task 3), `run_ppo_seed` (Task 4), `run_bc_seed` (Task 8), `watch_run` and `final_eval` (Task 6).
- Produces: `uv run --group rl python scripts/run_experiment.py --config experiments/<id>.json --out data/experiments [--seeds 0,1,2] [--steps N] [--resume]`. Per seed it starts one training process and one evaluator process (`subprocess`), the run folder `data/experiments/<id>/seed<k>/`. When all trainings end and all evaluators return, it runs `final_eval` per seed and prints one table: seed, opponent, mode, win rate with interval. `--steps` overrides the budget for trial runs and is written into `config.json`. Exit code 1 and a message when a child process fails; the other children are stopped. `experiments/README.md` gives the long-run commands, with the memory cap wrapper `systemd-run --user --scope -p MemoryMax=<n>G -p MemorySwapMax=0`, how to resume, and how to open the notebook.

- [ ] **Step 1: Failing tests** (`slow`): a PPO config with `--steps 1024 --seeds 0,1` produces `seed0/` and `seed1/`, each with `done.json`, `eval.csv` and `final_eval.csv` (final games overridden small via a test config); a child that fails (bad dataset path in a BC config) gives exit code 1 and stops the others.
- [ ] **Step 2-4:** fail, implement, pass.
- [ ] **Step 5:** commit.

### Task 8: BC variants and the BC run

**Files:**
- Modify: `src/quack_rl/rl/offline.py` (`train_bc`)
- Create: `src/quack_rl/rl/bc_run.py`
- Test: `tests/test_rl_bc_variants.py`

**Interfaces:**
- Consumes: `ExperimentConfig.bc` (Task 3), the dataset manifest (Task 2).
- Produces:
  - `train_bc(..., label_smoothing: float = 0.0, entropy_coef: float = 0.0, on_epoch_end: Callable[[int, nn.Module], None] | None = None)`. Label smoothing: target = (1 - eps) on the stored action, eps spread evenly over the legal actions only. Entropy bonus: loss = cross entropy - `entropy_coef` * mean entropy of the masked softmax.
  - `run_bc_seed(config: ExperimentConfig, seed: int, out: Path) -> Path`: writes `config.json` (with the dataset hash from its manifest), `bc.csv` (`epoch, loss, entropy, wall_seconds`), `checkpoints/epoch_<n>.pt` after each epoch, `model.pt`, `done.json`.

- [ ] **Step 1: Failing tests**: with defaults, `train_bc` gives the same loss curve as before for a fixed seed; the smoothed target sums to 1 and is 0 on every illegal action; a larger `entropy_coef` gives a higher mean policy entropy on a small synthetic dataset; `run_bc_seed` writes one checkpoint per epoch and records the dataset sha256.
- [ ] **Step 2-4:** fail, implement, pass.
- [ ] **Step 5:** commit.

### Task 9: PPO from BC with critic warm-up

**Files:**
- Modify: `src/quack_rl/rl/ppo_run.py`
- Test: `tests/test_rl_ppo_from_bc.py`

**Interfaces:**
- Consumes: `run_ppo_seed` (Task 4), `POLICY_KWARGS`, BC `model.pt` (Task 8, `make_mlp` layers 0, 2, 4).
- Produces: `load_bc_into_actor(model: MaskablePPO, bc_state: dict[str, torch.Tensor]) -> None` (BC layers 0 and 2 into `policy.mlp_extractor.policy_net`, layer 4 into `policy.action_net`; raises ValueError on a shape mismatch). With `init_from_bc` set, `run_ppo_seed` loads the weights before training, and for the first `critic_warmup_steps` steps the actor parameters (policy net and action net) do not change.

- [ ] **Step 1: Failing tests**: after `load_bc_into_actor`, the masked action probabilities of the PPO policy equal the BC softmax on 100 dataset observations (tolerance 1e-5); a hidden size of 64 raises ValueError; after a warm-up of 1,024 steps the actor parameters equal those after loading and the critic parameters have changed; after the warm-up the actor changes.
- [ ] **Step 2-4:** fail, implement, pass.
- [ ] **Step 5:** commit.

### Task 10: Live monitor notebook

**Files:**
- Create: `src/quack_rl/rl/monitor.py`, `notebooks/rl_monitor.py`
- Modify: `pyproject.toml` (group `monitor`: `marimo`, `altair`, `polars`)
- Test: `tests/test_rl_monitor.py`

**Interfaces:**
- Consumes: the run folder files of Tasks 4, 6 and 8.
- Produces: `load_run(run_dir: Path) -> RunData` (`RunData` holds polars frames `train` from `ppo.csv` or `bc.csv`, `evals` from `eval.csv`, `final` from `final_eval.csv`, each possibly empty, and `config: dict`); `load_experiment(exp_dir: Path) -> dict[int, RunData]` keyed by seed. A cut-off last line or a header-only CSV gives an empty or shorter frame, no exception.
- The notebook (load the `marimo-notebook` skill): a folder picker for an experiment, an optional baseline experiment; charts of the training numbers over steps and of the win rate per opponent over checkpoints with interval bands, the seeds as separate lines; refreshes by itself with `mo.ui.refresh` (default 30 s) and no manual click. Start: `uv run --group rl --group monitor marimo run notebooks/rl_monitor.py`.

- [ ] **Step 1: Failing tests** for `load_run`: a full fake folder, an empty folder, a header-only CSV, a cut-off last line.
- [ ] **Step 2-4:** fail, implement, pass. Then start the notebook headless on a fake folder that grows during the check, and confirm the new rows appear without a click (Engineer DONE describes the check).
- [ ] **Step 5:** commit.

### Task 11: Budget, experiment configs, trial runs, BC results

**Files:**
- Create: `experiments/P0.json`, `P1.json`, `P2.json`, `P3.json`, `B0.json`, `B1.json`, `B2.json`
- Modify: `experiments/README.md`

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1:** measure the PPO training speed with the faster engine: 3 trainings plus 3 evaluators side by side, 20,000 steps each. Set `steps` so that 3 runs plus evaluators end in at most 6 hours, with a margin of 15%. Record the measurement in `experiments/README.md`.
- [ ] **Step 2:** write the seven configs (P3 after Step 4, which picks its BC start). P0: opponents the three presets (weight 1 each), `win_loss`. P1: P0 plus `bot:random` and weak rule-bot settings (builder's choice, stated in `changes`). P2: P0 with `margin`. P3: P0 with `init_from_bc` the better of B1 and B2 per the spec rule, and `critic_warmup_steps`. B0: today's BC settings of #275 (`epochs` 10, dataset `data/datasets/rulebots`). B1: B0 plus `label_smoothing`. B2: B0 plus `entropy_coef`. A test `test_experiment_configs` loads each file and checks with `config_diff` that each changes exactly one key against its baseline (P3: `init_from_bc` and `critic_warmup_steps` count as one change, as the spec says).
- [ ] **Step 3:** a trial run of each PPO config with `--steps 20000 --seeds 0` into a folder outside `data/agents/`; Engineer DONE gives each command, its wall time and its exit code.
- [ ] **Step 4:** run B0, B1 and B2 in full (3 seeds each). Engineer DONE gives their final evaluation table (greedy and sampled) and the choice for P3 by the spec rule. No analysis report.
- [ ] **Step 5:** commit the configs and the README.
