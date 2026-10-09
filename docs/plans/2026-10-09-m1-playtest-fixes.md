# M1 Playtest Fixes Implementation Plan

> **Execution:** this plan is executed by the agent-graph-kit loop (`docs/process.md`). Each task below becomes one GitHub issue in `docs/task-template.md` format, a sub-issue of the stage issue. Do not use the superpowers skills subagent-driven-development or executing-plans (`AGENTS.md`).

**Goal:** Fix the scoring rule found in the first playtest, add the last-round multiplier and the `--rounds` flag, improve the board display, and clean up stale documents.

**Architecture:** Small changes inside the M1 engine, record header and CLI. The scoring field is derived from the landing field (`final_field` stays the stored value). Rules stay version `v1`.

**Tech Stack:** as M1 (Python 3.12, uv, pydantic, Typer, Rich, pytest, Hypothesis).

**Spec:** `docs/specs/2026-10-09-m1-playtest-fixes.md` (rules: `docs/rules/rules-v1.md`)

## Global Constraints

- Same constraints as `docs/plans/2026-10-08-m1-terminal-game.md` (all numbers in `src/quack_rl/rules/v1.toml`, engine does no I/O, test command `uv run --with pytest pytest`, ruff and pyright clean)
- Rules version stays `v1`. No versioning until real data exists
- Golden test records are regenerated (`tests/fixtures/make_golden.py`) in every task that changes game outcomes
- `data/` is gitignored; the owner's test record is not part of the repo

## Review Focus

- A last chip on field 53 scores field 53 (money 35); landings on 52 and 53 tie (task 2)
- A landing on 51 scores field 52, a ruby field (task 2)
- Both potions explode in the last round: each gets halved money, then x1.5, nobody rolls (task 3)
- `--rounds 1`: the only round is the last round, the multiplier applies, the game ends after its shop (task 4)
- `verify` and `replay` of a record with `rounds` 4 in the header work; a header with no `rounds` is refused with a clear message, no crash (task 4)

---

## Task order and blockers

1. #15 Ruleset value-range and kind-consistency validation (existing issue)
2. Scoring field (blocks 3 and 5)
3. Last-round money multiplier (blocked by 2)
4. `--rounds` flag (blocked by 3)
5. Board display: scoring field, ruby indicator, bonus die line (blocked by 2)
6. Doc drift cleanup (no blocker)

### Task 2: Scoring field

Issue title: `M1.13 Scoring field: money and ruby from the first free field`

- Rules: update `docs/rules/rules-v1.md` 4.2, 4.3, 5 to the spec section 1
- Engine: `src/quack_rl/engine/resolve.py` (ruby, bonus die "furthest", money), `src/quack_rl/engine/shop.py` (tie-break) use `scoring_field = min(final_field + 1, track_end)`; `track_end` comes from the ruleset
- Tests first (`tests/test_resolve.py`, `tests/test_shop_end.py`): landing 1 -> money 2; landing 4 -> scoring 5 (ruby); landing 51 -> scoring 52 (ruby, money 33); landing 53 -> scoring 53, money 35; landings 52 and 53 tie for the bonus die; tie-break after the last round compares scoring fields; an exploded potion gets halved money of the scoring field
- Regenerate golden records; update tests that hard-code old money values

### Task 3: Last-round money multiplier

Issue title: `M1.14 Last-round money multiplier x1.5`

- Ruleset: add `last_round_money_percent = 150` to `v1.toml` and the model (integer, at least 100)
- Resolve: in the last round (`state.round == rs.rounds`) money = `(field money, halved if exploded, plus die money) * percent // 100`
- Tests first: last round non-exploded; last round exploded (halve, then x1.5); last round with the +1 money die; a round before the last is unchanged; both explode in the last round
- Regenerate golden records

### Task 4: `--rounds` flag

Issue title: `M1.15 Number of rounds as a flag, stored in the record`

- `play` and `simulate` get `--rounds N` (default 9, at least 1, else a clear error and exit code 1). The ruleset is loaded with `rounds` overridden
- The record header gets `rounds` (schema in `src/quack_rl/record/schema.py`). `verify` and `replay` build the ruleset from the header. A header with no `rounds` is refused with a clear message
- Tests first: `simulate --rounds 4` writes records that `verify --seed-check` accepts; `--rounds 0` is refused; `--rounds 1` plays one round with the multiplier; `play --rounds 2` works with scripted keys; a header with no `rounds` is refused
- README: mention the flag

### Task 5: Board display

Issue title: `M1.16 Board shows scoring field, ruby check and bonus die result`

- `src/quack_rl/cli/render.py`: replace "next ruby" with the scoring field, its money, and whether stopping now gives a ruby (`ruby: yes` or `ruby: no`). Keep the board within 80 columns
- The bonus die result is its own clear line in the resolve output (`render_step` or the play output), for example `bonus die p1: +1 money`
- Tests first (`tests/test_cli_play.py`): ruby shown for a landing on 4, not for a landing on 3; die line present in the resolve output; board width at most 80

### Task 6: Doc drift cleanup

Issue title: `Remove stale references from AGENTS.md and the role documents`

- Fix only wrong references, change no process rule: `AGENTS.md` line about the `.claude/skills` symlink (say it is created with the first project skill); `docs/process.md` references to `.claude/hooks/`, `docs/specs/agent-graph-kit.md`, `.claude/agents/planner.md` and `docs/research/`; `docs/team/orchestrator.md` and `docs/team/pm.md` references to `docs/specs/agent-graph-kit.md`; `docs/team/pm.md` and `docs/team/planner.md` references to the README subsection "Auto mode allow entries"; the "2 to 6 minutes" figure in `docs/team/software-engineer.md`
- Where a reference points to something that now lives in the plugin, name the plugin (agent-graph-kit) instead
- Check with `grep` that each removed path is no longer referenced
