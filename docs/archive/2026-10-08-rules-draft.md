These rules are a simplified version of **The Quacks of Quedlinburg**
### Simplified Game Rules

_A push-your-luck game about brewing potions, improving your ingredients, and avoiding explosions._

## 1. Components & Setup

### Components

|Component|Description|
|---|---|
|⚪ **White chips**|Values 1, 2, 3. Increase explosion risk.|
|🟠 **Orange chips**|Value 1. Basic ingredients without explosion risk.|
|🔵 **Blue chips**|Values 1, 2, 4. Provide a movement bonus under certain conditions.|
|🟢 **Green chips**|Values 1, 2, 4. Can improve your starting position for future rounds.|
|**Player board**|Potion track showing positions and corresponding shopping money.|
|**Bag**|Contains each player's available ingredients.|
|**Droplet**|Marks the starting position on the potion track.|
|**Shop**|Allows players to purchase ingredients and upgrades.|
|**Die**|Provides a bonus to the player who brewed the best potion.|

### Starting Setup

Each player receives a player board, a bag, and a droplet.

**Starting ingredients per player:**

|Chip|Quantity|
|---|---|
|White 1|4|
|White 2|2|
|White 3|1|
|Orange 1|1|
|Green 1|1|

Place all starting chips in your bag.

Set your **droplet to position 0**.

The game lasts **9 rounds**.

---

## 2. Brewing a Potion

At the beginning of each round, players draw ingredients from their bags to brew their potions.

### Drawing Chips

1. Start at the position indicated by your droplet.
2. Draw one random chip from your bag without looking.
3. Place it on your potion track, advancing by the value printed on the chip.
4. Apply any special effects.
5. Decide whether to **draw another chip or stop voluntarily**.

Players may continue drawing as long as their potion has not exploded.

**Important:** Chips already drawn cannot be returned to the bag during the round.

### Chip Effects

|Chip|Effect|
|---|---|
|⚪ **White**|Advances by its value. Adds its value to the explosion total.|
|🟠 **Orange**|Advances by its value. No additional effects.|
|🔵 **Blue**|Advances by its value. **Moves 1 additional space if the previously placed chip did not have value 1.**|
|🟢 **Green**|Advances by its value. If it is among the **last two chips placed**, it gets a 50% chance at the end of the round to advance your droplet by 1.|

**Blue example:** A Blue 2 placed after a White 2 advances 3 spaces (2 + 1 bonus). If placed after a White 1, it advances only 2 spaces. A Blue chip placed first receives no bonus.

**Green example:** If your last three chips are Green 1 → Orange 1 → Green 2, only the Green 2 provides a bonus: a 50% chance to advance your droplet by 1.

Each qualifying green chip rolls on its own. If both of the last two chips are green, roll twice: the droplet can advance by 0, 1 or 2.

### Explosion

Your potion explodes when the **sum of your white chip values exceeds 7**.

For example:

- White 2 + White 3 + White 2 = 7 → Safe.
- White 2 + White 3 + White 3 = 8 → Explosion!

When your potion explodes:

- You must immediately stop drawing.
- You receive only **half of your earned shopping money**, rounded down.
- You cannot roll the bonus die.

All other chip effects, including green bonuses, still apply.

---

## 3. End of Round

Once all players have stopped drawing or exploded, resolve the round in the following order.

### Step 1: Green Chip Bonuses

Check the last two chips placed in your potion.

For each green chip among them, roll a die (each green chip rolls on its own):
1-3 -> nothing happens.
4-6 -> advance droplet by 1.

The droplet permanently advances your starting position in future rounds.

### Step 2: Bonus Die

The player with the **furthest-advanced potion that did not explode** rolls the bonus die.

|Probability|Reward|
|---|---|
|1/6|Advance droplet by 1|
|1/6|Advance droplet by 0.5|
|1/6|Receive 1 Orange 1 chip|
|3/6|Receive +1 shopping money this round|

If multiple eligible players are tied for first, each rolls the die.

### Step 3: Shopping

Every player receives shopping money according to the position reached on their potion track.

**If your potion exploded, your shopping money is halved (rounded down).**

Players can buy ingredients or upgrades from the following shop:

|Item|Price|
|---|---|
|🟠 Orange 1|3|
|🔵 Blue 1|5|
|🔵 Blue 2|9|
|🔵 Blue 4|16|
|🟢 Green 1|4|
|🟢 Green 2|8|
|🟢 Green 4|14|
|Remove one White 1|15|
|Advance droplet by 1|10|

**Shopping rules:**

- Players may buy as many items as they can afford.
- Newly purchased chips are added to their bags.
- Removing a White 1 permanently removes one such chip from the player's bag.
- Unspent shopping money is lost at the end of the round.

### Step 4: Prepare the Next Round

1. Return all chips from your potion track to your bag.
2. Keep newly purchased ingredients in your bag.
3. Leave the droplet at its current position.
4. Begin the next round.

---

## 4. Game End

The game lasts **9 rounds**.

Each round follows the same structure:

**Draw ingredients → Stop or explode → Apply green bonuses → Roll die → Shop → Reset**

After round 9, the game ends.

## 5. To be determined

### Board
How many fields moved equals how many shopping money.
The real game board has also ruby fields and when ending on that field you get a ruby (2 rubies move the drop by one). This first implementation we don't use rubies but maybe move the drop directly (50% chance)

### Win condition

The real game has both victory points and shopping money track in parallel. We don't use victory points. Maybe could do that who got furthest in round 9 wins automatically. Might be too punishing however. Also: what happens when explode in last round? Should be auto-loss?