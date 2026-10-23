# Quack RL rules v1

A simplified 1v1 version of **The Quacks of Quedlinburg**: a push-your-luck game about brewing potions, improving your ingredients and avoiding explosions.

Rules version: `v1`. Every game record stores the rules version it was played with. The machine-readable values (chips, track, shop, die) live in the ruleset data file of the engine; this document and that file must agree.

Status: working version, not final.

- **Settled:** the mechanics (simultaneous brewing per chip draw, explosion, resolve order, shop with victory points, game end)
- **Default:** every number (chip values, explosion limit, track money, ruby fields, die odds, shop prices, purchase limit, starting bag, number of rounds). These are tuning values. A change makes a new ruleset version (for example `v1.1`)

Earlier draft: `docs/archive/2026-10-08-rules-draft.md`.

## 1. Components

### Chips

| Chip | Values | Effect when placed |
|---|---|---|
| ⚪ White | 1, 2, 3 | Advance by its value. Add its value to the explosion total. |
| 🟠 Orange | 1 | Advance by its value. No other effect. |
| 🔵 Blue | 1, 2, 4 | Advance by its value, plus 1 if the previously placed chip of this round has a value other than 1. The first chip of a round gets no bonus. |
| 🟢 Green | 1, 2, 4 | Advance by its value. At round end, each green chip among the last two placed chips advances the droplet by 0.5 (see 4.3). |

Blue example: Blue 2 after White 2 advances 3. Blue 2 after White 1 advances 2.

### Track

Fields 0 to 53. Each field has a money value. Some fields have a ruby.

| Field | 0-14 | 15-16 | 17-18 | 19-20 | ... | 49-50 | 51-52 | 53 |
|---|---|---|---|---|---|---|---|---|
| Money | = field | 15 | 16 | 17 | ... | 32 | 33 | 35 |

Formula: `money(f) = f` for f ≤ 14, `15 + (f - 15) // 2` for 15 ≤ f ≤ 52, and `35` for f = 53.

A chip that would move past field 53 lands on field 53. There is no overflow.

Ruby fields: 5, 9, 13, 16, 20, 24, 28, 30, 34, 36, 40, 42, 46, 50, 52.

### Droplet

The droplet marks the start field of each round. It moves in half steps. The start field of a round is the droplet position rounded down.

### Bag

Each player has a bag. Chips are drawn at random. The players do not look into the bag.

A player's chips are either in the bag or placed on the track in the current round. At the end of every round, all placed chips go back into the bag (4.5), so every round starts with all of a player's chips in the bag.

### Bonus die

| Chance | Reward |
|---|---|
| 1/6 | Droplet +1 |
| 1/6 | Droplet +0.5 |
| 1/6 | Receive 1 Orange 1 chip (into the bag) |
| 2/6 | +1 shopping money this round |
| 1/6 | +1 victory point |

### Shop

| Item | Price |
|---|---|
| 🟠 Orange 1 | 3 |
| 🔵 Blue 1 | 5 |
| 🔵 Blue 2 | 9 |
| 🔵 Blue 4 | 16 |
| 🟢 Green 1 | 4 |
| 🟢 Green 2 | 8 |
| 🟢 Green 4 | 14 |
| Remove one White 1 | 15 |
| Advance droplet by 1 | 10 |
| 2 victory points | 6 |
| 5 victory points | 13 |
| 10 victory points | 22 |

## 2. Setup

- 2 players
- Each player's bag: White 1 ×4, White 2 ×2, White 3 ×1, Orange 1 ×1, Green 1 ×1
- Droplet on field 0, 0 victory points
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

Chips placed this round cannot go back into the bag during the round. They go back at the reset (4.5).

Brewing ends when no player brews anymore.

### 4.2 Final field and scoring field

A player's final field is the field of the player's last placed chip when brewing ends. It is the round result: it is settled once, cashed out once in Resolve (ruby, bonus die, money), and stored as the landing field. Nothing after brewing changes it: not the shop (also not removing a placed White 1), not droplet moves.

The **scoring field** is the first free field after the last placed chip: `min(final field + 1, last field)`. Ruby, bonus die and money in Resolve, and the tie-break after round 9, use the scoring field, not the final field. Example: a last chip on field 1 scores field 2 (money 2); a last chip on field 4 scores field 5 (ruby); a last chip on field 53 scores field 53 (money 35), so players on 52 and 53 are tied. The scoring field is derived from the final field and not stored.

### 4.3 Resolve

In this order, for each player:

1. **Ruby:** if the scoring field is a ruby field, the droplet advances by 0.5. This also applies after an explosion.
2. **Green chips:** for each green chip among the last two placed chips, the droplet advances by 0.5. Two green chips give 1. This also applies after an explosion.
3. **Bonus die:** the player with the furthest scoring field whose potion did not explode rolls the bonus die. If players are tied for furthest scoring field, each tied player rolls. A player whose potion exploded never rolls.
4. **Money:** the player receives the money of the scoring field. If the potion exploded, the money is halved, rounded down. Add +1 if the bonus die gave +1 money. In the last round (round 9) the result is multiplied by 1.5 and rounded down (`last_round_money_percent = 150`, money x 150 // 100), after the halving and the die money. Example: field money 25 gives 37; exploded, 25 gives 12, then 18; 25 plus a +1 die gives 26, then 39. The `money` event in the game record carries the multiplied amount.

Droplet changes take effect from the next round.

### 4.4 Shop

Shopping goes in steps, at the same time for both players. In each step, each player who still shops chooses one item to buy, or **Done**.

- At most 3 purchases per player per round
- The same item may be bought more than once
- A player cannot buy an item that costs more than the money left
- "Remove one White 1" is possible only while the player owns a White 1 (in the bag or placed this round). The removed chip is taken from the placed chips first, if one is there
- Bought chips go into the bag. Victory points are added at once
- A player stops shopping after Done or after the third purchase

Shopping ends when no player shops anymore.

### 4.5 Reset

1. All chips placed this round go back into the player's bag. After the reset, every chip the player owns is in the bag
2. Unspent money is lost
3. The droplet stays where it is

## 5. Game end

The game ends after the shop of round 9.

1. The player with the most victory points wins
2. On a tie: the player with the furthest scoring field in round 9 (4.2) wins
3. If that is tied too: the game is a draw

## 6. Planned rule changes (not in v1)

These are candidate changes for later versions. They are also test cases for the future "add a rule or component" skill.

- Alternating shop instead of a simultaneous shop
- Rubies as a currency that a player spends on a choice
- A new chip colour
- Random events
- Uncertain bag contents, for example chips that appear at random
