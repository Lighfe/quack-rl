from quack_rl.engine.state import GameState, Phase, PlayerState, Status
from quack_rl.rules import Ruleset, ShopItem

WAIT = "wait"
DRAW = "draw"
STOP = "stop"
DONE = "done"
BUY_PREFIX = "buy:"


def buy(item_id: str) -> str:
    return f"{BUY_PREFIX}{item_id}"


def action_names(rs: Ruleset) -> list[str]:
    return [WAIT, DRAW, STOP, DONE, *(buy(item.id) for item in rs.shop)]


def _can_buy(item: ShopItem, rs: Ruleset, p: PlayerState) -> bool:
    if item.price > p.money:
        return False
    if item.kind == "remove_chip":
        return item.chip is not None and p.owned(item.chip) > 0
    if item.kind == "chip" and item.chip is not None:
        if rs.max_chip_purchases is not None and p.chip_purchases >= rs.max_chip_purchases:
            return False
        if rs.distinct_chip_colours and rs.chip(item.chip).colour in p.chip_colours:
            return False
    return True


def legal_actions(state: GameState, rs: Ruleset, seat: str) -> list[str]:
    p = state.players[seat]
    if state.phase is Phase.BREW:
        if p.status is not Status.BREWING:
            return [WAIT]
        return [DRAW] if not p.placed else [DRAW, STOP]
    if state.phase is Phase.SHOP:
        if p.shop_done:
            return [WAIT]
        buys = [buy(item.id) for item in rs.shop if _can_buy(item, rs, p)]
        return [DONE, *buys]
    return []
