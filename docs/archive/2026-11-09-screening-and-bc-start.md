# Screening, PPO from BC, and one long run - Implementation Plan

> **For agentic workers:** each task below becomes one GitHub issue and goes through the loop of `docs/process.md` (PM, engineer, QA). Do not use subagent-driven-development or executing-plans (see `AGENTS.md`). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A faster env step, a paired BC start, two short screenings that choose the setup, and the config of one long run.

**Architecture:** The speed-up stays inside `QuackEnv` and its encoders. The paired BC start is a `{seed}` placeholder in `init_from_bc`, resolved in `run_ppo_seed`. The screenings are new experiment configs `S0`-`S5` run with `scripts/run_experiment.py`. Their results and choices go into one analysis file, and the long run is the config `L`.

**Tech Stack:** Python, gymnasium, sb3-contrib MaskablePPO, torch, pydantic, polars, pytest, uv.

**Spec:** `docs/specs/2026-11-09-screening-and-bc-start.md`

## Global Constraints

- Test command: `uv run --with pytest pytest` (fast subset `-m "not slow"` while working; no extra `-q`)
- Every run under the memory cap wrapper of `experiments/README.md` (`systemd-run --user --scope -p MemoryMax=<cap> -p MemorySwapMax=0 /usr/bin/time -v ...`)
- Nothing is written into `data/agents/`
- A game for a given seed stays the same, move by move; the observations and masks stay the same
- Long-run budget: `steps / rate + final evaluation time <= 18,360 s`. Screening budget: the same sum `<= 5,400 s`, with at least 6 checkpoints. `steps` a multiple of `checkpoint_every`, `checkpoint_every` a multiple of 1024
- Score of a PPO experiment: the mean greedy final win rate against the three presets over its 3 seeds (9 values from `final_eval.csv`)
- Choice rules (fixed now): X = best of S0, S1, S2 (within 0.01: order S0, S1, S2). Best BC arm = best of S3, S4, S5 (within 0.01: order S3, S5, S4). Long run = best BC arm if its score > X's score + 0.01, else X from scratch
- No BC model's own win rate decides anything

## Review Focus

- A seed whose BC file is missing (for example `B1/seed2/model.pt` deleted): the run must stop before any file is written, naming the resolved path (Task 2 test)
- `--resume` of a paired run after the BC file of that seed changed: `ResumeError` naming `init_from_bc_sha256` (Task 2 test)
- `init_from_bc` without `{seed}`: unchanged behaviour, all seeds load the same file (Task 2 test)
- An env speed-up that changes the observation dtype or the order of mask entries: games stay the same but the policy input changes (Task 1 identity test compares observations and masks, not only results)
- A choice that falls within the 0.01 band: the tie order must be applied and shown in numbers (Tasks 4 and 5 records)

---

### Task 1: Faster env step

**Files:**
- Modify: `src/quack_rl/rl/single_env.py` and the encoders it calls (the builder finds them by profiling)
- Create: `tests/fixtures/env_trace/` (a recorded trace) and `tests/test_env_trace.py`
- Modify: `docs/speed-measurement.md` (a section "Env step, 2026-11")

**Interfaces:**
- Produces: `QuackEnv` with the same public interface (`reset`, `step`, `action_masks`, spaces) and a higher `--env-steps` rate

- [ ] **Step 1: Record the trace before any change.** A script or test helper plays `QuackEnv` for seeds 0-4 with each of the three preset opponents and `bot:random`, choosing actions with `np.random.default_rng(seed)` among the legal actions, up to 2,000 steps per seed. It stores per step the observation, the mask, the reward, `terminated` and `truncated` in `tests/fixtures/env_trace/` (npz, compressed). Commit the fixture before touching env code.
- [ ] **Step 2: Write `test_env_trace_unchanged`** in `tests/test_env_trace.py`: replay the same plan and `np.testing.assert_array_equal` each observation (also the dtype), each mask, and `==` each reward and flag. Run it: PASS on the unchanged code.
- [ ] **Step 3: Measure before.** `uv run python scripts/measure_speed.py --env-steps 20000`, twice, and record both numbers.
- [ ] **Step 4: Profile** with `cProfile` over 20,000 env steps and record the top 15 functions by cumulative time.
- [ ] **Step 5: Make the slow parts faster.** The approach is the builder's call. Run `test_env_trace_unchanged` and the fast subset after each change.
- [ ] **Step 6: Measure after**, twice, on the same machine. Write the before and after numbers, the profile before and after, and the machine to `docs/speed-measurement.md`.
- [ ] **Step 7: Full test command, then commit.**

Acceptance: the trace test passes; the after rate and the before rate are both recorded. There is no target number. If no clear gain is found, the profile is recorded and the task is still done.

### Task 2: Paired BC start (`{seed}` in `init_from_bc`)

**Files:**
- Modify: `src/quack_rl/rl/ppo_run.py` (`run_ppo_seed`, around the `bc_path` lines)
- Modify: `src/quack_rl/rl/experiment.py` (docstring of `init_from_bc`)
- Test: `tests/test_rl_ppo_from_bc.py`

**Interfaces:**
- Produces: `resolve_bc_path(init_from_bc: str, seed: int) -> Path` in `src/quack_rl/rl/ppo_run.py`: replaces every `{seed}` with the seed number; a text without `{seed}` is returned as a `Path` unchanged. `run_ppo_seed` uses it; `config.json` gets a new key `init_from_bc_path` (the resolved path as a string) next to `init_from_bc_sha256`

- [ ] **Step 1: Write the failing tests**
  - `test_resolve_bc_path`: `resolve_bc_path("data/experiments/B1/seed{seed}/model.pt", 2) == Path("data/experiments/B1/seed2/model.pt")`, and `resolve_bc_path("a/model.pt", 2) == Path("a/model.pt")`
  - `test_paired_bc_start_loads_the_seed_file`: two tiny BC `model.pt` files in `tmp_path/seed0/` and `tmp_path/seed1/` with different weights; a PPO config with `init_from_bc = str(tmp_path / "seed{seed}" / "model.pt")` and a small step budget; run seed 1; `config.json` has `init_from_bc_path` ending in `seed1/model.pt` and the sha256 of that file
  - `test_paired_bc_start_missing_seed_file`: only `seed0/model.pt` exists; seed 1 raises `FileNotFoundError` whose message names `seed1/model.pt`, and the out folder has no `config.json`
  - `test_paired_bc_start_resume_checks_the_seed_file`: after a run of seed 0, change `seed0/model.pt`; `resume=True` raises `ResumeError` naming `init_from_bc_sha256`
- [ ] **Step 2: Run them, expect FAIL** (`resolve_bc_path` not defined).
- [ ] **Step 3: Implement `resolve_bc_path`** and use it in `run_ppo_seed` in place of `Path(config.init_from_bc)`.
- [ ] **Step 4: Run the tests, expect PASS;** the existing tests of `init_from_bc` without `{seed}` still pass.
- [ ] **Step 5: Full test command, then commit.**

### Task 3: Budgets and the screening configs S0-S2

Blocked by Task 1.

**Files:**
- Delete: `experiments/P0.json` - `experiments/P3.json`
- Create: `experiments/S0.json`, `S1.json`, `S2.json`
- Modify: `tests/test_experiment_configs.py`, `experiments/README.md` ("Step budget"), `docs/specs/2026-11-07-rl-experiment-setup.md` (a note under "Better of B1 and B2")
- Modify: any test or doc that loads `experiments/P<k>.json` (check with `grep -rn "experiments/P" src scripts tests notebooks docs experiments`)

**Interfaces:**
- Produces: `experiments/S0.json` (`baseline: null`), `S1.json` and `S2.json` (`baseline: "S0"`). Each has today's P0/P1/P2 settings unchanged, except `steps` = the screening budget and `checkpoint_every` = the screening checkpoint step. The long-run budget (`steps_long`, `checkpoint_every_long`) is written in the README for Task 5

- [ ] **Step 1: Measure the rate** as in "Step budget" of `experiments/README.md` (S0 settings, 3 seeds, `--steps 20000`, `--threads 1`, a trial `--out` folder), with the speed-up of Task 1 in place.
- [ ] **Step 2: Compute both budgets** with the formulas of the Global Constraints, and write the README section again: command, rate, final evaluation time, the screening budget with its sum (`<= 5,400 s`, at least 6 checkpoints), the long-run budget with its sum (`<= 18,360 s`).
- [ ] **Step 3: Write S0-S2, delete P0-P3.** Each `changes` names the one change (S1: the opponent mix of today's P1; S2: reward `margin`).
- [ ] **Step 4: Update `test_experiment_configs`:** `EXPECTED` has `S0: (None, None)`, `S1: ("S0", ["opponents"])`, `S2: ("S0", ["reward"])`, and B0-B2 as today; `test_screening_configs_share_the_step_budget` checks that S0-S2 have one `steps` and one `checkpoint_every`, and that `steps // checkpoint_every >= 6`.
- [ ] **Step 5: The old spec note:** under "Better of B1 and B2" in `docs/specs/2026-11-07-rl-experiment-setup.md`, add one paragraph: this rule is replaced by `docs/specs/2026-11-09-screening-and-bc-start.md`, because a BC variant meant as a PPO start is judged by what PPO learns from it, not by the BC model's own win rate.
- [ ] **Step 6: Trial run** of S0 with `--steps 2048 --seeds 0 --threads 1` into a temp folder: exit 0.
- [ ] **Step 7: Full test command, then commit.**

### Task 4: Screening 1 (S0, S1, S2) and the choice of X

Blocked by Task 3.

**Files:**
- Create: `docs/analysis/2026-11-screening.md` (part 1)

**Interfaces:**
- Consumes: `experiments/S0.json` - `S2.json`
- Produces: X (one of S0, S1, S2), named in the record's line `X: S<k>`, which Task 5 reads

- [ ] **Step 1: Run S0, S1, S2** one after another, full 3 seeds, `--out data/experiments --threads 1`, under the memory cap. Record each command, wall time, exit code and peak memory.
- [ ] **Step 2: Compute the scores** from the nine `final_eval.csv` rows per experiment (a short script or a polars snippet; show it in the record).
- [ ] **Step 3: Write part 1 of the record:** commands and run data; per experiment the final table (seed x opponent, greedy and sampled, with 95% interval); the score; the learning curve as a table (checkpoint step x mean greedy win rate against the presets over the seeds, from `eval.csv`); and the choice of X with the rule applied in numbers, including the 0.01 band.
- [ ] **Step 4: Commit** the record.

### Task 5: Screening 2 (X from B0, B1, B2) and the long-run config L

Blocked by Task 2 and Task 4.

**Files:**
- Create: `experiments/S3.json`, `S4.json`, `S5.json`, `experiments/L.json`
- Modify: `tests/test_experiment_configs.py`, `docs/analysis/2026-11-screening.md` (part 2)

**Interfaces:**
- Consumes: X from Task 4; `resolve_bc_path` of Task 2; the long-run budget from the README (Task 3)
- Produces: `experiments/L.json`, ready for the owner's run

- [ ] **Step 1: Write S3-S5.** S3: X's settings with `init_from_bc = "data/experiments/B0/seed{seed}/model.pt"` and `critic_warmup_steps = 51200`, `baseline` = X's id. S4 and S5: S3 with `B1` and `B2` in the path, `baseline: "S3"`.
- [ ] **Step 2: Extend `test_experiment_configs`:** `S3: (X, ["init_from_bc", "critic_warmup_steps"])`, `S4: ("S3", ["init_from_bc"])`, `S5: ("S3", ["init_from_bc"])`; and the shared-budget test covers S0-S5.
- [ ] **Step 3: Run S3, S4, S5** as in Task 4 Step 1. Check in each seed's `config.json` that `init_from_bc_path` names that seed's BC file.
- [ ] **Step 4: Write part 2 of the record:** the same tables as part 1, with X from scratch as the reference row; the best BC arm with the rule in numbers; the long-run choice with the rule in numbers.
- [ ] **Step 5: Write `experiments/L.json`:** the chosen config (X, or the best BC arm) with `steps` and `checkpoint_every` from the long-run budget, `baseline` = the chosen S id, `changes` naming the budget. Add `L: (<chosen>, ["steps", "checkpoint_every"])` to `EXPECTED`. Trial run of L with `--steps 2048 --seeds 0` into a temp folder: exit 0.
- [ ] **Step 6: README:** a short "Next: the long run" line in `experiments/README.md` with the exact command for L.
- [ ] **Step 7: Full test command, then commit.**
