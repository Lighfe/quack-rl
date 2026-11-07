"""`copy.deepcopy` of `GameState` and `PlayerState` (the explicit `__deepcopy__`, #285)."""

import copy
import dataclasses
import pickle

from quack_rl.engine import GameState, Phase, PlayerState
from quack_rl.engine.chance import RngChance
from quack_rl.rl.planner import make_rollout_bot
from quack_rl.rules import load_ruleset
from quack_rl.runner import play_game

RS = load_ruleset("v2.3")
BOT = "bot:topchip-draw20-pts6"
MUTABLE = (list, dict, set)


def _states(seed: int) -> list[GameState]:
    """Every state of one seeded game (before each step, and the final state)."""
    seats = {"p1": make_rollout_bot(RS, BOT, seed), "p2": make_rollout_bot(RS, BOT, seed + 1000)}
    states: list[GameState] = []
    final = play_game(RS, seats, RngChance(seed), on_step=lambda r, _ms: states.append(r.state))
    assert final.phase is Phase.GAME_OVER
    return states


def _mid_game() -> GameState:
    """A state in the middle of a game, with chips placed and bought."""
    states = _states(7)
    mid = states[len(states) // 2]
    assert any(p.placed for p in mid.players.values()) or mid.round > 1
    return mid


def _round_trip(state: GameState) -> GameState:
    return pickle.loads(pickle.dumps(state))


def test_deepcopy_equals_pickle_round_trip_in_seeded_games():
    checked = 0
    for seed in range(20):
        for state in _states(seed)[::10]:
            assert copy.deepcopy(state) == _round_trip(state)
            checked += 1
    assert checked > 20 * 5


def test_explicit_deepcopy_methods_exist():
    assert "__deepcopy__" in vars(GameState)
    assert "__deepcopy__" in vars(PlayerState)


def _changed(value):
    """A new value of the same kind as `value`, different from it."""
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, str):
        return value + "_x"
    return "changed"  # None and enums: any other value


def _mutate_player(p: PlayerState) -> None:
    for f in dataclasses.fields(p):
        value = getattr(p, f.name)
        if isinstance(value, list):
            value.append("x")
        elif isinstance(value, dict):
            value["new_chip"] = 99
        else:
            setattr(p, f.name, _changed(value))


def test_changing_the_copy_leaves_the_original_unchanged():
    original = _mid_game()
    before = _round_trip(original)
    clone = copy.deepcopy(original)
    for f in dataclasses.fields(clone):
        value = getattr(clone, f.name)
        if f.name == "players":
            for p in value.values():
                _mutate_player(p)
            value["p3"] = PlayerState(bag={})
        elif isinstance(value, list):
            value.append("x")
        elif isinstance(value, dict):
            value["new_key"] = 1
        else:
            setattr(clone, f.name, _changed(value))
    assert clone != before
    assert original == before


def _assert_not_shared(copied, original) -> None:
    for f in dataclasses.fields(original):
        a = getattr(copied, f.name)
        b = getattr(original, f.name)
        if isinstance(b, MUTABLE) or dataclasses.is_dataclass(b):
            assert a is not b, f"{type(original).__name__}.{f.name} is shared by the copy"


def test_every_field_is_copied():
    original = _mid_game()
    clone = copy.deepcopy(original)
    assert clone is not original
    _assert_not_shared(clone, original)
    for seat, p in original.players.items():
        assert clone.players[seat] is not p
        _assert_not_shared(clone.players[seat], p)
