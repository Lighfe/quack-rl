"""The labels of the actions: one function for the CLI menu and the web service."""

from quack_rl.cli.render import chip_text
from quack_rl.engine import (
    BUY_PREFIX,
    CARD_DROP_2,
    CARD_RUBIES,
    CONTINUE,
    PLAY_PREFIX,
    PUT_BACK_DRAW,
    PUT_BACK_STOP,
    REFILL_FLASK,
    RESTART,
    RUBY_DROP,
    TAKE_MONEY,
    TAKE_POINTS,
    USE_FLASK,
    GameState,
)
from quack_rl.engine.actions import (
    CARD_BLACK,
    CARD_CHIP4_PREFIX,
    CARD_CHIP_PREFIX,
    CARD_PLACE_PREFIX,
    CARD_POINTS,
    CARD_POINTS_AMOUNT,
    CARD_PURPLE,
    CARD_REMOVE_WHITE,
    CARD_SWAP_NO,
    CARD_SWAP_PREFIX,
    CARD_TAIL_POINTS,
    CARD_TAILS_PREFIX,
    CARD_UPGRADE_PREFIX,
    USE_CARD_17,
)
from quack_rl.engine.state import scoring_field
from quack_rl.rules import Ruleset


def _chip(chip_id: str, rs: Ruleset) -> str:
    return chip_text(chip_id, rs).plain


def _colour(chip_id: str, rs: Ruleset) -> str:
    return rs.chip(chip_id).colour


def _card_chip(colour: str, value: int, rs: Ruleset) -> str:
    return next(c.id for c in rs.chips if c.colour == colour and c.value == value)


def action_label(action: str, rs: Ruleset, state: GameState | None = None, seat: str = "") -> str:
    """The short text of an action. With a state and a seat, take_money, take_points and the
    hand picks name their amount or chip."""
    if state is not None and action in (TAKE_MONEY, TAKE_POINTS):
        p = state.players[seat]
        field = scoring_field(p.final_field if p.final_field is not None else p.field, rs)
        if action == TAKE_MONEY:
            return f"{action} (${rs.fields[field].money})"
        return f"{action} (+{rs.fields[field].points}pt)"
    if action.startswith(PLAY_PREFIX):
        slot = int(action.removeprefix(PLAY_PREFIX))
        if state is not None:
            return f"play {slot}: {_chip(state.players[seat].hand[slot], rs)}"
        return f"play {slot}"
    if action == RUBY_DROP:
        return f"ruby drop: {rs.ruby_cost} rubies, droplet +1"
    if action == USE_FLASK:
        return "flask: last white chip back to bag"
    if action == USE_CARD_17:
        return "card 17: first white chip back to bag"
    if action == REFILL_FLASK:
        return f"refill flask: {rs.ruby_cost} rubies"
    if action.startswith(CARD_TAILS_PREFIX):
        n = int(action.removeprefix(CARD_TAILS_PREFIX))
        return (
            f"card 8: {n} rat tail{'s' * (n != 1)} for rubies" if n else "card 8: keep my rat tails"
        )
    if action.startswith(CARD_PLACE_PREFIX):
        return f"card 10: place {_chip(action.removeprefix(CARD_PLACE_PREFIX), rs)}"
    if action.startswith(CARD_UPGRADE_PREFIX):
        return f"card 11: upgrade {_chip(action.removeprefix(CARD_UPGRADE_PREFIX), rs)}"
    if action.startswith(CARD_SWAP_PREFIX):
        return f"card 12: ruby for a {_colour(action.removeprefix(CARD_SWAP_PREFIX), rs)} 1"
    if action == CARD_SWAP_NO:
        return "card 12: no swap"
    if action == CARD_POINTS:
        return f"card 14: {CARD_POINTS_AMOUNT} points"
    if action == CARD_REMOVE_WHITE:
        return "card 14: remove a white 1 from the bag"
    if action.startswith(CARD_CHIP4_PREFIX):
        return f"card 19: a {_colour(action.removeprefix(CARD_CHIP4_PREFIX), rs)} 4 into the bag"
    if action == CARD_TAIL_POINTS:
        return "card 19: points for rat tails"
    if action == CONTINUE:
        return "continue brewing"
    if action == RESTART:
        return "restart: put the pot back, start over"
    if action == CARD_BLACK:
        return f"a {_chip(_card_chip('black', 1, rs), rs)} chip into the bag"
    if action == CARD_PURPLE:
        return f"a {_chip(_card_chip('purple', 1, rs), rs)} chip into the bag"
    if action == CARD_DROP_2:
        return "drop +2 now"
    if action == CARD_RUBIES:
        return "3 rubies"
    if action.startswith(CARD_CHIP_PREFIX):
        return f"a {_chip(action.removeprefix(CARD_CHIP_PREFIX), rs)} chip into the bag"
    if action == PUT_BACK_DRAW:
        return "put all back and Draw"
    if action == PUT_BACK_STOP:
        return "put all back and Stop"
    if action.startswith(BUY_PREFIX):
        item = rs.shop_item(action.removeprefix(BUY_PREFIX))
        return f"buy {item.id} ({item.price})"
    return action
