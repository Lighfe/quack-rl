from quack_rl.components import get_component
from quack_rl.engine.state import GameState, Phase, PlayerState, Status
from quack_rl.rules import Ruleset, ShopItem

WAIT = "wait"
DRAW = "draw"
STOP = "stop"
DONE = "done"
TAKE_MONEY = "take_money"
TAKE_POINTS = "take_points"
BUY_PREFIX = "buy:"
PLAY_PREFIX = "play:"
PUT_BACK_DRAW = "put_back_draw"
PUT_BACK_STOP = "put_back_stop"
MAX_HAND = 4  # the largest blue chip value in a ruleset: hand slots 0..3


def play(slot: int) -> str:
    return f"{PLAY_PREFIX}{slot}"


def has_hand(rs: Ruleset) -> bool:
    """True when some chip of the ruleset draws a hand (the pick step exists)."""
    return any(get_component(rs.component_name(c)).hand_size(c) > 0 for c in rs.chips)


def buy(item_id: str) -> str:
    return f"{BUY_PREFIX}{item_id}"


def action_names(rs: Ruleset) -> list[str]:
    choice = [TAKE_MONEY, TAKE_POINTS] if rs.explosion_choice else []
    pick = [*(play(i) for i in range(MAX_HAND)), PUT_BACK_DRAW, PUT_BACK_STOP] if has_hand(rs) else []
    return [WAIT, DRAW, STOP, DONE, *choice, *(buy(item.id) for item in rs.shop), *pick]


def _can_buy(item: ShopItem, rs: Ruleset, p: PlayerState, round_: int) -> bool:
    if item.price > p.money or item.min_round > round_:
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
        if p.hand:
            return [*(play(i) for i in range(len(p.hand))), PUT_BACK_DRAW, PUT_BACK_STOP]
        return [DRAW] if not p.placed else [DRAW, STOP]
    if state.phase is Phase.CHOICE:
        return [TAKE_MONEY, TAKE_POINTS] if p.status is Status.EXPLODED else [WAIT]
    if state.phase is Phase.SHOP:
        if p.shop_done:
            return [WAIT]
        buys = [buy(item.id) for item in rs.shop if _can_buy(item, rs, p, state.round)]
        return [DONE, *buys]
    return []
