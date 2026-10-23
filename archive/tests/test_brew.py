"""Moved from tests/test_brew.py (#170): the blue@1 place bonus (v2 has blue@2, no place bonus)."""

from quack_rl.engine import DRAW, STOP, ScriptedChance, new_game, step
from quack_rl.rules import load_ruleset

RS = load_ruleset("v1")


def play(state, p1, p2, *chance):
    return step(state, RS, {"p1": p1, "p2": p2}, ScriptedChance(chance))


def brew_start():
    return new_game(RS)


def test_blue_bonus_after_chip_with_value_other_than_one():
    s = new_game(RS)
    s.players["p1"].bag["blue_2"] = 1
    s = play(s, DRAW, DRAW, "white_2", "white_1").state
    r = play(s, DRAW, STOP, "blue_2")
    assert r.state.players["p1"].field == 5  # 2 + 2 + 1 bonus
    assert r.events[0]["bonus"] == 1


def test_no_blue_bonus_after_white_one():
    s = new_game(RS)
    s.players["p1"].bag["blue_2"] = 1
    s = play(s, DRAW, DRAW, "white_1", "white_1").state
    r = play(s, DRAW, STOP, "blue_2")
    assert r.state.players["p1"].field == 3  # 1 + 2, no bonus
    assert r.events[0] == {
        "seat": "p1",
        "kind": "place",
        "chip": "blue_2",
        "from": 1,
        "to": 3,
        "bonus": 0,
    }
