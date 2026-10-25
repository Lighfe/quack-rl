from collections.abc import Callable
from typing import Any

import typer
from rich.console import Console

from quack_rl.cli.render import draw_text, hand_text, render_board
from quack_rl.engine import (
    BUY_PREFIX,
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
    USE_CARD_17,
)
from quack_rl.engine.state import Phase
from quack_rl.labels import action_label
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
        elif action == USE_FLASK:
            keys[USE_FLASK_KEY] = USE_FLASK
        elif action == USE_CARD_17:
            keys[USE_CARD_17_KEY] = USE_CARD_17
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
    # The dict order is the menu order: the shop shows its chip buys before the ruby actions.
    for key, action in zip(BUY_KEYS, buys, strict=False):
        keys[key] = action
    if RUBY_DROP in legal:
        keys[RUBY_DROP_KEY] = RUBY_DROP
    if REFILL_FLASK in legal:
        keys[REFILL_FLASK_KEY] = REFILL_FLASK
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

    def choose(self, state: GameState, seat: str, legal: list[str]) -> str:
        keys = key_map(legal)
        self.console.print(render_board(state, self.rs, self.bag_assist))
        if any(a.startswith(PLAY_PREFIX) or a in (PUT_BACK_DRAW, PUT_BACK_STOP) for a in legal):
            self.console.print(hand_text(state.players[seat].hand, self.rs))
        if state.phase is Phase.CARD_CHOICE and state.players[seat].card_draw:
            self.console.print(draw_text(state.players[seat].card_draw, self.rs))
        menu = "   ".join(f"[{k}] {action_label(a, self.rs, state, seat)}" for k, a in keys.items())
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
