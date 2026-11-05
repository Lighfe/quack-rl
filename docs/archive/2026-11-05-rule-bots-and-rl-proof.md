# Rule bots and RL proof of concept: implementation plan

> Each task below becomes one GitHub issue in `docs/task-template.md` format (see `docs/process.md`). Do not run this plan with subagent-driven-development or executing-plans.

**Goal:** Replace the outdated heuristic bot with one rule-based bot with three shop strategies, and prove on v2.3 that the environment serves model-free online, self-play, offline and model-based (planning) agents, each playable in the tournament and the browser.

**Architecture:** A new `RuleBot` in `src/quack_rl/bots/` keeps the shared brew, card and ruby rules of `HeuristicBot` and adds a seeded, softmax shop pseudo-policy per strategy. Trained and planning agents live in `data/agents/<name>/agent.json` and load through one seat form, `agent:<name>`, used by the CLI, the tournament and the web service. The service publishes its opponents at `GET /opponents`, and the Lovable start screen reads it.

**Tech Stack:** Python 3.12, uv, pytest, gymnasium/pettingzoo, stable-baselines3 + sb3-contrib (MaskablePPO), torch (BC, CQL), FastAPI, Lovable frontend (submodule `frontend/`, bun).

**Spec:** `docs/specs/2026-11-05-rule-bots-and-rl-proof.md`

## Global Constraints

- Ruleset v2.3 only; observation layout `BOARD_LAYOUT` in `src/quack_rl/rl/encode.py` (9, or the number #212 sets).
- No legacy shims: no alias from old bot names (`draw20-pts1-points`) to new ones; old names are rejected.
- No per-strategy branches in the shared bot rules; a strategy is data plus one scoring function.
- No agent sees hidden information (the opponent's hidden hand, the order of any bag or of the card deck).
- Each training run: at most about one hour of wall time on the owner's laptop, CPU.
- Test command `uv run --with pytest pytest` (the "done" gate); fast subset `uv run --with pytest pytest -m "not slow"`. Do not add `-q`.
- Load the `quack_rule_changes` skill for any change to the observation encoding (task 1).
- No secrets in commits, issues or reports.

## Review Focus

1. An old bot name (`bot:draw20-pts1-points`) or an unknown strategy gives a clear error that names the new form `bot:<strategy>-draw<limit>-pts<round>`. Test in task 3.
2. Shop corner cases: nothing affordable → `done`; only one chip affordable for `spendmost`; a second chip of the colour already bought this round is never chosen; `blackpurple` with a third black after two earlier blacks is not preferred. Tests in task 2.
3. An agent folder made for another ruleset or layout, or with a weights file whose hash does not match, fails to load with a clear error. Test in task 5.
4. With no `data/agents/` folder, or an empty one, `GET /opponents` lists the three presets and nothing else, and a broken agent folder is skipped with a log line instead of an HTTP 500. Test in task 6.
5. The planner's choice does not depend on hidden information: two states that differ only in the opponent's hidden hand and in bag order give the same choice with the same planner seed. Test in task 8.

---

### Task 1: Close the hidden-hand leak of the RL observation (existing #212)

Keep the body of #212. It already states the criteria: the opponent's `bag_remaining` counts include the opponent's hand chips, and the own view is unchanged. Add: if the meaning of the vector changes, bump `BOARD_LAYOUT` as the `quack_rule_changes` skill says, and list the stale models and datasets in `## Engineer: DONE`.

### Task 2: `RuleBot` with three shop strategies

**Files:**
- Create: `src/quack_rl/bots/rule_bot.py`, `tests/test_rule_bot.py`
- Modify: `src/quack_rl/bots/strategy.py` (replace the five strategies with three)
- Keep for now: `src/quack_rl/bots/heuristic.py` (task 3 removes it)

**Interfaces:**
- Produces:
  - `STRATEGIES: dict[str, Strategy]` with keys `topchip`, `spendmost`, `blackpurple`
  - `Strategy(name: str, colour: str, score: Callable[[ShopView], dict[str, float]])`, where `ShopView` is a frozen dataclass: `round: int`, `money: int`, `legal: tuple[str, ...]` (shop actions), `bought_colours: frozenset[str]` (this round), `black_bought: int` (whole game), `prices: dict[str, int]`, `colours: dict[str, str]` (per shop item id)
  - `RuleBot(rs: Ruleset, strategy: str, draw_limit: int, points_round: int, seed: int | None = None, temperature: float = DEFAULT_TEMPERATURE)` with `kind = "bot"`, `name = bot_name(strategy, draw_limit, points_round)`, `params` holding all five settings, `choose(state, seat, legal) -> str`
  - `shop_probabilities(bot: RuleBot, state: GameState, seat: str, legal: list[str]) -> dict[str, float]` (for tests and the report)
  - `bot_name(strategy: str, draw_limit: int, points_round: int) -> str` → `"<strategy>-draw<limit>-pts<round>"`; `parse_bot_name(name: str) -> tuple[str, int, int]` (accepts the `bot:` prefix; raises `ValueError` naming the form)
  - Strategy colours: `topchip` blue, `spendmost` blue, `blackpurple` red

- [ ] **Step 1: Write the failing tests** in `tests/test_rule_bot.py`:
  - `test_topchip_buys_the_most_expensive_affordable_chip`: temperature 0, money 20 in round 1 → `buy:blue_4` (price 19)
  - `test_topchip_spends_the_rest_on_a_second_colour`: after `buy:blue_4` with 1 money left and nothing affordable → `done`
  - `test_spendmost_picks_the_best_pair`: temperature 0, money 20 in round 2 → the first buy is a chip of a pair whose total price is 20 or the highest below it, with distinct colours
  - `test_spendmost_with_one_affordable_chip_buys_it`
  - `test_blackpurple_buys_black_in_rounds_1_to_3` and `test_blackpurple_stops_preferring_black_after_two`
  - `test_blackpurple_buys_purple_in_rounds_5_to_7`
  - `test_blackpurple_prefers_red_or_orange_otherwise` (round 4, money for red and green → red)
  - `test_no_second_chip_of_a_bought_colour` (every strategy, every sampled choice over 200 seeds)
  - `test_nothing_affordable_gives_done`
  - `test_probabilities_sum_to_one_and_cover_only_legal_actions`
  - `test_same_seed_same_choices` and `test_default_temperature_varies_the_buy` (over 200 seeds the top buy is chosen in more than half of the games, and at least one other buy also occurs)
  - `test_bot_name_round_trip` and `test_parse_bot_name_rejects_old_form` (`draw20-pts1-points` → `ValueError` whose message contains `<strategy>-draw<limit>-pts<round>`)
  - `test_draw_and_card_rules_match_heuristic_bot`: for the non-shop phases, `RuleBot` and `HeuristicBot` with the same draw limit and points round choose the same action over 50 seeded games
- [ ] **Step 2: Run** `uv run --with pytest pytest tests/test_rule_bot.py`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement.** Move the non-shop rules of `HeuristicBot` into `RuleBot` unchanged (draw/stop, take-back, card 2 restart, pick step, ruby step, card choices with `strategy.colour`). The shop: build a `ShopView`, call `strategy.score`, give `done` its score from the strategy, apply a softmax at `temperature` (0 → argmax, ties to the first in shop order) and sample with the bot's `random.Random(seed)`. Choose `DEFAULT_TEMPERATURE` so that the top buy has a probability between 0.6 and 0.9 in a typical round-1 shop, and state the value in the docstring.
- [ ] **Step 4: Run** the tests again. Expected: PASS. Then run the fast subset.
- [ ] **Step 5: Commit** `Add RuleBot with three shop strategies`.

### Task 3: Retire `HeuristicBot` and switch every caller to the new name form

**Files:**
- Delete: `src/quack_rl/bots/heuristic.py`; the tests that only test it
- Modify: `src/quack_rl/bots/__init__.py`, `src/quack_rl/cli/seats.py` (`BOT_FORM = "bot:<strategy>-draw<percent>-pts<round>"`), `src/quack_rl/rl/opponents.py`, `src/quack_rl/tournament.py` (`_spec_for`, `field_specs`, `FIELD_*` constants: the full field becomes 3 strategies × draw limits 0, 20, 40 × points rounds 4, 6, plus `bot:random`), `scripts/build_dataset.py`, `scripts/train_ppo.py` defaults, `README.md`, the `quack_rule_changes` skill files that name the old bot
- Move: `docs/analysis/2026-10-*.md` → `archive/docs/analysis/` (stale results)
- Delete (local, git-ignored, stale after #212): `data/runs/*` and `data/datasets/draw20/`; name them in `## Engineer: DONE`
- Test: `tests/test_rule_bot_seats.py`

**Interfaces:**
- Consumes: `RuleBot`, `bot_name`, `parse_bot_name` (task 2)
- Produces: `explosion_chance` stays importable from `quack_rl.bots`; `field_specs("full")` returns 19 specs

- [ ] **Step 1: Write the failing tests:** `check_seat("bot:topchip-draw20-pts4")` passes; `check_seat("bot:draw20-pts1-points")` raises with the new form in the message; `parse_seat` returns a `RuleBot`; `make_opponent("spendmost-draw0-pts6")` returns a `RuleBot`; `field_specs("full")` has 19 entries and contains `bot:random`; a 4-game tournament with `bot:blackpurple-draw40-pts4` vs `bot:random` runs to the end.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.** Switch the callers, delete `heuristic.py` and the old strategies, and fix every test that used an old name. Then `grep -rn "draw20-pts\|HeuristicBot" src scripts tests README.md .agents` returns nothing.
- [ ] **Step 4: Run** the full test command. Expected: PASS.
- [ ] **Step 5: Commit** `Retire HeuristicBot; new bot name form everywhere`.

### Task 4: Baseline tournament and the three preset bots

**Files:**
- Create: `src/quack_rl/bots/presets.py`, `docs/analysis/2026-11-bot-baseline.md`, `tests/test_presets.py`

**Interfaces:**
- Consumes: `field_specs("full")` (task 3)
- Produces: `PRESET_BOTS: tuple[str, str, str]`, one `bot:<strategy>-draw<d>-pts<r>` spec per strategy, in the order `topchip`, `spendmost`, `blackpurple`; `PRESET_LABELS: dict[str, str]` (display label per preset, for example "Top chip (draw 20 %, points from round 4)")

- [ ] **Step 1: Run the baseline** with `quack-rl tournament` on the full field (19 seats), at least 200 games per pairing, a fixed seed, and record the command.
- [ ] **Step 2: Write the report:** the win rate of each setting with its 95% interval, the pick per strategy (best mean win rate), and each pick's win rate against `bot:random`.
- [ ] **Step 3: Write the failing test** `test_presets_are_valid_and_one_per_strategy`.
- [ ] **Step 4: Implement** `presets.py` with the picks. Run the test. Expected: PASS.
- [ ] **Step 5: Commit** `Bot baseline report and preset bots`.

Acceptance: each preset's win rate against `bot:random` has a 95% interval lower bound above 0.5.

### Task 5: Agent folders and the `agent:<name>` seat (rewrite of existing #199)

**Files:**
- Create: `src/quack_rl/rl/agents.py`, `tests/test_rl_agents.py`
- Modify: `src/quack_rl/rl/offline.py` (save the BC and CQL network), `src/quack_rl/rl/train.py` and `src/quack_rl/rl/selfplay.py` (save as an agent folder), `src/quack_rl/cli/seats.py` (`check_seat`/`parse_seat` accept `agent:<name>`), `src/quack_rl/tournament.py` (labels and `seats.parquet` rows for agent seats)

**Interfaces:**
- Produces:
  - `AGENTS_ROOT = Path("data/agents")`
  - `AgentManifest` (pydantic): `name: str`, `kind: Literal["ppo", "bc", "cql", "planner"]`, `rules: str`, `layout: int`, `weights: str | None` (file name in the folder), `weights_sha256: str | None`, `settings: dict[str, Any]`, `created_at: str`
  - `save_agent(folder: Path, manifest: AgentManifest) -> None` (writes `agent.json`; computes the hash)
  - `load_agent(name: str, rules: Ruleset, seed: int | None = None, root: Path = AGENTS_ROOT) -> Seat` (raises `AgentError` on a missing folder, a rules/layout mismatch, a hash mismatch, or a missing `rl` group for `ppo`/`bc`/`cql`, with a message that names the group)
  - `list_agents(root: Path = AGENTS_ROOT) -> list[AgentManifest]` (skips a broken folder with a warning)
  - Kind `planner` is resolved through a registry `PLANNER_FACTORY: Callable[[Ruleset, AgentManifest, int | None], Seat] | None`, which task 8 fills in

- [ ] **Step 1: Write the failing tests:** save then load a tiny PPO agent (`rl` group; skip without it) and play 4 games against `bot:random` with no illegal action; the same for a tiny BC and a tiny CQL agent; a layout mismatch, a rules mismatch and a hash mismatch each raise `AgentError`; a missing folder raises `AgentError` with the folder path in the message; without the `rl` group, a `ppo` agent raises with "rl" in the message; a tournament with `agent:<tiny>` vs `bot:random` labels the seat `agent:<name>` and records the weights hash in `config.json`.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.** The training functions write an agent folder (`agent.json` plus weights) next to their existing outputs. A loaded model can be trained further (PPO through `MaskablePPO.load`; BC/CQL by loading the state dict into `make_mlp`).
- [ ] **Step 4: Run** the full test command. Expected: PASS.
- [ ] **Step 5: Commit** `Agent folders and the agent:<name> seat`.

### Task 6: Agent seats and the opponent list in the game service (rewrite of existing #225)

**Files:**
- Modify: `src/quack_rl/web/app.py`, `src/quack_rl/web/session.py`
- Test: `tests/test_web_opponents.py`

**Interfaces:**
- Consumes: `PRESET_BOTS`, `PRESET_LABELS` (task 4); `list_agents`, `load_agent` (task 5)
- Produces: `GET /opponents` → `[{"spec": str, "label": str, "kind": "bot" | "ppo" | "bc" | "cql" | "planner"}]`, presets first, then agents by name; `POST /games` accepts `agent:<name>` for `p1`/`p2`

- [ ] **Step 1: Write the failing tests:** with no agents folder, `GET /opponents` returns exactly the three presets; with one tiny agent folder it returns four entries; a broken agent folder is skipped (status 200); `POST /games` with `p2 = agent:<tiny>` plays the seat like a bot; `agent:missing` gives HTTP 400 with a clear message; without the `rl` group, a `ppo` agent seat gives HTTP 400 that names the group.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.** The service reads the agents root from a setting (default `AGENTS_ROOT`) so that tests can use a temporary folder.
- [ ] **Step 4: Run** the full test command. Expected: PASS.
- [ ] **Step 5: Commit** `Game service: agent seats and GET /opponents`.

### Task 7: Start screen reads the opponent list (Lane: frontend)

Change through Lovable (project `quacks-frontend`). The start screen fetches `GET /opponents` and offers each entry by its `label`, grouped as "Bots" and "Trained agents". It drops the hard-coded list in `frontend/src/lib/start-game.ts`. The default opponent is the first preset. When the service is unreachable, it shows the existing error state. Describe the looks in words only, with no picture template. Acceptance: the frontend tests pass (`cd frontend && bun install && bun run test`); with the local service running, the list shows the three presets and every agent folder.

Blocked by: task 6.

### Task 8: The planner agent (model-based)

**Files:**
- Create: `src/quack_rl/rl/planner.py`, `src/quack_rl/rl/determinize.py`, `scripts/make_planner_agent.py`, `tests/test_rl_planner.py`

**Interfaces:**
- Consumes: `AgentManifest`, `save_agent`, `PLANNER_FACTORY` (task 5); `RuleBot` (task 2)
- Produces:
  - `determinize(state: GameState, rs: Ruleset, seat: str, rng: random.Random) -> GameState`: a copy where the opponent's hidden hand is back in the opponent's bag, and every bag and the card deck carry a fresh order drawn from `rng`
  - `PlannerBot(rs: Ruleset, simulations: int, rollout: str, seed: int | None = None, max_seconds: float = 2.0)` with `kind = "bot"`, `name = "planner"`, `choose(state, seat, legal) -> str`: flat Monte Carlo. With one legal action, return it. Otherwise split the simulations evenly over the legal actions; each simulation determinizes, applies the action, plays to the game end with the rollout bot in both seats under the planner's own chance RNG, and scores win 1, tie 0.5, loss 0. Pick the best mean (ties to the first legal action). Stop early at `max_seconds`
  - `scripts/make_planner_agent.py --name planner --simulations N --rollout <bot spec>` writes `data/agents/planner/agent.json` (kind `planner`, no weights)

- [ ] **Step 1: Write the failing tests:** `test_determinize_hides_the_opponent_hand` (the copy has no opponent hand; the opponent's bag counts equal bag plus hand of the original); `test_determinize_keeps_the_own_view` (own hand and own bag counts unchanged); `test_choice_ignores_hidden_information` (Review Focus 5); `test_single_legal_action_returns_it_without_simulating`; `test_planner_plays_full_games_legally` (4 games vs `bot:random`); `test_planner_never_touches_the_real_chance_rng`; `test_decision_time_stays_under_budget` (marked `slow`); `test_planner_agent_loads_as_seat` (`agent:planner` through `load_agent`).
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement** and register the factory in `PLANNER_FACTORY`.
- [ ] **Step 4: Run** the full test command. Expected: PASS. Then run 100 games against each preset and note the win rates in `## Engineer: DONE`. If a win rate is below 10%, try more simulations, then MCTS, within the 2 s budget, and report what was tried.
- [ ] **Step 5: Commit** `Planner agent: flat Monte Carlo with determinization`.

### Task 9: Train PPO online against the presets (rewrite of existing #263)

**Files:** Modify `scripts/train_ppo.py` (`--opponent` accepts a comma list, sampled per episode), `src/quack_rl/rl/train.py`; Create `docs/analysis/2026-11-ppo-online.md`

- [ ] **Step 1: Write the failing test** `test_train_ppo_with_an_opponent_mix_writes_an_agent` (tiny step count, a mix of two presets; the agent folder loads).
- [ ] **Step 2: Implement** the mix. Run the test. Expected: PASS.
- [ ] **Step 3: Run** training against `PRESET_BOTS`, at most about 1 h of wall time; save as `data/agents/ppo-online/`.
- [ ] **Step 4: Report** the command, the settings, the wall time, the learning curve and the win rate against each preset and `bot:random` (200 games each, 95% interval).
- [ ] **Step 5: Commit** `PPO online run on v2.3`.

Blocked by: tasks 1, 4, 5.

### Task 10: Resume an interrupted self-play run (existing #85)

Keep #85's goal. The criteria: `scripts/train_selfplay.py --resume <out>` continues from the newest checkpoint; the pool is rebuilt from the checkpoints up to that one; `selfplay.csv` is cut back to that checkpoint; a test interrupts a tiny run after round 2 and shows that the resumed run ends with the same number of rounds and rows as an uninterrupted one. Blocked by: task 5.

### Task 11: Self-play run on v2.3

**Files:** Create `docs/analysis/2026-11-selfplay.md`

- [ ] **Step 1: Run** `scripts/train_selfplay.py`, at most about 1 h of wall time; save the final model as `data/agents/selfplay/`.
- [ ] **Step 2: Report** the command, the settings, the wall time, the per-round curve and the win rate against each preset and `bot:random` (200 games each, 95% interval).
- [ ] **Step 3: Commit** `Self-play run on v2.3`.

Blocked by: tasks 1, 4, 5, 10.

### Task 12: Offline dataset and BC and CQL runs

**Files:** Modify `scripts/build_dataset.py` (build from a tournament field); Create `docs/analysis/2026-11-offline.md`

- [ ] **Step 1: Write the failing test** `test_build_dataset_from_field` (two bot specs, 4 games; the dataset has transitions from both seats and the current layout).
- [ ] **Step 2: Implement.** Run the test. Expected: PASS.
- [ ] **Step 3: Build** a dataset from the full field (`field_specs("full")` without `bot:random`) to `data/datasets/rulebots/`.
- [ ] **Step 4: Train** BC and CQL with `scripts/train_offline.py`, at most about 1 h each; save as `data/agents/bc/` and `data/agents/cql/`.
- [ ] **Step 5: Report** the dataset size and stats, the commands, the settings, the wall times, the loss curves and the win rate of each agent against each preset and `bot:random` (200 games each, 95% interval). Commit `Offline BC and CQL runs on v2.3`.

Blocked by: tasks 1, 4, 5.

### Task 13: Final tournament and stage report

**Files:** Create `docs/analysis/2026-11-rl-proof.md`

- [ ] **Step 1: Run** one tournament: `agent:ppo-online`, `agent:selfplay`, `agent:bc`, `agent:cql` and `agent:planner`, each against the three presets and `bot:random`, at least 200 games per pair (at least 100 for the planner if time demands it), fixed seed, seats swapped half the time.
- [ ] **Step 2: Report** a table of win rates with 95% intervals, and per agent whether it meets the bar (at least 10% wins against each preset). For an agent that misses it, say what was tried. Also include the tournament command and its run folder.
- [ ] **Step 3: Check** that every agent shows in `GET /opponents` and that one browser game against each one can be started (service test or a short manual note).
- [ ] **Step 4: Commit** `RL proof-of-concept report on v2.3`.

Blocked by: tasks 8, 9, 11, 12.
