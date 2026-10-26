# Rule fixes and the brew screen: implementation plan

Each task becomes one GitHub issue (`docs/task-template.md`) of one stage, run by the loop in `docs/process.md`. Steps use checkbox (`- [ ]`) syntax.

**Goal:** fix three v2.1 rule issues, add a local HTTP game service, and play a full game in a Lovable-built browser app whose brew screen shows the pot, the bag and the seats.

**Architecture:** the Python engine stays the only rulebook. A thin service (`quack_rl.web`) wraps `new_game`/`step`/`legal_actions`/`observe` behind JSON endpoints and drives automatic phases and bots. The Lovable app in the submodule `frontend/` renders the per-seat view and posts actions.

**Tech stack:** Python 3.12, pydantic, typer, FastAPI + uvicorn (new dependency group `web`), pytest; React + TypeScript + Tailwind (Lovable, TanStack router).

**Spec:** `docs/specs/2026-10-25-rule-fixes-and-brew-screen.md`. Lovable first prompt and brief: `docs/specs/2026-10-25-lovable-first-prompt.md`. Lovable's agreed screen plan: `.lovable/plan.md` in the frontend repo.

## Global constraints

- Ruleset `v2.1` is changed in place (only ruleset, no released records). Load the `quack_rule_changes` skill for tasks 1 to 3.
- Every event that changes rubies carries `total` (the ruby balance after the event).
- Golden files change only on purpose: `uv run python tests/fixtures/make_golden.py`, then update the pinned values in `tests/test_golden_v2_1.py`.
- After `ruff --fix` / `ruff format`, restore files outside the task.
- Test command: `uv run --with pytest pytest` (full, the done gate); inner loop `uv run --with pytest pytest -m "not slow"`.
- The service holds no rule logic; the frontend holds no rule logic and no Lovable Cloud.
- No text in the frontend that is not about a game component.

## Review focus

1. A human-vs-bot game where the human stops first: the bot must brew on without another request (task 4 test `test_bot_brews_on_after_human_stops`).
2. A double click on Draw: one draw only (task 4 test `test_duplicate_revision_is_rejected`).
3. The last round with an exploded player who takes money: no shop, money and rubies become points (task 2 test `test_last_round_explosion_take_money_then_game_end`).
4. A shop where a player has nothing to do at the start (no money, no rubies): never asked (task 3 test `test_shop_skips_player_with_nothing_to_do`).
5. A scoring field near 53: the window repeats field 53 and matches `ahead` (task 4 test `test_window_at_track_end_matches_ahead`).

---

### Task 1: No droplet half steps (pop the stash)

**Files:**
- From `stash@{0}` ("ruby-instead-of-half-droplet"): `src/quack_rl/components/{base,chips}.py`, `src/quack_rl/engine/{board,cards,resolve,shop,state}.py`, `src/quack_rl/rules/{model.py,v2.1.toml}`, `src/quack_rl/rl/encode.py`, `src/quack_rl/report.py`, `src/quack_rl/cli/render.py`, `docs/rules/rules-v2.1.md`, `README.md`, `.agents/skills/quack_rule_changes/{colour-change,project-map}.md`, golden fixtures, tests
- Fix: `src/quack_rl/report.py` and/or `tests/test_baseline_maximum.py`

**Interfaces:**
- Produces: `Component.round_end_rubies(chip, position_from_end) -> int`; `PotRoundEnd.rubies: int`; die face kind `"rubies"` with `DieFace.rubies: int` (face id `ruby_1`); `board.die_events(seat, p, face) -> list[dict]`; events `round_end_bonus {chip, rubies, total}`, `pot_round_end {component, points, halves, rubies, total}`, extra `ruby {rubies, total}` after a `die` event of a ruby face. `PlayerState.round_end_halves` is gone; layout 8 has 1528 entries.

- [ ] **Step 1:** `git stash pop` on a clean tree at current `main`; resolve conflicts if any (the stash was made on `fabaa44`).
- [ ] **Step 2:** Run `uv run --with pytest pytest tests/test_baseline_maximum.py -v`. Expected: `test_simulation_matches_the_calculated_field_table_points` FAILS (known).
- [ ] **Step 3:** Find why the calculated maximum (`realistic_baseline_maximum` / `_expected_points` in `report.py`) and the simulation differ now. The likely cause: the chain ignored green droplet halves before and now rubies; the simulated `points` bot may spend rubies (ruby drop) and move its droplet. Make the calculation model what the bot does (or the bot not spend rubies, if the issue #178 decision "baseline never buys" covers ruby drops), so both agree within the test's tolerance. Do not loosen the tolerance.
- [ ] **Step 4:** Run the full test command. Expected: all pass.
- [ ] **Step 5:** Check the stash is gone (`git stash list` empty). Commit.

### Task 2: The last round ends without a shop; rubies become points

**Files:**
- Modify: `src/quack_rl/engine/shop.py` (`_end_round` -> extract `end_game`), `src/quack_rl/engine/resolve.py:99`, `src/quack_rl/engine/choice.py:33`, `src/quack_rl/rules/model.py` (field), `src/quack_rl/rules/v2.1.toml`, `docs/rules/rules-v2.1.md` (4.3 point 6, 5. Game end), `src/quack_rl/cli/render.py:84` (round banner text), golden files
- Test: `tests/test_engine_last_round.py` (new)

**Interfaces:**
- Produces: `Ruleset.last_round_ruby_divisor: int` (ge=1, v2.1 value 2); `engine.shop.end_game(state, rs, events) -> None` (ruby points, then `game_end`); event `ruby_points {seat, rubies, points}` per seat, p1 then p2, before `game_end`.

- [ ] **Step 1: Write the failing tests** in `tests/test_engine_last_round.py`:
  - `test_last_round_resolve_goes_to_game_over`: state in RESOLVE of round `rs.rounds`, no explosion -> after `step`, `phase is Phase.GAME_OVER`, no SHOP.
  - `test_rubies_become_points_rounded_down`: p1 5 rubies, p2 0 -> events have `ruby_points` p1 `{rubies: 5, points: 2}`, p2 `{rubies: 0, points: 0}`, both before `game_end`; rubies end at 0.
  - `test_ruby_points_stop_at_max_points`: p1 at `max_points - 1` with 4 rubies -> points == `max_points`.
  - `test_last_round_explosion_take_money_then_game_end`: p1 exploded, chooses `take_money` -> money // 5 points, then GAME_OVER without SHOP.
  - `test_short_game_applies_in_its_last_round`: `rounds=4` ruleset copy, same as above in round 4.
  - `test_v21_ruleset_has_ruby_divisor_2`: `load_ruleset("v2.1").last_round_ruby_divisor == 2`.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Add the field; extract `end_game` from `_end_round`; in `apply_resolve` (no explosion) and `apply_choice` call `end_game` instead of entering SHOP when `state.round == rs.rounds`. Ruby points use `add_points` (the cap).
- [ ] **Step 4:** Run them. Expected: PASS. Regenerate the golden files; update `FINAL_POINTS`/`FINAL_FIELDS` in `tests/test_golden_v2_1.py` from the new `game_end` event. Update the rules document and the CLI round banner ("money and rubies become points").
- [ ] **Step 5:** Full test command passes. Commit.

### Task 3: Shop order in the CLI and no needless `done`

**Files:**
- Modify: `src/quack_rl/cli/human.py` (`key_map`), `src/quack_rl/engine/shop.py`, `docs/rules/rules-v2.1.md` (4.4)
- Test: `tests/test_shop_end.py`, `tests/test_cli_play.py`

**Interfaces:**
- Produces: `engine.shop.close_idle_shops(state, rs) -> None`: sets `shop_done` for every player whose shop legal set would be only `["done"]`; called when the SHOP phase starts and after each shop step. `legal_actions` keeps the engine order `done, buys, ruby_drop, refill_flask`.

- [ ] **Step 1: Write the failing tests:**
  - `test_cli_menu_lists_buys_before_ruby_drop_and_refill` (`test_cli_play.py`): `list(key_map(["done", "buy:orange_1", "ruby_drop", "refill_flask"]).values()) == ["done", "buy:orange_1", "ruby_drop", "refill_flask"]`.
  - `test_shop_skips_player_with_nothing_to_do` (`test_shop_end.py`): entering SHOP with p1 money 0, rubies 0, full flask -> `legal_actions(..., "p1") == ["wait"]`.
  - `test_second_chip_buy_ends_shop_without_rubies`: p1 buys 2 chips, has 1 ruby -> p1 not asked again.
  - `test_done_stays_when_ruby_drop_possible`: after 2 chip buys with 2 rubies -> legal is `["done", "ruby_drop"]`.
  - `test_both_idle_shops_end_the_round`: both players idle -> the round ends without shop actions.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Change `key_map` so buy keys are inserted right after `done` (before `k`/`l`); add `close_idle_shops` and call it in the places named above (resolve/choice when entering SHOP, `apply_shop` after the actions).
- [ ] **Step 4:** Run them. Expected: PASS. Regenerate golden files, update pinned values. Full test command passes. Commit.

### Task 4: The local game service

**Files:**
- Create: `src/quack_rl/labels.py`, `src/quack_rl/web/__init__.py`, `src/quack_rl/web/session.py`, `src/quack_rl/web/view.py`, `src/quack_rl/web/app.py`
- Modify: `src/quack_rl/cli/human.py` (use `action_label`), `src/quack_rl/cli/main.py` (`serve`), `pyproject.toml` (group `web`: `fastapi`, `uvicorn`; dev: `httpx` for the test client), `AGENTS.md` (`QA groups: rl, web`), `README.md` (section "Web service")
- Test: `tests/test_labels.py`, `tests/test_web_service.py`

**Interfaces:**
- Consumes: `new_game`, `step`, `legal_actions`, `needs_actions`, `observe` (`ahead`), seat specs of `quack-rl play` (`make_seat` or its equivalent in `cli/main.py`), `render_step` text lines.
- Produces:
  - `labels.action_label(action: str, rs: Ruleset, state: GameState | None = None, seat: str = "") -> str` — moved from `HumanSeat._describe`; the CLI calls it.
  - `web.session.GameSession(rs, seats: dict[str, Seat], seed: int | None)` with `.revision: int`, `.submit(seat: str, action: str, revision: int) -> None` (raises `IllegalAction`, `StaleRevision`), `.advance() -> None` (steps through CARD/RESOLVE, `wait`-only seats and bots until a human must act or GAME_OVER), `.events_for(seat) -> list[dict]`.
  - `web.view.seat_view(session, seat: str) -> dict` with keys `game, you, to_act, seats, window, chips, legal, hand, log` (content as in the spec: `game.revision`, effective `explosion_limit`, card `{id, effect, text}`; `seats[]` list with `pot[] {order, chip, colour, value, from, landing}` and `bag` per chip id; `window[] {field, money, points, ruby}`; `legal[] {id, label}`).
  - HTTP: `POST /games` `{p1, p2, rounds?, seed?}` -> `{game_id}`; `GET /games/{id}/view?seat=` -> view; `POST /games/{id}/actions` `{seat, action, revision}` -> view; 400 `{"error": "illegal_action", "legal": [...]}`; 409 `{"error": "stale_revision", "revision": n}`; CORS for `http://localhost:*`.
  - CLI: `uv run --group web quack-rl serve [--port 8000]`.

- [ ] **Step 1: Write the failing tests** (`tests/test_labels.py`, `tests/test_web_service.py` with FastAPI `TestClient`):
  - `test_cli_and_service_labels_are_the_same_function`: the CLI menu text for `ruby_drop` and `buy:orange_1` equals `action_label(...)` (`"ruby drop: 2 rubies, droplet +1"`, `"buy orange_1 (3)"`).
  - `test_two_bot_game_ends_with_a_winner`: create `bot:random` vs `bot:random`, view shows `phase == "game_over"` and a winner.
  - `test_new_human_game_waits_at_first_decision`: `human` vs `bot:random` -> p1's view has `"p1" in to_act`, phase `brew`, legal ids `["draw"]`, `game.revision` >= 1 (the card phase was stepped at creation).
  - `test_bot_brews_on_after_human_stops`: human stops at once -> the response view shows p2 no longer `brewing` or the phase past BREW, without a further request.
  - `test_illegal_action_gives_400_with_legal_list`.
  - `test_duplicate_revision_is_rejected`: two `draw` posts with the same revision -> second gives 409; p1 pot has one chip more, not two.
  - `test_view_of_p2_has_no_p1_hand_or_hidden_draw`: force a blue hand for p1 (seeded or scripted chance) -> p2's view `hand == []` and its `log` has no p1 hand chip ids.
  - `test_window_equals_observe_ahead` and `test_window_at_track_end_matches_ahead` (field 53 repeats).
  - `test_pot_entries_have_order_from_landing`: `from` of entry n == `landing` of entry n-1 + 1 (first: start field + 1).
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement in the files above; games in a dict in memory, one lock per game.
- [ ] **Step 4:** Run them. Expected: PASS. `uv run --group web quack-rl serve` starts and `curl -s -X POST localhost:8000/games -H 'content-type: application/json' -d '{"p1":"bot:random","p2":"bot:random"}'` returns a `game_id`. Full test command passes. Commit.

### Task 5: The `frontend/` submodule and the Lovable project line

**Files:**
- Create: `.gitmodules`, `frontend` (submodule of `https://github.com/Lighfe/quacks-frontend`)
- Modify: `AGENTS.md` (line `Lovable project: 34424226-c265-4c0c-a695-30527093b97c`, and a "Frontend" command line: `cd frontend && npm install && npm run dev`), `README.md` (section "Frontend": start the service, then the app, open `?seat=p1`)

- [ ] **Step 1:** `git submodule add https://github.com/Lighfe/quacks-frontend frontend`; pin to the current `origin/main`.
- [ ] **Step 2:** Check: `git submodule status` shows `frontend` at a commit; `frontend/.lovable/plan.md` exists; `frontend/package.json` has name `quacks-frontend`.
- [ ] **Step 3:** Add the lines to `AGENTS.md` and `README.md`. Full test command passes (no test reads `frontend/`). Commit.

### Task 6 (Lane: frontend): The brew screen connected to the service

Driven through Lovable (`docs/team/software-engineer.md`, lane `frontend`). The Lovable project knowledge holds the brief and the rules summary; `.lovable/plan.md` holds the agreed component plan, the `PotLayout` interface and the data module interface.

**Goal sent to Lovable:** build the brew screen from the brief in `docs/specs/2026-10-25-lovable-first-prompt.md` (section "The brief") and `.lovable/plan.md`, with both data backends: `mock` (canned views: brewing, blue hand, after a white chip with the flask, exploded) and `http` (default `http://localhost:8000`, configurable).

**Acceptance (checked by QA by reading the pinned frontend commit and running it against the service):**
- [ ] `npm run build` in `frontend/` succeeds.
- [ ] One pot layout module (`PotLayout`: `field(n) -> {center, outline}`, 54 fields, square snake spiral, field 0 in the centre, counter-clockwise); no other component computes field positions.
- [ ] No game rule in the app: no landing, explosion, score or legality computation (grep the source for the data module as the only service access).
- [ ] The pot fills `from..landing` in the chip colour, outlines the landing field with the value, lights the 11 window fields with money/points/ruby, and darkens the rest; other seats' pots show no window, also enlarged.
- [ ] Draw / Stop / Use flask / Card 17 buttons are enabled only when in `legal`; keys d/s/f/u; blue hand chips are selectable (`play:<i>`) with the two put-back buttons; any other legal action is a plain labelled button.
- [ ] Seats are rendered from the `seats` list (no fixed pair); `?seat=p1` picks the seat; hot seat switches to the seat in `to_act`.
- [ ] Chip-drop and explosion-smoke animations exist; off with reduced motion.
- [ ] No text that is not about a game component (no taglines, no flavour text, also not in page meta).
- [ ] Against `uv run --group web quack-rl serve`, a game `human` vs `bot:random` can be played through a full brew round in the browser (QA: run both and follow the steps in the issue's DONE comment).
- [ ] The submodule pointer is pinned to Lovable's merge commit.

### Task 7 (Lane: frontend): Start screen, plain phase screens, event log, end screen

**Acceptance:**
- [ ] Start screen: choose p1 and p2 (`human`, `bot:random`, and the heuristic bots `bot:draw20-pts1-points`, `bot:draw30-pts4-balanced`, `bot:draw20-pts4-blue`), rounds (default 9), start -> `POST /games`.
- [ ] Every non-brew phase (card choice, restart, resolve, explosion choice, shop) shows the service's `legal` actions as plain labelled buttons; nothing else is needed to act.
- [ ] The event log shows `log` text lines, newest at the bottom, per seat.
- [ ] End screen: final points per seat, the winner, a "New game" button.
- [ ] A full 9-round game `human` vs `bot:random` can be played to the end in the browser against the service; and a hot-seat game `human` vs `human` reaches round 2.
- [ ] `npm run build` succeeds; the submodule pointer is pinned.

---

## Order and blockers

1 -> 2 -> 3 -> 4 (4 needs 1 to 3 for final labels and views). 5 has no blocker. 6 needs 4 and 5. 7 needs 6.
