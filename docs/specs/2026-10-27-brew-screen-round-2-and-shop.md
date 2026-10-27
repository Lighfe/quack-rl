# Brew screen round 2, the ruby step and the shop screen

Date: 2026-10-27. Follows the stage review of #223 (M2.19) and the owner's play-test notes on #223.

## Intent

The owner play-tested the brew screen after M2.19. The pot and two icons did not match what the owner imagined: the pot was overcorrected. The owner also wants to play the shop in the browser as a real game screen, and found that the shop offers the ruby spends (droplet +1, refill flask) mixed in with the chip buys.

Success: the owner plays a full round in the browser (Lovable preview or local) and the pot looks like the first pot with a little more air between its loops, the numbers on it are easy to read, the icons are recognisable, the shop is a themed screen where the pot and the ingredients are one click apart, and rubies are spent in their own step after buying.

## Goals

1. **Pot rework.** The pot goes back to the square spiral that was there before #219.
2. **Icon colours.** The points icon is a purple star and the flask is green.
3. **Ruby step.** A new rule: the ruby spends move out of the chip shop into a separate step after it.
4. **Top area tabs and the shop screen.** "Cauldron" and "Ingredients" tabs in the top area, and a themed dialogue box in the bottom area.
5. **Play-test in the Lovable preview** without a long flag.
6. **QA can start the app** in its sandbox (#230).
7. **Bag draw animation** (#231).

## Non-goals

- Round cards as a pop-up. The owner wants the cards as a pop-up later; not in this stage.
- Buying by clicking a chip in the Ingredients tab, with a buy cursor. The owner's idea for later.
- Visuals for the spell book effects beyond a one-line text, and for the point board and dice (#214 keeps the rest).
- The Voronoi pot (#224).

## Anti-goals

- A pot that copies a reference image, tilts its fields or has more white space than the first pot plus "a tiny bit".
- Visual criteria with a bound on one side only: every size, gap or contrast criterion has a lower and, where it can grow too far, an upper limit.
- Game rules in the app: prices, availability, legality and effects come from the service view.
- A wildcard `*.lovable.app` CORS default: it would let any Lovable-hosted page call the local service.

## 1. Pot rework

Reference: the pot of frontend commit `a7f1fee` (`src/lib/pot-layout.ts`). It is a square snake spiral: field 0 in the centre, then counter-clockwise outwards with straight runs of 1, 1, 2, 2, 3, 3, … fields. Each field is an untilted square of 10 units on a 12-unit grid (gap 2 units everywhere).

- Fields are squares with axis-aligned sides. No field is turned.
- Field size: the same as in `a7f1fee` relative to the gap along the path (field 10 units, gap along the path 2 units).
- Gap between one loop and the next: a little more than the gap along the path, from 3 to 4 units (1.5 to 2 times the path gap). Never less than 3, never more than 4.
- The pot fills its panel as the first pot did: no large empty band around it.
- The thinner pixel border of #219 stays: a field must not read as a cross.
- The chip trail of #219 stays.
- **Readable numbers.** The money and points numbers on the window fields are readable at the field size above. Money numbers are a yellowish colour and point numbers a purplish one. Each has a contrast of at least 4.5:1 against the field fill, and a font size of at least 9 CSS px at the default screen width of the playtest mock (`/?mock=playtest`).
- The pot keeps its chips until the round reset after the ruby step. The engine already does this; the screen must not hide them in the shop or ruby step.

## 2. Icon colours

- The points icon is purple and is redrawn so that it reads as a star.
- The flask icon is green, clearly unlike the blue droplet. The empty flask is drawn tilted a little.
- Both apply in the seat panel and in the small window-field icons.

## 3. Ruby step (rule change)

Today (rules v2.1, "Shop"): during the shop a player may choose `ruby_drop` and `refill_flask` at any time, mixed with chip buys.

New:

- The shop offers only `done` and the chip buys. A player with nothing left but `done` stops shopping without being asked (as today).
- When no player shops anymore, a **ruby step** follows. In it, a player may choose `ruby_drop` (2 rubies, droplet +1, repeatable) or `refill_flask` (2 rubies, only with an empty flask) or `done`. A player who can pay for neither is not asked (auto `done`, as in the shop).
- When no player is in the ruby step anymore, the round reset follows.
- The last round has neither a shop nor a ruby step (unchanged: rubies become points).
- Card 16 (all flasks refilled at round end) keeps its place before the shop.
- The action ids stay the same (`ruby_drop`, `refill_flask`, `done`), so the RL action space keeps its size. The phase is new.
- Every place that knows the phases follows: engine, rules document, README, CLI menu, labels, records and replay, bots, the RL environment, the service view and the frontend.
- Whether this is a new ruleset version or an edit of v2.1 follows the `quack_rule_changes` skill (builder's call; no legacy shims, per the owner).

## 4. Top area tabs and the shop screen

The game screen has two areas.

**Top area.** Two tabs: "Cauldron" (left, the main view, with a pot icon) and "Ingredients" (right, with a book icon).

- Both tabs are reachable in every phase.
- "Cauldron" is the default in every phase except the shop.
- When the shop starts, the top area switches to "Ingredients" by itself. The player can switch back to "Cauldron" at any time.
- The Ingredients tab shows one note per chip colour that the ruleset has, white included. A note looks like a witchy parchment or papyrus note (torn edges, stains, a seal or pin in the chip colour), not an open book: a note has room for three chips side by side. Each note shows its chips with the value printed inside the chip and the price below it with a coin icon (white has no price), and a one-line effect text.
- A colour whose chips cannot be bought yet in this round (minimum round not reached) is faded out. There is no "from round N" text.
- The look follows the pixel-art palette of the brew screen. The real spell books of the board game are not a model; only their idea of a value and price table is.

**Bottom area.** A themed dialogue box, for example a parchment scroll.

- In the shop it asks exactly "What would you like to buy?" and shows one button per legal buy: the chip with its value inside and the price with a coin icon. `done` is a button too.
- In the ruby step it asks exactly "What would you like to do with your rubies?" and offers the droplet +1, the flask refill and `done`, each with its ruby price.
- The texts stay plain: no invented flavour lines. The box must look like part of the game, not like a form.

**Service.** The view gets what the Ingredients tab needs: per shop item the chip, price and minimum round, whether it is available in this round, and per colour the one-line effect text from the ruleset or spellbook. The app computes no price and no availability.

## 5. Lovable preview

- The service allows this project's own Lovable preview origin (and its published origin, if it has one) by default, as exact origins. No wildcard.
- The README gets a short step list "Play-test in the Lovable preview".
- When the start screen cannot reach the service (network or CORS failure), its error names the likely cause and the command to start the service.
- If the preview origin cannot be known as a fixed string, the builder reports it and falls back to a short flag; this is the owner's decision then.

## 6. QA start (#230) and 7. bag animation (#231)

As written in #230 and #231. #230 goes first: later screenshot criteria depend on it.

## Constraints

- Frontend changes go through Lovable (lane `frontend`); the app uses `bun`.
- Lovable messages and credits need no owner approval (`AGENTS.md`).
- **Big creative freedom for Lovable.** The brainstorm mockup (tabs, parchment notes, dialogue box) and every look described here are only a rough orientation for the layout and the content. Every message to Lovable says so in words and asks Lovable to design the look freely in the pixel-art style of the game. Acceptance criteria fix only content, behaviour, sizes, gaps and contrast, never the exact drawing.
- Rule changes follow `.agents/skills/quack_rule_changes/SKILL.md`.
- Screenshot checks run on `/?mock=playtest` (and a shop mock where needed) in a headless browser.

## Left to the builder

- The label text of each button (the two questions are fixed above).
- The exact pixel art of the notes, the star and the flask.
- The ruleset version question (see 3).
- The order of the frontend tasks after #230, as long as the blockers in the plan hold.
