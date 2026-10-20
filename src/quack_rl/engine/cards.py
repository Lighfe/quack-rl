"""Round-start cards (v1.11): the draw and the immediate effects.

The card effects that matter later in the round are read through `card_effect`: card 1 in
`resolve.py` (the ruby step) and card 4 in every place that reads the explosion limit
(`explosion_limit`). Cards 2, 5 and 6 are drawn and recorded and act like "no effect" for now.
"""

from typing import Any

from quack_rl.engine.chance import ChanceLog
from quack_rl.engine.state import SEATS, GameState, Phase, start_field
from quack_rl.rules import Ruleset


def card_effect(state: GameState, rs: Ruleset) -> str | None:
    """The effect name of the card of this round; None when no card is drawn (no cards)."""
    return rs.card(state.card).effect if state.card is not None else None


def explosion_limit(state: GameState, rs: Ruleset) -> int:
    """The explosion limit of this round: the ruleset limit, plus 2 with card 4."""
    return rs.explosion_limit + (2 if card_effect(state, rs) == "explosion_limit_plus_2" else 0)


def _green_one(rs: Ruleset) -> str:
    for chip in rs.chips:
        if chip.colour == "green" and chip.value == 1:
            return chip.id
    raise ValueError("card 7 needs a green chip of value 1 in the ruleset")


def apply_card(
    state: GameState, rs: Ruleset, chance: ChanceLog, events: list[dict[str, Any]]
) -> None:
    """Draw one card from the cards not drawn yet, resolve its immediate effects, start the brew."""
    card_id = chance.draw_card(state.deck)
    state.deck.remove(card_id)
    state.card = card_id
    effect = rs.card(card_id).effect
    events.append({"seat": None, "kind": "card_draw", "card": card_id, "effect": effect})
    if effect == "drop_all_1":
        for seat in SEATS:
            p = state.players[seat]
            p.droplet_halves += 2
            p.field = start_field(p, rs)
            events.append({"seat": seat, "kind": "card_drop", "halves": 2})
    elif effect == "fewest_points_green":
        fewest = min(state.players[s].points for s in SEATS)
        chip_id = _green_one(rs)
        for seat in SEATS:
            p = state.players[seat]
            if p.points == fewest:
                p.bag[chip_id] = p.bag.get(chip_id, 0) + 1
                events.append({"seat": seat, "kind": "card_chip", "chip": chip_id})
    state.phase = Phase.BREW
