# Quack RL design

Status: working draft. This spec records the current state of the design, not a final truth. Each section and decision carries one of these tags:

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
  record/       raw game log: write, read, replay, verify
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

## 6. Records and datasets (Proposed)

### 6.1 Raw game log: the source of truth

One JSON Lines file per game:

- Header: record schema version, rules version, seed, mode, seats (human or bot, with bot name and parameters), UI settings (bag assist), engine version, start time
- One line per step: the joint action, the chance events, the resulting public events
- Footer: final scores, winner

The engine can replay a log exactly from the seed and the actions. A `verify` command checks that the replay gives the same chance events and scores.

Records go to `data/games/` (gitignored), through a storage interface so that a hosted store can replace it later.

### 6.2 Derived datasets

- Minari datasets are built **from** raw logs: each game gives two episodes, one per seat (Minari is single-agent; the other seat is part of the environment)
- Changing the observation encoding or the reward means rebuilding datasets, not recording again
- Human games stay valid across encoding changes

## 7. Adapters

### 7.1 Terminal (M1, Proposed)

- `quack-rl play --p1 human --p2 bot:threshold` and `--p1 human --p2 human` (hot seat). Hot seat hides each player's simultaneous choice from the other with a "pass the keyboard" prompt
- `quack-rl replay <file>`: step through a record
- `quack-rl simulate --p1 bot:random --p2 bot:threshold --games 1000`: bot vs bot, recorded
- Text board: both potions, fields, explosion totals, droplets, points, optional bag composition

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

## 8. Testing (Proposed)

- Test-driven: one test per rule clause in `docs/rules/rules-v1.md`
- Deterministic tests with fixed seeds and scripted chance
- Golden replays: recorded games that must replay to the same result
- Property tests: random bot games never reach an illegal state
- Test command: `uv run --with pytest pytest`

## 9. Milestones (Proposed)

Milestones are the big steps of this spec. They are not the same as the stages of the agent-graph-kit process (`/stage-start`): one milestone can need one or more stages.

| Milestone | Purpose | Main content |
|---|---|---|
| M1 | Play the game in the terminal, recorded | Python project set-up, ruleset data, engine, random bot, raw log + replay + verify, terminal play and simulate |
| M2 | Standard RL environment and datasets | PettingZoo and Gymnasium envs with API tests, Minari export, tiny marimo smoke-test notebook, bot design session, tournament and balance report |
| M3 | Contract and server | JSON Schema, OpenAPI, fixtures, HTTP server |
| M4 | Web frontend | Kit Lovable lane set-up (owner steps), replay viewer, live play |
| later | Notebook and skills | RL notebook, `rules-to-rl-env` skill, add-rule skill, rule changes |

This intake plans M1 in detail. Later milestones are planned at later stage set-ups.

## 10. Open questions

- Bot design (section 4.3)

- Hot-seat terminal play: is a "pass the keyboard" screen enough to hide simultaneous choices?
- Tech stack confirmation: Python 3.12, uv, `src/` layout, TOML ruleset files
