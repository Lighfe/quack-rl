# Observation layout 5 (rules v1.10)

Status: built in issue #137. Based on `docs/specs/2026-10-18-ruleset-v1-10.md`, section "RL environments". Prior spec: `docs/specs/2026-10-17-observation-layout-4.md`.

## Which layout belongs to which ruleset

`observation_layout(rs)` in `src/quack_rl/rl/encode.py`: layout 5 for a ruleset with a hand and either more chip colours than the five of layout 4 or a shop item with `min_round > 1` (v1.10); layout 4 for the others with a hand (v1.9); layout 3 for `explosion_choice` without a hand (v1.8); layout 2 for v1 and v1.1. The vectors of layouts 2, 3 and 4 do not change: the stored sample `tests/fixtures/layout2/sample.npz` (script `tests/fixtures/make_layout2_sample.py`, made before the layout 5 change) pins v1, v1.1, v1.8 and v1.9 exactly.

The colour count of the map comes from the layout: `LAYOUT_COLOURS` in `encode.py` (layouts 2 and 3: 4, layout 4: 5, layout 5: 8).

## Vector of layout 5

Layout 4 with these changes:

1. **Eight colours.** The colour flags (`own.chip_colours.<c>`, `opponent.chip_colours.<c>`, `map.<f>.<who>.colour.<c>`, `own.hand.<i>.colour.<c>`) cover `white, orange, green, blue, red, black, yellow, purple` in the order of first appearance in the ruleset. The map block has 2 + 2 * (8 + 2) = 22 channels per field (`map_channels(rs)`).
2. **Chip ids.** `bag.remaining.<id>` and `bag.owned.<id>` follow the chips of v1.10: `black_1`, `yellow_1`, `yellow_2`, `yellow_4`, `purple_1` are new entries.
3. **Shop block**, after the hand block and before the map block, 2 entries per shop item in the ruleset order:
   - `shop.<item id>.min_round`: the minimum buy round of the item (constant per ruleset, 1 to `rounds`)
   - `shop.<item id>.open`: 1 when the current round is at least the minimum round, else 0

The shop block holds only public rule data and the round, so it adds no hidden information. The other player's hand is not in the vector, as in layout 4.

`observation_bounds` gives finite bounds for the shop block (`min_round` 1 to `rounds`, `open` 0 or 1).

## Action space and mask

`action_names(rs)` for v1.10: `wait, draw, stop, done, take_money, take_points`, then `buy:<item id>` for the shop items of the first five colours (and the non-chip items) in the ruleset order, then `play:0 .. play:3, put_back_draw, put_back_stop`, then the new shop items `buy:black_1, buy:yellow_1, buy:yellow_2, buy:yellow_4, buy:purple_1` appended at the end. So the indices of every action of v1.9 are the same in v1.10 (28 actions).

The rule in `src/quack_rl/engine/actions.py`: a chip shop item whose chip colour is the sixth or later colour of the ruleset is listed after the pick actions.

The mask is `legal_actions`. A shop item below its minimum round is not legal (engine `_can_buy`), so it is masked in a round before its minimum.

## Environments and refusals

`QuackEnv` and `QuackParallelEnv` run on v1.10 (`rules="v1.10"`); `parallel_api_test` and `check_env` pass. Defaults are not changed here (issue #138).

No policy is trained on layout 5. `check_policy_layout(rs)` raises `LayoutRefused` (a `ValueError`) for layout 4 and layout 5; the message names the layout number and says to name an older rules version. Entry points that call it: `PolicyBot` (constructor and `from_run`), `train`, `train_selfplay`, `finetune_online`, `train_offline_run`, `evaluate` (not with `reads_observation=False`). `runs.load_model` raises `LayoutMismatch` when the layout of a run differs from the layout of its ruleset.
