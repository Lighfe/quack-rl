# Ruleset v2.1, layout 8 and a test of the RL environment: Implementation Plan

> **For agents:** this plan is turned into GitHub issues (see `docs/process.md`, Intake). Do not execute it with subagent-driven-development or executing-plans (`AGENTS.md`). Each task becomes one issue that carries its own interfaces and cases.

**Goal:** Ruleset v2.1 (field table, rubies, flask, 20 cards) and observation layout 8 replace v2 as the only ruleset, then the RL environment is tested end to end against bots, in self-play and offline.

**Architecture:** v2 is renamed to v2.1 first (v2 files archived), then the one engine is changed in place, task by task, with no flags and no older-ruleset branches. Cards are an additive layer on a standard round start order. Part 2 rebuilds a small training path (scripts plus a thin library) on the finished env.

**Tech Stack:** Python 3.12, pydantic ruleset model, TOML rulesets, Gymnasium and PettingZoo envs, pytest and hypothesis, `sb3-contrib` `MaskablePPO` and a small torch module for part 2.

**Spec:** `docs/specs/2026-10-23-ruleset-v2-1-design.md` (all card texts, the field table and the decisions are there).

## Global Constraints

- Test command: `uv run --with pytest pytest`; fast subset `-m "not slow"`.
- Use the skill `quack_rule_changes` for every rule change. Standard rule first, a card is an extra on top; no base rule branches on a card.
- No flag, optional field, shim or `None` branch for an older ruleset. After task 2 there is one ruleset, `v2.1`, and it is the default everywhere.
- Moved, not deleted: archived code and tests keep their path below `archive/`.
- Chance outcomes are recorded and replayable; hidden information (bag order, a pending choice) never enters an observation.
- Public repo: no secrets in commits, issues or notes.

## Review Focus

- A stale name after a removal (`money`/`points`/`rubies` lists, `ruby_double`, `no_effect`, `CARD_DROP_END`, `v2` as default): each task that removes a name greps for it in `src/`, `tests/`, `docs/`, `README.md` and the skill, and lists the result.
- A deck with fewer than 9 implemented cards (`rounds` draws without replacement): the model validates `len(deck) >= rounds`.
- A joint choice in which one player's reward changes the other's entitlement (card 19): choices first, then rewards.
- A choice that is offered with no effect (card 14 (B) without a white 1, card 19 (B) at entitlement 0, a refill of a full flask): not offered, and the action mask matches `legal_actions` at every step.
- A new chance outcome that replay cannot reproduce (cards 9, 10, 11, 18, 20): `verify --seed-check` passes on games that include each card.

## File map

- `src/quack_rl/rules/` (`model.py`, `load.py`, `v2.1.toml`, `cards.py`): ruleset model, field table, deck.
- `src/quack_rl/engine/` (`state.py`, `actions.py`, `cards.py`, `board.py`, `resolve.py`, `shop.py`, `brew.py`, `chance.py`): state, actions, phases, card effects.
- `src/quack_rl/bots/heuristic.py`, `src/quack_rl/cli/` (`human.py`, `render.py`, `main.py`), `src/quack_rl/record/`, `src/quack_rl/report.py`, `src/quack_rl/tournament.py`.
- `src/quack_rl/rl/` (`encode.py`, `derive.py`, `single_env.py`, `parallel_env.py`, new `policy_bot.py`, `evaluate.py`).
- `scripts/` (new `train_ppo.py`, `train_selfplay.py`, `train_offline.py`), `docs/analysis/` (results notes).

## Part 1: ruleset v2.1 and layout 8

### Task 1: Fix the stale rule-change recipes and write the design principle
Files: `.agents/skills/quack_rule_changes/` (`SKILL.md`, `colour-change.md`, `shop-change.md`). Replace the 14 and 7 cited test names that no longer exist with live ones; add the principle "standard rule, plus extras"; a grep of the cited test names against `tests/` shows every cited name exists.

### Task 2: Rename v2 to v2.1 and retire v2
Files: `src/quack_rl/rules/v2.toml` → archived, new `v2.1.toml` (same numbers, `version = "v2.1"`), `docs/rules/rules-v2.md` → `archive/docs/rules/`, new `docs/rules/rules-v2.1.md`, the v2 golden replay and v2-only tests archived or ported, `tests/test_rules_defaults.py`. Every default `rules` value and every `"v2"` string in code, tests, README and skill becomes `v2.1`; `--rules v2` is an error. Produces: `load_ruleset("v2.1")`.

### Task 3: One field table
Files: `rules/model.py`, `rules/load.py`, `v2.1.toml`, every reader of `rs.money`/`rs.points`/`rs.rubies`. Produces: `rs.fields: list[Field]` with `Field(money: int, points: int, ruby: bool)`, length `track_end + 1`; the real points table of the spec; `docs/rules/rules-v2.1.md` table; a test that compares the table in the rules text with the TOML.

### Task 4: Existing issue #178 (report baseline maximum on the point board)

### Task 5: Rubies as a currency
Files: `engine/state.py`, `engine/resolve.py`, `engine/shop.py`, `engine/actions.py`, ruleset fields `start_rubies = 1`, `ruby_cost = 2`. Produces: `PlayerState.rubies: int`; a scoring field with `ruby` gives 1 ruby, also after an explosion; the droplet +0.5 ruby step is gone; action `RUBY_DROP` ("spend 2 rubies for drop +1") offered in the shop while `rubies >= ruby_cost`, repeatable. Card 1 (`ruby_extra`): +1 ruby on a ruby field, on top.

### Task 6: The flask
Files: `engine/state.py`, `engine/actions.py`, `engine/brew.py`, `engine/shop.py`. Produces: `PlayerState.flask_full: bool` (starts `True`); `USE_FLASK` offered after a white chip is placed when the player has not exploded and the flask is full; it moves that chip back into the bag, restores field and white total to the values before the chip, and empties the flask; `REFILL_FLASK` in the shop for `ruby_cost` rubies, only when the flask is empty.

### Task 7: The round-6 white chip
Files: `rules/model.py`, `v2.1.toml`, `engine/cards.py` (card step). Produces: ruleset table `round_chips` (`round = 6`, `chip = "white_1"`); each player gets the chip into the bag before the card is drawn.

### Task 8: Card framework, the 20-card deck and the cards without a new decision
Files: `rules/cards.py`, `rules/v2.1.toml`, `engine/cards.py`, `engine/board.py`, `engine/state.py`. Produces: the deck of 20 ids `card_1` … `card_20` (one each; only implemented cards are listed, validated `len(deck) >= rounds`); an effect registry in which a card is an additive handler; `calculate_rat_tails(points: dict[str, int], rs) -> dict[str, int]` (the uncapped entitlement, base `rat_tail_bonus`); `PlayerState.rat_tail_adjust: int` subtracted by the bonus step, net bonus never below 0. Cards: 1 (extra ruby, from task 5), 2, 3, 4, 7 (migrated, renumbered), 5 (A black, B value-2, C 3 rubies; the drop-at-round-end option is removed), 6 (migrated), 9 (second die roll), 13, 15, 16, 18. The five `no_effect` cards are gone.

### Task 9: Cards with a choice: 8, 12, 14, 19
Files: `engine/cards.py`, `engine/actions.py`. Produces the legal actions and effects of the spec table; two passes for card 19 (choices first, rewards after); card 8 uses `calculate_rat_tails` and `rat_tail_adjust`.

### Task 10: Cards with a draw: 11 and 20
Files: `engine/cards.py`, `engine/chance.py`. Produces a chance draw of `n` chips from a bag (`ChanceLog.draw_chip` reused, recorded per draw), the permanent upgrade (next higher value of the colour, `1 → 2 → 4`), the green 1 fallback, the lowest-sum rule with ties.

### Task 11: Cards that act in the brew: 10 and 17
Files: `engine/brew.py`, `engine/cards.py`, `engine/actions.py`. Card 10: after a stop without explosion, draw up to 5, choose one, the others back into the bag first, then a normal placement. Card 17: action `USE_CARD_17` for the first white chip of the round, same mechanism as the flask, flask untouched, offered once.

### Task 12: Records, replay, verify and tournament cover everything new
Files: `record/`, `runner.py`, `simgame.py`, `tournament.py`, `report.py`. A hypothesis test plays full random games with each of the 20 cards forced as the card of a round and replays them; `quack-rl verify --seed-check` passes; the report and tournament run on v2.1.

### Task 13: The heuristic bots answer every new action
Files: `bots/heuristic.py`, `bots/strategy.py`. Simple rules, no balance goal: every new action has an answer, and a test plays bot against bot with all cards without an `IllegalAction`.

### Task 14: Low-effort CLI
Files: `cli/human.py`, `cli/render.py`, `cli/seats.py`, `cli/main.py`. Show rubies and the flask; offer the new actions with keys; ask the choices of cards 5, 8, 10, 11, 12, 14, 19; the `--p2` help text names the heuristic bot form. Nothing beyond that. A scripted-input test plays a short game.

### Task 15: Observation layout 8 and the envs; layout 7 is archived
Files: `rl/encode.py`, `rl/derive.py`, `rl/single_env.py`, `rl/parallel_env.py`, `archive/src/quack_rl/rl/`. Layout 8 as in the spec (look-ahead window `K = 10`, `field_gap`, `points_gap`, rubies, flask, no static field table, no `ruby_fields_ahead`); the action mask follows the new action list and equals `legal_actions` at every step; layout 7 code and tests move to the archive.

### Task 16: Guards and documents
New golden replay and a stored layout 8 sample for v2.1; README, `docs/specs/2026-10-08-quack-rl-design.md`, the skill project map and recipes, `docs/rules/rules-v2.1.md` match the engine; a grep of every removed name (listed in the issue) is empty outside `archive/` and `docs/archive/`.

## Part 2: test of the RL environment (each task is blocked by the one before the part, i.e. task 16)

### Task 17: RL against the random bot and a heuristic bot
Files: `pyproject.toml` (group `rl`: `sb3-contrib`, `torch`), `src/quack_rl/rl/policy_bot.py` (`PolicyBot(model).choose(state, seat, legal)`), `src/quack_rl/rl/evaluate.py` (`evaluate(bot, opponent, games, seed) -> EvalResult`), `scripts/train_ppo.py`, `tests/test_rl_train_smoke.py`, a results note. Inspiration: `archive/scripts/train.py`, `archive/src/quack_rl/rl/train.py`, `archive/src/quack_rl/rl/evaluate.py`, `archive/src/quack_rl/rl/policy_bot.py`.

### Task 18: Self-play
Files: `src/quack_rl/rl/selfplay.py`, `scripts/train_selfplay.py`, test, results note. Inspiration: `archive/src/quack_rl/rl/selfplay.py`, `archive/scripts/train_selfplay.py`.

### Task 19: Offline RL
Files: `src/quack_rl/rl/dataset.py`, `src/quack_rl/rl/offline.py`, `scripts/train_offline.py`, test, results note. Inspiration: `archive/src/quack_rl/rl/dataset.py`, `archive/src/quack_rl/rl/offline.py`, `archive/scripts/build_dataset.py`, `archive/scripts/train_offline.py`, `archive/notebooks/offline_rl.py`.

### Task 20: README section and verdict
`README.md` section "Testing the RL environment" with the three commands and the numbers; `docs/analysis/` verdict note: the env works, or the list of env bugs found with issues filed for them.

## Self-review

- Spec coverage: field table → 3; rubies → 5; flask → 6; round-6 chip → 7; 20 cards → 8, 9, 10, 11 (cards 1 to 20 each appear once; card 16 needs the flask from 6); rat tail function → 8; layout 8 → 15; engine/bots/CLI → 12, 13, 14; decisions list → in the tasks above; part 2 → 17 to 20; retirement → 2 and 15; skill principle → 1.
- Order: 8 creates the deck with 12 implemented cards, so `rounds = 9` draws stay valid; 9, 10, 11 add cards one group at a time, and the deck check keeps `len(deck) >= rounds`.
- Proportion: task bodies repeat the spec's table only by reference; the issue bodies restate what the engineer needs.
