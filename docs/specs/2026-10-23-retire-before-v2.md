# Retire everything before ruleset v2; v2 becomes the only ruleset and the default

Status: designed 2026-10-23 in the owner brainstorm (`/stage-start`). Placeholder issue: #164. Prior spec: `docs/specs/2026-10-22-ruleset-v2.md`. Next spec after this one: `docs/specs/2026-10-23-ruleset-v2-1-design.md` (planned in its own stage).

## Intent

The repo carries seven rulesets (v1 to v2), six observation layouts (2 to 7) and a training stack built for the old ones. Every new rule has to keep all of them working, which forces compromises: optional ruleset fields, `None` branches, per-version tests and layouts nobody uses any more.

This stage moves everything from before v2, and the whole training stack, into an archive. v2 stays as the only ruleset and becomes the default. The result is a clean base on which v2.1 (the next stage) can rework the ruleset model, the engine and the observation without any legacy path.

The owner's decisions (2026-10-22 in #164 and 2026-10-23 in the brainstorm):

- Archived means moved, not deleted. The code stays available to recycle.
- Old saved data does not need to keep loading.
- v2 itself is retired as well once v2.1 exists (next stage). This stage does not build v2.1.

## Goals

- v2 is the only supported ruleset: `SUPPORTED_RULES_VERSIONS == ("v2",)`.
- `"v2"` is the default `rules` value everywhere (CLI, tournament, simulation, report, environments, scripts).
- No code path in `src/` exists only for a ruleset before v2.
- Observation layout 7 is the only layout. Its vector stays exactly as it is today.
- A v2 game replays exactly as before (determinism guard).
- The full test command passes, and every remaining test runs on v2.

## Non-goals and anti-goals

- No rule change, no new ruleset, no new layout. v2 plays and encodes exactly as today. Anti-goal: any change of a v2 game, record or observation vector.
- No rework of the ruleset model format (the per-field table is v2.1).
- No training on v2. Training is rebuilt later, on v2.1.
- No new notebooks. New ones are built later, on v2.1, designed afresh (not copies of the old ones).
- Anti-goal: deleting instead of moving. Every file that leaves `src/`, `tests/`, `scripts/`, `notebooks/` or `docs/` is moved into `archive/` with `git mv`.

## The archive

- A top-level folder `archive/` mirrors the old path of each file: `src/quack_rl/rules/v1.toml` becomes `archive/src/quack_rl/rules/v1.toml`, `tests/test_rl_train.py` becomes `archive/tests/test_rl_train.py`, and so on.
- Nothing imports from `archive/`. Pytest does not collect it (`testpaths = ["tests"]` already). Ruff and pyright do not check it (exclude it in `pyproject.toml` if they would).
- `archive/README.md` says in a few lines what is there, why, and that it is not run or tested.
- When a file is cleaned in place (it stays, but loses old branches), its state before the cleanup is copied into `archive/` first, as a separate file with the mirrored path. This holds for the bots and for `encode.py`.
- `docs/archive/` stays what it is (the planner's archive of finished plans). Old specs, rules texts and analysis go to `archive/docs/…`.

## What moves to the archive

### Rulesets and rules texts

- `src/quack_rl/rules/v1.toml`, `v1.1.toml`, `v1.8.toml`, `v1.9.toml`, `v1.10.toml`, `v1.11.toml`.
- `docs/rules/rules-v1.md` to `rules-v1.11.md`.
- Specs of old rulesets, old layouts and the training stack: `docs/specs/2026-10-09-m1-playtest-fixes.md`, `2026-10-09-m2-1-bots-and-balance.md`, `2026-10-10-m2-3-ruleset-v1-1.md`, `2026-10-12-m2-5-observation-layout-2.md`, `2026-10-12-m2-rl-environment.md`, `2026-10-13-self-play.md`, `2026-10-14-resume.md`, `2026-10-16-observation-layout-3.md`, `2026-10-16-ruleset-v1-8.md`, `2026-10-17-observation-layout-4.md`, `2026-10-17-ruleset-v1-9.md`, `2026-10-18-ruleset-v1-10.md`, `2026-10-19-observation-layout-5.md`, `2026-10-19-ruleset-v1-11.md`, `2026-10-20-observation-layout-6.md`.
- Stay in `docs/specs/`: the master design `2026-10-08-quack-rl-design.md`, the skill spec `2026-10-18-quack-rule-changes-skill.md`, `2026-10-22-ruleset-v2.md`, this spec and the v2.1 design.
- A spec that stays but links to a moved file gets its link updated to the `archive/` path.

### Training stack (owner decision: archive, rebuild on v2.1)

- `src/quack_rl/rl/`: `train.py`, `selfplay.py`, `offline.py`, `dataset.py`, `replay_dqn.py`, `finetune.py`, `evaluate.py`, `policy_bot.py`, `runs.py`.
- Stay in `src/quack_rl/rl/`: `encode.py`, `derive.py`, `parallel_env.py`, `single_env.py`, `reward.py`, `opponents.py` (bots only, see below), `__init__.py`. Remove from them every import and export of a moved module.
- `check_policy_layout` and `LayoutRefused` exist only for the policy paths. They move with them (no caller is left).
- The `policy:` seat: `src/quack_rl/cli/seats.py` loses the `policy:` branch; `check_seat` rejects `policy:` as an unknown seat, with a clear message. Tournament and CLI tests for policy seats move to the archive.
- `scripts/train.py`, `scripts/train_offline.py`, `scripts/train_selfplay.py`, `scripts/build_dataset.py`. `scripts/measure_speed.py` stays.
- The optional dependency group `train` (torch, stable-baselines3, sb3-contrib) is removed from `pyproject.toml`, and `uv.lock` is updated (`uv lock`). gymnasium and pettingzoo stay (the environments and their checks need them).
- The tests of the moved modules: `test_rl_train.py`, `test_rl_train_script.py`, `test_rl_selfplay.py`, `test_rl_offline.py`, `test_rl_dataset.py`, `test_replay_dqn.py`, `test_rl_finetune.py`, `test_rl_evaluate.py`, `test_rl_policy_bot.py`, `test_rl_runs.py`, and the refusal tests of `check_policy_layout` in the layout test files.

### Notebooks and analysis

- `notebooks/rl_env.py`, `notebooks/tournament_run.py`, `notebooks/offline_rl.py` (and `notebooks/__marimo__/` if tracked), with their tests `test_rl_notebook.py`, `test_offline_rl_notebook.py`, `test_notebook.py`.
- The dev dependency group entries that only the notebooks use (marimo, altair, polars) are removed, unless a remaining file imports them (builder checks with grep).
- `docs/analysis/` in full (balance v1 and v1.1, the self-play and offline RL runs, the offline RL research note).

### Observation layouts 2 to 6

- `observation_layout(rs)` returns 7 for v2; the branches for layouts 2 to 6 and the code only they use leave `encode.py` and `derive.py`. Code that layout 7 uses stays, even when layout 6 introduced it.
- Layout constants of the old layouts are removed. Layout 7 keeps its number 7 (renumbering is not worth it; v2.1 adds layout 8).
- `tests/fixtures/layout2/sample.npz`, `tests/fixtures/make_layout2_sample.py`, and the test files `test_rl_layout3.py`, `test_rl_layout4.py`, `test_rl_layout5.py`, `test_rl_layout6.py`, `test_rl_v1_8.py`.
- Guard (first task of the stage): a stored sample of layout 7 is made before any encoder change, from a fixed-seed v2 game (masked random actions, both seats, several rounds), with its generator script in `tests/fixtures/`. A test compares the encoder output with it. It must pass unchanged after the cleanup.

### Fixtures

- `tests/fixtures/golden/v1_bots_results.csv`, `tests/fixtures/golden/v1_random_seed7.jsonl`, `tests/fixtures/make_golden.py` (the v1 version), `tests/fixtures/dataset/`.
- Guard (first task of the stage): a v2 golden fixture replaces the v1 one: a fixed-seed v2 game record and a small bots results table, with a generator script. The tests that used the v1 golden files compare with the v2 ones. The v2 golden files are made before any engine change.
- `tests/fixtures/report/` stays if the report tests port to v2 (regenerate it from v2 if its content is v1-specific).

### Bots

- `src/quack_rl/bots/heuristic.py`, `strategy.py`, `random_bot.py` are copied to `archive/src/quack_rl/bots/` as they are.
- In place, the random bot stays unchanged. The heuristic bot loses the branches that only an old ruleset reaches (for example the v1.1 `max_chip_purchases` rule if v2 has no such limit, `max_purchases`, the v1.8 money-before-points-round rule if v2 does not reach it). Builder: decide per branch by what v2 sets; a branch v2 reaches stays.
- The heuristic bot plays v2 exactly as before: the v2 golden bots results (above) must not change.

## Engine and ruleset model cleanup

- `SUPPORTED_RULES_VERSIONS = ("v2",)`. Loading any other version fails with the existing error for an unknown version.
- Every branch that only an older ruleset reaches is removed. Known candidates (builder confirms each against `v2.toml`):
  - `rs.points is None` (v2 has points)
  - `explosion_choice` False (v2 has it)
  - `spellbook is None` and the per-chip `component` (v2 has a spellbook)
  - `point_board is None` (v2 has a board)
  - empty `cards` (v2 has cards)
  - `last_round_money_divisor is None`
  - `last_round_money_percent` other than 100
  - `max_purchases` (v2 has none)
  - shop item kinds and die face kinds that no v2 entry uses (for example the die `money` kind)
- The ruleset model makes these fields required with the v2 meaning instead of optional with an old-safe default. It still loads `v2.toml` without any change to that file. A field that v2 still uses with more than one value stays as it is.
- Tests that checked an old-safe default ("a ruleset without X plays as before") are moved to the archive with the version they covered.
- A v2 game, its record and its replay do not change (the golden fixture proves it).

## Tests

Every test file falls into one of three groups. The builder sorts each file into one group, and states the group of each file in the commit or issue comment of the task that moves or ports it.

1. **Per-version or per-layout tests** (`test_ruleset_v1_*.py`, `test_engine_v1_*.py`, `test_cli_v1_*.py`, `test_bots_v1_*.py`, `test_record_v1_*.py`, `test_default_rules_v1_11.py`, `test_rl_layout3` to `6`, `test_rl_v1_8.py`): move to the archive.
2. **Tests of a moved module** (training stack, notebooks, policy seats): move to the archive.
3. **Generic tests that use an old version only as a vehicle** (for example `test_ruleset.py`, `test_tournament.py`, `test_bots.py`, `test_record.py`, `test_report.py`, `test_overrides.py`, `test_rl_encode.py`, `test_rl_derive.py`, `test_rl_parallel_env.py`, `test_rl_single_env.py`, `test_cli_sim.py`, `test_cli_play.py`, `test_spellbook.py`, `test_components.py` and similar): stay, ported to v2. A single test inside such a file that checks behaviour v2 does not have (an old-version branch) moves to the archive with its version; the rest of the file stays.

Also:

- Loops over versions (`VERSIONS` lists and parametrisations) become v2 only, or lose the loop.
- `gymnasium.utils.env_checker.check_env` and PettingZoo `parallel_api_test` run on v2 (today `check_env` is only in `test_rl_v1_8.py`).
- No test is deleted to make the suite pass. A failing generic test is ported, not dropped.
- The full test command passes at the end of every task, not only at the end of the stage.

## Defaults and docs

- Every default `"v1.11"` becomes `"v2"`: `cli/main.py`, `tournament.py`, `report.py`, `rl/opponents.py`, `rl/parallel_env.py`, `rl/single_env.py`, `scripts/measure_speed.py` and any other place a grep finds. `tests/test_rules_defaults.py` checks the new default and loses the entries of moved modules.
- README: the rulesets, layouts, training and notebook sections say what is left, and point to `archive/` for the rest.
- The milestone table of `docs/specs/2026-10-08-quack-rl-design.md` gets a row for this stage, and notes that v2.1 comes next.
- The skill `quack_rule_changes` and its files: every `v1.11` default pin becomes `v2`; lists of versions and layouts name only v2 and layout 7; the training and notebook steps are removed or say they are archived. Include the stage review finding: `.agents/skills/quack_rule_changes/new-ruleset-version.md:72` names only "more colours or a `min_round`" as what picks a layout; it should match the rule in `project-map.md` (now: one layout, 7, for the point board).
- The kit documents: remove the stale bump-plugin-version references (#163).

## Local data (owner, by hand)

`data/` is untracked (gitignored) and 832 MB. It is not part of any task: the owner moves the old content by hand to `data/archive/` (`data/records/v1`, `v1.8`, `v1.11`, `data/datasets`, `data/runs`, `data/tournaments`). `data/records/v2` stays. The task that changes the defaults (step 8) checks with grep that no remaining default path points into a moved folder, and names any it finds.

## Parked issues touched by this stage

- #149 (retrain a policy on v1.11): moot, the owner decided pre-v2 policies are retired. Close.
- #79 (rules v2 and a new game implementation): v2 exists; the owner decides whether to close it or fold it into v2.1.
- #57, #58, #84, #85, #86 (reward shaping, offline RL, self-play): their code is archived. They stay parked and are re-judged when training is rebuilt on v2.1.
- #49 (tournament verify sample also checks seats.parquet): stays parked; the tournament stays, so it is still valid.
- New parked issue: research on the observation encoding (window vs raw absolute vs attention or convolution over the fields), after v2.1. See the v2.1 design.

## Order

1. Guards first: the v2 golden fixture and the layout 7 sample, made from the code as it is today.
2. Archive the training stack, the `policy:` seat and the `train` dependency group.
3. Archive the notebooks and `docs/analysis/`.
4. Port the generic tests to v2 and archive the per-version tests (group 1). After this no remaining test names an old version.
5. Archive rulesets v1 to v1.11 and their texts and specs; clean the ruleset model and the engine.
6. Archive layouts 2 to 6 and clean the encoder.
7. Copy the bots to the archive and clean the heuristic bot.
8. Defaults to v2, docs, README, skill texts, #163.

Steps 2 and 3 do not depend on each other. Step 4 needs 2 and 3 (their tests are gone by then). Steps 5, 6 and 7 need 4 (no remaining test needs an old version). Step 8 is last.

## Left to the builder

- The group of each test file, and which single tests inside a generic file move.
- The exact list of engine and model branches to remove, checked against `v2.toml`.
- The content and seed of the golden fixture and the layout 7 sample.
- The wording of `archive/README.md`.
- Whether a remaining dev dependency is still used.
