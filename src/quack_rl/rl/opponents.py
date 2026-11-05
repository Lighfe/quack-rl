"""Opponent names to bots."""

from typing import Any

from quack_rl.bots import RandomBot, RuleBot, parse_bot_name
from quack_rl.rules import load_ruleset


def make_opponent(name: str, seed: int | None = None, rules: str = "v2.3") -> Any:
    """Return a bot for `name`: `random`, or `<strategy>-draw<percent>-pts<round>` (each with or
    without the `bot:` prefix). Raise ValueError on any other name."""
    if name in ("random", "bot:random"):
        return RandomBot(seed)
    try:
        strategy, draw_limit, points_round = parse_bot_name(name)
    except ValueError as err:
        raise ValueError(
            f"unknown opponent {name!r}: known forms are 'random' and "
            f"'<strategy>-draw<percent>-pts<round>' ({err})"
        ) from err
    return RuleBot(load_ruleset(rules), strategy, draw_limit, points_round, seed)
