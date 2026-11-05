"""`RuleBot`: the shared bot rules plus a seeded pseudo-policy in the shop.

Each strategy (`bots/strategy.py`) scores every legal shop action by rank (best 0, next -1, ...).
A softmax at `temperature` turns the scores into probabilities (`shop_probabilities`), and the
bot samples one action with its own `random.Random(seed)`. Temperature 0 is the argmax; on a tie
the first action in `legal` order. Outside the shop the bot is deterministic (`CoreBot`).

`DEFAULT_TEMPERATURE` is 0.6. In the round 1 shop with money 20 and nothing bought,
the top action has these probabilities at the default temperature:

| strategy      | top action     | probability |
|---------------|----------------|-------------|
| `topchip`     | `buy:blue_4`   | 0.80        |
| `spendmost`   | `buy:red_4`    | 0.77        |
| `blackpurple` | `buy:black_1`  | 0.81        |
"""

import math
import random
import re
from typing import Any

from quack_rl.bots.core import CoreBot
from quack_rl.bots.strategy import STRATEGIES, ShopView, Strategy
from quack_rl.engine import GameState
from quack_rl.rules import Ruleset

DEFAULT_TEMPERATURE = 0.6
MAX_DRAW_LIMIT = 100
ROUNDS = 9
_NAME = re.compile(r"([a-z]+)-draw(\d+)-pts(\d+)")


def bot_name(strategy: str, draw_limit: int, points_round: int) -> str:
    return f"{strategy}-draw{draw_limit}-pts{points_round}"


def parse_bot_name(name: str) -> tuple[str, int, int]:
    """Split `topchip-draw20-pts4` (or `bot:topchip-draw20-pts4`) into its parameters.

    Raise ValueError on a bad name."""
    m = _NAME.fullmatch(name.removeprefix("bot:"))
    if m is None:
        raise ValueError(f"bad bot name {name!r} (expected <strategy>-draw<limit>-pts<round>)")
    strategy, draw_limit, points_round = m[1], int(m[2]), int(m[3])
    if strategy not in STRATEGIES:
        raise ValueError(
            f"bad bot name {name!r}: unknown strategy {strategy!r} "
            f"(known: {', '.join(sorted(STRATEGIES))})"
        )
    if not 0 <= draw_limit <= MAX_DRAW_LIMIT:
        raise ValueError(f"bad bot name {name!r}: draw limit must be 0 to {MAX_DRAW_LIMIT}")
    if not 1 <= points_round <= ROUNDS:
        raise ValueError(f"bad bot name {name!r}: points round must be 1 to {ROUNDS}")
    return strategy, draw_limit, points_round


def shop_view(rs: Ruleset, state: GameState, seat: str, legal: list[str]) -> ShopView:
    p = state.players[seat]
    return ShopView(
        round=state.round,
        money=p.money,
        legal=tuple(legal),
        bought_colours=frozenset(p.chip_colours),
        black_bought=p.owned("black_1"),
        prices={i.id: i.price for i in rs.shop},
        colours={i.id: rs.chip(i.chip).colour for i in rs.shop},
    )


def softmax(scores: dict[str, float], legal: list[str], temperature: float) -> dict[str, float]:
    """Probabilities over `legal`; temperature 0 puts all on the first best action."""
    if temperature == 0:
        best = max(legal, key=lambda a: scores[a])  # max keeps the first of equal scores
        return {a: 1.0 if a == best else 0.0 for a in legal}
    top = max(scores[a] for a in legal)
    weights = {a: math.exp((scores[a] - top) / temperature) for a in legal}
    total = sum(weights.values())
    return {a: w / total for a, w in weights.items()}


class RuleBot(CoreBot):
    """A strategy's shop pseudo-policy; the shared `CoreBot` rules for everything else."""

    def __init__(
        self,
        rs: Ruleset,
        strategy: str,
        draw_limit: int,
        points_round: int,
        seed: int | None = None,
        temperature: float = DEFAULT_TEMPERATURE,
    ):
        if strategy not in STRATEGIES:
            raise ValueError(
                f"unknown strategy {strategy!r} (known: {', '.join(sorted(STRATEGIES))})"
            )
        if not temperature >= 0:
            raise ValueError(f"temperature must be at least 0, got {temperature!r}")
        self.strategy: Strategy = STRATEGIES[strategy]
        super().__init__(rs, draw_limit, points_round, self.strategy.colour)
        self.temperature = temperature
        self._rng = random.Random(seed)
        self.name = bot_name(strategy, draw_limit, points_round)
        self.params: dict[str, Any] = {
            "strategy": strategy,
            "draw_limit": draw_limit,
            "points_round": points_round,
            "seed": seed,
            "temperature": temperature,
        }

    def _shop(self, state: GameState, seat: str, legal: list[str]) -> str:
        probs = shop_probabilities(self, state, seat, legal)
        actions = list(probs)
        return self._rng.choices(actions, weights=[probs[a] for a in actions])[0]


def shop_probabilities(
    bot: RuleBot, state: GameState, seat: str, legal: list[str]
) -> dict[str, float]:
    """The bot's probability of each legal shop action (keys: `legal`)."""
    scores = bot.strategy.score(shop_view(bot._rs, state, seat, legal))
    scores = {a: scores.get(a, -math.inf) for a in legal}
    return softmax(scores, legal, bot.temperature)
