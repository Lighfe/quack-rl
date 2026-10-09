from quack_rl.engine.state import GameState, Phase, Status
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


def _can_buy(item: ShopItem, money: int, owned: int) -> bool:
    if item.price > money:
        return False
    if item.kind == "remove_chip":
        return owned > 0
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
        buys = [
            buy(item.id)
            for item in rs.shop
            if _can_buy(item, p.money, p.owned(item.chip) if item.chip else 0)
        ]
        return [DONE, *buys]
    return []
