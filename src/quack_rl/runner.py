import time
from collections.abc import Callable, Mapping
from typing import Any, Protocol

from quack_rl.engine import (
    SEATS,
    WAIT,
    ChanceSource,
    GameState,
    Phase,
    StepResult,
    legal_actions,
    needs_actions,
    new_game,
    step,
)
from quack_rl.rules import Ruleset


class Seat(Protocol):
    kind: str
    name: str
    params: dict[str, Any]

    def choose(self, state: GameState, seat: str, legal: list[str]) -> str: ...


StepCallback = Callable[[StepResult, dict[str, int]], None]


def play_game(
    rs: Ruleset,
    seats: Mapping[str, Seat],
    chance: ChanceSource,
    on_step: StepCallback | None = None,
) -> GameState:
    state = new_game(rs)
    while state.phase is not Phase.GAME_OVER:
        actions: dict[str, str] | None = None
        decision_ms: dict[str, int] = {}
        if needs_actions(state):
            actions = {}
            for seat in SEATS:
                legal = legal_actions(state, rs, seat)
                if legal == [WAIT]:
                    actions[seat] = WAIT
                    continue
                started = time.perf_counter()
                actions[seat] = seats[seat].choose(state, seat, legal)
                if seats[seat].kind == "human":
                    decision_ms[seat] = round((time.perf_counter() - started) * 1000)
        result = step(state, rs, actions, chance)
        if on_step is not None:
            on_step(result, decision_ms)
        state = result.state
    return state
