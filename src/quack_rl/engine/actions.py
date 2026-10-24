from quack_rl.components import get_component
from quack_rl.engine.state import GameState, Phase, PlayerState, Status
from quack_rl.rules import ChipSpec, Ruleset, ShopItem

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
CONTINUE = "continue"  # v1.11 card 2
RESTART = "restart"
CARD_DROP_2 = "card_drop_2"  # card 6: drop +2 at once
CARD_PURPLE = "card_purple"  # card 6: a purple 1 chip
CARD_BLACK = "card_black"  # card 5: a black 1 chip
CARD_CHIP_PREFIX = "card_chip:"  # card 5: a chip with value 2, by id
CARD_RUBIES = "card_rubies"  # card 5: 3 rubies
RUBY_DROP = "ruby_drop"  # shop: ruby_cost rubies for a droplet +1
USE_FLASK = "use_flask"  # brew: the last white chip goes back into the bag
REFILL_FLASK = "refill_flask"  # shop: ruby_cost rubies fill the empty flask
MAX_HAND = 4  # the largest blue chip value in a ruleset: hand slots 0..3


def play(slot: int) -> str:
    return f"{PLAY_PREFIX}{slot}"


def has_hand(rs: Ruleset) -> bool:
    """True when some chip of the ruleset draws a hand (the pick step exists)."""
    return any(get_component(rs.component_name(c)).hand_size(c) > 0 for c in rs.chips)


def buy(item_id: str) -> str:
    return f"{BUY_PREFIX}{item_id}"


LEGACY_COLOURS = 5  # the first five chip colours of a ruleset (v1.9: white to red) keep their place


def _appended(item: ShopItem, rs: Ruleset) -> bool:
    """A chip of a colour beyond the first five (v1.10: black, yellow, purple) is listed after
    the pick actions, so the indices of the actions of v1.9 stay the same."""
    colours = list(dict.fromkeys(c.colour for c in rs.chips))
    return colours.index(rs.chip(item.chip).colour) >= LEGACY_COLOURS


def action_names(rs: Ruleset) -> list[str]:
    choice = [TAKE_MONEY, TAKE_POINTS]
    pick = [*(play(i) for i in range(MAX_HAND)), PUT_BACK_DRAW, PUT_BACK_STOP] if has_hand(rs) else []
    early = [buy(item.id) for item in rs.shop if not _appended(item, rs)]
    late = [buy(item.id) for item in rs.shop if _appended(item, rs)]
    return [WAIT, DRAW, STOP, DONE, *choice, *early, *pick, *late, *_card_actions(rs), RUBY_DROP, USE_FLASK, REFILL_FLASK]


def _card_actions(rs: Ruleset) -> list[str]:
    """The card actions, appended at the end of the list (the order of the RL mask)."""
    effects = {rs.card(c.id).effect for c in rs.cards}
    names: list[str] = []
    if "restart_after_5" in effects:
        names += [CONTINUE, RESTART]
    if "choice_drop2_or_purple" in effects:
        names += [CARD_DROP_2, CARD_PURPLE]
    if "choice_black_or_value2_or_rubies" in effects:
        chips = (f"{CARD_CHIP_PREFIX}{c.id}" for c in value_two_chips(rs))
        names += [CARD_BLACK, *chips, CARD_RUBIES]
    return names


def value_two_chips(rs: Ruleset) -> list[ChipSpec]:
    """Every chip of the ruleset with value 2, in ruleset order (card 5, option B)."""
    return [c for c in rs.chips if c.value == 2]


def _can_buy(item: ShopItem, rs: Ruleset, p: PlayerState, round_: int) -> bool:
    if item.price > p.money or item.min_round > round_:
        return False
    if rs.max_chip_purchases is not None and p.chip_purchases >= rs.max_chip_purchases:
        return False
    if rs.distinct_chip_colours and rs.chip(item.chip).colour in p.chip_colours:
        return False
    return True


def _can_use_flask(p: PlayerState, rs: Ruleset) -> bool:
    """A brewing player (not exploded, not stopped) with a full flask whose last chip is white."""
    return p.flask_full and rs.chip(p.placed[-1]).colour == "white"


def legal_actions(state: GameState, rs: Ruleset, seat: str) -> list[str]:
    p = state.players[seat]
    if state.phase is Phase.BREW:
        if p.status is not Status.BREWING:
            return [WAIT]
        if p.hand:
            return [*(play(i) for i in range(len(p.hand))), PUT_BACK_DRAW, PUT_BACK_STOP]
        if not p.placed:
            return [DRAW]
        flask = [USE_FLASK] if _can_use_flask(p, rs) else []
        return [DRAW, STOP, *flask]
    if state.phase is Phase.CARD_CHOICE:
        if state.card is not None and rs.card(state.card).effect == "choice_drop2_or_purple":
            return [CARD_DROP_2, CARD_PURPLE]
        chips = [f"{CARD_CHIP_PREFIX}{c.id}" for c in value_two_chips(rs)]
        return [CARD_BLACK, *chips, CARD_RUBIES]
    if state.phase is Phase.RESTART:
        return [CONTINUE, RESTART] if p.restart_pending else [WAIT]
    if state.phase is Phase.CHOICE:
        return [TAKE_MONEY, TAKE_POINTS] if p.status is Status.EXPLODED else [WAIT]
    if state.phase is Phase.SHOP:
        if p.shop_done:
            return [WAIT]
        buys = [buy(item.id) for item in rs.shop if _can_buy(item, rs, p, state.round)]
        ruby = [RUBY_DROP] if p.rubies >= rs.ruby_cost else []
        refill = [REFILL_FLASK] if not p.flask_full and p.rubies >= rs.ruby_cost else []
        return [DONE, *buys, *ruby, *refill]
    return []
