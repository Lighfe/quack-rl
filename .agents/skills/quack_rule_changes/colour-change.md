# Recipe: adding or changing a colour

Use it when a chip colour is added, or when what a colour does or costs is changed: the chip, its effect, its price. The parts are named as in the [project map](project-map.md); this recipe names no location. A colour change is a rule change, so the general advice in [SKILL.md](SKILL.md) holds, and a colour that needs a new ruleset field or phase also follows the [new ruleset version recipe](new-ruleset-version.md).

Read each step as "if my change touches this". Skip a step on purpose, never by forgetting.

## The three cases

Find your case first. A colour can be more than one.

### Case A: the effect comes from the spellbook

The colour only needs a component that already exists, or a new component class that uses the hooks that exist. The ruleset names a spellbook, the spellbook maps each colour to a component, and the engine asks the component.

- A round-end effect that needs the whole pot or the other player's pot is a new hook, not `round_end_droplet_halves` (which sees one chip and its position). `pot_round_end(pot, other_pot)` returns points and droplet half steps; `puts_back_previous(chip, previous)` is the placement hook of yellow. Both default to "nothing", so older components stay unchanged.
- Touches: Rules (the ruleset file with the chips, the shop and the start bag; the spellbook with one entry per colour; the exports when a name is public), Components (one class per effect, registered under a name with a version suffix), and the rules document.
- Engine, record, bots, CLI and RL need no code when the component only uses existing hooks. They still need tests on the new colour.
- White and orange are fixed in every spellbook. A new colour needs an entry in every spellbook that a ruleset can name, or a new spellbook. An existing spellbook may get an entry for a colour that no ruleset uses yet. Never change an existing entry. A test that lists the colours of a spellbook is then updated on purpose (see `tests/test_spellbook.py`).

### Case B: the chip needs more of the pot or the board (the place hook)

The effect depends on what the player placed this round, or on another part of the state. Example: a red chip that moves extra by the number of orange chips already in the pot.

- Touches: Components (the hook gets the new input as an optional argument with a default that keeps old components working), Engine (the call site passes the input), and every other caller of the hooks outside the engine: the balance report, the heuristic bot's look-ahead and the RL bounds. They are listed in the Components part of the map.
- Pass the same input everywhere the hook is called. Call the hook through one shared function where possible (`pot_effects` for the pot-wide round-end hook). A caller that is missed computes odds, look-aheads or bounds from a different rule than the engine plays.
- Decide what counts: chips placed before this one only, not the bag, not chips placed later. Say it in the spec and test each of these.

### Case C: the colour adds a step to a phase (the blue hand and pick step)

The colour draws a hand, and the player must then pick. This is the largest case; it is a new action set and new state, so it also follows the new ruleset version recipe.

- Touches: Components (a hook that says how many chips go into the hand), Engine (the state field for the hand with a default, the legal actions while a hand exists, the pick handling inside the brew phase, the full action list), Record and replay (a test only), Bots (a branch for the pick step), CLI (draw the own hand, keys and prompt lines for the new actions, enough buy keys), RL (a new layout with a hand block, the mask).
- The new actions go at the end of the full action list, because its order is the order of the RL action mask. The new shop items of a new colour are not at the end of the shop rows: `action_names` lists the shop, then the pick actions, so items of a later colour need the rule in `_appended` (`engine/actions.py`) to land after the pick actions. The number of hand slots is the largest value of the colour's chips.
- The hand leaves the bag, so every stop rule and every odds computation must say what happens to it (put back, played, or drawn again).

## The order of thought

Work through these five steps in order. Each step needs the one before it.

### 1. Where the effect lives

- Think about: which hook carries the effect (placing, explosion weight, hand size, round end, or a hook that does not exist yet). Name the number of chips, fields and the order of effects inside a step. The effect belongs in a component, never in an engine branch on the colour name.
- Goes wrong: a check on the colour name in the engine; an effect that changes the white total or the fields in a different order than the rules document says; a component that is shared with an older ruleset and changes its behaviour.
- Check: component tests that call the hook directly with chips and pots, and engine tests with scripted draws that walk the effect.

### 2. How the ruleset switches it

- Think about: a new colour is switched by the ruleset file and its spellbook, never by the version name. A new spellbook entry or a new component name leaves the older ones alone. Name the type of every value (an integer for a price and a chip value, a string for a colour, a list of what for the start bag).
- Goes wrong: an edit to a ruleset file that has recorded games; a TOML integer against a string field, or the other way round, which fails validation when the file loads; a spellbook that lacks a colour that the chips use, or that changes white or orange; a chip that names both a spellbook component and its own component.
- Check: a test that loads the ruleset and checks the colour set of the spellbook against the colours of the chips, and that an older ruleset still loads and plays unchanged.

### 3. The shop and the prices

- Think about: one shop item per chip, with a price, and the start bag. Check the whole price ladder of the colour against the other colours and against the money table of the ruleset. If a shop item is dropped, drop its id from the shop strategies of the bots that name it.
- Goes wrong: a chip without a shop item, or a shop item that names a chip that does not exist; a price list that makes one colour always the best buy; a bot strategy that names a dropped item; the rules document with other prices than the file.
- Check: the ruleset test for the new version (prices, shop size, ids), the bot tests that play full games with the shop strategies, and a tournament run on a small number of games to see the balance.

### 4. How bots, the CLI and the RL layouts cope with a new colour

- Think about: every place that lists or counts colours. Bots need a branch for each new action. The CLI needs a style and a short label for the chip, draws it in the pot and the bag, and has as many buy keys as the shop has items. RL needs the number of colours in the map from the layout in use (`map_colours` in `src/quack_rl/rl/encode.py`), because a count fixed for one layout is wrong for another layout; a new colour count is a new layout, so keep a stored sample of the current layout (`tests/fixtures/layout7/`) from before you change the encoder.
- Goes wrong: a chip label that clashes with another colour (`chip_text` in `render.py` uses the first letter of the colour, so black would be `B` like blue; `CHIP_LETTER` holds the exceptions, black is `K`); a colour count fixed for one layout and used for another, which makes the encoder fail or silently shift the vector; a hidden hand that leaks into the opponent view in the observation, the render or the record; buy keys that run out or collide with the fixed keys of other actions; a bot that loops or crashes on a phase it never saw.
- Check: the layout tests for the new colour count (names, length, bounds, mask), the stored sample of the current layout, the CLI tests with scripted input, and the bot and environment tests with the new version in the list they loop over.

### 5. What happens to old versions

- Think about: old versions keep their behaviour, their layout number and their saved data. New fields have old-safe defaults. The new version is added to the tests that loop over versions. No default points at it unless an issue makes it the default.
- Goes wrong: an older version that plays differently because a shared component changed; a loop that was not extended, so the new colour is never run through a generic test; a default that picks the new version by accident; saved runs that load on a layout they were not trained for.
- Check: the full test command. The tests of the older versions pass unchanged.

## Pitfalls

- A colour count fixed for one layout. The count must come from the layout in use (`map_colours` in `src/quack_rl/rl/encode.py`); a count fixed for one layout is wrong for another layout. Search for every place that counts or lists colours.
- A hidden hand that leaks. A hand is hidden state. It must not appear in the opponent's observation, the render or the record shown to the other seat. Test the view of the other seat explicitly.
- A TOML value of the wrong type for its field. A chip value, a price or a spellbook name of the wrong type fails when the ruleset loads. Load the file in a test.
- The board and shop tests that list colours. Tests that name the colours of the spellbook, the number of shop items, the buy keys or the colours drawn on the board fail when a colour is added. Update them on purpose, and check that they still test something.
- A place hook without its callers. A new input for the hook must reach the report, the bot look-ahead and the RL bounds.
- A new action inserted in the middle of the action list. It shifts the RL mask. Append.
- A formatter run that touches files outside the change. Look at `git status` after it and restore the rest.

## How to check the result

Run the narrow tests after each step, and the full test command at the end. These tests exist; copy their shape for the new colour.

- Ruleset: the ruleset test of the version (`tests/test_ruleset_v2_1.py`), the spellbook tests in `tests/test_spellbook.py`.
- Effect on the pot (case B): `test_only_blue_has_a_place_bonus` in `tests/test_components.py`, `test_pick_red_beats_orange_with_three_orange_in_the_pot` in `tests/test_bots.py`.
- Hand and pick step (case C): `tests/test_brew.py`, `test_pick_plays_the_highest_advance`, `test_random_bot_answers_all_three_kinds_at_the_pick_step`, `test_view_of_the_other_seat_has_no_hand_and_no_pending_choice`.
- CLI: `tests/test_cli_v2_1.py` and `tests/test_cli_play.py` (labels and styles of a colour, a scripted full game with a hidden-hand check); `test_keys_map_to_legal_actions`, `test_own_hand_is_shown_and_the_other_hand_is_not`.
- RL: `tests/test_rl_layout7.py`, `tests/test_rl_layout7_sample.py` and `tests/test_rl_encode.py` (names, order, bounds, the other player's hand not in the view, the mask equals the legal actions in every step).
- Defaults: the tests in `test_rules_defaults` check that every default is the default version (`v2.1`).

Edge cases to try for any new colour:

- An empty bag: `test_empty_bag_stops_the_player`, and for a hand case `test_pick_stop_rule_counts_the_hand_in_the_bag`. A bag with fewer chips than the colour draws: `test_bag_key_is_removed_when_its_count_reaches_zero`.
- A colour with zero chips in the pot: a pot-dependent chip placed first must give no bonus (`test_pick_red_beats_orange_with_three_orange_in_the_pot` as the shape to copy, with the count at zero; chips that are in the bag but not in the pot must not count).
- The end of the track: `test_two_chips_on_track_end_later_chip_fills_the_slot`.
