from quack_rl.components import get_component
from quack_rl.engine.board import calculate_rat_tails
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
CARD_TAILS_PREFIX = (
    "card_tails:"  # card 8: give up 1 to 3 rat tails for rubies; `card_tails:0` declines
)
CARD_TAILS_MAX = 3
CARD_SWAP_PREFIX = "card_swap:"  # card 12: a ruby for a value-1 chip, by id
CARD_SWAP_NO = "card_swap_no"  # card 12: decline
CARD_SWAP_COLOURS = ("green", "blue", "red", "yellow", "orange", "white")
CARD_POINTS = "card_points"  # card 14: 4 points
CARD_REMOVE_WHITE = "card_remove_white"  # card 14: a white 1 chip leaves the bag for good
CARD_POINTS_AMOUNT = 4
CARD_CHIP4_PREFIX = "card_chip4:"  # card 19: a value-4 chip, by id
CARD_TAIL_POINTS = "card_tail_points"  # card 19: points equal to the rat tail entitlement
CARD_CHIP4_COLOURS = ("green", "blue", "red", "yellow")
CARD_UPGRADE_PREFIX = (
    "card_upgrade:"  # card 11: a drawn chip becomes the next higher value of its colour
)
CARD_DRAW_COUNT = 4  # card 11: chips drawn by each player
CARD_NO_UPGRADE = ("white", "orange")  # colours card 11 cannot upgrade
CARD_PLACE_PREFIX = "card_place:"  # card 10: the drawn chip that is placed, by id
CARD_PLACE_DRAW = 5  # card 10: chips drawn by a player who stopped without exploding
USE_CARD_17 = "use_card_17"  # card 17: the first white chip of the round goes back into the bag
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
    pick = (
        [*(play(i) for i in range(MAX_HAND)), PUT_BACK_DRAW, PUT_BACK_STOP] if has_hand(rs) else []
    )
    early = [buy(item.id) for item in rs.shop if not _appended(item, rs)]
    late = [buy(item.id) for item in rs.shop if _appended(item, rs)]
    return [
        WAIT,
        DRAW,
        STOP,
        DONE,
        *choice,
        *early,
        *pick,
        *late,
        *_card_actions(rs),
        RUBY_DROP,
        USE_FLASK,
        REFILL_FLASK,
        *_late_card_actions(rs),
    ]


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


def swap_chips(rs: Ruleset) -> list[str]:
    """Card 12: the value-1 chips of the allowed colours, in the order of CARD_SWAP_COLOURS."""
    return [c.id for col in CARD_SWAP_COLOURS for c in rs.chips if c.colour == col and c.value == 1]


def chip4_chips(rs: Ruleset) -> list[str]:
    """Card 19: the value-4 chips of the allowed colours, in the order of CARD_CHIP4_COLOURS."""
    return [
        c.id for col in CARD_CHIP4_COLOURS for c in rs.chips if c.colour == col and c.value == 4
    ]


def upgrade_target(rs: Ruleset, chip_id: str) -> str | None:
    """Card 11: the next higher value of the colour of `chip_id`; None for white, orange and the
    top value of a colour."""
    chip = rs.chip(chip_id)
    if chip.colour in CARD_NO_UPGRADE:
        return None
    higher = [c for c in rs.chips if c.colour == chip.colour and c.value > chip.value]
    return min(higher, key=lambda c: c.value).id if higher else None


def upgradable_chips(rs: Ruleset) -> list[str]:
    """Card 11: the chips that have an upgrade, in ruleset order."""
    return [c.id for c in rs.chips if upgrade_target(rs, c.id) is not None]


def _late_card_actions(rs: Ruleset) -> list[str]:
    """The actions of cards 8, 10, 11, 12, 14, 17 and 19 (and 20, which has none), appended after
    the flask actions."""
    effects = {rs.card(c.id).effect for c in rs.cards}
    names: list[str] = []
    if "rat_tails_for_rubies" in effects:
        names += [f"{CARD_TAILS_PREFIX}{n}" for n in range(CARD_TAILS_MAX + 1)]
    if "ruby_for_chip" in effects:
        names += [*(f"{CARD_SWAP_PREFIX}{c}" for c in swap_chips(rs)), CARD_SWAP_NO]
    if "points_or_remove_white" in effects:
        names += [CARD_POINTS, CARD_REMOVE_WHITE]
    if "chip4_or_tail_points" in effects:
        names += [*(f"{CARD_CHIP4_PREFIX}{c}" for c in chip4_chips(rs)), CARD_TAIL_POINTS]
    if "draw4_upgrade" in effects:
        names += [f"{CARD_UPGRADE_PREFIX}{c}" for c in upgradable_chips(rs)]
    if "draw5_choose_place" in effects:
        names += [f"{CARD_PLACE_PREFIX}{c.id}" for c in rs.chips]
    if "first_white_back" in effects:
        names.append(USE_CARD_17)
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


def _can_use_card_17(state: GameState, rs: Ruleset, p: PlayerState) -> bool:
    """Card 17: the last placed chip is the first white chip of the round and no other chip has
    been placed since (`first_white_open`); the flask is not needed."""
    return (
        state.card is not None
        and rs.card(state.card).effect == "first_white_back"
        and p.first_white_open
    )


def late_card_choice(state: GameState, rs: Ruleset, seat: str) -> list[str] | None:
    """The options of the cards 8, 10, 11, 12, 14 and 19 for one seat ([WAIT] when it is not asked);
    None for any other card."""
    if state.card is None:
        return None
    effect = rs.card(state.card).effect
    p = state.players[seat]
    if effect == "rat_tails_for_rubies":
        entitlement = calculate_rat_tails({s: state.players[s].points for s in state.players}, rs)[
            seat
        ]
        if entitlement == 0:
            return [WAIT]
        return [f"{CARD_TAILS_PREFIX}{n}" for n in range(min(entitlement, CARD_TAILS_MAX) + 1)]
    if effect == "ruby_for_chip":
        if p.rubies < 1:
            return [WAIT]
        return [*(f"{CARD_SWAP_PREFIX}{c}" for c in swap_chips(rs)), CARD_SWAP_NO]
    if effect == "points_or_remove_white":
        if p.bag.get(white_one(rs), 0) < 1:
            return [WAIT]
        return [CARD_POINTS, CARD_REMOVE_WHITE]
    if effect == "draw4_upgrade":
        drawn = dict.fromkeys(p.card_draw)  # distinct chips, in draw order
        options = [f"{CARD_UPGRADE_PREFIX}{c}" for c in drawn if upgrade_target(rs, c) is not None]
        return options or [WAIT]
    if effect == "draw5_choose_place":
        drawn = dict.fromkeys(p.card_draw)  # distinct chips, in draw order
        return [f"{CARD_PLACE_PREFIX}{c}" for c in drawn] or [WAIT]
    if effect == "chip4_or_tail_points":
        chips = [f"{CARD_CHIP4_PREFIX}{c}" for c in chip4_chips(rs)]
        entitlement = calculate_rat_tails({s: state.players[s].points for s in state.players}, rs)[
            seat
        ]
        return [*chips, CARD_TAIL_POINTS] if entitlement > 0 else chips
    return None


def white_one(rs: Ruleset) -> str:
    """The white chip of value 1 (card 14)."""
    return next(c.id for c in rs.chips if c.colour == "white" and c.value == 1)


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
        card_17 = [USE_CARD_17] if _can_use_card_17(state, rs, p) else []
        return [DRAW, STOP, *flask, *card_17]
    if state.phase is Phase.CARD_CHOICE:
        late = late_card_choice(state, rs, seat)
        if late is not None:
            return late
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
        if rs.ruby_step:
            return [DONE, *buys]
        return [DONE, *buys, *_ruby_spends(p, rs)]
    if state.phase is Phase.RUBY:
        if p.ruby_done:
            return [WAIT]
        return [DONE, *_ruby_spends(p, rs)]
    return []


def _ruby_spends(p: PlayerState, rs: Ruleset) -> list[str]:
    """The ruby spends a player can pay: `ruby_drop`, and `refill_flask` with an empty flask."""
    ruby = [RUBY_DROP] if p.rubies >= rs.ruby_cost else []
    refill = [REFILL_FLASK] if not p.flask_full and p.rubies >= rs.ruby_cost else []
    return [*ruby, *refill]
