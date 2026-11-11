# PPO update size: implementation plan

> Tasks become issues in `docs/task-template.md` format (Intake in `docs/process.md`). Do not
> use subagent-driven-development or executing-plans (`AGENTS.md`).

**Goal:** record the shortcomings of stage #309, make `n_steps`, `batch_size` and `target_kl`
settings of every PPO experiment config, log the passes per update, and run two S1 variants (S6,
S7).

**Architecture:** the three settings live in `ExperimentConfig` and flow through `run_ppo_seed`
into MaskablePPO and the run's `config.json`. The `ppo.csv` callback adds one column. The monitor
notebook plots it. Docs and the screening record follow the form of parts 1 and 2.

**Tech stack:** Python 3.12, pydantic, sb3-contrib MaskablePPO, polars, marimo, altair.

**Spec:** `docs/specs/2026-11-11-ppo-update-size.md`

## Global constraints

- Test command: `uv run --with pytest pytest`; fast subset `uv run --with pytest pytest -m "not slow"`.
- No code defaults for `n_steps`, `batch_size`, `target_kl` in PPO configs: every PPO config
  states them.
- S0-S5 and L get `"n_steps": 1024, "batch_size": 64, "target_kl": null`.
- `quack_rl/rl/train.py` and `selfplay.py` keep their constants.
- No hard numeric stop rules; the sense check is prose.
- `data/experiments/` is git-ignored; run data is copied into the record, not committed.

## Review focus

1. A PPO config with `"target_kl": null` written in must load (null is a valid value; only a
   missing key is an error). Test in task 2.
2. The `ppo.csv` files of S0-S5 (no `epochs_run`) must still load in the monitor and the notebook
   must not fail on them. Test in task 3.
3. A resumed run must not log a wrong `epochs_run` for its first update after the resume (the
   pass count continues from the checkpoint). Test in task 3.
4. `checkpoint_every` 96,256 with `n_steps` 4,096 must be refused with a clear message. Test in
   task 2.
5. A BC config (B0-B2) must still load without the three fields. Test in task 2.

---

### Task 1: Shortcomings of stage #309, L on hold, sense check

**Files:**
- Modify: `docs/analysis/2026-11-screening.md` (new "Part 3: Shortcomings of stage #309" at the end)
- Modify: `experiments/README.md` ("Next: the long run": on-hold note; new section "Sense check after a screening")

- [ ] **Step 1:** Write part 3 with the content listed in the spec section "Part 3 of the record".
  Take the numbers from parts 1 and 2 and from the `ppo.csv` files of S0-S5 (`approx_kl`,
  `clip_fraction`, entropy, `explained_variance` at the start, middle and end, mean over seeds).
  Give the snippet that computed them, as parts 1 and 2 do.
- [ ] **Step 2:** In `experiments/README.md`, "Next: the long run": L is on hold, do not start it;
  one sentence of reason and a link to part 3.
- [ ] **Step 3:** In `experiments/README.md`, add the section "Sense check after a screening"
  with the text of the spec section of the same name (no thresholds).
- [ ] **Step 4:** Run the test command (doc-only change, the suite must still pass). Commit.

### Task 2: PPO settings in the experiment config

**Files:**
- Modify: `src/quack_rl/rl/experiment.py` (`ExperimentConfig`)
- Modify: `src/quack_rl/rl/ppo_run.py` (`_check`, `run_ppo_seed`: stored config and MaskablePPO args)
- Modify: `experiments/S0.json` ... `experiments/S5.json`, `experiments/L.json`
- Test: `tests/test_experiment.py`, `tests/test_experiment_configs.py`, `tests/test_rl_ppo_run.py`

**Interfaces:**
- Produces: `ExperimentConfig.n_steps: int | None`, `ExperimentConfig.batch_size: int | None`,
  `ExperimentConfig.target_kl: float | None`. For `kind == "ppo"` all three keys must be present
  in the JSON (`model_fields_set`); `target_kl` may be null. `run_ppo_seed` uses
  `config.n_steps`, `config.batch_size`, `config.target_kl`; the run's `config.json` stores the
  three values from the config.

- [ ] **Step 1: Failing tests**
  - `test_ppo_config_needs_n_steps` / `..._batch_size` / `..._target_kl`: a PPO config JSON
    without the key raises `ValueError` whose message names the field.
  - `test_ppo_config_target_kl_null_loads`: `"target_kl": null` loads, value `None`.
  - `test_bc_config_needs_no_ppo_settings`: B0.json loads unchanged.
  - `test_n_steps_multiple_of_batch_size`: `n_steps` 1000, `batch_size` 64 raises `ValueError`.
  - `test_target_kl_positive`: 0 and -0.01 raise `ValueError`.
  - `test_checkpoint_every_multiple_of_config_n_steps` (ppo_run `_check`): `n_steps` 4096,
    `checkpoint_every` 96256 raises `ValueError` naming 4096; 192512 passes.
  - `test_run_stores_ppo_settings` (slow if it trains): the run's `config.json` has the config's
    `n_steps`, `batch_size`, `target_kl`, and the MaskablePPO model has the same values
    (`model.n_steps`, `model.batch_size`, `model.target_kl`).
  - `test_old_configs_explicit_settings`: S0-S5 and L have exactly 1024, 64, null.
- [ ] **Step 2:** Run them; they fail.
- [ ] **Step 3:** Add the fields and the checks to `ExperimentConfig._check`; replace `N_STEPS` /
  `BATCH_SIZE` in `ppo_run.py` by the config values (the import from `train` goes away if
  unused); add the three keys to S0-S5 and L.
- [ ] **Step 4:** Fast subset passes, then the full test command. Commit.

### Task 3: `epochs_run` in `ppo.csv` and in the monitor

**Files:**
- Modify: `src/quack_rl/rl/ppo_run.py` (`PPO_COLUMNS`, the `PPORun` callback)
- Modify: `src/quack_rl/rl/monitor.py` (`PPO_SCHEMA`)
- Modify: `notebooks/rl_monitor.py` (`PPO_METRICS`, tolerate a missing column)
- Test: `tests/test_rl_ppo_run.py`, `tests/test_rl_monitor.py`

**Interfaces:**
- Consumes: `config.target_kl` from task 2.
- Produces: `ppo.csv` last column `epochs_run` (int): passes of this update, the difference of
  MaskablePPO's pass counter (`_n_updates`, logged as `train/n_updates`) to the previous row; the
  first row after a start or resume uses the counter's value at that start.

- [ ] **Step 1: Failing tests**
  - `test_epochs_run_without_target_kl`: a short run with `target_kl` null has `epochs_run` 10
    on every row.
  - `test_epochs_run_with_target_kl`: a short run with a tiny `target_kl` (for example 1e-6)
    has `epochs_run` < 10 on at least one row and >= 1 on every row.
  - `test_epochs_run_after_resume`: a run resumed from a checkpoint has `epochs_run` 10 (not the
    total counter) on its first new row.
  - `test_monitor_reads_ppo_csv_without_epochs_run`: an old-format `ppo.csv` loads, no
    `epochs_run` column or all null, no error.
- [ ] **Step 2:** Run them; they fail.
- [ ] **Step 3:** Implement. In the notebook, add `epochs_run` to `PPO_METRICS` and select only
  the metrics a run has (a missing one is left out for that run).
- [ ] **Step 4:** Tests pass. Export the notebook headless with S1 against S0 (old runs, no
  column) and check it renders without an error:
  `uv run --group rl --group monitor marimo export html notebooks/rl_monitor.py -o <scratch>.html -- --experiment S1 --baseline S0`.
  Full test command. Commit.

### Task 4: Screening 3: S6 and S7

**Files:**
- Create: `experiments/S6.json`, `experiments/S7.json`
- Modify: `docs/analysis/2026-11-screening.md` (new "Part 4: Screening 3 (S6, S7)")
- Test: `tests/test_experiment_configs.py`

**Interfaces:**
- Consumes: the config fields (task 2), `epochs_run` (task 3).

- [ ] **Step 1: Failing test** `test_s6_s7_differ_from_s1`: `config_diff(S1, S6)` ==
  `["n_steps", "batch_size", "checkpoint_every"]` with S6 values 4096, 256, 192512;
  `config_diff(S1, S7)` == `["target_kl"]` with 0.02 <= S7 `target_kl` <= 0.05; both have
  `baseline` "S1".
- [ ] **Step 2:** Choose `target_kl` for S7 in [0.02, 0.05]; write the value and the reason in
  S7's `changes` text (spec: SB3 stops at 1.5 x `target_kl` per minibatch; the logged
  `approx_kl` is a mean). Write both configs. Test passes. Commit before any run.
- [ ] **Step 3:** Run S6, then S7, with the commands of parts 1 and 2 (`systemd-run --user
  --scope -p MemoryMax=4G -p MemorySwapMax=0 /usr/bin/time -v uv run --group rl python
  scripts/run_experiment.py --config experiments/S6.json --out data/experiments --threads 1`).
- [ ] **Step 4:** Write part 4 with the content listed in the spec section "Screening 3": run
  data, per-seed rows, sha256, greedy final tables, scores, learning curves, win rate against
  `bot:random` per checkpoint (S1, S6, S7), PPO metrics (S0, S1, S6, S7), the sense check, and
  the suggestion to the owner. Commit.
