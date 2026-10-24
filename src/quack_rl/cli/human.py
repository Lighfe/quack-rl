from collections.abc import Callable
from typing import Any

import typer
from rich.console import Console

from quack_rl.cli.render import chip_text, draw_text, hand_text, render_board
from quack_rl.engine import (
    BUY_PREFIX,
    CARD_DROP_2,
    CARD_RUBIES,
    CONTINUE,
    DONE,
    DRAW,
    PLAY_PREFIX,
    PUT_BACK_DRAW,
    PUT_BACK_STOP,
    REFILL_FLASK,
    RESTART,
    RUBY_DROP,
    STOP,
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
from quack_rl.engine.state import Phase, scoring_field
from quack_rl.rules import Ruleset

# Skips d, s, m, p, r, t, k, f, l, u (fixed keys of other actions) so no key is used twice.
BUY_KEYS = "123456789abceghijnoqvwxyz"
PUT_BACK_DRAW_KEY = "r"
PUT_BACK_STOP_KEY = "t"
RUBY_DROP_KEY = "k"
USE_FLASK_KEY = "f"
USE_CARD_17_KEY = "u"
REFILL_FLASK_KEY = "l"
CONTINUE_KEY = "c"
RESTART_KEY = "r"
CARD_PREFIX = "card_"  # card 5 and 6 options: black, purple, drop, `card_chip:<id>`


def default_read_key() -> str:
    """Read one key without showing it (Ctrl+C raises KeyboardInterrupt, Ctrl+D EOFError)."""
    return typer.getchar(echo=False)


def key_map(legal: list[str]) -> dict[str, str]:
    keys: dict[str, str] = {}
    buys = [a for a in legal if a.startswith(BUY_PREFIX)]
    # The card choice offers only its own options, one digit each in the order of the list.
    card_options = [a for a in legal if a.startswith(CARD_PREFIX)]
    for number, action in enumerate(card_options, start=1):
        keys[str(number)] = action
    for action in legal:
        if action == DRAW:
            keys["d"] = DRAW
        elif action == STOP:
            keys["s"] = STOP
        elif action == DONE:
            keys["0"] = DONE
        elif action == TAKE_MONEY:
            keys["m"] = TAKE_MONEY
        elif action == TAKE_POINTS:
            keys["p"] = TAKE_POINTS
        elif action == RUBY_DROP:
            keys[RUBY_DROP_KEY] = RUBY_DROP
        elif action == USE_FLASK:
            keys[USE_FLASK_KEY] = USE_FLASK
        elif action == USE_CARD_17:
            keys[USE_CARD_17_KEY] = USE_CARD_17
        elif action == REFILL_FLASK:
            keys[REFILL_FLASK_KEY] = REFILL_FLASK
        elif action == CONTINUE:
            keys[CONTINUE_KEY] = CONTINUE
        elif action == RESTART:
            keys[RESTART_KEY] = RESTART
        elif action == PUT_BACK_DRAW:
            keys[PUT_BACK_DRAW_KEY] = PUT_BACK_DRAW
        elif action == PUT_BACK_STOP:
            keys[PUT_BACK_STOP_KEY] = PUT_BACK_STOP
        elif action.startswith(PLAY_PREFIX):
            keys[action.removeprefix(PLAY_PREFIX)] = action
    for key, action in zip(BUY_KEYS, buys, strict=False):
        keys[key] = action
    return keys


class HumanSeat:
    kind = "human"
    name = "human"

    def __init__(
        self,
        label: str,
        console: Console,
        bag_assist: bool,
        rs: Ruleset,
        read_key: Callable[[], str] | None = None,
    ):
        self.label = label
        self.console = console
        self.bag_assist = bag_assist
        self.rs = rs
        self.params: dict[str, Any] = {}
        self._read_key = read_key

    def _describe(self, action: str, state: GameState | None = None, seat: str = "") -> str:
        if state is not None and action in (TAKE_MONEY, TAKE_POINTS):
            p = state.players[seat]
            field = scoring_field(p.final_field if p.final_field is not None else p.field, self.rs)
            if action == TAKE_MONEY:
                return f"{action} (${self.rs.fields[field].money})"
            return f"{action} (+{self.rs.fields[field].points}pt)"
        if action.startswith(PLAY_PREFIX):
            slot = int(action.removeprefix(PLAY_PREFIX))
            if state is not None:
                chip = chip_text(state.players[seat].hand[slot], self.rs).plain
                return f"play {slot}: {chip}"
            return f"play {slot}"
        if action == RUBY_DROP:
            return f"ruby drop: {self.rs.ruby_cost} rubies, droplet +1"
        if action == USE_FLASK:
            return "flask: last white chip back to bag"
        if action == USE_CARD_17:
            return "card 17: first white chip back to bag"
        if action == REFILL_FLASK:
            return f"refill flask: {self.rs.ruby_cost} rubies"
        if action.startswith(CARD_TAILS_PREFIX):
            n = int(action.removeprefix(CARD_TAILS_PREFIX))
            return (
                f"card 8: {n} rat tail{'s' * (n != 1)} for rubies"
                if n
                else "card 8: keep my rat tails"
            )
        if action.startswith(CARD_PLACE_PREFIX):
            return (
                f"card 10: place {chip_text(action.removeprefix(CARD_PLACE_PREFIX), self.rs).plain}"
            )
        if action.startswith(CARD_UPGRADE_PREFIX):
            return f"card 11: upgrade {chip_text(action.removeprefix(CARD_UPGRADE_PREFIX), self.rs).plain}"
        if action.startswith(CARD_SWAP_PREFIX):
            return f"card 12: ruby for a {self._colour(action.removeprefix(CARD_SWAP_PREFIX))} 1"
        if action == CARD_SWAP_NO:
            return "card 12: no swap"
        if action == CARD_POINTS:
            return f"card 14: {CARD_POINTS_AMOUNT} points"
        if action == CARD_REMOVE_WHITE:
            return "card 14: remove a white 1 from the bag"
        if action.startswith(CARD_CHIP4_PREFIX):
            return (
                f"card 19: a {self._colour(action.removeprefix(CARD_CHIP4_PREFIX))} 4 into the bag"
            )
        if action == CARD_TAIL_POINTS:
            return "card 19: points for rat tails"
        if action == CONTINUE:
            return "continue brewing"
        if action == RESTART:
            return "restart: put the pot back, start over"
        if action == CARD_BLACK:
            return f"a {chip_text(self._card_chip('black', 1), self.rs).plain} chip into the bag"
        if action == CARD_PURPLE:
            return f"a {chip_text(self._card_chip('purple', 1), self.rs).plain} chip into the bag"
        if action == CARD_DROP_2:
            return "drop +2 now"
        if action == CARD_RUBIES:
            return "3 rubies"
        if action.startswith(CARD_CHIP_PREFIX):
            chip_id = action.removeprefix(CARD_CHIP_PREFIX)
            return f"a {chip_text(chip_id, self.rs).plain} chip into the bag"
        if action == PUT_BACK_DRAW:
            return "put all back and Draw"
        if action == PUT_BACK_STOP:
            return "put all back and Stop"
        if action.startswith(BUY_PREFIX):
            item = self.rs.shop_item(action.removeprefix(BUY_PREFIX))
            return f"buy {item.id} ({item.price})"
        return action

    def _colour(self, chip_id: str) -> str:
        return self.rs.chip(chip_id).colour

    def _card_chip(self, colour: str, value: int) -> str:
        return next(c.id for c in self.rs.chips if c.colour == colour and c.value == value)

    def choose(self, state: GameState, seat: str, legal: list[str]) -> str:
        keys = key_map(legal)
        self.console.print(render_board(state, self.rs, self.bag_assist))
        if any(a.startswith(PLAY_PREFIX) or a in (PUT_BACK_DRAW, PUT_BACK_STOP) for a in legal):
            self.console.print(hand_text(state.players[seat].hand, self.rs))
        if state.phase is Phase.CARD_CHOICE and state.players[seat].card_draw:
            self.console.print(draw_text(state.players[seat].card_draw, self.rs))
        menu = "   ".join(f"[{k}] {self._describe(a, state, seat)}" for k, a in keys.items())
        self.console.print(
            f"{self.label} ({seat}), press your key (hidden): {menu}", markup=False, highlight=False
        )
        # Looked up at call time so tests can replace `default_read_key`.
        read = self._read_key or default_read_key
        while True:
            key = read()
            if key in keys:
                return keys[key]
            self.console.print("unknown key, try again (hidden)", markup=False)
