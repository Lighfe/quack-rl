"""The old heuristic bot and its strategy API (kept until the callers move to `RuleBot`)."""

import random
import re
from dataclasses import dataclass
from typing import Any

from quack_rl.bots.core import (
    REFILL_RESERVE,
    RESTART_BELOW,
    TAIL_POINTS_FROM,
    CoreBot,
    explosion_chance,
)
from quack_rl.engine import BUY_PREFIX, DONE, GameState, buy
from quack_rl.rules import Ruleset

__all__ = [
    "BASELINE_NAME",
    "DEFAULT_COLOUR",
    "REFILL_RESERVE",
    "RESTART_BELOW",
    "STRATEGIES",
    "STRATEGY_COLOUR",
    "TAIL_POINTS_FROM",
    "HeuristicBot",
    "Strategy",
    "UnknownStrategy",
    "bot_name",
    "explosion_chance",
    "load_strategy",
    "parse_bot_name",
    "strategy_colour",
]

BASELINE_NAME = "draw20-pts1-points"
_NAME = re.compile(r"draw(\d+)-pts(\d+)-(.+)")


# --- the old strategy API (moved unchanged from `bots/strategy.py`) ----------------------------


class UnknownStrategy(ValueError):
    """A strategy name that is not in `STRATEGIES`."""


@dataclass(frozen=True)
class Strategy:
    """A strategy is data: the shop items it buys, best first, and optional weights.

    `priority` lists the items in order. `weights` maps an item id to a weight
    (default 0): a higher weight ranks first, equal weights keep the priority order.
    """

    name: str
    priority: tuple[str, ...] = ()
    weights: tuple[tuple[str, float], ...] = ()

    def ranked(self) -> list[str]:
        """The priority items, best first (weight descending, then priority order)."""
        weight = dict(self.weights)
        order = {item: i for i, item in enumerate(self.priority)}
        return sorted(self.priority, key=lambda item: (-weight.get(item, 0.0), order[item]))


STRATEGIES: dict[str, Strategy] = {
    "points": Strategy("points"),
    # First guesses, not tuned. Points are bought by the points rule of the bot core.
    "blue": Strategy(
        "blue",
        priority=("blue_4", "blue_2", "blue_1"),
        weights=(("blue_4", 3.0), ("blue_2", 2.0), ("blue_1", 1.0)),
    ),
    "green": Strategy(
        "green",
        priority=("green_4", "droplet_1", "green_2", "green_1"),
        weights=(("green_4", 3.0), ("droplet_1", 2.5), ("green_2", 2.0), ("green_1", 1.0)),
    ),
    # No droplet: removing white makes the bag better, so each added chip is drawn more often.
    "cleaner": Strategy(
        "cleaner",
        priority=("remove_white_1", "orange_1"),
        weights=(("remove_white_1", 3.0), ("orange_1", 1.0)),
    ),
    "balanced": Strategy(
        "balanced",
        priority=(
            "droplet_1",
            "blue_2",
            "green_2",
            "orange_1",
            "remove_white_1",
            "blue_1",
            "green_1",
        ),
        weights=(
            ("remove_white_1", 3.0),
            ("droplet_1", 2.5),
            ("blue_2", 2.0),
            ("green_2", 1.5),
            ("orange_1", 1.0),
        ),
    ),
}


# The colour a strategy takes when a card or the flask offers a coloured chip (cards 11, 12, 19).
# The shop lists of the strategies above carry no colour, so the table is here.
STRATEGY_COLOUR: dict[str, str] = {
    "points": "blue",
    "blue": "blue",
    "balanced": "blue",
    "green": "green",
    "cleaner": "green",
}
DEFAULT_COLOUR = "blue"


def strategy_colour(name: str) -> str:
    """The chip colour of a strategy (`STRATEGY_COLOUR`); blue for a strategy not in the table."""
    return STRATEGY_COLOUR.get(name, DEFAULT_COLOUR)


def load_strategy(name: str) -> Strategy:
    try:
        return STRATEGIES[name]
    except KeyError:
        raise UnknownStrategy(
            f"unknown strategy {name!r} (known: {', '.join(sorted(STRATEGIES))})"
        ) from None


def bot_name(draw_limit: int, points_round: int, strategy: str) -> str:
    return f"draw{draw_limit}-pts{points_round}-{strategy}"


def parse_bot_name(name: str) -> tuple[int, int, str]:
    """Split `draw30-pts3-blue` (or `bot:draw30-pts3-blue`) into its parameters.

    Raise ValueError on a bad name.
    """
    m = _NAME.fullmatch(name.removeprefix("bot:"))
    if m is None:
        raise ValueError(f"bad bot name {name!r} (expected draw<percent>-pts<round>-<strategy>)")
    draw_limit, points_round, strategy = int(m[1]), int(m[2]), m[3]
    if draw_limit > 100:
        raise ValueError(f"bad bot name {name!r}: draw limit must be 0 to 100 percent")
    if points_round < 1:
        raise ValueError(f"bad bot name {name!r}: points round must be at least 1")
    load_strategy(strategy)
    return draw_limit, points_round, strategy


class HeuristicBot(CoreBot):
    """Draw or Stop by the chance to explode; buy points from a round on, then by strategy.

    Every decision outside the shop follows the shared rules of `CoreBot`. The
    strategy colour is blue for `points`, `blue` and `balanced`, green for `green` and `cleaner`
    (`STRATEGY_COLOUR`). The shop buys the first legal item of the strategy list, else the most
    expensive legal item.
    """

    def __init__(
        self,
        rs: Ruleset,
        draw_limit: int = 20,
        points_round: int = 1,
        strategy: str | Strategy = "points",
        seed: int | None = None,
    ):
        self._strategy = strategy if isinstance(strategy, Strategy) else load_strategy(strategy)
        super().__init__(rs, draw_limit, points_round, strategy_colour(self._strategy.name))
        self._rng = random.Random(seed)
        self.name = bot_name(draw_limit, points_round, self._strategy.name)
        self.params: dict[str, Any] = {
            "draw_limit": draw_limit,
            "points_round": points_round,
            "strategy": self._strategy.name,
            "seed": seed,
        }

    def _shop(self, state: GameState, seat: str, legal: list[str]) -> str:
        affordable = [a.removeprefix(BUY_PREFIX) for a in legal if a.startswith(BUY_PREFIX)]
        # Items of the list that the shop lacks are never legal, so they are skipped here.
        for item_id in self._strategy.ranked():
            if item_id in affordable:
                return buy(item_id)
        # The most expensive legal item; on a tie the first in shop order.
        rest = [i for i in self._rs.shop if i.id in affordable]
        if rest:
            return buy(max(rest, key=lambda i: i.price).id)
        return DONE
