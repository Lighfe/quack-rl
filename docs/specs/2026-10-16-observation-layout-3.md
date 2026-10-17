# Observation layout 3 (rules v1.8)

Status: built in issue #104. Prior spec: `docs/specs/2026-10-12-m2-5-observation-layout-2.md`.

## Which layout belongs to which ruleset

`observation_layout(rs)` in `src/quack_rl/rl/encode.py`: layout 3 for a ruleset with `explosion_choice = true` (v1.8), layout 2 for the others (v1, v1.1). `OBSERVATION_LAYOUT` stays 2 (the layout of v1 and v1.1). The observation of v1 and v1.1 does not change; a stored sample (`tests/fixtures/layout2/sample.npz`, made before layout 3) pins it, vector and mask.

## Vector of layout 3

Layout 2 (`vector_names(rs)` of the spec above), with two changes, in this order:

1. The phase one-hot has five entries, in the order of the engine `Phase` enum: `phase.brew`, `phase.resolve`, `phase.choice`, `phase.shop`, `phase.game_over`. (Layout 2 has four: no `phase.choice`.)
2. After the derived entries of layout 2 (ending in `point_delta`) and before the map block, two entries are added:
   - `own.field_points`: `points[scoring field]` of the ruleset for the own seat (the points a potion that does not explode, or `take_points`, gives)
   - `last_round`: 1 in the last round (`round == rounds`), else 0

The own points are already in layout 2 as `own.points` (and `opponent.points`, `point_delta`); layout 3 keeps them. The map block stays last, so `map_slice` is unchanged in meaning.

Length for v1.8: 851 entries (v1.1 has 848: 1 phase entry and 2 derived entries more). A test checks the order: the five phase names, the derived block of layout 2 followed by `own.field_points` and `last_round`, then the map.

`own.money_if_stop` for v1.8: no halving after an explosion (the player chooses), and 0 in the last round (the money becomes points at once).

## Action space and mask

The action list of a v1.8 environment is `wait, draw, stop, done, take_money, take_points, buy:...` (the order of `action_names`): exactly two new actions compared with v1.1. The three point items of the v1.1 shop are removed in v1.8 (ruleset), so the list is two longer in the non-shop part but one shorter in total (14 against 15). The mask is `legal_actions`: in `choice` an exploded seat has exactly `take_money` and `take_points` legal, any other seat only `wait`. In the other phases the two actions are never legal.

## Loading a run

`config.json` of a run holds `layout` and `vector_names`. `runs.load_model` (and so `PolicyBot.from_run`) and `check_resumable` compare the layout with `observation_layout(rules)`; another layout raises `LayoutMismatch` with a message that names both layouts (the run's and the rules'). A run made on v1.1 (layout 2) does not load with rules v1.8, and the other way round.
