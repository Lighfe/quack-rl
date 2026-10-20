# Project map

How the parts of the game fit together, in the order a rule change travels, and where each part lives. Paths are relative to the repo root; `src/quack_rl/` is shortened to `qr/`. Read each part as "if my change touches this". The last section lists what a change often leaves alone.

## The path of a change

A rule change starts in the rules (a value or a switch), may need new chip behaviour (components), is carried out by the engine, and must then be seen by everything that reads or writes game state: record, bots, CLI, RL, notebooks and docs. Two links tie the parts together:

- A ruleset names a spellbook, the spellbook names a component for each colour, and the engine asks the component what a chip does. So a colour effect lives in a component, not in the engine.
- The engine knows nothing about RL. RL code reads the state and the ruleset and turns them into a vector and an action mask. A new state field or action therefore reaches RL only when someone adds it to the encoder.

## 1. Rules

Where: `qr/rules/` and `docs/rules/`.

- Ruleset files `qr/rules/<version>.toml`: the values (rounds, track, money, points, chips, shop, die, start bag) and the switches. One file per version; a recorded version is never edited.
- Model `qr/rules/model.py`: the pydantic types `Ruleset`, `ChipSpec`, `ShopItem`, `DieFace`, `CardSpec`, and the validation that ties them (unknown ids, the table lengths, the chip-to-component rule). A new switch is a new field here with a default that keeps older versions playing as before. Types must match the TOML (an integer in the file against a `str` field fails).
- Loader `qr/rules/load.py`: `SUPPORTED_RULES_VERSIONS` (a version missing here cannot be loaded), `load_ruleset`, `with_rounds`, and `apply_overrides`, which sets single values by dotted path and parses by the type of the current value.
- Spellbook `qr/rules/spellbook.py`: a registry from a spellbook name to a colour-to-component map. White and orange are fixed in every spellbook. A ruleset with a `spellbook` field leaves `component` out of its chips; a ruleset without one names a component on each chip.
- Card effects `qr/rules/cards.py` (v1.11): a registry of card effect names (`register_card_effect`, `get_card_effect`). A ruleset `cards` entry (`CardSpec`: `id`, `effect`, `count`) must name a registered effect; the model refuses an unknown one. The registry sits in `rules/` and not in `components/` because `components` imports `rules` (no import cycle). The engine does not play the cards yet.
- Exports `qr/rules/__init__.py`: the names other packages import (`load_ruleset`, `Ruleset`, `get_spellbook`, the spellbook functions and so on). A new public name needs an entry here, in the import and in `__all__`.
- Rules in words `docs/rules/rules-<version>.md`: it must agree with the TOML file; a test compares tables in it with the file.

Usually changes: the TOML file, `model.py` for a new field, `SUPPORTED_RULES_VERSIONS`, the rules document. A new colour also touches the spellbook.

## 2. Components (chips and hooks)

Where: `qr/components/`.

- `base.py` defines `Component` with the hooks. Each has a default that does nothing: `place_bonus(chip, previous, pot)` extra fields when a chip is placed (`pot` holds the chips already placed this round), `explosion_weight(chip)` amount added to the white total, `hand_size(chip)` chips drawn into a hand when the chip is placed, `round_end_droplet_halves(chip, position_from_end)` droplet half steps at round end, `pot_round_end(pot, other_pot)` points and droplet half steps from the whole pot (called after green, in the order of `round_end_order`: a lower number first, so a new round-end effect sets it), `puts_back_previous(chip, previous)` whether the placed chip sends the previous chip back into the bag, and `features(chip)` descriptive numbers for encodings.
- `chips.py` holds one class per component, registered under a name such as `blue@2` with the `@register` decorator. `registry.py` keeps the registry and `get_component`.
- A change of what a colour does is a new component class plus a spellbook (or a chip `component`) that names it; the existing class stays for the versions that use it. A new hook means a new method in `Component` and a call site in the engine; every place that already calls the hooks must then pass the new argument or accept its default. Callers outside the engine are `qr/report.py` (odds), `qr/bots/heuristic.py` (look-ahead) and `qr/rl/encode.py` (bounds), so check them too. The pot-wide round-end effects go through one function, `pot_effects` in `qr/components/pot.py`, which the engine (`resolve.py`) and the report both call, so they share the order and the inputs; a new round-end hook should be called through such a shared function, not copied. The report's odds (`_brew_outcomes`) pass `puts_back_previous` and `pot_effects` the engine's inputs, with an empty other pot (the odds are for one player), and track the whole pot only when a chip of the bag has such a hook. The heuristic bot's look-ahead is `_total_after` (the white total after a placement, put-back included); a new hook that changes the explosion total belongs there.

## 3. Engine

Where: `qr/engine/`. The engine is a pure function: `step(state, rules, joint actions, chance source)` returns the next state, the events and the chance outcomes.

- `state.py`: `Phase`, `Status`, `PlayerState`, `GameState`, and `state_to_dict` / `state_from_dict`. A new per-player field goes into `PlayerState` with a default, and it must survive the dict round trip.
- `actions.py`: the action names, `action_names(rules)` (the full action list; its order is the order of the RL action mask; shop items of the sixth and later colour are listed after the pick actions, so the indices of v1.9 stay), and `legal_actions` per phase.
- `game.py`: `step` and the routing from phase to handler; a joint action has exactly one action per seat, and phases without decisions take none.
- Handlers per phase: `brew.py` (draw, place, stop, explosion, the hand and pick step), `resolve.py` (round end: money, rubies, die, droplets, points), `choice.py` (the explosion choice), `shop.py` (buying). Which shop items are legal is decided in `actions.py` (`_can_buy`: price, `min_round`, chip limits); the shop handler trusts it.
- `chance.py`: every random event goes through the chance source and is logged, so a game can be replayed. New randomness must use it: add a method to the `ChanceSource` protocol, to `RngChance`, `ScriptedChance`, `ChanceLog` and to `RecordedChance` in `qr/record/replay.py` (the card draw, `draw_card`, is an example; its log entry has the seat `"table"`).
- `cards.py` (v1.11): the round-start card. `Phase.CARD` is a step without actions at the start of every round of a ruleset with `cards` (`new_game` and the round reset in `shop.py` set it; a ruleset without cards goes straight to BREW and draws nothing). `apply_card` draws one card from `state.deck` (card ids, one entry per copy) and resolves the immediate effects (card 3 drop, card 7 green chip). Effects that act later are read through `card_effect(state, rs)`: card 1 in `resolve.py`, card 4 through `explosion_limit(state, rs)`, which every reader of the limit must call instead of `rs.explosion_limit` (brew, heuristic bot, `rl/derive.py`, `rl/encode.py` observe, `cli/render.py`; `report.py` takes the limits from `_round_limits`, the ruleset limit and the card 4 limit weighted by the deck share). Cards 5 and 6 open `Phase.CARD_CHOICE` (a joint choice, `apply_card_choice`); card 2 opens `Phase.RESTART` from the end of `apply_brew` (`restart_pending` seats choose `continue` or `restart`, the other seat waits; `apply_restart`). The card actions (`continue`, `restart`, `card_drop_2`, `card_purple`, `card_black`, `card_chip:<id>`, `card_drop_end`) are appended at the end of `action_names`. The card phases are not in the one-hot phase list of the RL layouts 2 to 5 (`_CARD_PHASES` in `rl/encode.py`); layout 6 has all phases in its one-hot list.
- `__init__.py`: the exports (action names, constants, helpers). A new public name goes here.

Usually changes: `actions.py` and `state.py` for a new action or state, the handler of the phase, `game.py` for a new phase, the exports.

## 4. Record and replay

Where: `qr/record/`.

A game is written as JSON Lines: a header (rules version, overrides, seed, seats), one line per step (legal actions, actions, chance outcomes, events), and a footer. The format is generic: new action names and event kinds need no schema change. `schema.py` has the line types, `writer.py` and `reader.py` write and read, `store.py` decides where record files are placed on disk, and `replay.py` rebuilds a game from its recorded chance and checks it (`verify_game`, `verify_seed`). Change this part only when the line format itself changes; otherwise add a test that a game with the new actions writes, reads and replays to the same final state.

## 5. Bots, simulation and tournament

Where: `qr/bots/`, `qr/runner.py`, `qr/simgame.py`, `qr/tournament.py`, `qr/report.py`.

- `bots/heuristic.py`: the heuristic bot (draw limit, stop round, shop strategy). It must answer every action the engine can offer, so a new action or phase needs a branch here. It reads the component hooks for its look-ahead, and the card phases have branches: `CARD_CHOICE` takes the drop, `RESTART` uses a small rule (`RESTART_BELOW`). `bots/strategy.py` holds the shop strategies as lists of shop item ids; an id removed from a shop must go from the strategies that name it. `bots/random_bot.py` picks among legal actions and needs no change.
- `runner.py`: plays a game with seats, writes the record. `simgame.py` plays one bot-vs-bot game and collects statistics (draws, buys and explosions from event kinds; money from the money events; points and droplet position per round from the state at round end, so a new event that changes points or droplet needs no line there, but a new event that changes money may). `tournament.py` plays all pairs of a field and writes a table of results per pair. Its columns come from the ruleset (`csv_columns`: one buy column per shop item; `seat_columns`: one bag column per chip), so a new shop item or chip adds columns with no code change.
- `report.py`: the balance report, which reads the result files and calls the component hooks for odds. Its calculated maximum follows only the card 4 limit (`_round_limits`); the other card effects are not in it, and the report says so. The result rows (draws, explosions) come from event counts, so a restart needs no code there.

## 6. CLI

Where: `qr/cli/`.

`main.py` has the commands (`play`, `simulate`, `tournament`, `replay`, `verify`) and the `--rules` option; its default is `v1.11`. `render.py` draws the board and the steps (a chip is its colour's first letter plus its value, `CHIP_LETTER` overrides it where two colours share a letter; every colour needs an entry in `CHIP_STYLE`; the round-end and put-back events print in the generic `kind=… key=value` form): a new value, chip colour or state shown to a player is added here, and a hidden hand must not be drawn for the other seat. `human.py` prompts a human for each phase: a new action needs a key (add it in `key_map`; a key must not clash with `BUY_KEYS`, which uses digits and letters, so the card options take digits only in `CARD_CHOICE`, where no buy key is legal) and a prompt line, and `BUY_KEYS` must have at least as many keys as the shop has items. `seats.py` turns a seat spec into a bot or a human.

## 7. RL: layout, action mask and environments

Where: `qr/rl/`.

- Layout and mask `rl/encode.py`: `observation_layout(rules)` picks the layout number from the ruleset; `observe` builds the readable view of one seat (no hidden information: the opponent's hand and bag order never appear); `vector_names`, `vectorize` and `observation_bounds` give the flat vector; `action_mask` follows `action_names`. Layouts: 2 (v1, v1.1), 3 (v1.8), 4 (v1.9), 5 (v1.10: eight colours, a shop block with `min_round` and `open` per item), 6 (v1.11: chosen by `rs.cards`, not by the version name; layout 5 plus the card phases and a card block: `card.<kind>`, `deck.<kind>`, `restart.available`, `round_end_halves` per seat); the colour count per layout is `LAYOUT_COLOURS` (layout 6 uses `CARD_COLOURS`, 8). The colour count of the board map comes from `map_colours` for the layout in use; a count fixed for one layout is wrong for another layout. A change that adds state or actions either extends a layout (a new layout number, a spec in `docs/specs/`, and a stored sample of the layouts before it in `tests/fixtures/layout2/`, made by `tests/fixtures/make_layout2_sample.py`; it holds v1, v1.1, v1.8, v1.9 and v1.10, so add the newest older version to its `VERSIONS` and the test `test_layout2_output_equals_stored_sample` before you change the encoder) or is refused for the policy paths.
- `rl/derive.py`: derived features for the generic rules (fields, money, rubies, limit, die, points); keyed by ruleset switches.
- Environments: `rl/parallel_env.py` (both seats act), `rl/single_env.py` (one seat against a bot), `rl/reward.py`. They build on the engine and the encoder.
- Entry points that accept or refuse a layout. Each one that runs a trained policy calls `check_policy_layout(rules)`, which raises `LayoutRefused` for a layout no policy exists for (layouts 4, 5 and 6; its message names the layout number): `rl/evaluate.py` (evaluate), `rl/policy_bot.py` (policy bot, also `from_run`), `rl/selfplay.py` (self-play), `rl/finetune.py` (fine-tune), `rl/offline.py` (offline), `rl/train.py` (train). When a layout gets policy support, remove the refusal in each of them and test each one; until then, test that each refuses. `rl/runs.py` stores the layout number in a run's config and rejects a run whose layout differs from the ruleset's. Evaluating baseline bots must keep working where a policy is refused.
- `rl/dataset.py`, `rl/replay_dqn.py` and the `scripts/` that train or build data read the observation size and the action count; they follow the layout.
- `rl/__init__.py`: the exports.

## 8. Notebooks, scripts, defaults

Where: `notebooks/`, `scripts/`, and `tests/test_rules_defaults.py`.

The default of every `rules` parameter, option and field in `src` and `scripts` is `v1.11`. The notebooks name one ruleset version (once, as `RULES`) and stay on it until the owner decides otherwise. `tests/test_rules_defaults.py` scans the source and the scripts and checks that each default is `v1.11` (it fails on a planted other default); the notebooks are checked for their pinned version. When a later version becomes the default, change all defaults and this test in one issue. Saved data (records, runs, datasets) belongs to the version it names and must still load.

## 9. Docs and specs

Where: `docs/rules/`, `docs/specs/`, `README.md`.

A rule change has a spec in `docs/specs/` (name the types of keys and values), the rules document, and a row in the milestone table of `docs/specs/2026-10-08-quack-rl-design.md`. The README describes the observation layout, the CLI and the scripts; update it where the change alters what it says.

## 10. Tests

Where: `tests/`. Tests per version are named after the version (`test_ruleset_v1_9.py`, `test_engine_v1_9.py`, `test_record_v1_9.py`, `test_cli_v1_9.py`, `test_cli_v1_10.py`, `test_rl_layout4.py`, `test_rl_layout5.py`). Several tests loop over all versions and need the new one added: `test_ruleset.py` (supported versions), `test_bots.py`, `test_tournament.py`, `test_rl_parallel_env.py` (`VERSIONS`), `test_rules_defaults.py`. Test the view of the other seat whenever state is added. Tests of recorded versions stay unchanged and must still pass.

## What a change often does not touch

- The record schema, writer and reader: the format is generic.
- `rl/runs.py`, `rl/derive.py`, `rl/reward.py` and `bots/random_bot.py`: they read the layout number or the legal actions, not single rules.
- `simgame.py` and `tournament.py`: they run any version that loads, unless a new event changes money or points.
- The engine, when the change is only a value in a ruleset file or a different spellbook.
- Record, bots, CLI and RL, when the change adds no action, phase, event or state field.
- Notebooks: they stay on their pinned version.
- The layout and the policy entry points, when the change is not visible in the observation and adds no action.
