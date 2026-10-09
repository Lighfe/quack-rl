from collections.abc import Callable
from typing import Any

import typer
from rich.console import Console

from quack_rl.cli.render import render_board
from quack_rl.engine import BUY_PREFIX, DONE, DRAW, STOP, GameState
from quack_rl.rules import Ruleset

BUY_KEYS = "123456789abc"


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

    def _describe(self, action: str) -> str:
        if action.startswith(BUY_PREFIX):
            item = self.rs.shop_item(action.removeprefix(BUY_PREFIX))
            return f"buy {item.id} ({item.price})"
        return action

    def choose(self, state: GameState, seat: str, legal: list[str]) -> str:
        keys = key_map(legal)
        self.console.print(render_board(state, self.rs, self.bag_assist))
        menu = "   ".join(f"[{k}] {self._describe(a)}" for k, a in keys.items())
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
