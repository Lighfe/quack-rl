---
name: quack_rule_changes
description: Load this skill when a game rule, a ruleset version, a colour or a shop item changes or is added (a new ruleset file, a new ruleset field, a new phase or action). Not for RL training or notebook edits alone.
---

# Changing the rules of quack-rl

The skill has three parts, in this order:

1. General advice: what holds for every rule change. Read it first.
2. Recipes: short how-tos for typical changes.
3. Project map: how the game parts fit together and where each one lives.

## 1. General advice

### Versioning

- Never edit a ruleset version that has recorded games. Saved games, runs and datasets name their version and must replay the same.
- A change is a new version, a new ruleset file next to the old ones.
- New behaviour is switched by ruleset fields. The engine reads the field; old versions leave it at a default that keeps them playing as before. Give every new field an old-safe default.
- The default `rules` value is `v2.3`, everywhere in the code (CLI, tournament, run and simulate functions, RL modules, the web service and scripts). v2.3 is the only ruleset; its rules are in `docs/rules/rules-v2.3.md`. v2.1 and v2.2 are archived (`archive/src/quack_rl/rules/`, `archive/docs/rules/`, their golden records in `archive/tests/fixtures/golden/`), as are v2 and the older ones; `v2`, `v2.1` and `v2.2` are unknown names, and records of schema version 2 are not read; the older rulesets, observation layouts 2 to 6 and the notebooks are in `archive/` (see `archive/README.md`) and not checked. A later ruleset version (v3, say) is not the default until an issue makes it the default, and that issue changes every default, the defaults test and these skill texts together. `tests/test_rules_defaults.py` checks that every default is the current default version and fails on a default that points anywhere else.
- There is one observation layout, 10 (`BOARD_LAYOUT`): the round and the phase, the state of each seat (money, rubies, flask, points, droplet, bag), the derived features of each seat and the gaps, the hand, the shop, the card block, the board block, a look-ahead window of the fields and, last, the map of the placed chips; the droplet values `own.droplet` and `opponent.droplet` are whole steps; the opponent's hidden hand counts as in its bag (`opponent.bag.*` and `opponent.explosion_chance`), the own seat's bag values exclude its hand (the [project map](project-map.md) lists the blocks). Environments and baseline bots work on v2.3. The policy stack is tracked and tested: the modules `src/quack_rl/rl/policy_bot.py` (`PolicyBot`), `src/quack_rl/rl/train.py`, `src/quack_rl/rl/selfplay.py`, `src/quack_rl/rl/offline.py`, `src/quack_rl/rl/dataset.py` and `src/quack_rl/rl/evaluate.py`, the scripts `scripts/train_ppo.py`, `scripts/train_selfplay.py`, `scripts/train_offline.py` and `scripts/build_dataset.py`, and their tests `tests/test_rl_train_smoke.py`, `tests/test_rl_selfplay.py`, `tests/test_rl_offline.py`, `tests/test_rl_evaluate.py` and `tests/test_rl_dataset_import.py`. Training needs the `rl` dependency group (`--group rl`: torch, stable-baselines3, sb3-contrib); the training tests skip without it (`pytest.importorskip`). `quack_rl.rl` does not export the policy modules (`__all__` holds only the encoder, env, reward and opponent names); code imports them by module path. There is no `policy:` seat: `check_seat` in `src/quack_rl/cli/seats.py` rejects it (`tests/test_training_archived.py` checks this and the exports). Only in `archive/`: `archive/src/quack_rl/rl/finetune.py`, `archive/src/quack_rl/rl/runs.py`, `archive/src/quack_rl/rl/replay_dqn.py`, `archive/src/quack_rl/rl/policy_layout.py`, `archive/scripts/train.py` and the notebooks (`archive/notebooks/`). `PolicyBot` uses the encoder of the env (`observe`, `vectorize`, `action_mask`), so a new layout changes what a policy sees.

### Standard rule, plus extras

- Implement the standard rule once. A card or a special case adds an extra effect on top of it. Never write a base rule with an "if card X is active" value or a special order.
- Example 1: a ruby field gives its standard 1 ruby, and a card adds one more.
- Example 2: the rat tail bonus is one function that cards read, and a card changes the result with an additive adjustment.

### Known mistakes

- Colour count fixed for one layout. The colour count of the RL board map must come from the layout in use (`map_colours` in `src/quack_rl/rl/encode.py`). A count fixed for one layout is wrong for another layout. Search for every place that counts or lists colours before you add one.
- Bounds from the ruleset value. A per-round effect (card 4: explosion limit +2) can push an observation entry past the ruleset value, and the env then leaves its observation space. Take the bounds from the largest value any round can reach (`_max_limit` in `rl/encode.py`), and run a masked random game against the env's observation space.
- Hidden information leaks. A hand that is hidden must not appear in the opponent's view: not in the observation (also not as a drop in the opponent's bag counts or values derived from them: the hand counts as in the bag), not in the render, not in the record shown to the other side. Test the opponent's view explicitly whenever a change adds state.
- Formatter side effects. `ruff --fix` and `ruff format` touch unrelated files. Run them, look at the diff, and restore the files that are not part of your change.
- Wrong type in a ruleset file. A TOML integer against a `str` field fails validation (and the other way round). Check the type of every new field against the model and load the file in a test.
- Untyped spec. A spec that says "Spellbook 1" without naming the key type leaves the engineer to guess. Name the types of keys and values in the spec.
- A new phase changes every layout. The RL phase one-hot (`PHASES` in `src/quack_rl/rl/encode.py`) is built from the `Phase` enum, so a new phase adds a `phase.<name>` entry to the layout. Regenerate the stored layout 10 sample on purpose (`tests/fixtures/make_golden.py layout10`) and check that every old name keeps its value.
- Steps that do not apply. A step list rarely fits one change. Read each step as "if your change touches X", and skip the rest on purpose, not by forgetting.

## 2. Recipes

- [A new ruleset version that adds a field or a phase](new-ruleset-version.md): from the spec to the pinned defaults, step by step, with the checks.
- [Adding or changing a colour](colour-change.md): the three cases (spellbook effect, place hook, a step added to a phase), five steps in order, the pitfalls and the tests to run.
- [Changing the shop](shop-change.md): remove an item, add an item or change a price; which parts each one touches, eight steps in order, the pitfalls and the tests to run.

## 3. Project map

The map is in [project-map.md](project-map.md). It explains how the parts work together in the order a rule change travels, where each lives, and which parts a change often does not touch.
