# Observation layout 6 (rules v1.11)

Status: built in issue #147. Based on `docs/specs/2026-10-19-ruleset-v1-11.md`, section "RL environments". Prior spec: `docs/specs/2026-10-19-observation-layout-5.md`.

## Which layout belongs to which ruleset

`observation_layout(rs)` in `src/quack_rl/rl/encode.py`: layout 6 for a ruleset with `cards` (a non-empty card list); the version name is not read. Without cards the old rule holds: layout 5 (hand and more than five colours or a minimum buy round, v1.10), 4 (hand, v1.9), 3 (`explosion_choice`, v1.8), 2 (v1, v1.1). The vectors of layouts 2 to 5 do not change: the stored sample `tests/fixtures/layout2/sample.npz` (script `tests/fixtures/make_layout2_sample.py`) pins v1, v1.1, v1.8, v1.9 and v1.10 exactly; v1.10 was added to it in its own commit before the encoder change.

The colour count of the map comes from the layout: `CARD_COLOURS` in `encode.py` is 8 (layout 6 keeps the colours of layout 5; `LAYOUT_COLOURS` for layouts 2 to 5 is unchanged).

## Vector of layout 6

Layout 5 with these changes:

1. **Phases.** The one-hot phase list holds every phase: `card`, `card_choice`, `restart`, `brew`, `resolve`, `choice`, `shop`, `game_over` (8 entries, 3 more than layout 5).
2. **Card block**, after the shop block and before the map block. With `K` card kinds (one kind per distinct card effect name of the ruleset, in the order of the ruleset; v1.11 has `K = 8`: `ruby_double`, `restart_after_5`, `drop_all_1`, `explosion_limit_plus_2`, `choice_black_or_value2_or_drop`, `choice_drop2_or_purple`, `fewest_points_green`, `no_effect`), it has `2K + 3` entries (19 for v1.11):
   - `card.<kind>` (K entries, 0 or 1): the card of the round. All 0 before the first draw. A card without an effect is the kind `no_effect`, so it is told apart from "no card drawn yet".
   - `deck.<kind>` (K entries): the cards left in the deck, as counts per kind (bounds: 0 to the number of cards of that kind in the ruleset). Open information.
   - `restart.available` (0 or 1): the restart is available to this seat: the card of the round is the restart card and the seat is brewing and has not been offered the restart yet, or has the offer open now. 0 after the offer was answered.
   - `own.round_end_halves`, `opponent.round_end_halves`: the drop (in half steps) that a resolved card 5 choice adds at round end. It is open information after the choice has resolved (the card choice phase is over); it is 0 for both seats during the choice, because a joint choice is not stored in the state before it resolves.
3. **Explosion limit of the round.** The existing entry `explosion_limit` already holds the limit of the round (`explosion_limit(state, rs)`: 9 with card 4, else 7), and `own/opponent.limit_distance` follow it. Its bounds are now 1 to the largest limit of a round (`_max_limit`: the ruleset limit plus 2 when the ruleset has the limit card), not the ruleset limit alone.

Resolved choices are also visible in what the vector already holds: a chip taken by a choice is in the bag counts of that seat (bags are public), and a drop is in `droplet_halves`.

## Hidden information

The pending choice of the opponent is not in the observation: neither the card choice (a joint action, not stored before it resolves) nor the restart answer. `restart.available` is for the own seat only; there is no `opponent.restart*` entry. The test `test_pending_choice_of_the_opponent_is_not_in_the_view` checks the view of the other seat.

## Action space and mask

`action_names(rs)` for v1.11 is the list of v1.10 (28 actions) with the card actions appended at the end, in this order: `continue, restart, card_drop_2, card_purple, card_black, card_chip:white_2, card_chip:green_2, card_chip:blue_2, card_chip:red_2, card_chip:yellow_2, card_drop_end` (39 actions). So the indices of every action of v1.10 are the same. The mask is `legal_actions` over the full list. `observation_bounds` covers the new values (see above).

## Environments and refusals

`QuackParallelEnv` and `QuackEnv` run on v1.11; `parallel_api_test` and `check_env` pass. Defaults are not changed here (issue #148).

No policy is trained on layout 6. `check_policy_layout(rs)` raises `LayoutRefused` for layouts 4, 5 and 6; the message names the layout number. Entry points that call it: `PolicyBot` (constructor and `from_run`), `train`, `train_selfplay`, `finetune_online`, `train_offline_run`, `evaluate` (not with `reads_observation=False`). `runs.load_model` and resume raise `LayoutMismatch` when the layout number of a run differs from the layout of its ruleset. Each refusal has a test in `tests/test_rl_layout6.py`.
