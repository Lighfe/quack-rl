# Skill `quack_rule_changes`

## Intent

The project skill `rule_changes` grew from one rule change (v1.8). It is a file list and three rules. The owner wants shared senior knowledge instead: what a person who changed the rules of this game several times would tell a new engineer. The skill is renamed `quack_rule_changes` and rebuilt in three parts, grown step by step from changes that were really made.

## Parts of the skill

1. **General advice.** Senior knowledge that holds for any rule change. Versioning is the first point: never edit a ruleset version that has recorded games; a change is a new version; new behaviour is switched by ruleset fields with old-safe defaults; defaults and notebooks stay pinned. Common mistakes follow (see "Known mistakes"). Other points are added when someone has them. The part may stay short.
2. **Recipes.** Short how-tos for typical changes of this game: what to think about, in what order, what goes wrong, how to check. They name no file paths, so they do not go stale when files move. They are written from changes already made, not from guesses. The first recipes: new ruleset version with a new field or phase, add or change a colour, change the shop.
3. **Project map.** How the game parts interact (rules, components, engine, record and replay, bots, CLI, RL layout and environments, notebooks, docs) and where each one lives. This is the only part that names files and folders. Recipes point to it.

## Where it lives

- `SKILL.md` stays short: a short intro, the general advice, a list of recipes, a pointer to the map.
- Each recipe and the map may be a file next to `SKILL.md` (for example `recipes/<name>.md`, `project-map.md`); the engineer decides the layout, as long as `SKILL.md` links every file.
- The skill folder moves to `.agents/skills/quack_rule_changes/`. The symlink `.claude/skills/quack_rule_changes` points to `../../.agents/skills/quack_rule_changes`. The old folder and symlink are gone.
- The `description` keeps the trigger: load when a game rule, ruleset version, colour or shop item changes. Not for RL training or notebook edits alone.

## Known mistakes (input for the general advice)

From the Skill notes of stage "M2.10":

- A hard-coded colour count (`MAP_COLOURS`) breaks when a colour is added.
- A hidden hand must not leak into the opponent's view.
- `ruff --fix` and `ruff format` touch unrelated files; restore them.
- A TOML integer against a `str` field fails validation; check the type of a new field.
- The spec says "Spellbook 1" without naming the key type: name types in the spec.
- Steps often do not apply to one issue; a skill step list must say "if your change touches X".

## Goals

- A new engineer finds every place a rule change touches, including `components/`, the spellbook files, the `rules/__init__.py` exports and the RL entry points that accept or refuse a layout.
- Recipes read like advice from a colleague, not like a checklist of paths.
- Issue numbers and history wording stay out of the skill (as #112 did).

## Non-goals

- No general (project-free) version of the skill now. The owner postponed it.
- No independent review of the old skill. The owner skipped it.
- No dry run on a real rule change in this stage.
- No change to rules, engine, bots, CLI or RL code.

## Anti-goals

- A skill that lists paths in the recipes.
- A long skill that repeats code. Say where to look; do not copy code.

## Left to the engineer

The file layout inside the skill folder, the wording, and the order of points inside a part.
