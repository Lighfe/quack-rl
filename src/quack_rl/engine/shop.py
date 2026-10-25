from typing import Any

from quack_rl.engine.actions import BUY_PREFIX, DONE, REFILL_FLASK, RUBY_DROP
from quack_rl.engine.state import (
    SEATS,
    GameState,
    Phase,
    PlayerState,
    Status,
    scoring_field,
    start_field,
)
from quack_rl.rules import Ruleset, ShopItem


def _apply_item(p: PlayerState, item: ShopItem) -> None:
    """Buy a chip: it goes into the bag."""
    p.bag[item.chip] = p.bag.get(item.chip, 0) + 1


def decide_winner(state: GameState, rs: Ruleset) -> str:
    """Rule 5: most points; tie -> furthest scoring field; tie again -> draw."""
    p1, p2 = state.players["p1"], state.players["p2"]
    key1 = (p1.points, scoring_field(p1.final_field or 0, rs))
    key2 = (p2.points, scoring_field(p2.final_field or 0, rs))
    if key1 == key2:
        return "draw"
    return "p1" if key1 > key2 else "p2"


def _end_round(state: GameState, rs: Ruleset, events: list[dict[str, Any]]) -> None:
    if state.round >= rs.rounds:
        state.winner = decide_winner(state, rs)
        state.phase = Phase.GAME_OVER
        events.append(
            {
                "seat": None,
                "kind": "game_end",
                "winner": state.winner,
                "points": {s: state.players[s].points for s in SEATS},
                "final_fields": {s: state.players[s].final_field for s in SEATS},
            }
        )
        return
    for p in state.players.values():
        for chip_id in p.placed:
            p.bag[chip_id] = p.bag.get(chip_id, 0) + 1
        p.placed = []
        p.placed_fields = []
        p.money = 0
        p.white_total = 0
        p.status = Status.BREWING
        p.final_field = None
        p.purchases = 0
        p.chip_purchases = 0
        p.chip_colours = []
        p.shop_done = False
        p.restart_offered = False
        p.restart_pending = False
        p.rat_tail = 0
        p.rat_tail_adjust = 0
        p.card_draw = []
        p.card_place_done = False
        p.first_white_placed = False
        p.first_white_open = False
        p.field = start_field(p, rs)
    state.round += 1
    state.card = None
    state.phase = Phase.CARD
    events.append({"seat": None, "kind": "round_end", "next_round": state.round})


def apply_shop(
    state: GameState, rs: Ruleset, actions: dict[str, str], events: list[dict[str, Any]]
) -> None:
    """Rules 4.4, 4.5 and 5: purchases, then the round reset or the game end."""
    for seat in SEATS:
        p = state.players[seat]
        action = actions[seat]
        if action == DONE:
            p.shop_done = True
            events.append({"seat": seat, "kind": "done"})
        elif action == RUBY_DROP:
            p.rubies -= rs.ruby_cost
            p.droplet_halves += 2
            events.append(
                {
                    "seat": seat,
                    "kind": "ruby_drop",
                    "rubies": rs.ruby_cost,
                    "halves": 2,
                    "total": p.rubies,
                }
            )
        elif action == REFILL_FLASK:
            p.rubies -= rs.ruby_cost
            p.flask_full = True
            events.append(
                {"seat": seat, "kind": "refill_flask", "rubies": rs.ruby_cost, "total": p.rubies}
            )
        elif action.startswith(BUY_PREFIX):
            item = rs.shop_item(action.removeprefix(BUY_PREFIX))
            p.money -= item.price
            p.purchases += 1
            p.chip_purchases += 1
            p.chip_colours.append(rs.chip(item.chip).colour)
            _apply_item(p, item)
            events.append({"seat": seat, "kind": "buy", "item": item.id, "price": item.price})
    if all(p.shop_done for p in state.players.values()):
        _end_round(state, rs, events)
