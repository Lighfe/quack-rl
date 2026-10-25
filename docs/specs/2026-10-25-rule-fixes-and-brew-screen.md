# Rule fixes and the first frontend: the brew screen

Date: 2026-10-25. Status: draft for the owner.

## Intent

The owner wants to see and play the game in a browser, not only in the terminal and as an RL observation. The long-term frontend shows every game component (pot, bag, spell books, shop, point board) in a retro pixel-art style: dark, alchemist, witchcraft practised in a cellar, but warm and playful, with no real horror. The game is The Quacks of Quedlinburg for two players with the first spellbook (plus the v2.1 additions), not a simplified version. It has three uses: player against player (hot seat), player against a bot or an RL policy, and replay of recorded games.

This stage builds the first slice: one full game in the browser, where the brew (Draw or Stop) gets the real visual treatment and every other phase is shown as plain buttons and a text log, like the CLI. Before that, three small rule fixes found while play-testing v2.1 go in.

## Goals

1. Rule fix A: no droplet half steps. Every former droplet +0.5 becomes 1 ruby (details below).
2. Rule fix B: the last round has no shop, and rubies become points at the end.
3. Rule fix C: the shop lists chip buys first and skips `done` when nothing else is left.
4. A local game service: a small HTTP service in front of the Python engine, so a browser can start a game, see a seat's view and send actions.
5. The Lovable frontend app in `frontend/` (a git submodule), with a brew screen and plain screens for the other phases, playing a full 9-round game against a bot or hot seat.

## Non-goals (this stage)

- The shop, spell book, point board, card scroll and dice visuals. They are plain buttons and log lines now; later stages replace them one at a time.
- Replay of recorded games, and a policy seat (needs the PolicyBot seat, issue #199).
- Hosting. The service and the app run on the owner's machine. Nothing is built for hosting, but nothing assumes it can never be hosted.
- More than two players in the engine. The engine stays two-seat.

## Anti-goals

- Game logic in the frontend. The rules live only in the Python engine. The app shows what the service sends and sends back the action the player chose.
- A view that shows more than the observation of the seat. The screen must not leak what the RL observation hides.
- A layout hard-wired to two seats.

## Rule fix A: no droplet half steps (ruleset v2.1, in place)

The droplet moves in whole steps only. Every source of a half step becomes rubies, one ruby per half step:

| Source | Before | After |
|---|---|---|
| Green chip among the last two placed chips (round end) | droplet +0.5 each | 1 ruby each |
| Purple, exactly 2 chips in the pot | 1 point, droplet +0.5 | 1 point, 1 ruby |
| Black, the larger count | droplet +1.5 | 3 rubies |
| Bonus die face `droplet_half` | droplet +0.5 | face `ruby_1`: 1 ruby (kind `rubies`) |

Unchanged: black on equal counts (droplet +1 each), purple 3 or more (2 points, droplet +1), die face `droplet_1`, the ruby drop in the shop (+1), cards 3 and 6.

v2.1 is changed in place: it is the only ruleset and has no released recorded games to keep. The work exists as `stash@{0}` ("ruby-instead-of-half-droplet"): the engine, the components, the rules document, the golden record and the tests. It also removes the unused player field `round_end_halves` and its two observation entries (layout 8 shrinks from 1530 to 1528 entries). One test fails with it: `tests/test_baseline_maximum.py::test_simulation_matches_the_calculated_field_table_points`, because `report.py` no longer counts the green, black and purple droplet moves the same way the simulation does. The fix makes the report's calculation and the simulation agree again.

Every event that changes rubies carries the ruby balance `total`: `ruby` (also for the die face `ruby_1`, as an extra event after `die`), `round_end_bonus`, `pot_round_end`.

## Rule fix B: the last round ends without a shop, rubies become points

Today, in round 9 (the last round), money becomes points (`money // 5`) and the player keeps no money, but the shop phase still runs: a player can spend rubies on a ruby drop or a flask refill, which is useless. New rule:

- After Resolve (and the explosion choice, when a potion exploded) of the last round, there is no shop. The game ends.
- At the game end, before the winner is decided, each player's rubies become points: `rubies // 2` points (rounded down), new ruleset field `last_round_ruby_divisor = 2` (type: integer, at least 1). The points stop at `max_points` like all points. The rubies of the player become 0.
- Event: `ruby_points` with `seat`, `rubies` (spent), `points` (added), one per player, p1 then p2, also when the player has 0 rubies (then `points` is 0). It comes before `game_end`.
- A game with fewer rounds (`--rounds 4`) applies the same in its last round.
- The rules document (`docs/rules/rules-v2.1.md`, 4.3 point 6 and the end of the game) says the same.

## Rule fix C: shop order and no needless `done`

- In the shop, the actions are offered in this order: `done`, the chip buys, then `ruby_drop`, then `refill_flask`. The CLI menu shows the chip buys before the ruby drop and the refill. (Today the engine order is already `done`, buys, ruby, refill, but the CLI menu shows `[k] ruby drop` before `[1] buy …`; the fix is in the menu order, and the label list of the service in goal 4 uses the same order.)
- When `done` would be the only legal shop action of a player (no buyable chip, for example after the second chip buy; no ruby drop and no refill they can pay for), the player is not asked: the shop ends for that player at once (as if they chose `done`). If a ruby drop or a refill is still possible, `done` stays and the player is asked.
- The record, verify and the RL action mask follow the engine: a player who is not asked gets `wait`.

## The local game service

A small HTTP JSON service in Python, started with one command, for example `uv run quack-rl serve` (port 8000 by default, `--port` to change). The libraries are the builder's call (FastAPI with uvicorn is the expected choice), in a new dependency group `web`, so the default install does not grow. `AGENTS.md` line `QA groups:` gets `web` so QA can run its tests.

It allows CORS from the frontend dev server on localhost.

Endpoints (the builder may rename; the frontend issue states the final names):

- `POST /games` with `{"p1": "human", "p2": "bot:random", "rounds": 9, "seed": null}`: seat specs as in `quack-rl play` (`human`, `bot:random`, `bot:draw<percent>-pts<round>-<strategy>`). Returns `{"game_id": …}`. Games live in memory; no persistence.
- `GET /games/{id}/view?seat=p1`: the view of one seat (below).
- `POST /games/{id}/actions` with `{"seat": "p1", "action": "draw", "revision": 12}`: the action must be one of the seat's legal actions, else HTTP 400 with the legal list. `revision` is the decision revision from the view the player acted on; a stale revision (the game moved on) gives HTTP 409, and a second action of a seat for the same revision is rejected (409), so a duplicated or late click can never draw twice. Submissions of one game are processed one at a time. When every seat that must act has an action, the engine steps; the response is the new view of that seat. A seat's pending action is never visible to another seat before the step, and a seat whose action is accepted is not in `to_act` any more.

Errors: an illegal action gives HTTP 400 `{"error": "illegal_action", "legal": [...]}`; a stale or duplicate revision gives HTTP 409 `{"error": "stale_revision", "revision": <current>}`. There is no push: the app polls the view (about every 500 ms) while its seat is not in `to_act`; the round card in the view is `{id, effect, text}`.

Advancement: the service drives the game forward by itself until a human decision is needed or the game is over: at creation (a new game starts in the card phase), after each step, through the phases that take no actions (card, resolve), through seats that can only `wait`, and through bot decisions (bots choose at once). A human who stopped never blocks a bot that is still brewing. The `revision` increases with every engine step.

The view of a seat (JSON; field names are the builder's call, the content is fixed):

- `game`: round, rounds, phase, the decision `revision`, the explosion limit in effect this round (card 4 included, so the frontend does no rule arithmetic), the round card (id, effect name and text), winner when the game is over.
- `you`: the seat id this view is for; `to_act`: the seats that must act now.
- `seats`: a list, one entry per seat (not a fixed own/opponent pair), each with: seat id, kind (human or bot name), status, points, money, rubies, flask full, white total, droplet (whole steps), start field (droplet plus rat tail bonus), rat tail bonus, the bag (count per chip id still in the bag and owned), and the pot: per placed chip, in placement order: `order` (1 = first chip of the round), chip id, colour, value, `from` (the first field it covers) and `landing` (its landing field), so the frontend can fill every cell the chip passed over, outline the landing field, and spot a new chip by the highest `order` it has not seen (chips can also leave the pot: flask, card 17, yellow). Seat ids are strings (`p1`, `p2`). Bag counts are per chip id.
- `window`: for the viewing seat only, the look-ahead window of the observation: for k = 0 … 10 the field `min(scoring field + k, track_end)`, each with field number, money, points and ruby. Exactly the cells of `ahead` in the RL observation; near the end of the track the last field repeats, and the frontend lights each field once. Other seats have no window.
- `chips`: the chip table of the ruleset (id, colour, value), so the frontend has no chip list of its own.
- `legal`: for the viewing seat, each legal action with its id and a label. The labels are the CLI menu labels (for example `ruby drop: 2 rubies, droplet +1`, `buy orange_1 (3)`), from one shared function used by the CLI and the service, so the two never differ.
- `hand`: the viewing seat's hand (blue chip) as chip ids in slot order (picking slot i is action `play:<i>`, from 0; putting all back is `put_back_draw` or `put_back_stop`), and the chips a card draw shows only to this seat; never another seat's.
- `log`: the events of the steps since the game start, as text lines and as the raw events, filtered per seat: an event that only the acting seat may see (a hidden card draw) is not in another seat's log.

Hidden from other seats, everything else is public: a seat's chosen action before the step, the hand, and card draws that the rules show to the choosing player only.

Tests: a full game through the HTTP API with two bot seats ends with a winner; a human-vs-bot game advances to the human's first decision at creation, and after the human stops the bot brews on to the end of the round without further requests; a duplicated or stale submission (same or old revision) is rejected and does not draw twice; the window at a scoring field near 53 matches `ahead`; a human seat gets `legal` and its action is applied; an illegal action gives 400; the view of p2 never holds p1's hand or a hidden draw; the `window` equals `observe(...)["ahead"]`; the labels equal the CLI labels.

## The frontend app

### How it gets made

- Lovable builds the app. Lovable's stack is React, TypeScript, Tailwind and Vite; inside it, Lovable decides the rendering (canvas, SVG or CSS pixel art), fonts, libraries and animations.
- The owner creates the Lovable project `quacks-frontend` with the first prompt in `docs/specs/2026-10-25-lovable-first-prompt.md` and connects it to GitHub. Its kick-off part only sets up the project, the base theme and an empty start page, and asks Lovable for a plan; the brief in it is built later by the brew-screen issue. Before that issue runs, the planner adds the v2.1 rules to the Lovable project knowledge and discusses the plan with Lovable in plan mode. That is the owner's only manual step. Then a task adds the repo as the submodule `frontend/` and the line `Lovable project: <id>` to `AGENTS.md`; after that all frontend work is `Lane: frontend` issues in the normal loop (frontend engineer drives Lovable, QA checks).
- The browser's seat comes from the URL (`?seat=p1`). Lovable's agreed plan for the brew screen is in `frontend/.lovable/plan.md` (components, the `PotLayout` interface, the data module `getView(seat)` / `sendAction(seat, action, revision)` with a mock and an HTTP backend, the animations); the project knowledge in Lovable holds the brief and a rules summary.
- The app runs locally (`npm run dev` in `frontend/`) and talks to the service at a configurable base URL, default `http://localhost:8000`.

### Look and feel

Retro pixel art. Dark, alchemist, witchcraft practised in a cellar, but at the same time warm and playful; no real horror. Crisp pixel fonts and pixel borders, a limited palette with glowing accents for the chip colours. The playfulness is visual only: no text that is not about a game component (no flavour texts, no jokes). The owner showed the indie game Loop Hero as an illustration of "pixelated" only; nothing is copied from it.

### The brew screen (the heart of this stage)

- **The pot**: the track fields 0 … 53 (`track_end`) laid out as a spiral that starts in the centre and runs counter-clockwise to the outside. First shape: a square "snake" spiral of pixel tiles. The shape must be replaceable by design: one pot layout module maps each field (0 … 53) to its position and outline, and everything else (filling the covered cells, the landing outline, the lit window, the dark rest, the drop animation) works on those outlines without knowing the shape. A Voronoi-cell spiral as a second layout with a toggle is a later stage (planner's call); this stage only makes it possible.
- **What is visible** equals the observation of the seat: every field a placed chip covers is filled with the chip's colour (from the first field it covers to its landing field), and the landing field has a clear outline (and the chip value). The look-ahead window (the next 11 fields from the scoring field) is lit and shows money, points and a ruby mark. Every other field is grey or dark.
- **Around the pot**: round and round card, the seat's points, money, rubies, flask, droplet and start field, the white total against the explosion limit (an "explosion meter"), and status.
- **The bag**: the chips still in the bag as coloured dots (value shown on or by the dot).
- **Decisions**: Draw and Stop, plus Use flask and card 17 when they are legal, as big buttons; keyboard keys like the CLI (`d`, `s`, `f`, `u`) are a nice extra.
- **Blue hand**: when a blue chip gives the player a hand, the hand chips are shown as selectable chips (the legal `play:<slot>` actions), with the put-back options (`put all back and Draw`, `put all back and Stop`) as buttons; a chained blue placement shows the next hand.
- **Fallback**: any legal action that has no dedicated control on the screen is shown as a plain labelled button, so a game can never get stuck in the UI.
- **Other seats**: each other seat has a smaller panel of the same kind (its pot and bag, points, status). Other seats have no look-ahead window: their pots show only the placed chips, also when the panel is enlarged. A panel can be enlarged. The layout takes a list of seats, so three or four seats need no redesign.
- **Hot seat**: the screen shows the seat that is to act; when both humans act at the same time (Draw or Stop is simultaneous), the app asks them one after the other and does not show the first choice to the second.
- **Animations**: a drawn chip drops into the pot and lands with a small pixel effect; an explosion gets its own moment (a puff of smoke).

### Every other phase (plain for now)

- A plain list of buttons, one per legal action, with the service's labels: resolve and explosion choice, card questions, restart, the shop.
- An event log as text lines (as the CLI prints them).
- Start screen: choose each seat (human, random bot, a heuristic bot from a short list), the number of rounds, and start.
- End screen: final points, the winner, and a button for a new game.

## Constraints

- Python 3.12, the existing engine (`step`, `legal_actions`, `observe`), seat specs and bots; ruff and pyright as in the repo.
- The service is a thin layer: no rules in it beyond calling the engine.
- The frontend lives only in the submodule `frontend/` and changes only through Lovable (frontend lane rules in `docs/team/software-engineer.md`).
- Public repo: no secrets in commits, issues or the Lovable prompt.

## Order

1. Rule fix A (pop the stash, fix the baseline test).
2. Rule fix B.
3. Rule fix C.
4. The local game service (needs A to C, so its labels and views are final).
5. The submodule `frontend/` and the `Lovable project:` line (needs the owner's Lovable project and GitHub repo).
6. The brew screen, connected to the service (needs 4 and 5).
7. The plain screens for the other phases, start and end screens, and the event log (needs 6).

## Left to the builder

- Service library, module layout, endpoint names (the content of the view is fixed above).
- Everything visual inside the frame above: palette, tile size, fonts, sprite style, the exact spiral geometry, animation timing.
