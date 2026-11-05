"""`PlannerBot`: flat Monte Carlo search with the game engine as its simulator.

At a decision with more than one legal action the planner splits its `simulations` evenly over
the legal actions. One simulation determinizes the state (`determinize`: the opponent's hidden
hand and card draw are drawn again, the deck is shuffled), applies the action, and plays to the
end of the game with the rollout bot in both seats and an `RngChance` seeded from the planner's
own `random.Random`. A win scores 1, a tie 0.5, a loss 0. The best mean wins; on a tie the first
legal action.

The k-th simulation of every action uses the same determinized world and the same seeds (common
random numbers), so the actions are compared on the same luck.

The planner never reads the opponent's hand or `card_draw`, never the real game's chance source
and never the global `random` module, so a seeded planner plays the same game again.
`max_seconds` is a safety cap only: a decision that hits it stops early, counts in
`time_capped` and logs a warning (`CAPPED_MESSAGE`, also from a tournament worker). At the
defaults of `scripts/make_planner_agent.py` it is not reached.

Importing this module registers the planner as `agents.PLANNER_FACTORY`, so `load_agent` can
build an `agent:<name>` seat of kind `planner` in any process.
"""

import logging
import random
import time
from typing import Any

from quack_rl.bots import RandomBot, RuleBot, parse_bot_name
from quack_rl.engine import (
    SEATS,
    WAIT,
    GameState,
    Phase,
    RngChance,
    legal_actions,
    needs_actions,
    step,
)
from quack_rl.rl import agents
from quack_rl.rl.agents import AgentManifest
from quack_rl.rl.determinize import determinize
from quack_rl.rules import Ruleset
from quack_rl.runner import Seat

DEFAULT_SIMULATIONS = 60
DEFAULT_ROLLOUT = "bot:topchip-draw20-pts6"
DEFAULT_MAX_SECONDS = 2.0
RANDOM_ROLLOUT = "bot:random"
CAPPED_MESSAGE = "planner decision stopped by the clock"

log = logging.getLogger(__name__)


def check_rollout(spec: str) -> None:
    """Raise ValueError when `spec` is not a rollout bot (`bot:random` or a rule bot spec)."""
    if spec == RANDOM_ROLLOUT:
        return
    if not spec.startswith("bot:"):
        raise ValueError(f"rollout {spec!r} is not a bot seat (bot:random or bot:<rule bot>)")
    parse_bot_name(spec)


def make_rollout_bot(rs: Ruleset, spec: str, seed: int) -> Seat:
    """The rollout bot of `spec`, seeded with `seed`."""
    if spec == RANDOM_ROLLOUT:
        return RandomBot(seed)
    strategy, draw_limit, points_round = parse_bot_name(spec)
    return RuleBot(rs, strategy, draw_limit, points_round, seed)


def score(final: GameState, seat: str) -> float:
    """1 for a win of `seat`, 0.5 for a tie, 0 for a loss."""
    if final.winner == seat:
        return 1.0
    if final.winner == "draw":
        return 0.5
    return 0.0


class PlannerBot:
    """A seat that plans by flat Monte Carlo search (see the module docstring)."""

    kind = "bot"
    name = "planner"

    def __init__(
        self,
        rs: Ruleset,
        simulations: int = DEFAULT_SIMULATIONS,
        rollout: str = DEFAULT_ROLLOUT,
        seed: int | None = None,
        max_seconds: float = DEFAULT_MAX_SECONDS,
    ):
        if simulations < 1:
            raise ValueError(f"simulations must be at least 1, got {simulations}")
        if not max_seconds > 0:
            raise ValueError(f"max_seconds must be above 0, got {max_seconds}")
        check_rollout(rollout)
        self.rs = rs
        self.simulations = simulations
        self.rollout = rollout
        self.max_seconds = max_seconds
        self._rng = random.Random(seed)
        self.time_capped = 0  # decisions stopped by the clock
        self.params: dict[str, Any] = {
            "simulations": simulations,
            "rollout": rollout,
            "seed": seed,
            "max_seconds": max_seconds,
        }

    def choose(self, state: GameState, seat: str, legal: list[str]) -> str:
        if len(legal) == 1:
            return legal[0]
        per_action = max(1, self.simulations // len(legal))
        seeds = [self._rng.getrandbits(64) for _ in range(per_action)]
        totals = [0.0] * len(legal)
        counts = [0] * len(legal)
        deadline = time.perf_counter() + self.max_seconds
        capped = False
        for world_seed in seeds:
            world_rng = random.Random(world_seed)
            world = determinize(state, self.rs, seat, world_rng)
            run_seeds = (
                world_rng.getrandbits(64),
                world_rng.getrandbits(64),
                world_rng.getrandbits(64),
            )
            for i, action in enumerate(legal):
                if time.perf_counter() > deadline:
                    capped = True
                    break
                totals[i] += self._simulate(world, seat, action, run_seeds)
                counts[i] += 1
            if capped:
                break
        if capped:
            self.time_capped += 1
            log.warning(
                "%s after %.1f s (%d of %d simulations)",
                CAPPED_MESSAGE,
                self.max_seconds,
                sum(counts),
                len(seeds) * len(legal),
            )
        means = [t / c if c else -1.0 for t, c in zip(totals, counts, strict=True)]
        best = max(range(len(legal)), key=lambda i: means[i])  # max keeps the first of a tie
        return legal[best]

    def _simulate(
        self, world: GameState, seat: str, action: str, run_seeds: tuple[int, int, int]
    ) -> float:
        """Play `world` to the end after `seat` takes `action`; the score of `seat`."""
        chance_seed, p1_seed, p2_seed = run_seeds
        chance = RngChance(chance_seed)
        bots = {
            "p1": make_rollout_bot(self.rs, self.rollout, p1_seed),
            "p2": make_rollout_bot(self.rs, self.rollout, p2_seed),
        }
        first = {seat: action}
        state = world
        while state.phase is not Phase.GAME_OVER:
            actions: dict[str, str] | None = None
            if needs_actions(state):
                actions = {}
                for s in SEATS:
                    if s in first:
                        actions[s] = first[s]
                        continue
                    legal = legal_actions(state, self.rs, s)
                    actions[s] = WAIT if legal == [WAIT] else bots[s].choose(state, s, legal)
                first = {}
            state = step(state, self.rs, actions, chance).state
        return score(state, seat)


def planner_from_manifest(rs: Ruleset, manifest: AgentManifest, seed: int | None) -> PlannerBot:
    """The planner of an agent folder of kind `planner` (`agents.PLANNER_FACTORY`)."""
    s = manifest.settings
    try:
        bot = PlannerBot(
            rs,
            simulations=int(s.get("simulations", DEFAULT_SIMULATIONS)),
            rollout=str(s.get("rollout", DEFAULT_ROLLOUT)),
            seed=seed,
            max_seconds=float(s.get("max_seconds", DEFAULT_MAX_SECONDS)),
        )
    except (TypeError, ValueError) as err:
        raise agents.AgentError(f"agent {manifest.name!r} has bad planner settings: {err}") from err
    bot.params["agent"] = manifest.name
    return bot


agents.PLANNER_FACTORY = planner_from_manifest
