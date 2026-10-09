import copy
from dataclasses import dataclass
from typing import Any

from quack_rl.engine.actions import legal_actions
from quack_rl.engine.brew import apply_brew
from quack_rl.engine.chance import ChanceLog, ChanceSource
from quack_rl.engine.state import SEATS, GameState, Phase
from quack_rl.rules import Ruleset


class IllegalAction(ValueError):
    """An action that is not legal for the seat in the current state."""


class GameOver(RuntimeError):
    """step() was called after the game ended."""


@dataclass
class StepResult:
    state: GameState
    n: int
    round: int
    phase: Phase
    legal: dict[str, list[str]] | None
    actions: dict[str, str] | None
    chance: list[dict[str, Any]]
    events: list[dict[str, Any]]


def needs_actions(state: GameState) -> bool:
    return state.phase in (Phase.BREW, Phase.SHOP)


def step(
    state: GameState, rs: Ruleset, actions: dict[str, str] | None, chance: ChanceSource
) -> StepResult:
    if state.phase is Phase.GAME_OVER:
        raise GameOver("the game is over")
    new = copy.deepcopy(state)
    log = ChanceLog(chance, rs)
    events: list[dict[str, Any]] = []
    legal: dict[str, list[str]] | None = None
    if needs_actions(state):
        if actions is None or set(actions) != set(SEATS):
            raise IllegalAction("a joint action needs exactly one action per seat")
        legal = {seat: legal_actions(state, rs, seat) for seat in SEATS}
        for seat in SEATS:
            if actions[seat] not in legal[seat]:
                raise IllegalAction(
                    f"{seat}: {actions[seat]!r} is not legal (legal: {legal[seat]})"
                )
        if state.phase is Phase.BREW:
            apply_brew(new, rs, actions, log, events)
        else:
            raise NotImplementedError("shop: Task 7")
    else:
        if actions is not None:
            raise IllegalAction("this step takes no actions")
        raise NotImplementedError("resolve: Task 6")
    new.step = state.step + 1
    return StepResult(
        state=new,
        n=new.step,
        round=state.round,
        phase=state.phase,
        legal=legal,
        actions=dict(actions) if actions is not None else None,
        chance=log.outcomes,
        events=events,
    )
