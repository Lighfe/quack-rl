"""Determinization: fill what one seat cannot see with a draw from what it can see.

Hidden per player are the blue chip `hand` (out of the bag) and the `card_draw` of cards 10 and
11 (the chips stay in the bag). Bags are counts, so they have no order to shuffle; the deck is a
list and is shuffled. Everything else in the state is public.
"""

import copy
import random

from quack_rl.engine import SEATS, GameState
from quack_rl.rules import Ruleset


def _sorted_bag(bag: dict[str, int]) -> dict[str, int]:
    """The bag with its chip ids in sorted order and no empty entries (the engine deletes an entry
    when its count reaches 0), so two equal bags give the same draws."""
    return {chip_id: bag[chip_id] for chip_id in sorted(bag) if bag[chip_id] > 0}


def _draw_without_replacement(bag: dict[str, int], n: int, rng: random.Random) -> list[str]:
    """`n` chips drawn from `bag` without replacement; the bag itself is not changed."""
    left = dict(bag)
    drawn: list[str] = []
    for _ in range(min(n, sum(left.values()))):
        pick = rng.randrange(sum(left.values()))
        for chip_id in sorted(left):
            pick -= left[chip_id]
            if pick < 0:
                drawn.append(chip_id)
                left[chip_id] -= 1
                break
    return drawn


def determinize(state: GameState, rs: Ruleset, seat: str, rng: random.Random) -> GameState:
    """A copy of `state` as `seat` may see it, with the hidden parts drawn with `rng`.

    The opponent's hand goes back into its bag (empty hand), the opponent's `card_draw` is a fresh
    draw of the same length from that bag, and the deck is shuffled. The state is not changed.
    `rs` is part of the interface for rules that hide more; v2.3 needs nothing from it.
    """
    if seat not in SEATS:
        raise ValueError(f"unknown seat {seat!r}")
    world = copy.deepcopy(state)
    for other in SEATS:
        if other == seat:
            continue
        p = world.players[other]
        bag = dict(p.bag)
        for chip_id in p.hand:
            bag[chip_id] = bag.get(chip_id, 0) + 1
        p.bag = _sorted_bag(bag)
        p.hand = []
        p.card_draw = _draw_without_replacement(p.bag, len(p.card_draw), rng)
    world.deck = sorted(world.deck)
    rng.shuffle(world.deck)
    return world
