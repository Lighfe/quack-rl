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
- Defaults and notebooks stay pinned to a version. No default may be the newest version, and a notebook names its version once. Then nothing picks up a new version by accident. The defaults test guards this; extend it when you add a version.

### Known mistakes

- Colour count fixed for one layout. The colour count of the RL board map must come from the layout in use (`map_colours` in `src/quack_rl/rl/encode.py`). A count fixed for one layout is wrong for another layout. Search for every place that counts or lists colours before you add one.
- Hidden information leaks. A hand that is hidden must not appear in the opponent's view: not in the observation, not in the render, not in the record shown to the other side. Test the opponent's view explicitly whenever a change adds state.
- Formatter side effects. `ruff --fix` and `ruff format` touch unrelated files. Run them, look at the diff, and restore the files that are not part of your change.
- Wrong type in a ruleset file. A TOML integer against a `str` field fails validation (and the other way round). Check the type of every new field against the model and load the file in a test.
- Untyped spec. A spec that says "Spellbook 1" without naming the key type leaves the engineer to guess. Name the types of keys and values in the spec.
- Steps that do not apply. A step list rarely fits one change. Read each step as "if your change touches X", and skip the rest on purpose, not by forgetting.

## 2. Recipes

- [A new ruleset version that adds a field or a phase](new-ruleset-version.md): from the spec to the pinned defaults, step by step, with the checks.
- [Adding or changing a colour](colour-change.md): the three cases (spellbook effect, place hook, a step added to a phase), five steps in order, the pitfalls and the tests to run.
- [Changing the shop](shop-change.md): remove an item, add an item or change a price; which parts each one touches, eight steps in order, the pitfalls and the tests to run.

## 3. Project map

The map is in [project-map.md](project-map.md). It explains how the parts work together in the order a rule change travels, where each lives, and which parts a change often does not touch.
