# Retire everything before ruleset v2: implementation plan

> For agentic workers: each task below becomes one GitHub issue and runs through the loop in `docs/process.md` (PM, engineer, QA). Do not use the skills subagent-driven-development or executing-plans (see `AGENTS.md`).

**Goal:** v2 is the only ruleset and the default; everything older, the training stack and the notebooks are moved to `archive/`; v2 plays, records and encodes exactly as before.

**Architecture:** guards first (a v2 golden replay and a stored layout 7 sample, made from today's code), then moves with `git mv`, then the cleanup of the code paths that only old rulesets reach, then the defaults and docs. Every task keeps the full test command green.

**Tech stack:** Python, uv, pytest, pydantic, gymnasium, pettingzoo.

**Spec:** `docs/specs/2026-10-23-retire-before-v2.md`

## Global constraints

- Archived means moved with `git mv` into `archive/<old path>`. Nothing is deleted to make a test pass.
- Nothing imports from `archive/`; pytest, ruff and pyright do not check it.
- A v2 game, its record and its layout 7 vector do not change (the guards of task 1 prove it in every later task).
- Test command: `uv run --with pytest pytest`. It passes at the end of every task.
- Public repo: no secrets.

## Review focus

1. A generic test that used an old version silently stops testing anything after the port (for example a loop over versions that becomes empty): each ported loop still runs at least one v2 case.
2. An engine branch that v2 does reach is removed as "old": the golden replay of task 1 must stay byte-identical.
3. Layout 7 depends on a helper that only layout 6 seemed to use: the layout 7 sample of task 1 must stay equal.
4. `check_seat("policy:...")` after the policy seat is gone: a clear error, not an import error.
5. A remaining file still imports a moved module or a removed dependency (marimo, torch): `uv run --with pytest pytest` from a fresh `uv sync` catches it; the engineer runs it once.

---

### Task 1: Guards: v2 golden replay and layout 7 sample

**Files:**
- Create: `tests/fixtures/golden/v2_random_seed7.jsonl`, `tests/fixtures/golden/v2_bots_results.csv` (generator: `tests/fixtures/make_golden.py`, which gets a v2 mode next to the v1 one)
- Create: `tests/fixtures/layout7/sample.npz`, `tests/fixtures/make_layout7_sample.py`
- Create: `tests/test_golden_v2.py`, `tests/test_rl_layout7_sample.py`

**Interfaces:**
- Produces: the fixture paths above, used by task 4 to replace every use of the v1 golden files.

- [ ] Test `test_golden_v2_replay`: playing v2 with `RandomBot(15)` / `RandomBot(16)` and `RngChance(7)` writes a record equal to `v2_random_seed7.jsonl` line by line (the header time and engine version are fixed as in the v1 generator).
- [ ] Test `test_golden_v2_bots_results`: the same small bots table as `v1_bots_results.csv` (same bots and seeds as the v1 test that reads it), on v2, equals `v2_bots_results.csv`.
- [ ] Test `test_layout7_sample`: a fixed-seed v2 game with masked random actions (both seats, at least three rounds) encoded with `QuackParallelEnv` gives exactly the stored arrays (`np.array_equal`, names and values).
- [ ] Generate the fixtures from the code as it is (no other change in this task), run the full test command, commit.

### Task 2: Archive the training stack and the policy seat

**Files:**
- Move to `archive/`: `src/quack_rl/rl/{train,selfplay,offline,dataset,replay_dqn,finetune,evaluate,policy_bot,runs}.py`, `scripts/{train,train_offline,train_selfplay,build_dataset}.py`, `tests/test_rl_{train,train_script,selfplay,offline,dataset,finetune,evaluate,policy_bot,runs}.py`, `tests/test_replay_dqn.py`, `tests/fixtures/dataset/`
- Create: `archive/README.md`
- Modify: `src/quack_rl/rl/__init__.py`, `src/quack_rl/rl/opponents.py`, `src/quack_rl/rl/encode.py` (remove `check_policy_layout`, `LayoutRefused`), `src/quack_rl/cli/seats.py`, `pyproject.toml` (drop the `train` group; exclude `archive/` from ruff and pyright if needed), `uv.lock`
- Modify: the layout test files, to drop their refusal tests

- [ ] Test `test_policy_seat_rejected`: `check_seat("policy:runs/x")` raises the existing unknown-seat error, and its message names `policy:` as not supported.
- [ ] Test: `import quack_rl.rl` works without torch installed and exports no moved name.
- [ ] Move, clean imports, `uv lock`, full test command, commit.

### Task 3: Archive the notebooks and the analysis

**Files:**
- Move to `archive/`: `notebooks/rl_env.py`, `notebooks/tournament_run.py`, `notebooks/offline_rl.py` (and `notebooks/__marimo__/` if tracked), `tests/test_rl_notebook.py`, `tests/test_offline_rl_notebook.py`, `tests/test_notebook.py`, `docs/analysis/`
- Modify: `pyproject.toml` / `uv.lock` (drop marimo, altair, polars from the dev group if `grep -r` finds no remaining import in `src/`, `tests/`, `scripts/`), `tests/test_rules_defaults.py` (stop scanning `notebooks/`)

- [ ] Move, update the scan, `uv lock`, full test command, commit.

### Task 4: Port the generic tests to v2; archive the per-version tests

**Files:**
- Move to `archive/tests/`: `test_ruleset_v1_1.py`, `test_ruleset_v1_8.py`, `test_ruleset_v1_9.py`, `test_ruleset_v1_10.py`, `test_ruleset_v1_11.py`, `test_engine_v1_8.py`, `test_engine_v1_9.py`, `test_engine_v1_10.py`, `test_engine_v1_11.py`, `test_engine_v1_11_choices.py`, `test_cli_v1_8.py`, `test_cli_v1_9.py`, `test_cli_v1_10.py`, `test_cli_v1_11.py`, `test_bots_v1_10.py`, `test_bots_v1_11.py`, `test_record_v1_8.py`, `test_record_v1_9.py`, `test_default_rules_v1_11.py`, `test_rl_layout3.py`, `test_rl_layout4.py`, `test_rl_layout5.py`, `test_rl_layout6.py`, `test_rl_v1_8.py`, `tests/fixtures/golden/v1_*`, `tests/fixtures/layout2/`, `tests/fixtures/make_layout2_sample.py`
- Modify (port to v2): every other test file that names `"v1"` … `"v1.11"`, among them `test_ruleset.py`, `test_tournament.py`, `test_bots.py`, `test_record.py`, `test_report.py`, `test_overrides.py`, `test_rl_encode.py`, `test_rl_derive.py`, `test_rl_parallel_env.py`, `test_rl_single_env.py`, `test_cli_sim.py`, `test_cli_play.py`, `test_rounds.py`, `test_verify.py`, `test_spellbook.py`, `test_components.py`, `test_state_actions.py`, `test_placed_fields.py`, `test_baseline_maximum.py`, `test_rules_defaults.py`
- Modify: `tests/fixtures/make_golden.py` (v2 only), `tests/fixtures/report/` (regenerate from v2 if its content is v1-specific)

**Interfaces:**
- Consumes: the v2 golden files and layout 7 sample of task 1.

- [ ] Test `test_check_env_v2`: `gymnasium.utils.env_checker.check_env(QuackEnv(rules="v2"), skip_render_check=True)` passes (moved from `test_rl_v1_8.py`).
- [ ] Test: no file under `tests/` (outside `fixtures/`) contains a string literal `"v1"`, `"v1.1"`, `"v1.8"`, `"v1.9"`, `"v1.10"` or `"v1.11"` (a check test, `test_no_old_versions_in_tests`). A line that ends with the comment `# old-version-ok` is skipped (task 5 needs it for its refusal test).
- [ ] Port each generic file; a single test inside it that checks old-version behaviour moves to `archive/tests/` in a file named after its source. State in the issue comment the group of each file (spec, section "Tests").
- [ ] Full test command, commit.

### Task 5: Archive rulesets v1 to v1.11; clean the ruleset model and the engine

**Files:**
- Move to `archive/`: `src/quack_rl/rules/v1.toml`, `v1.1.toml`, `v1.8.toml`, `v1.9.toml`, `v1.10.toml`, `v1.11.toml`, `docs/rules/rules-v1*.md`, and the old specs listed in the spec, section "Rulesets and rules texts" (to `archive/docs/specs/`)
- Modify: `src/quack_rl/rules/load.py` (`SUPPORTED_RULES_VERSIONS = ("v2",)`), `src/quack_rl/rules/model.py`, `src/quack_rl/engine/*.py`, `src/quack_rl/report.py`, `src/quack_rl/cli/*.py`, `src/quack_rl/components/*.py`, links in the specs that stay

**Interfaces:**
- Produces: `Ruleset` with `points`, `spellbook`, `point_board`, `cards`, `explosion_choice`, `last_round_money_divisor` required (no `None` / empty default). `v2.toml` loads unchanged.

- [ ] Test `test_old_version_refused`: `load_ruleset("v1.11")` raises the existing unknown-version error.
- [ ] Test `test_supported_versions`: `SUPPORTED_RULES_VERSIONS == ("v2",)`.
- [ ] Test: a `v2.toml` copy without `point_board` (or `points`) fails validation.
- [ ] Remove each branch only an old ruleset reaches (spec, section "Engine and ruleset model cleanup"); check each against `v2.toml`. List the removed branches in the issue comment.
- [ ] Golden and layout 7 sample tests unchanged; full test command, commit.

### Task 6: Archive observation layouts 2 to 6

**Files:**
- Create: `archive/src/quack_rl/rl/encode.py`, `archive/src/quack_rl/rl/derive.py` (copies of the files before this task)
- Modify: `src/quack_rl/rl/encode.py`, `src/quack_rl/rl/derive.py`, `src/quack_rl/rl/parallel_env.py`, `src/quack_rl/rl/single_env.py`

- [ ] Test: `observation_layout(load_ruleset("v2")) == 7`.
- [ ] Remove the layout 2 to 6 branches and their constants; keep every helper layout 7 uses.
- [ ] `test_layout7_sample` and `test_rl_layout7.py` unchanged and passing; full test command, commit.

### Task 7: Clean the bots

**Files:**
- Create: `archive/src/quack_rl/bots/heuristic.py`, `strategy.py`, `random_bot.py` (copies, before the cleanup)
- Modify: `src/quack_rl/bots/heuristic.py`, `src/quack_rl/bots/strategy.py`

- [ ] Remove the branches v2 does not reach (for example `max_purchases`); list them in the issue comment with the `v2.toml` value that makes each one dead.
- [ ] `test_golden_v2_bots_results` unchanged; full test command, commit.

### Task 8: Defaults to v2, docs, skill texts, kit docs

**Files:**
- Modify: every default `rules = "v1.11"` in `src/` and `scripts/` (grep), `tests/test_rules_defaults.py`, `README.md`, `docs/specs/2026-10-08-quack-rl-design.md` (milestone row), `.agents/skills/quack_rule_changes/` (all files), the kit documents named in #163

- [ ] Test `test_rules_defaults`: every default `rules` value in `src/quack_rl` and `scripts/` is `"v2"`.
- [ ] Skill texts: v2 is the default; only v2 and layout 7 are listed; training and notebook steps say they are archived; `new-ruleset-version.md:72` matches the layout rule of `project-map.md`.
- [ ] Remove the stale bump-plugin-version references (#163).
- [ ] grep: no remaining default path points into the folders the owner moves to `data/archive/` (spec, section "Local data"); name any found in the issue comment.
- [ ] Full test command, commit.

## Order and blockers

- Task 1 first. Tasks 2 and 3 are blocked by 1 and not by each other.
- Task 4 is blocked by 2 and 3.
- Tasks 5, 6 and 7 are blocked by 4. 6 and 7 are also blocked by 5 (they read the cleaned model).
- Task 8 is blocked by 5, 6 and 7.
