# Ruleset v2.1 (field table, rubies, flask, 20 cards) and observation layout 8: design draft

Status: draft, written 2026-10-23 in the owner brainstorm (`/stage-start`), so the decisions are on record. It is planned in its own stage, with `/stage-start`, after the stage "Retire everything before ruleset v2" (`docs/specs/2026-10-23-retire-before-v2.md`) is done and its review is posted. The section "Open questions" is the agenda of that planning session. Use the skill `quack_rule_changes` when you build this.

## Intent

v2.1 finishes the rules. The points table of v2 was a placeholder; rubies are an automatic drop step instead of a currency; the flask is missing; 5 of the 12 cards have no effect. v2.1 brings the rules to the physical game.

After the retirement stage v2 is the only ruleset. v2.1 replaces it: when v2.1 is done, v2 is retired too (moved to the archive), and v2.1 becomes the only ruleset and the default. So v2.1 needs no compatibility with any older version: no optional fields, no shims, no `None` branches.

## Rule changes against v2

### The field table (one source per field)

The pot fields 0 to 53 are one table. Each field has `money`, `points` and `ruby` (yes or no). The separate lists `money`, `points` and `rubies` are gone. This is the only source: the ruleset model, the engine, the bots, the report, the CLI and the observation read it, and no code builds the old three lists from it.

Suggested TOML form (builder may refine): one `[[fields]]` entry per field, in field order, with `money`, `points` and `ruby`. Validation: exactly `track_end + 1` entries.

Every field has points; some have 0. The money and the ruby fields are as in v2. The points, read from the physical board and confirmed by the owner:

| Fields | Points |
|---|---|
| 0 to 5 | 0 |
| 6 to 9 | 1 |
| 10 to 13 | 2 |
| 14 to 17 | 3 |
| 18 to 21 | 4 |
| 22 to 25 | 5 |
| 26 to 28 | 6 |
| 29 to 31 | 7 |
| 32 to 34 | 8 |
| 35 to 37 | 9 |
| 38 to 40 | 10 |
| 41 to 43 | 11 |
| 44 to 47 | 12 |
| 48 to 50 | 13 |
| 51 to 52 | 14 |
| 53 | 15 |

The rules text `docs/rules/rules-v2.1.md` shows the same one table (field, money, points, ruby), and a test compares it with the TOML file.

### Rubies

- Each player has a ruby count. It starts at 0 (my call), carries over between rounds and stays until spent.
- A scoring field with a ruby gives the player 1 ruby, also after an explosion (as the ruby step did). The automatic drop +0.5 of a ruby field is gone.
- The board does not change with cards. A card that changes what a ruby field gives is an extra effect in the engine (card 1, card 15), not a board value.
- At the end of the shop, a player may spend 2 rubies for drop +1, as often as they can pay.
- At the end of the shop, a player may spend 2 rubies to refill the flask (only when it is empty; my call).

### Flask

- Each player has one flask. It is full at the start of the game (owner confirmed the draft; the corrections were the white-only rule and the explosion rule below).
- After a white chip is placed and the player has not exploded, the action "use flask" is offered (when the flask is full). It puts that white chip back into the bag: the chip leaves the pot, the field and the white total go back to before that chip, and the player draws on. The flask is then empty.
- It is not usable after an explosion: an explosion stops the player at once. It is not usable after a stop.
- It is not like the yellow chip effect. White chips have no effects, so nothing is undone besides the chip, the field and the white total.
- An empty flask is refilled for 2 rubies at the end of the shop, or by card 16.

### White chip at round 6

At the start of round 6, each player gets one white 1 chip into the bag, for the rest of the game.

### Cards

The deck has 20 cards, one of each. The 5 `no_effect` cards are removed. 9 rounds draw 9 of the 20 cards, without replacement, as today. All effects are per player.

| Card | Effect |
|---|---|
| 1 | A ruby field gives 2 rubies instead of 1 this round. |
| 2 | Unchanged: once per round, after the 5th chip, a player may restart (all 5 chips back, bag reshuffled, pot and totals back to the start field). Not after an explosion on the 5th chip. |
| 3 | Unchanged: every player's drop +1 at round start. |
| 4 | Unchanged: explosion limit +2 this round. |
| 5 | Each player chooses: (A) a black 1 chip into the bag, (B) any value-2 chip into the bag, (C) 3 rubies. |
| 6 | Unchanged: each player chooses (A) drop +2 now, or (B) a purple 1 chip into the bag. |
| 7 | Unchanged: the player(s) with the fewest points get a green 1 chip. |
| 8 | A player may give up 1 to 3 of their rat tail bonus this round and take the same number of rubies instead. At most the bonus they have; a player with no bonus cannot use it. |
| 9 | A player who rolls the die this round rolls it twice. |
| 10 | This round, a player who stopped without exploding must draw 5 chips from the bag (or all that are left) and choose one to place. The others go back. This can make the player explode, with all consequences. |
| 11 | Each player draws 4 chips from the bag and upgrades one drawn chip that is not orange and not white to the next higher value of its colour. If no drawn chip can be upgraded (all white or orange, or all at the highest value), the player takes a green 1 chip instead. All drawn chips (with the upgraded one in place of its original) go back into the bag. Example: W1, W2, Y2, G1: choose Y2 → Y4 or G1 → G2. Example: W2, K1, P1, O1: the player gets a G1. |
| 12 | A player with at least one ruby may swap one ruby for a value-1 chip of a colour they choose (not black, not purple). Once. Without a ruby, no effect. |
| 13 | The player(s) with the fewest rubies get 1 ruby. |
| 14 | Each player chooses: (A) 4 points, or (B) remove a white 1 chip from the bag. |
| 15 | A player whose scoring field is a ruby field gets +2 points on top of the ruby, also after an explosion. |
| 16 | At the end of the round, all flasks are refilled. |
| 17 | This round, a player may put the first chip they draw back into the bag. |
| 18 | Every player rolls the die once and gets the reward. |
| 19 | Each player chooses: (A) a value-4 chip of any colour, or (B) 1 point per rat tail they would get this round. The rat tail bonus is calculated again after (B). |
| 20 | Each player draws 5 chips from the bag and sums their values. The player(s) with the lowest sum take a blue 2 chip; all other players get 1 ruby. All drawn chips go back into the bag. |

In v2 the value-4 chips are green, blue, red and yellow; the next higher value of a colour is 1 → 2 → 4; black and purple have only value 1, orange has 1 and 6.

## Observation layout 8

Layout 7 stays as it is until v2 is retired. v2.1 gets layout 8. It is built from the field table alone, with no optional branches.

Principle: the observation gives the information the way a human reads the board: relative to the player, not as a fixed map. This follows state-of-the-art practice: Gran Turismo Sophy (Sony AI, Nature 2022) sees the course as points ahead of the car, not as a map; NetHack/MiniHack offer an egocentric crop around the agent because it "makes representation learning easier".

- **No static field table.** The money, points and ruby of every field are constants of the ruleset; repeating them in every observation (162 numbers) gives no information about the moment. They leave the observation. The per-field chips (own and opponent: colour, value, order) stay, because they change and chip effects read them.
- **Look-ahead window.** For `k = 0 … K`, the field `scoring field + k`: `ahead.<k>.money`, `ahead.<k>.points`, `ahead.<k>.ruby`. `k = 0` is "what I get if I stop now". Past the last field the window repeats the last field (the scoring field is capped there, so this is the true game value; no "past the end" flag). `K` is a parameter with default 10; `K = track_end` gives the whole rest of the pot.
- **Gaps as metrics** (derived entries): `field_gap` (own field − opponent field) and `points_gap` (own points − opponent points), next to the existing derived entries. The rat tail bonus already measures the gap on the point board.
- **Absolute state** (own and opponent; all public): money, points, rubies, flask full, drop, white total, status, the point board block of layout 7, the card of the round and the cards left, the explosion limit of the round.
- `ruby_fields_ahead` is removed (the window replaces it).
- Builder: the per-field chip map is still absolute (field index); whether it should become relative too is part of the research issue below.

## Research issue (parked, after v2.1)

Compare observation encodings with the same training budget, by win rate against the baseline bots:

1. raw absolute state (positions plus the static table),
2. the look-ahead window of layout 8 (with several values of `K`, and a window that grows with the average chip value of the bag, as Sophy's grows with speed),
3. structure in the network: each field as a token (money, points, ruby, chips, distance to own and opponent position) read by attention or a 1D convolution.

Training is rebuilt on v2.1 first (the retirement stage archives the old training stack).

## Engine, bots, CLI (outline; detail in planning)

- New state: rubies per player, flask full per player, the card 2/10/11/17/20 draw and choice states.
- New actions (appended to the action list): use flask, put back the first chip (card 17), the shop-end ruby spends (drop, flask refill), the choices of cards 5, 8, 11, 12, 14, 19, and the chip choice of card 10.
- The heuristic bot answers every new action with a simple rule; balance is not a goal.
- The CLI shows rubies and the flask, and asks the new questions.
- Records, replay and `verify --seed-check` work for all new chance outcomes (the draws of cards 10, 11, 20 and the extra die rolls of cards 9, 18).

## Open questions (agenda of the planning session)

1. (Settled: the flask starts full.)
2. Rubies at game start: 0? Can a player refill a full flask (assumed no)?
3. Order at round start: the round-6 white chip, the card draw, card choices, and the rat tail bonus. Card 8 needs the bonus before its choice; card 19 (B) needs the bonus, then a recalculation. Today the bonus is set after the card and its choices.
4. Card 9: two rolls, both rewards? Who rolls the die (today: the rule in v2)?
5. Card 10: which chip effects fire for the chosen chip (normal placement)? What if the bag is empty?
6. Card 11: when (round start)? Does each player draw, or only some? Does the upgraded chip replace the drawn one (assumed yes)?
7. Card 12: may a player decline? Is white a valid colour, and orange?
8. Card 14 (B): no white 1 in the bag → only (A)?
9. Card 17: only the very first draw of the round; does it also apply after a card 2 restart?
10. Card 18: when in the round, and is it on top of the normal die roll?
11. Card 19 (A): which colours (green, blue, red, yellow have value 4)? (B) with bonus 0 gives 0 points?
12. Card 20: ties for the lowest sum: all get the blue 2 chip (assumed)? Fewer than 5 chips in the bag?
13. Card 15 and card 1 on the same round cannot happen (one card per round), so no interaction.
14. Does v2.1 keep the name `v2.1`, and does v2 move to the archive in the same stage or the next one?
15. Window length default: 10 (owner) or the whole rest of the pot; final choice by the research issue.
