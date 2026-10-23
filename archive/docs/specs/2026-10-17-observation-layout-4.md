# Observation layout 4 (rules v1.9)

Status: built in issue #119. Based on `docs/specs/2026-10-17-ruleset-v1-9.md`. Prior spec: `docs/specs/2026-10-16-observation-layout-3.md`.

## Which layout belongs to which ruleset

`observation_layout(rs)` in `src/quack_rl/rl/encode.py`: layout 4 for a ruleset where a chip draws a hand (`has_hand(rs)`, v1.9), layout 3 for `explosion_choice = true` without a hand (v1.8), layout 2 for the others (v1, v1.1). The vectors of layouts 2 and 3 do not change; the stored layout 2 sample and `tests/test_rl_layout3.py` pin them.

## Vector of layout 4

Layout 3 (phase one-hot with `choice`, derived block ending in `own.field_points` and `last_round`, map last), with these changes:

1. **Five colours.** The colour flags (`own.chip_colours.<c>`, `map.<f>.<who>.colour.<c>`) cover `white, orange, green, blue, red` in the order of first appearance in the ruleset (layouts 2 and 3: four). The map block has 16 channels per field instead of 12 (`map_channels(rs)`; `MAP_CHANNELS` stays 12 for layouts 2 and 3). `map_slice(rs)` uses it.
2. **Chip ids.** `bag.remaining.<id>` and `bag.owned.<id>` follow the chips of v1.9, so `orange_6` and `red_1`, `red_2`, `red_4` are new entries.
3. **Own hand block**, after the derived entries and before the map block, 29 entries:
   - for each hand slot `i` in 0..3: `own.hand.<i>.present` (1 when the slot holds a chip), `own.hand.<i>.value` (the chip value), `own.hand.<i>.colour.<c>` (one flag per colour); all 0 for an empty slot
   - `own.hand_size`: chips in the hand (0 to 4)

   The slot order is the order of the hand, so `play:<i>` plays the chip that slot `i` shows. Only the own hand is in the vector. The opponent's hand is not, as in the observation dict (`observe(...)["own"]["hand"]` only). The opponent's remaining bag is public as in layout 2; chips in a hand are out of the bag, so its count is lower while a hand is held.

Length for v1.9: 1006 entries. `observation_bounds` gives finite bounds for the hand block (flags 1, value up to the largest chip value, size up to 4).

## Action space and mask

`action_names(rs)` for v1.9: `wait, draw, stop, done, take_money, take_points`, then the shop actions `buy:<item id>` in the ruleset order, then the pick actions `play:0, play:1, play:2, play:3, put_back_draw, put_back_stop` (23 actions). Compared with v1.8:

- the shop items change: `buy:orange_1, buy:orange_6, buy:green_*, buy:blue_*, buy:red_*`; `buy:remove_white_1` is gone, so the indices of all `buy` actions differ from v1.8
- the six pick actions are new and last, so they are the same indices at the end of the list

The mask is `legal_actions`. In a pick step a seat with a hand has exactly `play:i` for each hand slot `i` plus `put_back_draw` and `put_back_stop`; Draw and Stop are not legal then. Pick actions are never legal for a seat without a hand. The other seat in the same step keeps `draw` and `stop`.

## Loading a run and the refusal

No policy is trained on layout 4. `check_policy_layout(rs)` raises `LayoutRefused` (a `ValueError`) whose message names layout 4 for v1.9. It is called at the start of `PolicyBot` (the constructor and `from_run`), `train`, `train_selfplay`, `finetune_online`, `train_offline_run` and `evaluate`. `evaluate(..., reads_observation=False)` skips the check for a baseline that only reads the mask (`random_policy`); this runs the heuristic bots as opponents on v1.9. Runs of v1.1 and v1.8 do not load with v1.9: `runs.load_model` raises `LayoutMismatch` on the layout number.
