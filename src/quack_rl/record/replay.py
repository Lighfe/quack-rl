"""Replay a record and check it against the engine (spec 6.1)."""

from collections.abc import Mapping, Sequence
from typing import Any

from quack_rl.engine import (
    SEATS,
    GameOver,
    GameState,
    IllegalAction,
    IllegalChance,
    Phase,
    RngChance,
    new_game,
    step,
)
from quack_rl.record.reader import RecordedGame
from quack_rl.rules import SUPPORTED_RULES_VERSIONS, DieFace, load_ruleset


class ChanceMismatch(ValueError):
    """The recorded chance outcomes do not fit the replayed step."""


class RecordedChance:
    """Returns the recorded chance outcomes of one step, in order."""

    def __init__(self, outcomes: list[dict[str, Any]]):
        self._outcomes = outcomes
        self._next = 0

    def _take(self, kind: str, seat: str) -> str:
        if self._next >= len(self._outcomes):
            raise ChanceMismatch(f"missing chance outcome: expected {kind} for {seat}")
        outcome = self._outcomes[self._next]
        if outcome.get("kind") != kind or outcome.get("seat") != seat:
            raise ChanceMismatch(
                f"chance outcome {outcome} does not fit: expected {kind} for {seat}"
            )
        self._next += 1
        value = outcome.get("value")
        if not isinstance(value, str):
            raise ChanceMismatch(f"chance outcome {outcome} does not fit: value is not a name")
        return value  # ChanceLog checks the value against the state

    def draw_chip(self, bag: Mapping[str, int], seat: str) -> str:
        return self._take("draw_chip", seat)

    def roll_die(self, faces: Sequence[DieFace], seat: str) -> str:
        return self._take("die", seat)

    def assert_consumed(self) -> None:
        if self._next != len(self._outcomes):
            raise ChanceMismatch(f"extra chance outcome: {self._outcomes[self._next :]}")


def _footer_problems(game: RecordedGame, state: GameState) -> list[str]:
    footer = game.footer
    if footer is None:
        return ["incomplete game: no footer"]
    if state.phase is not Phase.GAME_OVER:
        return ["footer before the game ended"]
    expected = (
        {s: state.players[s].points for s in SEATS},
        {s: state.players[s].final_field for s in SEATS},
        state.winner or "",
    )
    if (footer.points, footer.final_fields, footer.winner) != expected:
        return [f"footer differs: recorded {footer.model_dump()}, replayed {expected}"]
    return []


def verify_game(game: RecordedGame) -> list[str]:
    """Replay the recorded actions and chance outcomes. Returns problems; [] means valid."""
    version = game.header.rules_version
    if version not in SUPPORTED_RULES_VERSIONS:
        return [f"unsupported rules version {version!r}"]
    rs = load_ruleset(version)
    state = new_game(rs)
    for line in game.steps:
        where = f"step {line.n}"
        if (line.n, line.round, line.phase) != (state.step + 1, state.round, state.phase.value):
            return [
                f"{where}: position differs (replayed step {state.step + 1}, "
                f"round {state.round}, {state.phase.value})"
            ]
        chance = RecordedChance(line.chance)
        try:
            result = step(state, rs, line.actions, chance)
            chance.assert_consumed()
        except (IllegalAction, IllegalChance, ChanceMismatch, GameOver) as e:
            return [f"{where}: {e}"]
        if result.legal != line.legal:
            return [
                f"{where}: legal actions differ: recorded {line.legal}, replayed {result.legal}"
            ]
        if result.events != line.events:
            return [f"{where}: events differ: recorded {line.events}, replayed {result.events}"]
        state = result.state
    return _footer_problems(game, state)


def verify_seed(game: RecordedGame) -> list[str]:
    """Replay the recorded actions with the header seed and compare the chance outcomes."""
    if game.header.seed is None:
        return ["no seed recorded"]
    version = game.header.rules_version
    if version not in SUPPORTED_RULES_VERSIONS:
        return [f"unsupported rules version {version!r}"]
    rs = load_ruleset(version)
    chance = RngChance(game.header.seed)
    state = new_game(rs)
    for line in game.steps:
        try:
            result = step(state, rs, line.actions, chance)
        except (IllegalAction, IllegalChance, GameOver) as e:
            return [f"step {line.n}: {e}"]
        if result.chance != line.chance:
            return [
                f"step {line.n}: chance differs from seed: "
                f"recorded {line.chance}, seed gives {result.chance}"
            ]
        state = result.state
    return []
