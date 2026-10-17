from typing import Any

from quack_rl.engine.actions import TAKE_MONEY, TAKE_POINTS
from quack_rl.engine.state import SEATS, GameState, Phase, scoring_field
from quack_rl.rules import Ruleset


def apply_choice(
    state: GameState, rs: Ruleset, actions: dict[str, str], events: list[dict[str, Any]]
) -> None:
    """v1.8: an exploded player takes the money or the points of the scoring field, in full.

    In the last round with last_round_money_divisor the money becomes points at once.
    """
    for seat in SEATS:
        action = actions[seat]
        if action not in (TAKE_MONEY, TAKE_POINTS):
            continue
        p = state.players[seat]
        assert p.final_field is not None
        fld = scoring_field(p.final_field, rs)
        if action == TAKE_MONEY:
            money = rs.money[fld]
            if state.round == rs.rounds and rs.last_round_money_divisor is not None:
                p.points += money // rs.last_round_money_divisor
                money = 0
            elif state.round == rs.rounds:
                money = money * rs.last_round_money_percent // 100
            p.money = money
            events.append({"seat": seat, "kind": "take_money", "amount": p.money})
        else:
            gained = rs.points[fld] if rs.points is not None else 0
            p.points += gained
            events.append({"seat": seat, "kind": "take_points", "amount": gained})
    state.phase = Phase.SHOP
