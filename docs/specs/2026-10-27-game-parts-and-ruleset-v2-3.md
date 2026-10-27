# Game parts on screen, ruleset v2.3 and saved web games

Status: designed 2026-10-27 in the owner brainstorm (`/stage-start`), after the owner's play test of stage #239 (M2.20). Prior spec: `docs/specs/2026-10-27-brew-screen-round-2-and-shop.md`.

## Intent

The owner played a full round in the browser. The pot spiral is fine now, but the screen does not yet feel like the real game: the round card, the bonus die and the point board are not visible as game parts, so the rat tails make no sense to the player. The play test also found two rule-level problems (the black chip gives 3 rubies, and the droplet is stored in half steps although the rules have none) and that web games are not saved.

This stage makes the game parts visible, cleans up the brew screen so the cauldron gets the space, fixes the black chip rule in a new ruleset v2.3, and saves every web game as a record.

The owner said: continue development; the actions, the cards, the dice and the point board matter now, not small conveniences such as buying from a note.

## Goals

1. Ruleset v2.3 is the only ruleset and the default. Black chip: equal counts (1 or more) give each player droplet +1; the larger count gives droplet +1 and 1 ruby. The droplet is a whole-step count everywhere.
2. Every web game is saved as a game record, like a CLI game.
3. The log reads as plain sentences.
4. The cauldron gets most of the screen; the status shows without boxes and titles.
5. The ingredient notes are redesigned from scratch; the shop shows the player's status.
6. After the shop and the ruby step the screen returns to the cauldron with a clean-up animation.
7. The round card appears as a scroll at the start of each round.
8. The bonus die rolls visibly in the cauldron of the player who rolls.
9. A Point board tab shows both players on a track with rat tails, laps and the round flames.

## Non-goals

- Buying a chip by clicking its note (#241, stays parked).
- An animation for opponent draws (#242; the owner closes it, not needed).
- Spell books as a game part, the Voronoi pot (#224).
- Any policy or training work. A policy on the old observation vector no longer fits and must be retrained on v2.3 later (#225, #199, #86 carry that dependency).

## Anti-goals

- Copying from pictures. No image, photo or mockup is sent to Lovable as a template. The board game photo the owner showed in the brainstorm stays out of every Lovable message; the board is described in words, as structure only.
- Lovable copying its earlier note design or the old mockup again.
- Legacy shims: no reader for old record formats, no switch that keeps v2.1 or v2.2 behaviour.
- Any game rule in the app: legality, prices, die rewards, rat tail positions and points come from the service.

## 1. Ruleset v2.3 (one change)

Owner decisions:

- Retire v2.1 and v2.2. v2.3 is the only supported ruleset and the default everywhere. Their rule docs, ruleset files and golden records move to `archive/` (moved, not deleted), as in `docs/specs/2026-10-23-retire-before-v2.md`.
- The ruby step after the shop (from v2.2) is now simply the rule: the `ruby_step` switch goes away.
- Black chip, at round end, comparing the black chips of both pots (an exploded pot counts): `a >= 1` and `a == b`: droplet +1 for each; `a > b`: droplet +1 and 1 ruby for the player with more; otherwise nothing.
- The droplet moves in whole steps and is stored as whole steps: `PlayerState.droplet` (not `droplet_halves`), `PotRoundEnd.droplet`, the die face reward, the card effects and the ruby drop all count whole steps. Events carry `drop` (whole steps), not `halves`.
- Old records are not read any more: the record schema version goes up (to 3); files under `data/records/` from earlier versions stay on disk but are not replayed by the current code.
- The observation vector changes (`droplet` in whole steps instead of `droplet_halves`); my call: this is observation layout 9, and the stored sample is regenerated.

Everything else plays as in v2.2.

## 2. Saved web games

- Every game the web service starts writes a game record to the record root (`data/records/` by default, the same store as `quack-rl play`), with the same header form and mode `web` (my call), the seats, the seed and the rules version.
- The record is written step by step while the game runs, so a closed browser window or a stopped service leaves a record of every step so far. A finished game gets the final line as in a CLI record.
- The record root can be set for the service (my call: an option of `quack-rl serve`, default `data/records`). Tests write into a temporary folder.
- A saved web game replays with the existing replay check.

## 3. Plain log sentences

- Each log line in the view is a plain sentence, for example "You drew Orange 1." or "p2: Black chips: droplet +1 and 1 ruby." (the exact words are the builder's call).
- A field that is 0 or empty is not shown. No internal names (`halves`, `pot_round_end`, component ids such as `black@1`) appear in a line.
- The raw events stay in `log.events` for the app.

## 4. Brew screen clean-up (frontend)

From the owner's notes:

- The cauldron view gets most of the screen. The bag side becomes thin.
- Each player's sack is a small bag. Hovering over it (or tapping it on a touch screen) expands it into the big sack with the content, like a pop-up. Lovable may redesign the sack.
- No box around the white chip total and no "White chips" title; no box around coins, points and rubies; no "P1" title; no "P1 – Brewing" title.
- The money and point numbers in the pot fields are bigger and centred in the field. Colours stay as they are.

## 5. Notes and shop (frontend and service text)

- The effect texts lose "Advance by its value" everywhere (spellbook texts in the service and the rules doc). A colour with no other effect (orange) has an empty effect text, and its note shows no effect line.
- The ingredient notes are redesigned from scratch. The owner's criticism of the current notes: they look outrageously ugly; Lovable almost copied the mockup although it was told not to; there is no pixel art left; they do not look like parchment or notes; the wax dots do not look like wax; nothing is witchy or mysterious; all notes look exactly the same. The original instruction stays: a witchy parchment or papyrus note (torn edges, stains, a seal or pin in the chip colour) in the pixel-art palette of the brew screen, room for three chips side by side, value inside the chip and price with a coin below. New: the notes vary slightly from each other (edges, stains, tilt, seal place), clearly the same kind of object, not one template.
- During the shop and the ruby step, the player's status is visible: money (updated after each buy, so it shows what is left), points, rubies and the flask (full or empty).

## 6. Return to the cauldron (frontend)

- When the player's shop and ruby step are over and the next round starts, the screen switches back to the Cauldron tab by itself.
- An animation clears the cauldron: the chips of the pot fly back into the player's bag, then the pot is empty for the new round. Under reduced motion there is no flight; the pot is simply empty.

## 7. Round card scroll (frontend)

- At the start of each round, the round card appears big over the screen as a papyrus scroll (not a literal card that shows only the element name) with the card's text.
- When the card asks the player to choose, the choices are on the scroll, and it stays until the player has chosen.
- When the card needs no choice, the scroll waits for the player's click before the round goes on.
- During the round, a control reopens the scroll to read the text again.

## 8. Bonus die (frontend, with a service field)

- After both players stop, the die rolls in the cauldron of the player who rolls: in the player's own (big) cauldron, or in the opponent's (smaller) cauldron when the opponent rolls. On a tie both roll, one after the other.
- The die shows the face it landed on, then the reward appears (a chip into the bag, the droplet moving, points).
- A player whose pot exploded never rolls, so no die appears for that player. When nobody rolls, no die appears.
- Service: the view says which seats rolled in the latest resolve, the face and a plain reward text, so the app computes nothing (my call: a field `game.last_roll` with the round and a list of `{seat, face, text}`).

## 9. Point board tab (frontend, with a service field)

- A third tab "Point board" next to "Cauldron" and "Ingredients".
- A track runs around the outside edge of the board: fields 0 to 49, like a frame of numbered tiles.
- Rats lie between the fields where the rat tails are, so the player can count the tails between the players. The board does not count them and does not show the start bonus.
- Each player has a marker on the track. Past 49 the marker goes on for a second lap; a marker per player shows 0 or 50 for the lap.
- In the middle: the round counter as flames, one flame per round, the current round lit (my call on the exact form; the owner named flames).
- Service: the view gives the board from the ruleset (my call: `board: {fields, laps, rat_tails}`); the app places nothing by its own rule.

## Constraints

- Rule changes follow `.agents/skills/quack_rule_changes/SKILL.md`.
- Frontend changes go through Lovable (lane `frontend`); the app uses `bun`. Lovable messages and credits need no owner approval (`AGENTS.md`).
- Every message to Lovable says that the look is free, in the pixel-art style of the game, and that no earlier design or mockup is a template. Acceptance criteria fix content, behaviour, sizes and contrast, never the drawing.
- Standard rule plus additive effects: no per-card or per-chip branch in a base rule.

## Left to the builder

- Exact log sentences, the form of the reopen control, the flame drawing, the die drawing and the animation timings (each animation is short and has a reduced-motion form).
- The exact names of the new view fields, if the ones above clash with existing names.
- Where a marker stands at the point cap (`fields × laps` points; the engine stops points there).
