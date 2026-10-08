# Quack RL design

Status: working draft, reviewed with the owner up to section 7.1 and sections 8-10. This spec records the current state of the design, not a final truth. Each section and decision carries one of these tags:

- **Settled:** the owner decided. It changes only through the owner
- **Default:** a working choice to build with, expected to change (tuning, a later design session). Code keeps it in data or config, never hard-coded
- **Open:** needs a design session or an owner decision before anyone builds it
- **Proposed:** written by the planner, not yet reviewed by the owner

## 1. Purpose

A learning project out of curiosity about boardgame implementations, push-your-luck decisions and Reinforcement Learning. Implement a simplified board game, make it a standard RL environment, and collect game data that is fit for online and offline RL.

RL training itself is **not** the purpose. At most, a small notebook later shows that the environment works for online and offline RL. No dedicated algorithm tuning.

The look of the game is not important. The data is as well as the RL environment being in line with common benchmarks.

## 2. Goals

### Current goals (this spec, milestones M1-M4)

- The game: rules v1 (`docs/rules/rules-v1.md`), 1v1
- One rules engine in Python, the only place the rules live
- Game modes, all recorded:
  - bot vs bot (watch live or replay)
  - human vs bot
  - human vs human on one machine (hot seat)
- Terminal play first, Lovable web frontend later
- A standard RL environment (PettingZoo, Gymnasium)
- Game records and offline RL datasets in standard form (Minari)

### Future goals (outside this spec, design must not block them)

- A skill: game rules + components + interactive owner feedback → Python RL environment (`rules-to-rl-env`)
- A skill: add a rule or component to an existing game in a structured way (test cases: section 6 of the rules)
- Rule changes from section 6 of the rules
- Transfer Learning use cases: use a model trained on one rules version on a changed version (section 7.4)
- Hosted play and hosted records
- Marimo notebooks that show online and offline RL on the environment in depth (M2 has only a tiny smoke-test notebook)

## 3. Decisions so far

| Topic | Decision | Reason | Status |
|---|---|---|---|
| Rules location | One Python engine; nobody writes the rules a second time (no TypeScript copy) | One source of truth; rule changes happen once. Common practice (OpenSpiel, PettingZoo, Kaggle environments) | Settled |
| Layers | Pure engine → adapters (RL env, CLI, server) → versioned contract | The engine has no I/O, so every adapter is thin and testable | Settled |
| Frontend | Lovable, replay-first, in a later milestone, built against a finished contract | The kit's frontend lane cannot reach the Python code; QA uses fixtures; Lovable gets exact instructions | Settled |
| First human interface | Terminal play | Play and test the rules in M1, with no frontend | Settled |
| Brewing | Simultaneous per chip draw: hidden choices, public results after each step | Owner decision | Settled |
| Shop | Simultaneous for now; alternating later (planned rule change) | Owner decision | Default |
| Win condition | Victory points bought in the shop; most points wins | Coins split between engine and points: a real trade-off, no easy best path | Settled (prices: Default) |
| Explosion | Half money, no choice | Owner simplification: one fixed penalty, smaller action space | Settled |
| Rewards | The env exposes the plain game outcome: 0 per step, +1/-1/0 at the end. No reward design | Reward design is RL work, out of scope. Raw logs allow any reward to be recomputed later | Settled |
| Records | Local files first, behind a storage interface; hosting later | Owner decision | Settled (hosting: Open) |

## 4. Architecture (Default)

```
src/quack_rl/
  rules/        ruleset data: v1.toml (chips, track, rubies, shop, die, setup)
  components/   registry of components and their effect hooks
  engine/       state, phases, legal actions, step, seeded chance
  bots/         random, threshold, greedy, points-first
  record/       raw game log: write, read, replay, verify, RecordStore
  encodings/    observation encodings, one versioned module each        (M2)
  env/          PettingZoo ParallelEnv, Gymnasium single-agent wrapper   (M2)
  datasets/     Minari export from raw logs                             (M2)
  cli/          play (terminal), simulate, tournament, replay
notebooks/      marimo notebooks                                        (M2)
  server/       HTTP API for the frontend                               (M3)
```

### 4.1 Engine

- `GameState` is a plain data object (dataclasses). It can be serialized to JSON and back with no loss
- `legal_actions(state, player)`, `step(state, joint_action, rng) -> (state, events)`
- All chance comes from one seeded RNG owned by the game. Each chance outcome (chip drawn, bonus die) is emitted as an explicit chance event (the OpenSpiel idea of chance nodes). Same seed + same actions → same game
- The engine does no I/O and knows nothing about bots, terminals, files or HTTP

### 4.2 Components and plug-ins

Rule changes must be cheap. So the rules are data plus small hooks:

- Each chip type is a registered component with descriptive features (colour, value, explosion weight, ...) and effect hooks on engine events, for example `on_place` (blue bonus, white explosion total) and `on_round_end` (green droplet bonus)
- Shop items, die faces and the track are data in the ruleset file
- A ruleset file names its version (`v1`) and the components it uses
- Adding a chip colour = one component module + entries in a ruleset file + tests. The engine core does not change

### 4.3 Bots (Open: needs a dedicated design session)

Which bots exist, how they decide, and how they serve as opponents and for a balance check is not designed yet. It needs its own design session before the bot work is built.

Fixed now only: a bot uses the same interface as a human seat (it gets the observation and the legal actions, and returns one action). M1 needs at least one bot so that human vs bot and bot vs bot can be played; the minimal default is a random bot (uniform over legal actions).

## 5. State, observations, actions (Settled, details Default)

### 5.1 Turn structure

A round has the phases Brew → Resolve → Shop → Reset.

- Brew: simultaneous steps; each brewing player sends Draw or Stop
- Resolve: no player actions (rubies, green bonus, bonus die, money)
- Shop: simultaneous steps; each shopping player sends one Buy or Done
- A player with nothing to do in a step (stopped, exploded, done shopping) sends `Wait`. This is the usual way to handle this in a PettingZoo `ParallelEnv`

### 5.2 Information and the bag

The rules say: do not look into the bag. But every chip that enters or leaves a bag is public, so a player can reconstruct the bag contents from the history. A computer always can; a human often does not.

The principled RL answer (OpenSpiel terms):

- An **information state** holds everything a player could know from the history (perfect recall). The bag composition (chips in the bag minus chips drawn this round) is part of it, because it follows from public events
- An **observation** may hold less; then the agent needs memory (for example a recurrent policy) to recover the rest

Decision:

- The env gives the information state by default: the remaining bag composition is part of the observation. The env is then Markov, and standard RL methods apply without memory
- What a human sees is a separate UI choice: the terminal and the frontend may show or hide the bag composition ("bag assist" on or off)
- Each record stores the assist setting, because it changes how humans play. For offline RL this is part of the behavior policy context
- Later uncertain bag contents (random chips appearing) fit the same model: the information state then holds the known part and counts of unknown chips

Hidden in v1: the draw order (chance, unknown to everyone) and the opponent's current simultaneous choice until the reveal. Everything else is public, so both players' observations come from one encoder, from the seat's point of view.

### 5.3 Observation format

PettingZoo board-game convention:

```
{ "observation": <encoded state from my seat's view>,
  "action_mask": <1 for each legal action> }
```

Two encodings of the same state:

- a structured dict: readable, used for logs, terminal and frontend
- a flat vector for RL libraries, generated from the dict

### 5.4 Actions

One `Discrete` action space with an action mask: `Wait, Draw, Stop, Done, Buy<item 1> ... Buy<item n>`, built from the ruleset. v1 has 16 actions.

## 6. Records and datasets (Settled, details Default)

### 6.1 Raw game log: the source of truth

A record is an event log in JSON Lines (one JSON object per line). Every line carries the `game_id`.

- `header` line: record schema version, `game_id`, rules version, seed, mode, seats (human or bot, with bot name and parameters), UI settings (bag assist), engine version, start time (ISO 8601, Berlin local time with UTC offset)
- One `step` line per joint step, written after the reveal:
  - `legal`: the legal actions of each player, as names
  - `actions`: the action of each player, as names (`draw`, `stop`, `wait`, `done`, `buy:<item>`); a player with nothing to do has `wait`
  - `chance`: each chance outcome, explicit (chip drawn, bonus die face)
  - `events`: the resulting public events (chip placed, explosion, ruby, green bonus, money, purchase)
  - `decision_ms`: for human seats, the time each action took (Default)
- A resolve step has no player actions: only `chance` and `events`
- `footer` line: final scores, winner

Actions and legal actions are stored as names, not indices, so a record stays readable when the action set changes.

Replay applies the recorded chance outcomes; it does not need the RNG. A `verify` command replays a record and checks, at every step, that the legal actions, events and final scores match.

Ruleset rule: once a ruleset version has recorded games, it is never edited, only superseded (for example `v1` → `v1.1`). A changed chip effect is a new component version; the old one stays, so old records can always be replayed.

### 6.2 Files and storage

A record file holds one or more games, each enclosed by its `header` and `footer` lines.

```
data/records/<rules_version>/play/<time>_<short id>.jsonl          one game with a human seat
data/records/<rules_version>/sim/<time>_<short id>/shard-0001.jsonl  simulations, up to 1000 games per shard
```

`<time>` is Berlin local time with its UTC offset, for example `2026-10-08_21-15-03+0200`. The same naming holds for game files and simulation runs. The header is the truth; the path is only for convenience.

All access goes through a `RecordStore` interface (write steps, list, read), so a hosted store can replace the local folder later. `data/` is gitignored: human and simulated records stay local for now.

### 6.3 Derived datasets

- Format: Minari (Default; to be confirmed by a short research task before M2)
- Built on demand from raw records with `quack-rl dataset build ...`: replay with the record's ruleset, encode the observations, attach the stored legal actions as action masks, and the outcome reward
- Each game gives two episodes, one per seat; the other seat is part of the environment. Default: both seats; a filter can select seats (for example only human seats, or only the winner)
- Each observation encoding has its own version, independent of the rules version. Encoder code: `src/quack_rl/encodings/`
- Dataset ids: `quack-rl/<rules_version>/<encoding>/<record filter>-v<n>`, for example `quack-rl/v1/flat1/human_vs_bot-v0`
- Datasets go to `data/datasets/` (Minari's `MINARI_DATASETS_PATH`)
- Changing the encoding or the reward means rebuilding datasets, not recording again

## 7. Adapters

### 7.1 Terminal (M1, Settled, details Default)

- Command-line library: Typer. Display: Rich (coloured chips, tables)
- Commands:
  - `quack-rl play --p1 human --p2 bot:random`, and `--p1 human --p2 human` (hot seat)
  - `quack-rl replay <file> [--game <game_id>]`: step through a recorded game
  - `quack-rl simulate --p1 bot:random --p2 bot:random --games 1000`: bot vs bot, recorded in shards
  - `quack-rl verify <file>`: replay and check a record (6.1)
- Simultaneous choices: each human seat chooses with a hidden keypress (no echo), then all choices are revealed. Hot seat is a simple mode for now (testing, a single person); real two-person play comes with hosting
- Text board: round, phase, step; per player: droplet and start field, chips placed, field and money, white total, ruby fields ahead, points, status (brewing, stopped, exploded); the bag composition when bag assist is on (`--bag-assist`, default on)

### 7.2 RL environment (M2, Proposed)

- PettingZoo `ParallelEnv`, checked with PettingZoo's `parallel_api_test`
- Gymnasium single-agent wrapper: the agent plays one seat, a given bot plays the other. Checked with Gymnasium's `check_env`
- Tournament command and balance report: win rates of the bots against each other, to see whether one strategy dominates (depends on the bot design session)
- A tiny marimo notebook as a smoke test: one short online RL run on the Gymnasium env, and one offline step on a Minari dataset made from recorded games. It shows that env and datasets work with common RL tooling; no tuning

### 7.3 Server and frontend (M3 and M4, Proposed)

- The contract: JSON Schema of the game record and the state, an OpenAPI description of the HTTP API, and example fixtures. They are files in this repo
- A small HTTP server (for example FastAPI) wraps the engine, the bots and the recorder
- The Lovable frontend is a thin client: replay viewer first, then live play. It holds no rules. Its project knowledge says: no backend, no game rules in TypeScript, only read records and call the API
- Frontend QA uses the fixtures, not a live server
- For human play, the frontend runs locally from the `frontend/` submodule next to the server, because browsers increasingly block public pages from calling `localhost`

### 7.4 Transfer across rule changes (future; design hook now: Default)

Goal: train a model on one ruleset, then use it on a changed ruleset (new chip colour, changed effects).

A flat vector with one slot per chip type breaks when a chip type is added. The usual approach is an entity encoding: every chip type and every shop item is an entity with a feature vector (value, colour features, explosion weight, movement bonus, price, ...). A set or attention network reads the entities. Actions are scored per entity ("buy the item with these features"), so the action set can change size.

Design hook now: components declare descriptive features (4.2), and the structured observation lists chips and shop items as entities with these features. The entity encoder itself is future work.

## 8. Testing and code quality (Settled, details Default)

- pytest; test command `uv run --with pytest pytest`
- Rule-clause tests: one or more tests per clause of `docs/rules/rules-v1.md`, named after the clause, with scripted chance
- Invariant tests with Hypothesis on random games: chip accounting per chip type holds at every step (owned = starting bag + bought + received from the bonus die - removed, and owned = in bag + placed this round), after each reset all owned chips are in the bag, money is never negative, the field is never above 53, only legal actions are applied, every generated record passes `verify`
- Golden replays: a few small records in `tests/fixtures/` that must replay to the same result
- Run time: the default suite stays under about 30 seconds (Hypothesis example counts capped); a deeper Hypothesis profile is opt-in
- Ruff for linting and formatting; pyright in basic mode for type checking

## 9. Stack (Settled)

- Python 3.12, uv, `src/` layout
- Ruleset files in TOML (read with `tomllib`)
- Pydantic for the ruleset and record models (validation, JSON Schema generation for the M3 contract); plain dataclasses for the engine state
- Typer and Rich for the terminal
- M2 adds: Gymnasium, PettingZoo, Minari, marimo

## 10. Milestones (Settled)

Milestones are the big steps of this spec. They are not the same as the stages of the agent-graph-kit process (`/stage-start`): one milestone can need one or more stages.

| Milestone | Purpose | Main content |
|---|---|---|
| M1 | Play the game in the terminal, recorded | Python project set-up, ruleset data, engine, random bot, raw log + replay + verify, terminal play and simulate |
| M2 | Standard RL environment and datasets | Minari research, PettingZoo and Gymnasium envs with API tests, Minari export, tiny marimo smoke-test notebook, bot design session, tournament and balance report |
| M3 | Contract and server | JSON Schema, OpenAPI, fixtures, HTTP server |
| M4 | Web frontend | Kit Lovable lane set-up (owner steps), replay viewer, live play |
| later | Notebook and skills | RL notebook, `rules-to-rl-env` skill, add-rule skill, rule changes |

This intake plans M1 in detail. Later milestones are planned at later stage set-ups.

## 11. Open questions

- Bot design (section 4.3): a design session in M2
- Minari as dataset format: short research task before the M2 dataset work
- Sections 7.2-7.4: reviewed with the owner at the stage set-up of M2-M4
- Hosting of play and records
