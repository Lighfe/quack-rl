# Skill `quack_rule_changes` Implementation Plan

> This plan becomes issues (see `docs/process.md`, Intake). Do not run it with subagent-driven-development or executing-plans (see `AGENTS.md`).

**Goal:** Rename the skill `rule_changes` to `quack_rule_changes` and rebuild it as general advice, recipes and a project map.

**Architecture:** A skill folder in `.agents/skills/quack_rule_changes/` with `SKILL.md` and files next to it. No code changes.

**Spec:** `docs/specs/2026-10-18-quack-rule-changes-skill.md`

## Global Constraints

- Only skill, docs and `AGENTS.md` change. No file under `src/` or `tests/` changes.
- No issue numbers, no history wording, no file paths in recipes.
- Recipes and the map come from the git history and the code, not from guesses. The rule changes already made: v1.8 (points, explosion choice), spellbook (v1.9), v1.9 colours (blue hand and pick step, red, orange 6), v1.9 shop without "Remove one White 1".

## Tasks (each becomes one issue, in this order, each blocked by the one before)

1. Rename the skill, set up its three parts, write the general advice.
2. Project map.
3. Recipe: new ruleset version with a new field or phase.
4. Recipe: add or change a colour (existing issue #109, rewritten).
5. Recipe: change the shop.
