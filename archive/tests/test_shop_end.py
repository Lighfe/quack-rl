"""Moved from tests/test_shop_end.py (#170): shop items v2 does not have (points, droplet, remove_white_1).

`shop_state` and `last_round` are as in tests/test_shop_end.py; RS is load_ruleset("v1").
"""

from quack_rl.engine import DONE, WAIT, Phase, Status, buy, new_game, step, ScriptedChance
from quack_rl.rules import load_ruleset

RS = load_ruleset("v1")


def play(state, p1, p2, *chance):
    return step(state, RS, {"p1": p1, "p2": p2}, ScriptedChance(chance))


def test_points_are_added_at_once():
    r = play(shop_state(p1_money=22), buy("points_10"), DONE)
    assert r.state.players["p1"].points == 10


def test_bought_droplet_moves_the_start_field_of_the_next_round():
    s = shop_state(p1_money=10)
    assert s.players["p1"].droplet_halves == 0
    s = play(s, buy("droplet_1"), DONE).state
    assert s.players["p1"].droplet_halves == 2
    r = play(s, DONE, WAIT)
    p1 = r.state.players["p1"]
    assert r.state.phase is Phase.BREW
    assert (p1.droplet_halves, p1.field) == (2, 1)


def test_remove_white_1_takes_a_placed_chip_first():
    s = shop_state(p1_money=15)
    s = play(s, buy("remove_white_1"), DONE).state
    assert s.players["p1"].placed == ["white_2"]
    r = play(s, DONE, WAIT)
    # after the reset all chips are back in the bag: 4 white_1 at start, 1 removed
    assert r.state.players["p1"].bag["white_1"] == 3


def test_remove_white_1_without_a_placed_one_takes_it_from_the_bag():
    s = shop_state(p1_money=15)
    p1 = s.players["p1"]
    p1.placed = ["white_2"]
    p1.bag["white_1"] += 1
    assert p1.bag["white_1"] == 4
    r = play(s, buy("remove_white_1"), DONE)
    p1 = r.state.players["p1"]
    assert p1.bag["white_1"] == 3
    assert p1.placed == ["white_2"]


def test_final_field_is_not_changed_by_removing_the_last_placed_chip():
    s = last_round(5, 5, 20, 12)
    s.players["p1"].money = 15
    s.players["p1"].placed = ["white_2", "white_1"]
    s = play(s, buy("remove_white_1"), DONE).state
    r = play(s, DONE, WAIT)
    assert r.state.winner == "p1"
    assert r.state.players["p1"].final_field == 20
