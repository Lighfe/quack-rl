# Brew screen round 2, the ruby step and the shop screen: implementation plan

> For agentic workers: this plan becomes GitHub issues (see Intake in `docs/process.md`). Do not run it with subagent-driven-development or executing-plans (`AGENTS.md`).

**Goal:** the owner play-tests a full round in the browser: the reworked square pot, readable numbers, recognisable icons, a ruby step after the shop, Cauldron / Ingredients tabs and a themed dialogue box, with the Lovable preview working out of the box.

**Architecture:** the rule change (ruby step) is a new ruleset version v2.2 with a new phase in the engine, following `.agents/skills/quack_rule_changes/SKILL.md`. The service view gains a shop catalogue for the Ingredients tab. The frontend tasks go through Lovable one after the other, after the QA start fix (#230).

**Tech stack:** Python 3 (engine, FastAPI service, pytest via `uv run --with pytest pytest`); frontend React + TypeScript in the Lovable project, `bun`.

**Spec:** `docs/specs/2026-10-27-brew-screen-round-2-and-shop.md`

## Global constraints

- Every message to Lovable says that any mockup or look in the issue is a rough orientation only, and asks Lovable to design the look freely in the pixel-art style of the game (big creative freedom). Criteria fix only content, behaviour, sizes, gaps and contrast.
- No game rule in the app: prices, availability, legality, effects and landing fields come from the service view.
- Dialogue texts: shop "What would you like to buy?", ruby step "What would you like to do with your rubies?". No invented flavour lines.
- Tab names: "Cauldron" (left, main view) and "Ingredients" (right).
- No CORS wildcard such as `*.lovable.app`.
- Frontend lane: changes only through Lovable; the app uses `bun`; frontend tests `cd frontend && bun install --frozen-lockfile && bun run build && bun run test`.

## Review focus

1. A player with exactly 2 rubies and an empty flask in the ruby step: both `ruby_drop` and `refill_flask` are offered; after one, the other is gone and the player is closed automatically.
2. Both players have nothing to do in the shop and in the ruby step: the round ends in the same step, with no step that waits for actions.
3. The last round: no shop, no ruby step, rubies become points (unchanged).
4. v2.1 games (the golden records) still replay unchanged after v2.2 exists.
5. The Ingredients tab in a round where some colours are below their minimum round: faded, not hidden, and the buy buttons show only legal buys.

---

### Task 1: QA starts the frontend app with `--host 127.0.0.1` (existing #230)

As written in #230. Lane default, docs only. No blocker.

### Task 2: The service allows this project's Lovable preview origin by default

**Lane:** default.

**Files:** `src/quack_rl/web/app.py` (the `DEFAULT_ORIGINS` tuple), `README.md` ("Web service" section), `tests/test_web_service.py`.

**Interfaces:** produces the constant `LOVABLE_ORIGINS` in `src/quack_rl/web/app.py`, part of `DEFAULT_ORIGINS`.

- Test first: `origin_regex()` fully matches `https://id-preview--34424226-c265-4c0c-a695-30527093b97c.lovable.app` and does not match `https://evil.lovable.app`, `https://id-preview--34424226-c265-4c0c-a695-30527093b97c.lovable.app.evil.com` or `http://id-preview--34424226-c265-4c0c-a695-30527093b97c.lovable.app`. A CORS preflight `OPTIONS /games` from the preview origin, with `Access-Control-Request-Private-Network: true`, answers 200 with that origin in `access-control-allow-origin`.
- `LOVABLE_ORIGINS` holds exact, escaped origins of project `34424226-c265-4c0c-a695-30527093b97c` only: the preview origin above, and the editor preview frame origin if the engineer can confirm it (for example from the browser console of the editor); an unconfirmed origin is not added and is named in `## Engineer: DONE`.
- README: a short step list "Play-test in the Lovable preview" (start the service with `uv run --group web quack-rl serve`, open the preview URL, start a game). The `--allow-origin` example with `[a-z0-9-]+\.lovable\.app` is replaced by an example that is not a wildcard over all Lovable sites.

### Task 3: Ruby step after the shop (ruleset v2.2)

**Lane:** default. Load `.agents/skills/quack_rule_changes/SKILL.md` first.

**Files:** `src/quack_rl/rules/v2.2.toml` (new, copy of v2.1 with `version = "v2.2"` and `ruby_step = true`), `src/quack_rl/rules/model.py` (field `ruby_step: bool = False`), `src/quack_rl/engine/state.py` (`Phase.RUBY = "ruby"`, `PlayerState.ruby_done: bool = False`), `src/quack_rl/engine/actions.py` (`legal_actions`), `src/quack_rl/engine/shop.py`, `src/quack_rl/engine/game.py` (`needs_actions`, `step`), `src/quack_rl/bots/heuristic.py`, the CLI menu, `docs/rules/rules-v2.2.md` (new, from v2.1 with the changed shop section), `README.md`, every default `rules` value (see the skill: `tests/test_rules_defaults.py`), the RL encoding (`PHASES` grows by one), the golden fixtures that the skill says to regenerate for the new default. v2.1 stays playable and its recorded games replay unchanged.

**Interfaces:**
- Produces `Phase.RUBY` (value `"ruby"`), `Ruleset.ruby_step: bool`, `PlayerState.ruby_done: bool`, `close_idle_ruby(state, rs, events) -> None` and `apply_ruby(state, rs, actions, events) -> None` in `src/quack_rl/engine/shop.py`.
- The view's `game.phase` is `"ruby"` in the ruby step; the action ids stay `ruby_drop`, `refill_flask`, `done`.

Behaviour with `ruby_step = true`:
- SHOP legal set: `[DONE, *buys]`. RUBY legal set: `[WAIT]` when `ruby_done`, else `[DONE, *([RUBY_DROP] if rubies >= ruby_cost), *([REFILL_FLASK] if not flask_full and rubies >= ruby_cost)]`.
- When every shop is closed, the phase becomes RUBY and `close_idle_ruby` runs (auto `done` with `"auto": True` for a seat whose legal set is `[DONE]`). When every seat is `ruby_done`, `_end_round` runs (it resets `ruby_done`).
- With `ruby_step = false` (v2.1) nothing changes.

Tests (names and the key assertion):
- `test_v2_2_shop_offers_no_ruby_spends`: a seat with 4 rubies and an empty flask in SHOP has no `ruby_drop` and no `refill_flask` in its legal set.
- `test_v2_2_ruby_step_follows_shop`: after both seats choose `done` in SHOP, `state.phase is Phase.RUBY`.
- `test_v2_2_ruby_step_two_rubies_empty_flask`: with exactly 2 rubies and an empty flask both spends are legal; after `refill_flask` the seat has 0 rubies and is auto-closed.
- `test_v2_2_ruby_step_skipped_when_nobody_can_pay`: both seats under 2 rubies: shop `done` leads to the next round's CARD phase in the same step.
- `test_v2_2_last_round_has_no_ruby_step`: round 9 ends the game as in v2.1.
- `test_v2_1_unchanged`: the v2.1 golden record replays.
- A masked random v2.2 game stays inside the RL observation space (skill, "Known mistakes").

### Task 4: Shop catalogue in the service view

**Lane:** default. Blocked by Task 3.

**Files:** `src/quack_rl/web/view.py`, `tests/test_web_service.py`; the effect texts in the ruleset or spellbook module (engineer's choice, one place, used by the view).

**Interfaces:** produces a top-level view field `ingredients`: a list, one entry per chip colour of the ruleset in ruleset order, each `{"colour": str, "effect": str, "chips": [{"chip": str, "value": int, "price": int | None, "min_round": int | None, "available": bool}]}`. `price` and `min_round` are `None` for a chip that is not in the shop (white). `available` is true when the chip is in the shop and `round >= min_round`. `effect` is one line, at most 60 characters.

Tests:
- `test_view_ingredients_round_1`: in round 1 of v2.2, yellow and purple chips have `available == False`, orange 6 has `price == 22` and `available == True`, white chips have `price is None`.
- `test_view_ingredients_same_for_both_seats`: p1 and p2 get the same `ingredients`.
- Every colour of the ruleset appears once, with a non-empty `effect`.

### Task 5: Pot: the square spiral back, a little more air between loops, readable numbers

**Lane:** frontend. Blocked by Task 1 (#230).

Acceptance (for the issue):
- The layout is the square snake spiral of frontend commit `a7f1fee` (`src/lib/pot-layout.ts`): field 0 in the centre, runs of 1, 1, 2, 2, 3, 3, … counter-clockwise; every field an axis-aligned square (no rotation transform on any field).
- In layout units: field side 10, gap along the path 2, gap between one loop and the next from 3 to 4 inclusive. A unit test of the layout checks all three for every pair of neighbouring fields.
- The pot's bounding box fills its panel (no side margin larger than one field side at the default width of `/?mock=playtest`).
- The thinner field border of #219 and the chip trail stay.
- Money numbers yellowish, point numbers purplish, each with a contrast of at least 4.5:1 against the field fill and a rendered font size of at least 9 CSS px on `/?mock=playtest` (checked in a headless browser).

### Task 6: Icon colours: purple points star, green flask

**Lane:** frontend. Blocked by Task 5.

Acceptance: the points icon is purple and shaped as a five-pointed star; the flask is green (hue clearly apart from the blue droplet); the empty flask is drawn tilted by a small angle (5 to 20 degrees). Applies in the seat panel and the window-field icons. Screenshot on `/?mock=playtest`.

### Task 7: Cauldron and Ingredients tabs, shop and ruby dialogue box

**Lane:** frontend. Blocked by Tasks 3, 4 and 6.

Acceptance:
- The top area has two tabs, "Cauldron" (left, pot icon) and "Ingredients" (right, book icon), reachable in every phase. Cauldron is the default; when `game.phase` becomes `shop`, the Ingredients tab opens by itself; the player can switch back to Cauldron at any time, and the pot shows this round's chips in the shop and in the ruby step.
- The Ingredients tab shows one witchy parchment or papyrus note per entry of the view's `ingredients` (not an open book), with each chip drawn with its value inside and its price with a coin icon below; a colour whose chips are all `available == false` is faded out, with no "from round" text; the effect line is shown.
- The bottom area in phase `shop` is a themed dialogue box asking exactly "What would you like to buy?" with one button per `buy:<chip id>` entry of `legal` (chip with value inside, price with a coin icon) and a `done` button. In phase `ruby` it asks exactly "What would you like to do with your rubies?" with buttons for `ruby_drop`, `refill_flask` (each with its ruby price) and `done`, as far as they are in `legal`.
- Mock views `/?mock=shop` (round 1, so yellow and purple are faded) and `/?mock=ruby` exist for screenshots.
- The Lovable message carries the creative-freedom sentence (Global constraints).

### Task 8: Start screen names the cause of a failed connection

**Lane:** frontend. Blocked by Tasks 2 and 7.

Acceptance: when `POST /games` fails with a network or CORS error, the start screen says that the local game service is not reachable from this page and shows the command `uv run --group web quack-rl serve`. A unit test with a mocked failing fetch checks the text.

### Task 9: Bag draw animation (existing #231)

As written in #231, with the mock route it names. Blocked by Task 8 (frontend tasks run one at a time).
