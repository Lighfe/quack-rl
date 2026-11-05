# New rule-based bots and an RL proof of concept on v2.3

Date: 2026-11-05. Source: owner intake after the stage review of #267 (M2.23).

## Intent

The opponents that the web game and the tournament offer are outdated: one heuristic bot with five
shop strategies and names like `draw20-pts1-points`. They are retired and replaced by one new
rule-based bot with three shop strategies.

The repo also has to prove again, on ruleset v2.3 (layout 9), that its environment serves every
main kind of RL: model-free online, model-free offline, self-play and model-based (planning). Every
earlier trained result is stale (it was made on older rules and layouts). Each new agent must be
playable by the owner in the browser.

The new bots have two jobs: someone to play against that is not an automatic win (as the random
bot is), and a yardstick for the RL agents.

## Goals

1. One new rule-based bot with three shop strategies, a draw limit and a points round. Its shop
   choice is a pseudo-policy: a probability per legal buy, sampled with a seed.
2. The old heuristic bot, its strategies, its name form and its old results are retired.
3. Four kinds of agent, each trained or run on v2.3:
   - model-free online: MaskablePPO against the new bots
   - model-free self-play: MaskablePPO against its own earlier checkpoints
   - model-free offline: BC and CQL on a dataset of new-bot games
   - model-based: a planning agent that uses the game engine as its simulator
4. Every agent is a seat in the tournament and in the web game.
5. A report measures each agent against each offered bot.

## Non-goals

- Transfer learning (a later goal; this stage only keeps it possible, see "Agent files").
- Reward shaping, observation research, tuning for maximum strength.
- A second, tuned self-play run (#86 stays parked).

## Anti-goals

- An agent that sees hidden information: the opponent's hidden blue hand or the order of any bag.
  This holds for the RL observation and for the planner's simulations.
- Legacy shims: no alias from old bot names to new ones, no second code path for the old bot.
- Per-strategy special cases inside the shared bot rules. A strategy is data plus one scoring
  function; the draw, stop, card, flask and ruby rules are shared.

## The new bot

### Settings

| Setting | Values | Meaning |
|---|---|---|
| strategy | `topchip`, `spendmost`, `blackpurple` | how the bot buys (below) |
| draw limit | 0 to 100 (offered: 0, 20, 40) | stop drawing when the explosion chance of the next draw is above this percent |
| points round | 1 to 9 (offered: 4, 6) | after an explosion: money before this round, points from it on |

Name form: `bot:<strategy>-draw<limit>-pts<round>`, for example `bot:topchip-draw20-pts4`. The
CLI, the tournament, the RL opponents and the web service all accept this form. `bot:random` stays
as the floor for RL measurements; the web game does not offer it.

### Shop strategies

The v2.3 shop: at most 2 chip buys per player per round, of distinct colours; each buy is one
action, then the bot shops again or says `done`. Black is on sale from round 1, yellow from round
2, purple from round 3.

1. `topchip` (top chip first): buy the most expensive chip it can pay for, then spend what is left
   on the most expensive chip it can still pay for.
2. `spendmost` (spend the most): choose the one or two buys whose total price is the highest that
   the money pays for. The first buy is the first chip of that best pair.
3. `blackpurple` (black, then purple): in rounds 1 to 3, buy a black chip (at most two black chips
   over these rounds; the colour rule allows one per round). In rounds 5 to 7, buy a purple chip.
   Otherwise prefer red and orange chips. The rest of the money goes as in `topchip`.

`done` is chosen only when no buy is legal, or when the strategy's scoring ranks it first (for
example nothing affordable that the strategy values).

### Pseudo-policy

Each strategy gives every legal shop action (each `buy:<item>` and `done`) a score. The bot turns
the scores into probabilities with a softmax with one setting, the temperature, and samples one
action with its own seeded RNG. Temperature 0 means argmax (on a tie, the first in shop order),
which the tests use. The default temperature makes the top choice most likely while the others
still happen sometimes; the builder picks the default and states the top-choice probability it
gives in a typical round-1 shop.

Only the shop is a pseudo-policy. The other decisions stay deterministic.

### Shared rules (kept from the old heuristic bot)

Draw or stop by the explosion chance against the draw limit, the take-back with card 17 or the
flask, the restart rule of card 2, the pick step of the blue hand, the ruby step and the card
choices (cards 5, 6, 8, 10, 11, 12, 14, 19) keep the rules of the current `HeuristicBot`. The
"strategy colour" that cards 11, 12 and 19 use is `blue` for `topchip` and `spendmost`, `red`
for `blackpurple` (builder's call, see "Calls made").

### Offered bots

The web game offers three preset bots, one per strategy. A baseline tournament of all 18 settings
(3 strategies x 3 draw limits x 2 points rounds) plus `bot:random` picks, per strategy, the
setting with the best win rate. The report states the picks. Each preset must win clearly against
`bot:random` (the report gives the win rate with its 95% interval).

## RL agents

### Before training

- The hidden-hand leak of the RL observation is fixed first (#212). The observation vector
  changes, so every model and dataset made before is stale.
- The old runs and datasets under `data/` (local, git-ignored) are deleted. The analysis reports
  in `docs/analysis/` about the old runs move to `archive/docs/analysis/`.

### Agent files

Every agent that the seats can load lives in `data/agents/<name>/` with a file `agent.json`:
its kind (`ppo`, `bc`, `cql`, `planner`), the ruleset and layout it was made for, the file of the
weights (none for `planner`), the training settings and a hash of the weights file. A model is
saved so that it can be loaded and trained further (this keeps transfer learning possible later).
BC and CQL models are saved too (today `offline.py` does not save them).

Loading an agent whose ruleset or layout does not match the current one fails with a clear error.

### Model-free online

MaskablePPO against the three preset bots (a mix, or one run per preset; builder's call). At most
about one hour of wall time per training run on the owner's laptop.

### Self-play

MaskablePPO against a pool of its own earlier checkpoints, as `scripts/train_selfplay.py` does.
An interrupted run can be resumed from its newest checkpoint (#85). At most about one hour of wall
time.

### Model-free offline

A dataset of games between the new bots (all 18 settings, so the pseudo-policies give varied
lines of play), built with `scripts/build_dataset.py`. BC and CQL train on it with
`scripts/train_offline.py`. At most about one hour of wall time per run.

### Model-based: the planner

A seat that learns nothing. At each decision with more than one legal action it copies the
state and, for each legal action, runs simulations to the end of the game, with a rollout policy
(the new bot with a fixed setting, or random; builder's call) for both seats. It picks the action
with the best mean result (win = 1, tie = 0.5, loss = 0).

Determinization: before each simulation, the planner fills what its seat cannot see with a draw
from what it can see: the order of every bag and of the card deck is shuffled, and the opponent's hidden hand is put
back into the opponent's bag and the opponent's view is rebuilt from public information. Chance
in the simulation (bag draws, dice, cards) comes from a seeded RNG of the planner, never from the
real game's RNG.

Plain flat Monte Carlo first. MCTS only if flat Monte Carlo misses the bar below.

Speed: a planner decision takes at most about 2 s on the laptop by default (a simulation budget
per decision), so a browser game stays playable.

## Seats

A seat `agent:<name>` loads `data/agents/<name>/`. The tournament (replaces #199's
`policy:<path>`) and the web service (replaces #225's `policy:<path>`) accept it. Without the `rl`
dependency group, a seat of kind `ppo`, `bc` or `cql` fails with a message that names the group;
`planner` needs no extra group.

The web service publishes its list of opponents (`GET /opponents`): the three preset bots and
every agent found in `data/agents/`, each with a display label. The frontend start screen reads
this list instead of its hard-coded one (`frontend/src/lib/start-game.ts`).

## Bar for success

A final tournament plays each agent (PPO online, self-play, BC, CQL, planner) against each preset
bot and `bot:random`, with fixed seeds, at least 200 games per pair (at least 100 for the planner
when time demands it), seats swapped half the time. The report in `docs/analysis/` gives each
win rate with its 95% interval.

Each agent must win at least 10% of its games against each preset bot ("sometimes beats the
bots"). An agent that misses the bar is reported as such, with what was tried; it does not block
the other agents.

## Constraints

- Ruleset v2.3, layout 9 only (after #212 the layout number changes as the
  `quack_rule_changes` skill says).
- Training runs: at most about one hour of wall time each, on the owner's laptop, CPU.
- No secrets in commits, issues or reports.
- The frontend is changed through Lovable (Lane frontend); the Lovable credits need no approval.

## Calls made (by the planner, not the owner)

- `blackpurple` uses red as its strategy colour for cards 11, 12 and 19; the two others use blue.
- The web game offers one preset per strategy, picked by the baseline tournament.
- The agent folder and `agent:<name>` seat form replace the `policy:<path>` form of #199 and #225.
- The service publishes the opponent list; the frontend no longer hard-codes it.
- The bar of 10% wins per preset bot, and 200 games per pair.
- The planner's 2 s budget per decision.

## Left to the builder

- The default temperature of the pseudo-policy and the exact scores per strategy.
- Network sizes, learning settings, the number of self-play checkpoints in the pool.
- The rollout policy of the planner.
