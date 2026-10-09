from typing import Any

from quack_rl.engine.actions import BUY_PREFIX, DONE
from quack_rl.engine.state import SEATS, GameState, Phase, PlayerState, Status, start_field
from quack_rl.rules import Ruleset, ShopItem


def _apply_item(p: PlayerState, item: ShopItem) -> None:
    if item.kind == "chip" and item.chip is not None:
        p.bag[item.chip] = p.bag.get(item.chip, 0) + 1
    elif item.kind == "remove_chip" and item.chip is not None:
        if item.chip in p.placed:
            p.placed.remove(item.chip)
        else:
            p.bag[item.chip] -= 1
            if p.bag[item.chip] == 0:
                del p.bag[item.chip]
    elif item.kind == "droplet":
        p.droplet_halves += item.halves
    elif item.kind == "points":
        p.points += item.points


def decide_winner(state: GameState) -> str:
    """Rule 5: most points; tie -> furthest final field; tie again -> draw."""
    p1, p2 = state.players["p1"], state.players["p2"]
    key1 = (p1.points, p1.final_field or 0)
    key2 = (p2.points, p2.final_field or 0)
    if key1 == key2:
        return "draw"
    return "p1" if key1 > key2 else "p2"


def _end_round(state: GameState, rs: Ruleset, events: list[dict[str, Any]]) -> None:
    if state.round >= rs.rounds:
        state.winner = decide_winner(state)
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
        p.money = 0
        p.white_total = 0
        p.status = Status.BREWING
        p.final_field = None
        p.purchases = 0
        p.shop_done = False
        p.field = start_field(p, rs)
    state.round += 1
    state.phase = Phase.BREW
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
            _apply_item(p, item)
            events.append({"seat": seat, "kind": "buy", "item": item.id, "price": item.price})
            if p.purchases >= rs.max_purchases:
                p.shop_done = True
    if all(p.shop_done for p in state.players.values()):
        _end_round(state, rs, events)
