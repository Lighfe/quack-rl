import random
import re
from typing import Any

from quack_rl.bots.strategy import Strategy, load_strategy
from quack_rl.components import get_component
from quack_rl.engine import BUY_PREFIX, DONE, DRAW, STOP, GameState, Phase, buy
from quack_rl.rules import Ruleset

BASELINE_NAME = "draw30-pts1-points"
_NAME = re.compile(r"draw(\d+)-pts(\d+)-(.+)")


def _explosive_chips(bag: dict[str, int], white_total: int, rs: Ruleset) -> tuple[int, int]:
    """(chips that would push the white total over the limit, bag size)."""
    bad = 0
    size = 0
    for chip_id, count in bag.items():
        size += count
        chip = rs.chip(chip_id)
        if white_total + get_component(chip.component).explosion_weight(chip) > rs.explosion_limit:
            bad += count
    return bad, size


def explosion_chance(bag: dict[str, int], white_total: int, rs: Ruleset) -> float:
    """Chance that the next draw explodes. The bag is public. An empty bag gives 0."""
    bad, size = _explosive_chips(bag, white_total, rs)
    return bad / size if size else 0.0


def bot_name(draw_limit: int, points_round: int, strategy: str) -> str:
    return f"draw{draw_limit}-pts{points_round}-{strategy}"


def parse_bot_name(name: str) -> tuple[int, int, str]:
    """Split `draw30-pts3-blue` (or `bot:draw30-pts3-blue`) into its parameters. Raise ValueError on a bad name."""
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


class HeuristicBot:
    """Draw or Stop by the chance to explode; buy points from a round on, then by strategy."""

    kind = "bot"

    def __init__(
        self,
        rs: Ruleset,
        draw_limit: int = 30,
        points_round: int = 1,
        strategy: str | Strategy = "points",
        seed: int | None = None,
    ):
        self._rs = rs
        self._strategy = strategy if isinstance(strategy, Strategy) else load_strategy(strategy)
        self.draw_limit = draw_limit
        self.points_round = points_round
        self._rng = random.Random(seed)
        self.name = bot_name(draw_limit, points_round, self._strategy.name)
        self.params: dict[str, Any] = {
            "draw_limit": draw_limit,
            "points_round": points_round,
            "strategy": self._strategy.name,
            "seed": seed,
        }

    def choose(self, state: GameState, seat: str, legal: list[str]) -> str:
        if state.phase is Phase.BREW:
            action = self._brew(state, seat)
            return action if action in legal else DRAW if DRAW in legal else legal[0]
        if state.phase is Phase.SHOP:
            action = self._shop(state, seat, legal)
            return action if action in legal else DONE if DONE in legal else legal[0]
        return legal[0]

    def _brew(self, state: GameState, seat: str) -> str:
        p = state.players[seat]
        bad, size = _explosive_chips(p.bag, p.white_total, self._rs)
        # chance > limit, in exact integer arithmetic: bad / size > percent / 100
        return STOP if bad * 100 > self.draw_limit * size else DRAW

    def _shop(self, state: GameState, seat: str, legal: list[str]) -> str:
        p = state.players[seat]
        if p.purchases >= self._rs.max_purchases:
            return DONE
        affordable = [a.removeprefix(BUY_PREFIX) for a in legal if a.startswith(BUY_PREFIX)]
        if state.round >= self.points_round:
            points = [self._rs.shop_item(i) for i in affordable]
            points = [i for i in points if i.kind == "points"]
            if points:
                best = max(i.points for i in points)
                return buy(self._rng.choice([i.id for i in points if i.points == best]))
        for item_id in self._strategy.ranked():
            if item_id in affordable:
                return buy(item_id)
        return DONE
