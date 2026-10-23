# Quack RL rules v2.1

A simplified 1v1 version of **The Quacks of Quedlinburg**: a push-your-luck game about brewing potions, improving your ingredients and avoiding explosions.

Rules version: `v2.1`. Every game record stores the rules version it was played with. The machine-readable values (chips, track, shop, die) live in the ruleset data file of the engine; this document and that file must agree.

Status: v2.1 is in progress (the numbers are those of the archived v2; the stage changes this one engine in place). Working version, not final. The ruleset file exists; the engine does not play the points board, the rat tails and the new die faces yet (later issues of the same stage).

Changes from v1.11 (`archive/docs/rules/rules-v1.11.md`): see "Changes from v1.11" at the end of this document. Everything not named there is the same as in v1.11.

- **Settled:** the mechanics (simultaneous brewing per chip draw, explosion, resolve order, shop without victory points, game end)
- **Default:** every number (chip values, explosion limit, track money, ruby fields, die odds, shop prices, purchase limits, starting bag, number of rounds). These are tuning values. A change makes a new ruleset version (for example `v3`)

Earlier draft: `docs/archive/2026-10-08-rules-draft.md`.

## 1. Components

### Chips

The ruleset names a **spellbook** (`spellbook = 1`). The spellbook says what each colour does; a chip in the ruleset file has only a colour and a value. White and orange work the same in every spellbook.

| Chip | Values | Effect when placed (spellbook 1) |
|---|---|---|
| ⚪ White | 1, 2, 3 | Advance by its value. Add its value to the explosion total. |
| 🟠 Orange | 1, 6 | Advance by its value. No other effect. |
| 🟢 Green | 1, 2, 4 | Advance by its value. At round end, each green chip among the last two placed chips advances the droplet by 0.5 (see 4.3). |
| 🔵 Blue | 1, 2, 4 | Advance by its value, then draw hand chips and pick (see "Blue" below). No placement bonus. |
| 🔴 Red | 1, 2, 4 | Advance by its value, plus an extra for the orange chips placed this round (see "Red" below). |
| ⚫ Black | 1 | Advance by its value. At round end, a droplet effect that compares the black chips of both pots (see "Black" below). |
| 🟡 Yellow | 1, 2, 4 | Advance by its value. A white chip placed just before it goes back into the bag (see "Yellow" below). |
| 🟣 Purple | 1 | Advance by its value. At round end, points and a droplet effect by the number of purple chips in the pot (see "Purple" below). |

#### Red

When a red chip is placed, it counts the orange chips already placed this round (any orange value; not the bag, not itself, not other red chips). It advances its value plus 1 for one or two orange chips, plus 2 for three or more, plus 0 for none.

#### Black

At round end, when both players have stopped, count the black chips in each player's pot (an exploded pot counts). Let `a` be the count of one player and `b` the count of the other:

- `a` is at least 1 and `a == b`: each of the two players advances the droplet by 1.
- `a > b` (so `a` is at least 1): the player with the larger count advances the droplet by 1.5. The other player gets nothing.
- Otherwise nothing.

The effect fires once per player, however many black chips there are.

#### Yellow

A yellow chip advances by its value. Then, if the chip placed just before it in the same pot was white, that white chip goes back into the bag. The droplet movement of that white chip is not taken back. The explosion total goes down by the value of that white chip. The effect is the same for all values of yellow. The effect runs before the explosion check of the same step. If the yellow chip is the first chip of the pot, or the chip before it is not white, nothing happens.

#### Purple

At round end, count the purple chips in the player's pot (an exploded pot counts):

- exactly 1: 1 point.
- exactly 2: 1 point and the droplet advances by 0.5.
- 3 or more: 2 points and the droplet advances by 1.

Purple chips are not used up. Droplet values are in half steps.

#### Blue

When a blue chip is placed, it advances by its value first. Then the player draws as many chips from the bag as the value of the blue chip (fewer if the bag has fewer). These chips are the player's **hand**; only that player sees it. In the next step the player makes a hidden **pick** instead of Draw or Stop:

- **Play chip i** of the hand: the chip is placed as a normal draw (it advances, its effect runs, a white chip counts toward the explosion total). The rest of the hand goes back into the bag.
- **Put all back and Draw:** the hand goes back into the bag, then the player draws one random chip as a normal Draw.
- **Put all back and Stop:** the hand goes back into the bag and the player stops brewing.

A played blue chip draws a new hand, and so on. An empty bag with a non-empty hand does not stop the player. If the bag is empty when blue is placed, the hand is empty and there is no pick step.

**Status of the engine:** the ruleset file and the component hooks of black, yellow and purple exist, but the engine does not play their effects yet (a later issue of the same stage). Until then these chips only advance by their value. This document states the intended rules.

### Track

Fields 0 to 53. Each field has a money value. Some fields have a ruby.

| Field | 0-14 | 15-16 | 17-18 | 19-20 | ... | 49-50 | 51-52 | 53 |
|---|---|---|---|---|---|---|---|---|
| Money | = field | 15 | 16 | 17 | ... | 32 | 33 | 35 |

Every field also has a point value (see "Points per field" in 4.3 and the table at the end of this document).

Formula: `money(f) = f` for f ≤ 14, `15 + (f - 15) // 2` for 15 ≤ f ≤ 52, and `35` for f = 53.

A chip that would move past field 53 lands on field 53. There is no overflow.

Ruby fields: 5, 9, 13, 16, 20, 24, 28, 30, 34, 36, 40, 42, 46, 50, 52.

### Points board

Victory points are shown on a board with fields 0 to 50 (`fields = 50`), shared by all players, with two laps (`laps = 2`). A player has 0 to 100 points (`fields * laps`); points above 100 are lost. The marker moves one field per point. A total of 50 is field 50 with `has_50pts` False; a total of 51 is field 1 with `has_50pts` True.

Between some fields lie **rat tails**. A rat tail lies after the field named in the list (23 tails, the same on both laps):

| Rat tails after field |
|---|
| 1, 4, 7, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32, 34, 36, 38, 40, 42, 44, 46, 48 |

A tail after field `f` lies at total `f` and at total `f + 50`. It counts for a player at total `low` behind a leader at total `high` when `low <= position < high`.

**Rat tail rule:** at the start of each round, after the round card and its choices, the player(s) with the most points get bonus 0 (a tie for the lead: all get 0). Every other player gets as bonus the number of tails between the player and the leader. The player starts the round that many fields further along the pot than the droplet. The bonus lasts one round and is public.

### Droplet

The droplet marks the start field of each round. It moves in half steps. The start field of a round is the droplet position rounded down.

### Bag

Each player has a bag. Chips are drawn at random. The players do not look into the bag.

A player's chips are either in the bag or placed on the track in the current round. At the end of every round, all placed chips go back into the bag (4.5), so every round starts with all of a player's chips in the bag.

### Bonus die

| Face id | Chance | Reward |
|---|---|---|
| orange_1 | 1/6 | Receive 1 Orange 1 chip (into the bag) |
| droplet_1 | 1/6 | Droplet +1 |
| droplet_half | 1/6 | Droplet +0.5 |
| point_1 | 2/6 | +1 victory point |
| point_2 | 1/6 | +2 victory points |

There is no money face any more.

### Shop

| Item | Price | Min. round |
|---|---|---|
| 🟠 Orange 1 | 3 | 1 |
| 🟠 Orange 6 | 22 | 1 |
| 🟢 Green 1 | 4 | 1 |
| 🟢 Green 2 | 8 | 1 |
| 🟢 Green 4 | 14 | 1 |
| 🔵 Blue 1 | 5 | 1 |
| 🔵 Blue 2 | 10 | 1 |
| 🔵 Blue 4 | 19 | 1 |
| 🔴 Red 1 | 6 | 1 |
| 🔴 Red 2 | 10 | 1 |
| 🔴 Red 4 | 16 | 1 |
| ⚫ Black 1 | 10 | 1 |
| 🟡 Yellow 1 | 8 | 2 |
| 🟡 Yellow 2 | 12 | 2 |
| 🟡 Yellow 4 | 18 | 2 |
| 🟣 Purple 1 | 9 | 3 |

A shop item can be bought only in a round that is at least its minimum round. An item below its minimum round is not a legal action. Rounds are numbered 1 to 9.

The shop has no "Remove one White 1" item. Orange 6 is only in the shop; the bonus die gives Orange 1.

The shop has no droplet item, no victory points item and no remove item. The droplet moves only by rubies, green chips, black chips, purple chips and the bonus die.

## 2. Setup

- 2 players
- Each player's bag: White 1 ×4, White 2 ×2, White 3 ×1, Orange 1 ×1, Green 1 ×1
- Droplet on field 0, 0 victory points, 1 ruby
- The game lasts 9 rounds

## 3. Round overview

Brew → Resolve → Shop → Reset (all placed chips go back into the bag)

## 4. Round in detail

### 4.1 Brew

Brewing goes in steps. In each step:

1. Each player who still brews chooses **Draw** or **Stop**, at the same time and hidden from the other player.
2. The choices are revealed. Each player who chose Draw draws one random chip from the bag and places it: the chip advances from the player's current field (at the start of the round: the start field) as described in "Chips".
3. If the sum of a player's white chip values this round is more than 7, the potion explodes. That player stops brewing at once.
4. Both players see both potions: chips placed, field, explosion total.

A player stops brewing when the player chooses Stop, the potion explodes, or the bag is empty.

The first action of a round must be Draw: a player places at least one chip each round.

A player on field 53 may still draw.

Chips placed this round cannot go back into the bag during the round, with two exceptions: a yellow chip puts the white chip placed just before it back into the bag (see "Yellow"), and the flask (see "Flask" below) puts the white chip just placed back into the bag. All other placed chips go back at the reset (4.5).

Brewing ends when no player brews anymore.

### 4.2 Final field and scoring field

A player's final field is the field of the player's last placed chip when brewing ends. It is the round result: it is settled once, cashed out once in Resolve (ruby, bonus die, money), and stored as the landing field. Nothing after brewing changes it: not the shop, not droplet moves.

The **scoring field** is the first free field after the last placed chip: `min(final field + 1, last field)`. Ruby, bonus die and money in Resolve, and the tie-break after round 9, use the scoring field, not the final field. Example: a last chip on field 1 scores field 2 (money 2); a last chip on field 4 scores field 5 (ruby); a last chip on field 53 scores field 53 (money 35), so players on 52 and 53 are tied. The scoring field is derived from the final field and not stored.

### Rubies

Rubies are a currency. Each player has a ruby count (`PlayerState.rubies`). It starts at 1 (`start_rubies = 1`), carries over from round to round and stays until it is spent. A ruby field gives 1 ruby in Resolve (also after an explosion). Card 1 (`ruby_extra`) adds 1 ruby on top of that standard ruby. In the shop, 2 rubies (`ruby_cost = 2`) buy a droplet +1 with the action `ruby_drop`, as often as the player can pay. There is no automatic droplet step for a ruby field (v1.11 and v2 had +0.5). The game record shows the balance: the events `ruby` and `ruby_drop` carry `total`, the ruby count after the event.

### Flask

Each player has one flask (`PlayerState.flask_full`). It is full at the start of the game and stays as it is between rounds. After a white chip is placed, a player who is still brewing (not exploded, not stopped) and has a full flask may choose **Use flask** (`use_flask`) next to Draw and Stop. The white chip leaves the pot and goes back into the bag; the field goes back to where it was before that chip (the landing field of the chip placed before it, or the start field, with the rat tail bonus, when it was the first chip) and the white total goes down by the chip's value. The flask is then empty and the player draws on. White chips have no effects, so nothing else is undone. The game record has the event `use_flask` with the chip, the new field and the new white total. The flask is not offered after an explosion, after a stop, after a chip of another colour or with an empty flask.

In the shop, a player with an empty flask and at least 2 rubies (`ruby_cost = 2`) may choose **Refill flask** (`refill_flask`): it costs 2 rubies and fills the flask (event `refill_flask`, with the ruby `total`). A full flask is never refilled.

### 4.3 Resolve

In this order, for each player:

1. **Ruby:** if the scoring field is a ruby field, the player gets 1 ruby. This also applies after an explosion. Rubies are a currency (see "Rubies" below); the droplet does not move for a ruby field.
2. **Green chips:** for each green chip among the last two placed chips, the droplet advances by 0.5. Two green chips give 1. This also applies after an explosion.
2a. **Black and purple chips:** the round-end effects of the black and purple chips in the pot (see "Black" and "Purple"), black first, then purple. They also apply after an explosion.
3. **Bonus die:** the player with the furthest scoring field whose potion did not explode rolls the bonus die. If players are tied for furthest scoring field, each tied player rolls. A player whose potion exploded never rolls.
4. **Money and points:** a potion that did not explode gives the money and the points of the scoring field. The bonus die gives points, never money. There is no last-round money factor (`last_round_money_percent = 100`). The `money` event in the game record carries the amount.
5. **Exploded potion:** an exploded potion gives nothing yet and nothing is halved. The player chooses in the explosion choice step (4.3a).
6. **Last round (round 9):** all money a player receives in round 9 (field money or the money of `take_money`) becomes `money // 5` points at once (`last_round_money_divisor = 5`), and the player keeps no money. Points from the field (or `take_points`) are added as in other rounds. The shop of round 9 then has no money to spend.

### 4.3a Explosion choice

A step between Resolve and Shop, only when at least one potion exploded (`explosion_choice = true`). Each player who exploded chooses `take_money` or `take_points`, at the same time and hidden, as the Draw or Stop choice. A player who did not explode waits.

- `take_money`: the money of the scoring field, in full (no halving).
- `take_points`: the points of the scoring field. The player gets no money this round.
- The ruby and the green droplet bonus after an explosion still apply.
- In round 9, `take_money` gives `money // 5` points and `take_points` gives the points of the scoring field.

Droplet changes take effect from the next round.

### 4.4 Shop

Shopping goes in steps, at the same time for both players. In each step, each player who still shops chooses one item to buy, or **Done**.

- At most 2 chips per player per round, and they must be of different colours (for example Green 1 and Blue 2, but not Green 1 and Green 2). Only chips bought in the shop count; a chip from the bonus die does not
- A player cannot buy an item that costs more than the money left
- A player with at least 2 rubies (`ruby_cost = 2`) may also choose **Ruby drop**: it costs 2 rubies and moves the droplet by 1 (+1, two halves). The player stays in the shop and may choose it again as long as they can pay
- A player with an empty flask and at least 2 rubies may also choose **Refill flask** (see "Flask")
- Bought chips go into the bag
- A player stops shopping only with Done
- The chip count and the colours bought start again from zero in every round

Shopping ends when no player shops anymore.

### 4.5 Reset

1. All chips placed this round go back into the player's bag. After the reset, every chip the player owns is in the bag
2. Unspent money is lost
3. The droplet stays where it is
4. Unspent rubies stay: a player keeps them for later rounds

## 5. Game end

The game ends after the shop of round 9.

1. The player with the most victory points wins
2. On a tie: the player with the furthest scoring field in round 9 (4.2) wins
3. If that is tied too: the game is a draw

## 6. Planned rule changes (not in v2.1)

These are candidate changes for later versions. They are also test cases for the future "add a rule or component" skill.

- Alternating shop instead of a simultaneous shop
- Random events
- Uncertain bag contents, for example chips that appear at random

## 7. Changes from v1.11

- **Points board:** a new optional ruleset table `point_board` (`fields`, `rat_tails`, `laps`), see "Points board" above. Rulesets without it play as before.
- **Bonus die:** the +1 money face (weight 2) became +1 point (weight 2), the old +1 point face (weight 1) became +2 points (weight 1).
- **Rubies:** a currency instead of the automatic droplet +0.5 of a ruby field, see "Rubies" above. Card 1 is `ruby_extra`.
- Everything else is as in v1.11.

### Round-start cards (unchanged from v1.11)

At the start of every round, one card is drawn at random from the cards not yet drawn in this game (without replacement). The 9 rounds use 9 of the 12 cards. Each entry of the deck has an `id`, an `effect` (the name of a card effect) and a `count`. The effect names are in the ruleset file.

| Card id | Effect name | Effect | Count |
|---|---|---|---|
| card_1 | ruby_extra | a ruby field gives 1 ruby more (2 in total) | 1 |
| card_2 | restart_after_5 | restart option after 5 chips | 1 |
| card_3 | drop_all_1 | every drop +1 | 1 |
| card_4 | explosion_limit_plus_2 | explosion limit +2 this round | 1 |
| card_5 | choice_black_or_value2_or_drop | choice: black 1 chip, or any value-2 chip, or drop +1.5 at round end | 1 |
| card_6 | choice_drop2_or_purple | choice: drop +2, or purple 1 chip | 1 |
| card_7 | fewest_points_green | fewest points get a green 1 chip | 1 |
| card_8_to_12 | no_effect | no effect | 5 |

The deck has 12 cards, 5 of them without an effect.

**Status of the engine:** the ruleset file and the card effect names exist, but the engine does not draw or play the cards yet (later issues of the same stage). Until then a v2.1 game plays as v1.10. This document states the intended rules; the full card text is in `archive/docs/specs/2026-10-19-ruleset-v1-11.md`.

Points per field (the real values of the physical board):

| Field | Money | Points | Ruby |
|---|---|---|---|
| 0 | 0 | 0 | no |
| 1 | 1 | 0 | no |
| 2 | 2 | 0 | no |
| 3 | 3 | 0 | no |
| 4 | 4 | 0 | no |
| 5 | 5 | 0 | yes |
| 6 | 6 | 1 | no |
| 7 | 7 | 1 | no |
| 8 | 8 | 1 | no |
| 9 | 9 | 1 | yes |
| 10 | 10 | 2 | no |
| 11 | 11 | 2 | no |
| 12 | 12 | 2 | no |
| 13 | 13 | 2 | yes |
| 14 | 14 | 3 | no |
| 15 | 15 | 3 | no |
| 16 | 15 | 3 | yes |
| 17 | 16 | 3 | no |
| 18 | 16 | 4 | no |
| 19 | 17 | 4 | no |
| 20 | 17 | 4 | yes |
| 21 | 18 | 4 | no |
| 22 | 18 | 5 | no |
| 23 | 19 | 5 | no |
| 24 | 19 | 5 | yes |
| 25 | 20 | 5 | no |
| 26 | 20 | 6 | no |
| 27 | 21 | 6 | no |
| 28 | 21 | 6 | yes |
| 29 | 22 | 7 | no |
| 30 | 22 | 7 | yes |
| 31 | 23 | 7 | no |
| 32 | 23 | 8 | no |
| 33 | 24 | 8 | no |
| 34 | 24 | 8 | yes |
| 35 | 25 | 9 | no |
| 36 | 25 | 9 | yes |
| 37 | 26 | 9 | no |
| 38 | 26 | 10 | no |
| 39 | 27 | 10 | no |
| 40 | 27 | 10 | yes |
| 41 | 28 | 11 | no |
| 42 | 28 | 11 | yes |
| 43 | 29 | 11 | no |
| 44 | 29 | 12 | no |
| 45 | 30 | 12 | no |
| 46 | 30 | 12 | yes |
| 47 | 31 | 12 | no |
| 48 | 31 | 13 | no |
| 49 | 32 | 13 | no |
| 50 | 32 | 13 | yes |
| 51 | 33 | 14 | no |
| 52 | 33 | 14 | yes |
| 53 | 35 | 15 | no |
