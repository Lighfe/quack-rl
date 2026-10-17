---
name: rule_changes
description: Load this skill when someone changes or adds a game rule or a ruleset version (a new ruleset file, a new ruleset field, a new phase or action). Not for other work, for example adding a colour, RL training, or editing a notebook alone.
---

# Changing the rules

This list is a map of what a rule change touches. Read `docs/specs/2026-10-16-ruleset-v1-8.md` for the shape of such a change.

## Three rules

1. Never edit a ruleset version that has recorded games. Saved games, runs and datasets name their version and must replay the same. A change is a new file (for example `v1.8.toml` sits next to `v1.toml` and `v1.1.toml`).
2. New behaviour is switched by ruleset fields. The engine reads the field, for example `points`, `explosion_choice`, `last_round_money_divisor`. Old versions leave the field at its default, so they play as before.
3. Pin defaults and notebooks explicitly to a ruleset version. Nothing may pick up the new version by accident: no default of `rules` is the newest version, and the notebooks name their version once (`RULES = "v1.1"`). `tests/test_rules_defaults.py` checks this.

## Places a rule change touches

1. Rules document and ruleset file
   - `docs/rules/rules-v1.8.md` (the rules in words)
   - `src/quack_rl/rules/v1.8.toml` (the values)
   - `src/quack_rl/rules/model.py` (new fields with defaults that keep old versions unchanged, and their validation)
   - `src/quack_rl/rules/load.py` (`SUPPORTED_RULES_VERSIONS`)
2. Engine
   - `src/quack_rl/engine/actions.py` (new action names and `legal_actions`)
   - `src/quack_rl/engine/state.py` (new phase or state field)
   - `src/quack_rl/engine/game.py` (phase routing)
   - `src/quack_rl/engine/resolve.py` and `src/quack_rl/engine/choice.py` (the new resolution step)
   - `src/quack_rl/engine/__init__.py` (exports)
3. Record schema and replay
   - `src/quack_rl/record/` (`schema.py`, `writer.py`, `reader.py`, `replay.py`): a game with the new actions must write and replay. check that a test of the record with the new actions exists, for example `tests/test_record_v1_8.py`, and whether your change needs more than that.
4. Bots
   - `src/quack_rl/bots/heuristic.py` (the heuristic bot must answer every new action)
   - `src/quack_rl/simgame.py` and `src/quack_rl/tournament.py`
5. CLI
   - `src/quack_rl/cli/render.py` (show the new values)
   - `src/quack_rl/cli/human.py` (prompt for the new choice)
6. RL layout and environments
   - `src/quack_rl/rl/encode.py` (observation layout and action mask)
   - `src/quack_rl/rl/__init__.py`, `src/quack_rl/rl/derive.py`, `src/quack_rl/rl/runs.py` (layout check by ruleset)
   - A new layout gets a spec, for example `docs/specs/2026-10-16-observation-layout-3.md`. Store a sample of the old layout first (`tests/fixtures/layout2/sample.npz`, made by `tests/fixtures/make_layout2_sample.py`) so old layouts stay checked.
7. Tests on the new version
   - `tests/test_ruleset_v1_8.py`, `tests/test_engine_v1_8.py`, `tests/test_record_v1_8.py`, `tests/test_cli_v1_8.py`, `tests/test_rl_layout3.py`, `tests/test_rl_v1_8.py`
   - Extend the existing tests that list versions: `tests/test_ruleset.py`, `tests/test_bots.py`, `tests/test_tournament.py`, `tests/test_rl_parallel_env.py`
8. Defaults and notebooks
   - `tests/test_rules_defaults.py`
   - `notebooks/rl_env.py`, `notebooks/offline_rl.py` (they stay on their pinned version until the owner decides)
9. Spec
   - `docs/specs/2026-10-08-quack-rl-design.md` (the milestone table)

## Checklist for a new ruleset version

Work in this order, one commit per step, because each step builds on the one before.

- [ ] Ruleset file and rules document: new ruleset file in `src/quack_rl/rules/`, new model fields with old-safe defaults, `SUPPORTED_RULES_VERSIONS`, the rules document in `docs/rules/`, test for the file
- [ ] Engine: new actions, phase and resolution, switched by the new fields; old versions unchanged
- [ ] Record and replay: a game with the new actions writes and replays
- [ ] Bots: every bot answers the new actions
- [ ] CLI: render and prompt the new rule
- [ ] RL layout and environments: observation, action mask, layout check by ruleset; store a sample of the old layout first
- [ ] Tests on the new version: engine, RL environments, evaluate, self-play and dataset; add the version to the parallel env tests
- [ ] Defaults and notebooks: no default is the new version, notebooks pinned, saved data of old versions still loads
- [ ] Spec: update the milestone table in `docs/specs/2026-10-08-quack-rl-design.md`

Run the full test command from `AGENTS.md` after the last step. Old versions must still pass.
