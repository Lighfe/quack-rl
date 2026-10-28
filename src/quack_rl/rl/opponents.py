"""Opponent names to bots."""

from typing import Any

from quack_rl.bots import HeuristicBot, RandomBot, parse_bot_name
from quack_rl.rules import load_ruleset


def make_opponent(name: str, seed: int | None = None, rules: str = "v2.3") -> Any:
    """Return a bot for `name`: `random`, or `draw<percent>-pts<round>-<strategy>` (each with or
    without the `bot:` prefix). Raise ValueError on any other name."""
    if name in ("random", "bot:random"):
        return RandomBot(seed)
    try:
        draw_limit, points_round, strategy = parse_bot_name(name)
    except ValueError as err:
        raise ValueError(
            f"unknown opponent {name!r}: known forms are 'random' and "
            f"'draw<percent>-pts<round>-<strategy>' ({err})"
        ) from err
    return HeuristicBot(load_ruleset(rules), draw_limit, points_round, strategy, seed)
