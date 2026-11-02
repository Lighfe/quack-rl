# Game parts on screen, ruleset v2.3 and saved web games: implementation plan

> For agentic workers: this plan becomes GitHub issues (see Intake in `docs/process.md`). Do not run it with subagent-driven-development or executing-plans (`AGENTS.md`).

**Goal:** the round card, the bonus die and the point board are visible game parts; the cauldron gets the screen; the black chip rule is fixed in ruleset v2.3 with whole-step droplets; every web game is saved.

**Architecture:** one default-lane change makes v2.3 the only ruleset (retiring v2.1 and v2.2, whole-step droplet, record schema 3, observation layout 9). Three default-lane tasks then extend the service: view fields for the board and the die plus cleaner effect texts, saved web games, plain log sentences. Six frontend tasks go through Lovable one after the other.

**Tech stack:** Python 3 (engine, FastAPI service, pytest via `uv run --with pytest pytest`); frontend React + TypeScript in the Lovable project, `bun`.

**Spec:** `docs/specs/2026-10-27-game-parts-and-ruleset-v2-3.md`

## Global constraints

- Every message to Lovable says that the look is free, in the pixel-art style of the game, and that no earlier design, mockup or picture is a template. No image is sent to Lovable as a template. Criteria fix content, behaviour, sizes and contrast.
- No game rule in the app: legality, prices, die rewards, rat tails and points come from the service view.
- Every animation is short and has a reduced-motion form (no flight, the end state shows at once).
- Frontend lane: changes only through Lovable; the app uses `bun`; frontend checks `cd frontend && bun install --frozen-lockfile && bun run test && bun run build`.

## Review focus

1. Black chip: equal counts 0 and 0 give nothing; 1 and 1 give each droplet +1; 2 and 1 give the first droplet +1 and 1 ruby, the second nothing; an exploded pot counts.
2. No `halves` and no `droplet_halves` left in `src/`, events, records or the observation names.
3. A web game whose window is closed mid-round leaves a record of every step so far, and a finished web game replays with `verify_game` returning `[]`.
4. The die rolls in the opponent's cauldron when the opponent rolls; no die for an exploded pot.

---

### Task 1: Ruleset v2.3: black chip rule, whole-step droplet, v2.1 and v2.2 retired

**Lane:** default. Load `.agents/skills/quack_rule_changes/SKILL.md` first.

- New `src/quack_rl/rules/v2.3.toml` from v2.2, `version = "v2.3"`. `SUPPORTED_RULES_VERSIONS == ("v2.3",)`; `"v2.3"` is the default `rules` value everywhere (`tests/test_rules_defaults.py`).
- v2.1 and v2.2 move to `archive/` (ruleset files, `docs/rules/rules-v2.1.md`, `docs/rules/rules-v2.2.md`, golden records `v2_1_random_seed7.jsonl`, `v2_2_random_seed7.jsonl`, `v2_1_bots_results.csv` and the tests that only test them). Moved, not deleted.
- `Ruleset.ruby_step` is removed; the ruby step after the shop always runs.
- Black (`src/quack_rl/components/chips.py`): `a >= 1 and a == b` → droplet +1; `a > b` → droplet +1 and 1 ruby; else nothing.
- Whole-step droplet: `PlayerState.droplet` replaces `droplet_halves`; `PotRoundEnd.droplet` replaces `droplet_halves`; die faces, card effects (`card_drop`), the ruby drop and purple count whole steps. Events carry `drop` instead of `halves`. `start_field` uses `droplet` directly.
- Record schema version 3 (`RECORD_SCHEMA_VERSION`); no reader for version 2.
- Observation layout 9 (`BOARD_LAYOUT = 9`): `droplet` (whole steps) replaces `droplet_halves`; `tests/fixtures/golden/layout8_sample.json` is replaced by a layout 9 sample.
- New golden record `tests/fixtures/golden/v2_3_random_seed7.jsonl` (written by `tests/fixtures/make_golden.py`), replays with `verify_game == []`.
- `docs/rules/rules-v2.3.md` (from v2.2: black section, droplet text, ruby step without switch), `README.md`, the skill texts name v2.3.

### Task 2: View: point board, last bonus die roll, effect texts without "Advance by its value"

**Lane:** default. Blocked by task 1.

- `seat_view` gets `board: {"fields": int, "laps": int, "rat_tails": list[int]}` from `rs.point_board`.
- `game.last_roll`: `None` before the first resolve of the game, else `{"round": int, "rolls": [{"seat", "face", "text"}]}` for the latest resolve; `rolls` is empty when nobody rolled. `text` is a plain reward text such as "Orange 1 into the bag", "Droplet +1", "+2 points".
- Spellbook effect texts (`src/quack_rl/rules/spellbook.py`) drop "Advance by its value" (and its joining words); orange's effect text is `""`. `docs/rules/rules-v2.3.md` chip table the same.

### Task 3: Save every web game as a record

**Lane:** default. Blocked by task 1.

- `GameSession` writes a record with `GameRecorder` into `LocalRecordStore(<record root>)`, mode `"web"` (added to the header `mode` literal), seats, seed, rules version, started time.
- Each step is written and flushed when it happens; a finished game writes the final line. A service stopped mid-game leaves the steps so far.
- `quack-rl serve --out <path>` (default `data/records`); `create_app(record_root=...)`. Tests use a temporary folder.
- A finished web game with two bot seats replays with `verify_game == []`.

### Task 4: Plain log sentences

**Lane:** default. Blocked by task 1.

- `event_text` gives one plain sentence per event kind; fields that are 0 or empty are left out; no internal names (`halves`, `pot_round_end`, component ids like `black@1`, raw chip ids like `orange_1` — chips by name such as "Orange 1"). Every event kind the engine emits has a sentence (a test runs a seeded game and checks every line).

### Task 5: Brew screen clean-up

**Lane:** frontend. No blocker.

- The cauldron view takes most of the screen; the bag side is thin.
- Each sack is a small bag; hover (tap on touch) expands it into the big sack with its contents; the sack may be redesigned.
- Removed: box and "White chips" title around the white total; box around coins, points, rubies; "P1" title; "P1 – Brewing" title.
- Money and point numbers in the pot fields bigger (at least 1.4 × today's smallest size) and centred in the field; colours unchanged.

### Task 6: Round card as a scroll (existing #240, rewritten)

**Lane:** frontend. Blocked by task 5.

- At the start of each round (`game.card` id or `game.round` changes) the card appears big over the screen as a papyrus scroll with `game.card.text` (not a card showing the element name).
- A card with a choice: the legal choice actions are buttons on the scroll; it stays until one is sent.
- A card with no choice: the scroll waits for a click before the brew screen takes input.
- A control reopens the scroll during the round.

### Task 7: Bonus die in the roller's cauldron

**Lane:** frontend. Blocked by tasks 2 and 6.

- When `game.last_roll` changes to a new round with rolls, a die rolls in the cauldron of each rolling seat, in its own cauldron (the opponent's smaller cauldron when the opponent rolls), one after the other on a tie; it lands on `face`, then shows `text`.
- No die when `rolls` is empty; never for a seat not in `rolls`.

### Task 8: Point board tab

**Lane:** frontend. Blocked by tasks 2 and 7.

- Third tab "Point board". Track of fields `0..board.fields-1` around the edge as numbered tiles; a rat between field `t` and `t+1` for each `t` in `board.rat_tails`; one marker per seat at `points mod fields`; a lap marker per seat showing `0` or `50` (`fields × floor(points / fields)`); round flames in the middle, `game.rounds` flames, round `game.round` lit.
- No start bonus or tail count is shown.

### Task 9: Ingredient notes from scratch, status in the shop

**Lane:** frontend. Blocked by tasks 2 and 8.

- Notes redesigned from scratch with the owner's criticism and the original instruction (spec section 5); notes vary slightly from each other; an empty effect text shows no effect line.
- In `shop` and `ruby` phases, the player's money, points, rubies and flask are visible next to the dialogue box and update after each action.

### Task 10: Back to the cauldron with a clean-up animation

**Lane:** frontend. Blocked by task 9.

- When a new round starts after the shop or ruby step, the Cauldron tab is selected by itself.
- The pot chips fly back into the own bag, then the pot is empty; under reduced motion, no flight.
