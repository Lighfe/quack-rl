from typing import Any

from quack_rl.engine.actions import BUY_PREFIX, DONE
from quack_rl.engine.board import add_points
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


def _apply_item(p: PlayerState, item: ShopItem, rs: Ruleset) -> None:
    if item.kind == "chip" and item.chip is not None:
        p.bag[item.chip] = p.bag.get(item.chip, 0) + 1
    elif item.kind == "remove_chip" and item.chip is not None:
        if item.chip in p.placed:
            index = p.placed.index(item.chip)
            if index < len(p.placed_fields):  # states built by hand may lack the landing fields
                p.placed_fields.pop(index)
            p.placed.remove(item.chip)
        else:
            p.bag[item.chip] -= 1
            if p.bag[item.chip] == 0:
                del p.bag[item.chip]
    elif item.kind == "droplet":
        p.droplet_halves += item.halves
    elif item.kind == "points":
        add_points(p, item.points, rs)


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
        p.round_end_halves = 0
        p.field = start_field(p, rs)
    state.round += 1
    state.card = None
    state.phase = Phase.CARD if rs.cards else Phase.BREW
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
        elif action.startswith(BUY_PREFIX):
            item = rs.shop_item(action.removeprefix(BUY_PREFIX))
            p.money -= item.price
            p.purchases += 1
            if item.kind == "chip" and item.chip is not None:
                p.chip_purchases += 1
                p.chip_colours.append(rs.chip(item.chip).colour)
            _apply_item(p, item, rs)
            events.append({"seat": seat, "kind": "buy", "item": item.id, "price": item.price})
            if rs.max_purchases is not None and p.purchases >= rs.max_purchases:
                p.shop_done = True
    if all(p.shop_done for p in state.players.values()):
        _end_round(state, rs, events)
