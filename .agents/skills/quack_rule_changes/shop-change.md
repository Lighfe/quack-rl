# Recipe: changing the shop

Use it when a shop item is removed, a shop item is added, or a price changes. The parts are named as in the [project map](project-map.md); this recipe names no location. A shop change is a rule change, so the general advice in [SKILL.md](SKILL.md) holds. Never edit a ruleset version that has recorded games: the change is a new ruleset file, as in the [new ruleset version recipe](new-ruleset-version.md). A new chip colour also follows the [colour recipe](colour-change.md).

Read each step as "if my change touches this". Skip a step on purpose, never by forgetting.

## Which parts each change touches

| Part | Remove an item | Add an item | Change a price |
| --- | --- | --- | --- |
| Rules: shop table of the ruleset file | yes | yes | yes |
| Rules: chips, start bag (the chip an item gives) | no | only for a new chip | no |
| Rules in words and its doc test | yes | yes | yes |
| Action list and legal actions | yes, if it was the last item of its kind | only for a new kind of item | no |
| Bots that buy (shop strategies) | yes | optional | check |
| Human CLI buy keys | check | yes, if the shop gets longer | no |
| RL action mask and layout | yes | yes | no |
| Tests that loop over versions | add the new version | add the new version | add the new version |

How to read the table:

- Remove: the ruleset file loses the item. The rules document loses its row. The action list is built from the shop of the ruleset, so a removed item drops its buy action. The mask follows the action list, so its length changes and the shop part of the RL layout changes with it.
- Add: the item needs a row in the shop table, a row in the rules document, and a chip behind it (an existing chip, or a new chip in the chip table and, when the chip is new, in the spellbook). It adds a buy action, so the action list and the mask grow. A new kind of item (not a chip, not points, not a removal) needs engine code for what buying does, and a legality rule.
- Price: only the number in the shop table and the matching number in the rules document. The action list stays the same, so the mask and the layout stay the same. Everything that reads a price (the buy prompt in the CLI, the report, the shop rule of the bots) follows the ruleset without a code change.

## The order of thought

Work through these steps in order. Each step needs the one before it.

### 1. Think about old versions first

- Think about: old versions keep their shop. A removed item stays in every version that has recorded games, so its buy action is still a valid action there, its kind of item is still handled by the engine, and the code that buys it must not be deleted. A shop change is a new ruleset file, never an edit of an old one. Games that were recorded under an old version must replay to the same final state.
- Goes wrong: the engine branch for a removed kind of item is deleted, and old records fail to replay; a ruleset file with recorded games is edited in place; a default moves to the new version by accident.
- Check: the tests of the older versions pass unchanged, and a recorded game of an older version still verifies.

### 2. The shop table of the new ruleset

- Think about: start the new file from the file before it and change only the shop rows and what depends on them. Name the types: the item id is a string, the price is an integer, the kind is one of the kinds the model knows, the chip of an item is the id of a chip that exists. Keep the order of the rows on purpose: the order of the shop is the order of the buy actions in the action list and of the buy keys.
- Goes wrong: an item that names a chip that does not exist; a chip with no shop item (check whether that is meant); a price that is a string; a row inserted in the middle, which shifts the buy actions; a leftover comment in the file that still describes the removed item.
- Check: a ruleset test for the new version that pins the items and their prices, that nothing of the removed kind is left (for a removal), and that every other field is the same as in the version before it.

### 3. The rules document and its doc test

- Think about: the rules document must agree with the ruleset file. A test compares the shop table of the file with the text of the document, row by row, as a string: the item name written in title case, a bar, the price, a bar. So the name and the spacing of a row decide whether the test passes.
- Goes wrong: the doc test matches the text of the shop table, so a row that is reworded, a price that is changed in one place only, or a removed item whose row is left in the document makes it fail, or, worse, a new row with the wrong text is not found and the test fails far from the cause. A document that still lists a removed item passes a test that only checks the rows of the file, so read the table yourself.
- Check: the doc test of the new version, and a read of the "changes from" section of the document so it names the shop change.

### 4. The action list and the legal actions

- Think about: the full action list is built from the shop of the ruleset, and its order is the order of the RL mask. Buying is legal when the player can pay and the chip rules allow it. A removal item is legal only when the player owns the chip it removes. A shop without such an item has no such action at all, in the list and in the legal actions.
- Goes wrong: an action name that is hard-coded somewhere and not taken from the ruleset; a legal action for an item the shop does not have; a new item appended in the middle of the list.
- Check: the tests of the action list for the new version (the buy actions equal the shop, a removed item is absent) and of the legal actions in the shop phase.

### 5. Bots that buy

- Think about: the shop strategies are lists of item ids. An id that the shop lacks is never legal, so the bot skips it without an error. The bot then plays a different strategy than its name says, for example a strategy built around the removed item buys only what is left. Decide for each strategy whether it still makes sense, and keep the strategies of the older versions working. The points rule and the fallback rule of the bot read the kinds of the items, so check them when a new kind is added.
- Goes wrong: a strategy that silently degrades after a removal; a new item that no strategy ever buys, so it is never tested in games of bots; a price change that makes a strategy unaffordable at the point where it was meant to buy.
- Check: the bot tests that play a full game with every strategy on the new version, and the report test that expects a column for each shop item of the ruleset.

### 6. The human CLI buy keys

- Think about: a human presses one key per buy action. The keys are a fixed string, and some keys are reserved for other actions. The string must be at least as long as the largest shop, and no key may be used twice. A removal makes the shop shorter and needs nothing. An addition may make it longer than the string.
- Goes wrong: a shop longer than the key string, so the last items get no key; a key that collides with the key of another action; a buy prompt that shows a stale price.
- Check: the CLI test that every legal buy has its own key and that the last one can be chosen, the test with more buy actions than the usual shop, and the test of the buy prompt with the prices.

### 7. The RL layout and the action mask

- Think about: the mask has one entry per action of the full list. A removed or added item changes the length of the list, so it changes the size of the observation and of the action space for that ruleset. That is a new layout, not an edit: keep a stored sample of the current layout (`tests/fixtures/layout7/`) from before you change the encoder. A price change does not change the size, but a price is a feature in the observation, so check the bounds.
- Goes wrong: the layout number is not changed although the vector changed; the mask does not follow the legal actions; the bounds of a price are too narrow for the new price.
- Check: the layout tests (names, length, bounds), the test that the mask equals the legal actions in every step of random games, and the environment tests with the new version in the list they loop over.

### 8. The tests that loop over versions

- Think about: add the new version to every test that loops over versions. No default points at the new version unless an issue makes it the default (the default is `v2`). The notebooks are archived and not checked.
- Goes wrong: a loop is not extended, so the new shop is never run through a generic test; a default points at the new version by accident.
- Check: the full test command.

## Pitfalls

- A doc test that matches the text of the shop table. It fails on a reworded row, an added space or a changed name, and it does not catch a removed item whose row is still in the document. Change the document and the file together.
- A removed item whose kind of item is deleted from the engine. Old versions still have it. Leave the engine code and the legal action rule as they are.
- A strategy that names a removed id. It is skipped without an error, so no test fails. Read the strategies yourself.
- A shop longer than the buy keys. The last items cannot be bought by a human.
- An item inserted in the middle. It shifts the buy actions, the keys and the RL mask. Append, or accept a new layout on purpose.
- A mask or a layout that is not changed for a new shop size. The encoder then builds a vector of the wrong size.
- A price change made in the file and not in the document, or the other way round.
- A formatter run that touches files outside the change. Look at `git status` after it and restore the rest.

## How to check the result

Run the narrow tests after each step, and the full test command at the end. These tests exist; copy their shape.

- Ruleset: `tests/test_ruleset_v2.py` (shop prices; a new file equals the file before it except for the shop), and the doc test that compares the rules document with the file (the shop table text).
- Action list and legal actions: `tests/test_state_actions.py`, `test_shop_legal_actions_follow_money`, `test_shop_item_priced_at_money_left_is_legal`, `tests/test_state_actions.py` (the removal rule that old versions keep).
- Bots: the shop tests in `test_bots` (`test_strategy_priority_before_points_round`).
- CLI: `test_keys_map_to_legal_actions`, `test_buy_keys_continue_with_letters`, `test_choose_prints_board_and_menu_with_buy_details`.
- RL: `test_action_mask_equals_legal_actions_at_every_step` in `tests/test_rl_encode.py`.
- Record and replay: a game of the new version writes, reads and replays to the same final state (`tests/test_record.py`), and the record tests of the older versions pass unchanged.
- Defaults: `test_rules_defaults` (every default is `v2`).
