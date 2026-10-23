import random
import re
from typing import Any

from quack_rl.bots.strategy import Strategy, load_strategy
from quack_rl.components import get_component
from quack_rl.engine import (
    BUY_PREFIX,
    CARD_DROP_2,
    CARD_DROP_END,
    CONTINUE,
    DONE,
    DRAW,
    PUT_BACK_DRAW,
    PUT_BACK_STOP,
    RESTART,
    STOP,
    TAKE_MONEY,
    TAKE_POINTS,
    GameState,
    Phase,
    buy,
    explosion_limit,
    play,
    start_field,
)
from quack_rl.rules import Ruleset

BASELINE_NAME = "draw20-pts1-points"
RESTART_BELOW = 8  # card 2: the bot restarts only a pot that moved it fewer fields than this
_NAME = re.compile(r"draw(\d+)-pts(\d+)-(.+)")


def _total_after(chip_id: str, white_total: int, last: str | None, rs: Ruleset) -> int:
    """The white total after the chip is placed behind `last` (None: first chip of the pot).

    As the engine does it: the chip's weight is added, and when the chip puts the chip before it
    back into the bag (yellow after white), that chip's weight leaves the total."""
    chip = rs.chip(chip_id)
    component = get_component(rs.component_name(chip))
    total = white_total + component.explosion_weight(chip)
    if last is not None:
        previous = rs.chip(last)
        if component.puts_back_previous(chip, previous):
            total -= get_component(rs.component_name(previous)).explosion_weight(previous)
    return total


def _explosive_chips(
    bag: dict[str, int],
    white_total: int,
    rs: Ruleset,
    last: str | None = None,
    limit: int | None = None,
) -> tuple[int, int]:
    """(chips that would push the white total over the limit, bag size).

    `last` is the chip placed last in the pot; with it the yellow put-back is counted.
    `limit` is the explosion limit of the round (card 4); the ruleset limit when None."""
    limit = rs.explosion_limit if limit is None else limit
    bad = 0
    size = 0
    for chip_id, count in bag.items():
        size += count
        if _total_after(chip_id, white_total, last, rs) > limit:
            bad += count
    return bad, size


def explosion_chance(
    bag: dict[str, int],
    white_total: int,
    rs: Ruleset,
    last: str | None = None,
    limit: int | None = None,
) -> float:
    """Chance that the next draw explodes. The bag is public. An empty bag gives 0."""
    bad, size = _explosive_chips(bag, white_total, rs, last, limit)
    return bad / size if size else 0.0


def _last(p: Any) -> str | None:
    return p.placed[-1] if p.placed else None


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


class HeuristicBot:
    """Draw or Stop by the chance to explode; buy points from a round on, then by strategy.

    Explosion choice: after an explosion take money before the points round and points from it
    on; the shop has no points items and the bot buys nothing in the last round.

    Cards: the explosion look-ahead uses the explosion limit of the round (card 4).
    Card 6 and card 5: take the drop (card 6 `card_drop_2`, card 5 `card_drop_end`), which
    risks no chip in the bag. Card 2 (restart offered at 5 chips in the pot): restart when the
    next draw explodes with more than the draw limit (the bot would stop) and the pot moved the
    bot fewer than `RESTART_BELOW` fields; else continue.
    """

    kind = "bot"

    def __init__(
        self,
        rs: Ruleset,
        draw_limit: int = 20,
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
        if state.phase is Phase.BREW and state.players[seat].hand:
            action = self._pick(state, seat)
            return action if action in legal else legal[0]
        if state.phase is Phase.BREW:
            action = self._brew(state, seat)
            return action if action in legal else DRAW if DRAW in legal else legal[0]
        if state.phase is Phase.SHOP:
            action = self._shop(state, seat, legal)
            return action if action in legal else DONE if DONE in legal else legal[0]
        if state.phase is Phase.CARD_CHOICE:
            wanted = CARD_DROP_2 if CARD_DROP_2 in legal else CARD_DROP_END
            return wanted if wanted in legal else legal[0]
        if state.phase is Phase.RESTART:
            return RESTART if self._restart(state, seat) and RESTART in legal else (
                CONTINUE if CONTINUE in legal else legal[0]
            )
        if state.phase is Phase.CHOICE:
            action = TAKE_POINTS if state.round >= self.points_round else TAKE_MONEY
            return action if action in legal else legal[0]
        return legal[0]

    def _brew(self, state: GameState, seat: str) -> str:
        p = state.players[seat]
        bad, size = _explosive_chips(
            p.bag, p.white_total, self._rs, _last(p), explosion_limit(state, self._rs)
        )
        # chance > limit, in exact integer arithmetic: bad / size > percent / 100
        return STOP if bad * 100 > self.draw_limit * size else DRAW

    def _restart(self, state: GameState, seat: str) -> bool:
        """Card 2: restart a pot that would be stopped now and has moved the bot little."""
        p = state.players[seat]
        bad, size = _explosive_chips(
            p.bag, p.white_total, self._rs, _last(p), explosion_limit(state, self._rs)
        )
        moved = p.field - start_field(p, self._rs)
        return bad * 100 > self.draw_limit * size and moved < RESTART_BELOW

    def _advance(self, chip_id: str, p: Any) -> int:
        """How far the engine would move the player if the chip were played now."""
        chip = self._rs.chip(chip_id)
        component = get_component(self._rs.component_name(chip))
        previous = self._rs.chip(p.placed[-1]) if p.placed else None
        bonus = component.place_bonus(chip, previous, [self._rs.chip(c) for c in p.placed])
        return min(p.field + chip.value + bonus, self._rs.track_end) - p.field

    def _pick(self, state: GameState, seat: str) -> str:
        """Pick step: play the safe chip with the highest advance; else put back and Draw or Stop.

        The stop rule is computed on the bag with the whole hand put back."""
        p = state.players[seat]
        best_slot, best_advance = None, 0
        all_explode = True
        limit = explosion_limit(state, self._rs)
        for slot, chip_id in enumerate(p.hand):
            if _total_after(chip_id, p.white_total, _last(p), self._rs) > limit:
                continue
            all_explode = False
            advance = self._advance(chip_id, p)
            if advance > best_advance:  # strictly: on a tie the lowest slot stays
                best_slot, best_advance = slot, advance
        if best_slot is not None:
            return play(best_slot)
        if all_explode:
            return PUT_BACK_STOP
        bag = dict(p.bag)
        for chip_id in p.hand:
            bag[chip_id] = bag.get(chip_id, 0) + 1
        bad, size = _explosive_chips(
            bag, p.white_total, self._rs, _last(p), explosion_limit(state, self._rs)
        )
        return PUT_BACK_STOP if bad * 100 > self.draw_limit * size else PUT_BACK_DRAW

    def _shop(self, state: GameState, seat: str, legal: list[str]) -> str:
        if state.round >= self._rs.rounds:
            return DONE  # money of the last round is worth nothing in the shop
        affordable = [a.removeprefix(BUY_PREFIX) for a in legal if a.startswith(BUY_PREFIX)]
        # Items of the list that the shop lacks are never legal, so they are skipped here.
        for item_id in self._strategy.ranked():
            if item_id in affordable:
                return buy(item_id)
        # The most expensive legal non-points item; on a tie the first in shop order.
        rest = [i for i in self._rs.shop if i.id in affordable and i.kind != "points"]
        if rest:
            return buy(max(rest, key=lambda i: i.price).id)
        return DONE
