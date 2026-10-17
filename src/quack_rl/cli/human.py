from collections.abc import Callable
from typing import Any

import typer
from rich.console import Console

from quack_rl.cli.render import chip_text, hand_text, render_board
from quack_rl.engine import (
    BUY_PREFIX,
    DONE,
    DRAW,
    PLAY_PREFIX,
    PUT_BACK_DRAW,
    PUT_BACK_STOP,
    STOP,
    TAKE_MONEY,
    TAKE_POINTS,
    GameState,
)
from quack_rl.engine.state import scoring_field
from quack_rl.rules import Ruleset

# Skips d, s, m, p, r, t (fixed keys of other actions) so no key is used twice.
BUY_KEYS = "123456789abcefghijklnoquvwxyz"
PUT_BACK_DRAW_KEY = "r"
PUT_BACK_STOP_KEY = "t"


def default_read_key() -> str:
    """Read one key without showing it (Ctrl+C raises KeyboardInterrupt, Ctrl+D EOFError)."""
    return typer.getchar(echo=False)


def key_map(legal: list[str]) -> dict[str, str]:
    keys: dict[str, str] = {}
    buys = [a for a in legal if a.startswith(BUY_PREFIX)]
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
                return f"{action} (${self.rs.money[field]})"
            points = self.rs.points[field] if self.rs.points is not None else 0
            return f"{action} (+{points}pt)"
        if action.startswith(PLAY_PREFIX):
            slot = int(action.removeprefix(PLAY_PREFIX))
            if state is not None:
                chip = chip_text(state.players[seat].hand[slot], self.rs).plain
                return f"play {slot}: {chip}"
            return f"play {slot}"
        if action == PUT_BACK_DRAW:
            return "put all back and Draw"
        if action == PUT_BACK_STOP:
            return "put all back and Stop"
        if action.startswith(BUY_PREFIX):
            item = self.rs.shop_item(action.removeprefix(BUY_PREFIX))
            return f"buy {item.id} ({item.price})"
        return action

    def choose(self, state: GameState, seat: str, legal: list[str]) -> str:
        keys = key_map(legal)
        self.console.print(render_board(state, self.rs, self.bag_assist))
        if any(a.startswith(PLAY_PREFIX) or a in (PUT_BACK_DRAW, PUT_BACK_STOP) for a in legal):
            self.console.print(hand_text(state.players[seat].hand, self.rs))
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
