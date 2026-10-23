# Ruleset v2.1 (field table, rubies, flask, 20 cards), observation layout 8, and a test of the RL environment

Status: decided 2026-10-23 in the owner dialogue of `/stage-start` (stage set-up after the review of stage #166). The draft questions are answered in the section "Decisions". One stage with two parts: part 1 builds ruleset v2.1 and layout 8; part 2 tests the RL environment on it and is blocked by part 1. Use the skill `quack_rule_changes` when you build part 1.

## Intent

v2.1 finishes the rules. The points table of v2 was a placeholder; rubies are an automatic drop step instead of a currency; the flask is missing; 5 of the 12 cards have no effect. v2.1 brings the rules to the physical game.

v2.1 replaces v2 at once. The first rules task renames v2 to v2.1 (the v2 files go to `archive/`), so v2.1 is the only ruleset and the default from the start and every later task changes the one engine in place. There is no flag, no optional field, no shim and no `None` branch for an older ruleset. The v2 golden replay and its guards are archived with v2; the last rules task records new ones for v2.1.

Part 2 is a test of the RL environment: does it work end to end against bots, in self-play and offline? It is not a search for a strong policy and it does no fine tuning.

## Design principle: the standard rule, plus extras

Implement the standard rule once; a card adds an extra effect on top. No base rule is written with an "if card X is active" value or a special order. Examples: a ruby field gives 1 ruby, card 1 gives 1 more; the rat tail bonus is calculated by one function, and cards 8 and 19 read the same function. This rule goes into the `quack_rule_changes` skill (first task).

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

- Each player has a ruby count. It starts at 1 (owner decision), carries over between rounds and stays until spent.
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
| 1 | A ruby field gives 1 ruby more this round (the field itself still gives its standard 1 ruby; the card adds 1 on top). |
| 2 | Unchanged: once per round, after the 5th chip, a player may restart (all 5 chips back, bag reshuffled, pot and totals back to the start field). Not after an explosion on the 5th chip. |
| 3 | Unchanged: every player's drop +1 at round start. |
| 4 | Unchanged: explosion limit +2 this round. |
| 5 | Each player chooses: (A) a black 1 chip into the bag, (B) any value-2 chip into the bag, (C) 3 rubies. |
| 6 | Unchanged: each player chooses (A) drop +2 now, or (B) a purple 1 chip into the bag. |
| 7 | Unchanged: the player(s) with the fewest points get a green 1 chip. |
| 8 | A player may give up 1 to 3 of their rat tail entitlement this round (at most the entitlement from `calculate_rat_tails`) and take the same number of rubies. The engine stores a negative bonus adjustment of the same size, which cancels part of the standard bonus calculated afterwards. A player with entitlement 0 is not asked. |
| 9 | Every player who rolls the bonus die at round end rolls it a second time on top of the standard roll; both rewards apply, in order. Who rolls does not change. |
| 10 | This round, a player who stopped without exploding must draw 5 chips from the bag (all that are left if fewer) and choose one. The other chips go back into the bag first; then the chosen chip is placed as a normal placement (its effects fire; a blue chip draws its hand from the bag that already holds the returned chips, then picks or stops as usual). The placement can make the player explode, with all consequences. An empty bag skips the step. |
| 11 | At the card step each player draws 4 chips from their own bag (p1 then p2, recorded chance events). The player chooses one drawn chip that is not white, not orange and not at the highest value of its colour, and it becomes the next higher value of its colour (permanent: it goes back into the bag as the upgraded chip). If no chip can be upgraded, the player takes a green 1 chip. All drawn chips go back into the bag. Black and purple have only value 1 and cannot be upgraded. Example: W1, W2, Y2, G1: choose Y2 -> Y4 or G1 -> G2. Example: W2, K1, P1, O1: the player gets a G1. |
| 12 | A player with at least one ruby may swap one ruby for a value-1 chip of green, blue, red, yellow, orange or white (not black, not purple), or decline. Once. Without a ruby the player is not asked. |
| 13 | The player(s) with the fewest rubies get 1 ruby. |
| 14 | Each player chooses: (A) 4 points, or (B) remove a white 1 chip from the bag for the rest of the game. When the bag has no white 1, (B) is not offered and the player gets (A) without being asked. The points count for the rat tail bonus of the same round. |
| 15 | A player whose scoring field is a ruby field gets +2 points on top of the ruby, also after an explosion. |
| 16 | At the end of the round, all flasks are refilled. |
| 17 | A free use of the flask action for the first white chip a player places this round: that white chip goes back into the bag exactly as with the flask (the chip leaves the pot, the field and the white total go back to before that chip, the player draws on). The flask itself is not touched. Offered once per round, only for the first white chip; if the player draws on, it is gone. When a player has a full flask, both "use card 17" and "use flask" are offered. |
| 18 | At the card step every player rolls the bonus die once (p1 then p2, recorded chance events) and gets the reward at once. This is separate from the standard roll in Resolve, which stays. A droplet face moves the start position of the round; points count for the rat tail bonus. |
| 19 | Each player chooses: (A) a value-4 chip of green, blue, red or yellow, or (B) points equal to their entitlement from `calculate_rat_tails` (not capped; the number of rat tails they would get this round). When the entitlement is 0, (B) is not offered and the player gets (A) without being asked. The choices of all players are made first, then all rewards are paid (two passes), so one player's reward never changes another player's entitlement. The standard bonus step runs once afterwards, on the new points. |
| 20 | At the card step each player draws 5 chips from their own bag (p1 then p2, recorded chance events) and sums the values. The player(s) with the lowest sum take a blue 2 chip (a tie: all tied players); every other player gets 1 ruby. All drawn chips go back into the bag. A bag always holds more than 5 chips at the card step, so there is no short-bag rule. |

In v2 the value-4 chips are green, blue, red and yellow; the next higher value of a colour is 1 → 2 → 4; black and purple have only value 1, orange has 1 and 6.

## Observation layout 8

Layout 7 stays until layout 8 is built; then layout 7 is archived like layouts 2 to 6 and layout 8 is the only layout. v2.1 gets layout 8. It is built from the field table alone, with no optional branches.

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
- New actions (appended to the action list): use flask, use card 17 (put back the first white chip of the round), the shop-end ruby spends (drop, flask refill), the choices of cards 5, 8, 11, 12, 14, 19, and the chip choice of card 10.
- The heuristic bot answers every new action with a simple rule; balance is not a goal.
- The CLI shows rubies and the flask, and asks the new questions.
- Records, replay and `verify --seed-check` work for all new chance outcomes (the draws of cards 10, 11, 20 and the extra die rolls of cards 9, 18).

## Round start order and the rat tail function

Order at the start of a round, one fixed sequence with no special cases:

1. Round 6 only: each player gets a white 1 chip into the bag.
2. The round card is drawn; its effect and its choices are resolved (all choices of all players first, then all rewards; chance draws for p1 then p2).
3. The rat tail bonus is calculated once, on the points after the card, and each pot moves to its start field.

`calculate_rat_tails(points, rs)` (arbitrary name; the engine has `rat_tail_bonus` in `src/quack_rl/engine/board.py` as its base) returns the number of rat tails between each player and the leader. It is the entitlement, not capped (it can be 10 or more for a trailing player). Card 8 reads it, lets the player give up 1 to 3 of it (at most the entitlement) and stores a negative adjustment (`rat_tail_adjust`) that the standard bonus step subtracts, never below 0. Card 19 reads it for choice (B). The standard bonus step is the same for every round.

## Decisions on the open questions of the draft (owner, 2026-10-23)

1. The flask starts full. Rubies start at 1. A refill of a full flask is never offered.
2. Order at round start: see above.
3. Card 9: both rewards of the two rolls apply; who rolls does not change.
4. Card 10: the other chips go back first, then the chosen chip is placed as a normal placement (a blue chip draws from the bag that holds the returned chips). Empty bag: skipped.
5. Card 11: at the card step, each player, permanent upgrade, green 1 when nothing can be upgraded.
6. Card 12: may decline; colours green, blue, red, yellow, orange, white.
7. Card 14 (B): not offered without a white 1 in the bag; then (A) without a question.
8. Card 17: the first white chip of the round, as a free use of the flask mechanism; the flask is untouched. Cards 2 and 17 never meet (one card per round).
9. Card 18: at the card step, on top of the standard roll.
10. Card 19: (A) green, blue, red or yellow value 4; (B) uncapped; (B) not offered at entitlement 0; two passes.
11. Card 20: ties for the lowest all take the blue 2 chip; no short-bag rule (the start bag has 9 chips and only card 14 removes one).
12. Cards 1 and 15 never meet in one round (one card per round).
13. The name is `v2.1`. v2 is renamed and archived in the first rules task.
14. The look-ahead window default is `K = 10` (11 entries); `K` is a parameter of the layout.
15. The CLI is low-effort: it shows rubies and the flask, offers the new actions and asks the new questions. It adds no new features.

## Part 2: test of the RL environment (blocked by part 1)

Purpose: show that `QuackEnv` and `QuackParallelEnv` work end to end on v2.1 and layout 8. The aim is to find env bugs (wrong mask, reward, observation, opponent handling, replay), not to train a strong policy. No fine tuning, no hyper-parameter search, small budgets.

Three set-ups, each as a script in `scripts/` with a small library part in `src/quack_rl/rl/` and a fast test, plus a short results note in `docs/analysis/`:

1. RL against the random bot and against a heuristic bot: `MaskablePPO` (`sb3-contrib`), evaluation of the win rate over a fixed number of games with the same opponent.
2. Self-play: the opponent is a pool of earlier checkpoints of the agent; checkpoints are saved; the last one is evaluated against random, a heuristic bot and the first checkpoint.
3. Offline RL: a dataset of transitions from bot games (heuristic against random and heuristic against heuristic) built through the env; behaviour cloning and one simple offline method (discrete conservative Q-learning) trained on it; both evaluated in the env.

The archived stack (`archive/src/quack_rl/rl/`, `archive/scripts/`, `archive/notebooks/`) is the inspiration; code is ported, not imported. Scripts and notes only, no marimo notebook. A final task writes the README section and the verdict "the env works" with the evidence, or the list of env bugs found.
