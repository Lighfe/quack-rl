from typing import Any

from quack_rl.engine.actions import TAKE_MONEY, TAKE_POINTS
from quack_rl.engine.board import add_points
from quack_rl.engine.shop import close_idle_shops, end_game
from quack_rl.engine.state import SEATS, GameState, Phase, scoring_field
from quack_rl.rules import Ruleset


def apply_choice(
    state: GameState, rs: Ruleset, actions: dict[str, str], events: list[dict[str, Any]]
) -> None:
    """An exploded player takes the money or the points of the scoring field, in full.

    In the last round the money becomes points at once (money // last_round_money_divisor), and
    the game ends after the choice (`end_game`: no shop in the last round).
    """
    for seat in SEATS:
        action = actions[seat]
        if action not in (TAKE_MONEY, TAKE_POINTS):
            continue
        p = state.players[seat]
        assert p.final_field is not None
        fld = scoring_field(p.final_field, rs)
        if action == TAKE_MONEY:
            money = rs.fields[fld].money
            if state.round == rs.rounds:
                add_points(p, money // rs.last_round_money_divisor, rs)
                money = 0
            p.money = money
            events.append({"seat": seat, "kind": "take_money", "amount": p.money})
        else:
            gained = add_points(p, rs.fields[fld].points, rs)
            events.append({"seat": seat, "kind": "take_points", "amount": gained})
    if state.round == rs.rounds:
        end_game(state, rs, events)
    else:
        state.phase = Phase.SHOP
        close_idle_shops(state, rs, events)
