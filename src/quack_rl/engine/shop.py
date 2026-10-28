from typing import Any

from quack_rl.engine.actions import BUY_PREFIX, DONE, REFILL_FLASK, RUBY_DROP, legal_actions
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


def end_game(state: GameState, rs: Ruleset, events: list[dict[str, Any]]) -> None:
    """Rule 5: the game ends after Resolve (and the explosion choice) of the last round.

    Every player's rubies become rubies // last_round_ruby_divisor points (event `ruby_points`,
    seats p1, p2, also with 0 rubies), then the winner is decided (event `game_end`).
    """
    for seat in SEATS:
        p = state.players[seat]
        rubies = p.rubies
        added = add_points(p, rubies // rs.last_round_ruby_divisor, rs)
        p.rubies = 0
        events.append(
            {"seat": seat, "kind": "ruby_points", "rubies": rubies, "points": added, "total": 0}
        )
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


def _end_round(state: GameState, rs: Ruleset, events: list[dict[str, Any]]) -> None:
    """The round reset after the shop; the last round has no shop (see `end_game`)."""
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
        p.ruby_done = False
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


def _spend_ruby(
    p: PlayerState, rs: Ruleset, seat: str, action: str, events: list[dict[str, Any]]
) -> None:
    """A ruby spend: `ruby_drop` (droplet +1) or `refill_flask` (the flask is full again)."""
    p.rubies -= rs.ruby_cost
    if action == RUBY_DROP:
        p.droplet += 1
        events.append(
            {
                "seat": seat,
                "kind": "ruby_drop",
                "rubies": rs.ruby_cost,
                "drop": 1,
                "total": p.rubies,
            }
        )
    else:
        p.flask_full = True
        events.append(
            {"seat": seat, "kind": "refill_flask", "rubies": rs.ruby_cost, "total": p.rubies}
        )


def apply_shop(
    state: GameState, rs: Ruleset, actions: dict[str, str], events: list[dict[str, Any]]
) -> None:
    """Rules 4.4 and 4.5: purchases, then the ruby step (the last round has no shop)."""
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
            p.chip_purchases += 1
            p.chip_colours.append(rs.chip(item.chip).colour)
            _apply_item(p, item)
            events.append({"seat": seat, "kind": "buy", "item": item.id, "price": item.price})
    close_idle_shops(state, rs, events)


def close_idle_shops(state: GameState, rs: Ruleset, events: list[dict[str, Any]]) -> None:
    """Rule 4.4: a player with nothing left to do but Done stops shopping without being asked.

    Called when the SHOP phase is entered and after each shop step. A seat whose shop legal set
    is only `[DONE]` gets `shop_done` and the event `{"seat", "kind": "done", "auto": True}`.
    When every shop is closed, the ruby step follows (see `close_idle_ruby`) in the same step.
    """
    for seat in SEATS:
        p = state.players[seat]
        if not p.shop_done and legal_actions(state, rs, seat) == [DONE]:
            p.shop_done = True
            events.append({"seat": seat, "kind": "done", "auto": True})
    if all(p.shop_done for p in state.players.values()):
        state.phase = Phase.RUBY
        close_idle_ruby(state, rs, events)


def apply_ruby(
    state: GameState, rs: Ruleset, actions: dict[str, str], events: list[dict[str, Any]]
) -> None:
    """The ruby step after the shop: `ruby_drop`, `refill_flask` or `done`, then the round reset."""
    for seat in SEATS:
        p = state.players[seat]
        action = actions[seat]
        if action == DONE:
            p.ruby_done = True
            events.append({"seat": seat, "kind": "done"})
        elif action in (RUBY_DROP, REFILL_FLASK):
            _spend_ruby(p, rs, seat, action, events)
    close_idle_ruby(state, rs, events)


def close_idle_ruby(state: GameState, rs: Ruleset, events: list[dict[str, Any]]) -> None:
    """A player who can pay for no ruby spend leaves the ruby step without being asked.

    Called when the RUBY phase is entered and after each ruby step. A seat whose ruby legal set
    is only `[DONE]` gets `ruby_done` and the event `{"seat", "kind": "done", "auto": True}`.
    When every seat is done, the round ends (`_end_round`) in the same step.
    """
    for seat in SEATS:
        p = state.players[seat]
        if not p.ruby_done and legal_actions(state, rs, seat) == [DONE]:
            p.ruby_done = True
            events.append({"seat": seat, "kind": "done", "auto": True})
    if all(p.ruby_done for p in state.players.values()):
        _end_round(state, rs, events)
