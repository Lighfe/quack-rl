"""Opponent names to bots, and a mix of bots that picks one per episode."""

import random
from typing import Any

from quack_rl.bots import RandomBot, RuleBot, parse_bot_name
from quack_rl.rules import load_ruleset

RANDOM_NAMES = ("random", "bot:random")


def make_opponent(name: str, seed: int | None = None, rules: str = "v2.3") -> Any:
    """Return a bot for `name`: `random`, or `<strategy>-draw<percent>-pts<round>` (each with or
    without the `bot:` prefix). Raise ValueError on any other name."""
    if name in RANDOM_NAMES:
        return RandomBot(seed)
    try:
        strategy, draw_limit, points_round = parse_bot_name(name)
    except ValueError as err:
        raise ValueError(
            f"unknown opponent {name!r}: known forms are 'random' and "
            f"'<strategy>-draw<percent>-pts<round>' ({err})"
        ) from err
    return RuleBot(load_ruleset(rules), strategy, draw_limit, points_round, seed)


def parse_opponents(text: str) -> list[str]:
    """Split a comma-separated list of bot specs (spaces around commas allowed, repeats kept).

    Raise ValueError naming the first empty or unknown item."""
    specs = [item.strip() for item in text.split(",")]
    for spec in specs:
        if not spec:
            raise ValueError(f"empty item '' in the opponent list {text!r}")
        make_opponent(spec)  # raises ValueError that names the item
    return specs


def distinct_specs(specs: list[str]) -> list[str]:
    """The distinct specs in list order, then `bot:random` unless it is already in the list."""
    out = list(dict.fromkeys(specs))
    if not any(spec in RANDOM_NAMES for spec in out):
        out.append("bot:random")
    return out


class OpponentMix:
    """A bot that plays each episode as one bot of a list, sampled on `reset()`.

    `QuackEnv.reset` calls `reset()`. Each spec is drawn with weight one per time it appears in
    `specs`, from a generator seeded with `seed`, so the same seed gives the same sequence. One bot
    is built per distinct spec and kept for the whole run.
    """

    kind = "bot"
    name = "mix"

    def __init__(self, specs: list[str], seed: int | None = None, rules: str = "v2.3"):
        if not specs:
            raise ValueError("the opponent mix needs at least one spec")
        self.specs = list(specs)
        self.params: dict[str, Any] = {"specs": self.specs, "seed": seed}
        self._rng = random.Random(seed)
        self._bots = {spec: make_opponent(spec, seed, rules) for spec in dict.fromkeys(specs)}
        self.current: str | None = None  # the spec of this episode

    def reset(self) -> None:
        self.current = self._rng.choice(self.specs)

    def choose(self, state: Any, seat: str, legal: list[str]) -> str:
        if self.current is None:
            raise RuntimeError("the opponent mix picks its bot on reset(): call reset() first")
        return self._bots[self.current].choose(state, seat, legal)
