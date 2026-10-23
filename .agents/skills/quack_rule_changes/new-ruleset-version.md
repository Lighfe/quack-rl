# Recipe: a new ruleset version that adds a field or a phase

Use it when the rules change in a way an existing version cannot express: a new ruleset field (a value or a switch), a new phase, a new action, a new state field. Locations are in the [project map](project-map.md); this recipe names none.

Read each step as "if my change touches this". Where a step does not apply, the note at its end says so. Skip a step on purpose, never by forgetting.

Every step ends with a check. The checks are commands and tests that exist: the full test command, a single test file, `uv run quack-rl verify <record file> --seed-check`, and the tournament command run on the new version. Run the narrow check after each step and the full test command at the end. Look at `git status` after every formatter run.

## The order, and why

Work from the rules outward. Each step needs the one before it: the engine cannot read a field that is not in the model, a record test needs an engine that plays the field, a bot needs the engine's legal actions, the RL layer needs all of it.

## 1. Spec first

Decide the whole change on paper before any code.

- Think about: what is a new field, what is a new phase, what is a new action, what is a new event. Name the type of every key and value (an integer, a string, a list of what). Say what the old versions do (nothing: they keep their behaviour). Say what a hidden player sees.
- Goes wrong: a spec that says "table 1" without the key type; a field that two readers can take in two ways; a rule that works in the engine but has no words for the rules document.
- Check: someone who has not seen the idea can write the ruleset file and the model field from the spec alone. The rules document you write later must agree with the ruleset file, and a test compares their tables.
- Does not apply: never. A small change still gets a few lines saying what is new and what stays.

## 2. The ruleset file and the model field

A new ruleset file next to the old ones, and a new field in the model.

- Think about: the default. The default of a new field must keep every older version playing exactly as before (no behaviour, `None`, an empty table). Then the older files need no edit. Think about what ties the field to others: lengths of tables, unknown ids, the rule that chips either name a component or get one from a spellbook.
- Goes wrong: a default that changes old behaviour; a TOML integer against a `str` field (or the other way round), which fails validation; the new version missing from the list of supported versions, so it cannot be loaded; a new public name that is not exported; a shop-item field that a pydantic model coerces (`"2"` passes for an int unless the field is `strict=True`); the rules document drifting from the file; an edit to an old ruleset file "just to add the field".
- Check: a test file for the new version that loads the file and checks the new field, the validation errors, and that an older version still loads with the default. Run the ruleset tests and the other tests that loop over versions: the list of supported versions is checked there.
- Does not apply: the model step, when the change only changes values and adds no field. The new file is still needed.

## 3. The engine behind the field

The engine reads the field and carries out the rule.

- Think about: where the rule enters (an existing phase handler, or a new phase and its routing), what the legal actions are in each phase, what the state must remember, and in which order things happen inside a step (the order of effects is part of the rule). Every random event must go through the chance source, so a game can be replayed. A new state field needs a default and must survive the dict round trip. A new action goes into the full action list; the order of that list is the order of the RL action mask, so append, never insert in the middle. A new component hook needs a call site in the engine, and every other caller of the hooks (report, bot look-ahead, RL bounds) must pass the new argument or accept its default.
- Goes wrong: behaviour that leaks into older versions because the check is on the version name and not on the field; an action offered by the legal-action function but not handled by the step (or the other way round); a new phase that the routing does not know; randomness drawn outside the chance source, so replay differs; a joint action that must have exactly one action per seat, including a waiting action for the seat that does not decide; a new public name missing from the engine exports.
- Check: engine tests on the new version with scripted draws that walk the new rule step by step, including the edge cases (empty bag, explosion in the same step, last round). Then the full engine tests of the older versions: they must pass unchanged.
- Does not apply: when the change is only a value or a different spellbook, the engine needs no change.

## 4. Record and replay

A game is a recorded list of steps; the format is generic.

- Think about: new action names and event kinds need no schema change. So the work is a test: a game that uses the new rule writes, reads and replays to the same final state, and verifies against its seed.
- Goes wrong: an event that carries something the replay cannot rebuild; a field that the state dict does not save; a record that shows a hidden hand to the other side.
- Check: the record test for the new version, and `uv run quack-rl verify <record file> --seed-check` on a record the test or a short simulation wrote.
- Does not apply: a change with no new action, phase, event or state field needs no new record test. Change the record code only when the line format itself changes.

## 5. Bots

Every bot must answer every action the engine can offer.

- Think about: the heuristic bot needs a branch for each new action or phase, and must always return a legal action (fall back to the first legal one). Its look-ahead reads the component hooks. The random bot picks among legal actions and needs nothing. If an id is removed from a shop, remove it from the strategies that name it. Statistics code that reads event kinds may need a line when a new event changes money or points.
- Goes wrong: a bot that loops forever or crashes on the one phase it never saw; a stop rule computed on the wrong bag (for example, without chips that go back into it); a tie-break that is not deterministic; statistics that silently miss a new event.
- Check: bot tests on the new version (every bot plays full games without an illegal action), the tournament command on the new version with a small number of games, and the tournament tests. The results header comes from the ruleset, so a new column should appear without code.
- Does not apply: a change that offers no new action or phase and no new component hook.

## 6. CLI

The terminal game for a human.

- Think about: a new value, chip or state shown to a player goes into the drawing of the board and the steps; a new action needs a key and a prompt line; the buy keys must be at least as many as the shop has items. The other seat must not see a hidden hand.
- Goes wrong: a prompt that offers an action the engine does not accept; a render that prints hidden state; too few buy keys for a bigger shop.
- Check: CLI tests on the new version that feed scripted input through a full game and check the output, including that the other seat's view hides what it should.
- Does not apply: a change with no new action, phase or visible state.

## 7. RL: layout, action mask, environments

The engine knows nothing about RL. A new state field or action reaches RL only when someone adds it to the encoder.

- Think about: is the change visible in the observation or the action list? If not, there is nothing to do here. If yes, you need a new observation layout.
- A new layout needs, in this order: first keep a stored sample of the old layout (a small saved set of observations made by a script, run before you touch the encoder), so the old layouts stay checked against exact numbers after your change. Then write a short spec of the new layout (names and sizes). A new layout is picked in `observation_layout` by a feature of the ruleset (here: more colours or a `min_round`), not by the version name; add the colour count to `LAYOUT_COLOURS`. Then extend the encoder: the layout number is chosen from the ruleset, vector names, vector, bounds and action mask follow the full action list, and the number of colours in the map comes from the layout in use (`map_colours` in `src/quack_rl/rl/encode.py`). Then decide the policy side: either extend all entry points that run a trained policy, or refuse the new layout in each of them with the shared check, and test that each one refuses. Evaluating baseline bots must keep working where a policy is refused. Saved runs store their layout number and must be rejected when it differs from the ruleset's.
- Goes wrong: changing the old layout by accident (its sample test catches this only if the sample was made first); the hidden information of the opponent in the observation; bounds that do not cover the new values; a mask in another order than the action list; an entry point that is forgotten and tries to run a policy on a layout it was not trained for; an environment test that only runs on the older versions.
- Check: the encoder tests for every layout, including the stored sample of the old layout; layout tests for the new one (names, vector length, bounds, mask, opponent view); the environment tests with the new version added to the list they loop over; the tests of the entry points (refusal or support).
- Does not apply: a change not visible in the observation that adds no action needs no new layout. Then only add the new version to the environment tests.

## 8. Tests on the new version

- Think about: the tests per version, and the tests that loop over versions. The new version must be added to the loops (supported versions, bots, tournament, environments, defaults). Tests of older versions stay unchanged and must pass.
- Goes wrong: a loop that was not extended, so the new version is never run through a generic test; a test written for the new version that reaches into hidden state instead of using the view of the other seat.
- Check: run the full test command. It also has a fast subset for the inner loop, which is not the finish line.

## 9. Defaults

- Think about: the default `rules` value is `v1.11` (the default version). A new version is used only when someone passes it, until an issue makes it the default. The notebooks are archived and not checked. A version that becomes the default changes all defaults in one issue (grep `rules[^=]*=\s*"v1` in `src` and `scripts`); every test that relied on the old default, a policy entry point or old-rules data must then name its version.
- Goes wrong: a new function with a default that is not the default version; a script that follows the newest version; a test that silently relied on the old default.
- Check: the defaults test scans the source and the scripts and checks that every default is the default version (it fails on a planted default, as the existing cases do). Add the new version to the loops. Saved data of the older versions must still load.
- Does not apply: never skip the extension of the defaults test, even when nothing else here applies.

## 10. Docs

- Think about: the rules document, the row in the milestone table of the design spec, and the README where the change alters what it says (layout, CLI, scripts). The rules document must state every new field, phase and action in the words of the ruleset file.
- Goes wrong: a rules table that differs from the ruleset file; a milestone row left out; a README that still describes the old layout or the old CLI keys; the rules document written from memory and not from the file.
- Check: read the rules document against the ruleset file; its table test does the mechanical part, so run it. Run the full test command once more at the end.
- Does not apply: the README, when nothing it says changes. The rules document and the milestone row are always needed.

## Planning the work

- The work splits well into small steps in the order above, each with its own tests and commit: rules, engine, record, bots, CLI, RL, defaults. Check every step before the next is written. The steps that surprise an engineer cross a boundary: a hook with a new argument, an action list whose order matters, a table that two readers parse differently.
- A new field alone (a switch with an old-safe default, used by the next version) can ship in its own small step. The next version then only sets it.
- A new phase touches the most: the legal actions, the routing, the bot, the CLI prompt, the layout and the mask. Count them before you estimate.
- The statistics and tournament code read event kinds. A change in how money or points arrive is easy to miss there, and the miss shows only in a table of results, not in a failing test, until a test for the new version compares the numbers.
- The layout step is where old and new meet. The stored sample made before the change is the only proof that old data still looks the same.
- The last step is small and easy to forget: the defaults test, the milestone row, the README (the row says whether the version is the default).
