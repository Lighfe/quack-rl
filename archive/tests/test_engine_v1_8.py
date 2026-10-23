"""Engine under ruleset v1.8: field points, explosion choice, round 9 conversion."""

import pytest

from quack_rl.engine import (
    DRAW,
    TAKE_MONEY,
    TAKE_POINTS,
    WAIT,
    IllegalAction,
    Phase,
    RngChance,
    ScriptedChance,
    Status,
    action_names,
    legal_actions,
    new_game,
    step,
)
from quack_rl.rules import load_ruleset

RS = load_ruleset("v1.8")
RS_V11 = load_ruleset("v1.1")


def resolve_state(rnd, p1_field=39, p2_field=10, exploded=()):
    """Start of Resolve; final field 39 scores on field 40 (money 27, points 10)."""
    s = new_game(RS)
    s.round = rnd
    s.phase = Phase.RESOLVE
    for seat, fld in (("p1", p1_field), ("p2", p2_field)):
        p = s.players[seat]
        p.field = p.final_field = fld
        p.placed = ["white_1"]
        p.status = Status.EXPLODED if seat in exploded else Status.STOPPED
    return s


def resolve(state, *chance):
    return step(state, RS, None, ScriptedChance(chance))


def choose(state, p1, p2):
    return step(state, RS, {"p1": p1, "p2": p2}, ScriptedChance([]))


def test_action_names_only_with_explosion_choice():
    assert TAKE_MONEY in action_names(RS) and TAKE_POINTS in action_names(RS)
    assert TAKE_MONEY not in action_names(RS_V11)
    assert TAKE_POINTS not in action_names(RS_V11)


def test_normal_potion_gets_money_and_points():
    r = resolve(resolve_state(2), "orange_1")
    assert r.state.phase is Phase.SHOP
    assert (r.state.players["p1"].money, r.state.players["p1"].points) == (27, 10)


def test_die_money_added_to_field_money():
    r = resolve(resolve_state(2), "money_1")
    assert r.state.players["p1"].money == 28


def test_nobody_exploded_goes_straight_to_shop():
    assert resolve(resolve_state(2), "orange_1").state.phase is Phase.SHOP


def test_exploded_goes_to_choice_with_legal_actions():
    r = resolve(resolve_state(2, exploded=("p1",)), "orange_1")
    s = r.state
    assert s.phase is Phase.CHOICE
    assert legal_actions(s, RS, "p1") == [TAKE_MONEY, TAKE_POINTS]
    assert legal_actions(s, RS, "p2") == [WAIT]
    assert (s.players["p1"].money, s.players["p1"].points) == (0, 0)


def test_take_money_gives_full_money_no_points():
    s = resolve(resolve_state(2, exploded=("p1",)), "orange_1").state
    r = choose(s, TAKE_MONEY, WAIT)
    assert r.state.phase is Phase.SHOP
    assert (r.state.players["p1"].money, r.state.players["p1"].points) == (27, 0)


def test_take_points_gives_points_no_money():
    s = resolve(resolve_state(2, exploded=("p1",)), "orange_1").state
    r = choose(s, TAKE_POINTS, WAIT)
    assert (r.state.players["p1"].money, r.state.players["p1"].points) == (0, 10)


def test_both_exploded_both_choose_then_shop():
    s = resolve(resolve_state(2, p2_field=39, exploded=("p1", "p2"))).state
    assert s.phase is Phase.CHOICE
    r = choose(s, TAKE_MONEY, TAKE_POINTS)
    assert r.state.phase is Phase.SHOP
    assert r.state.players["p1"].money == 27 and r.state.players["p2"].points == 10


def test_choice_rejects_illegal_actions():
    s = resolve(resolve_state(2, exploded=("p1",)), "orange_1").state
    with pytest.raises(IllegalAction):
        choose(s, TAKE_MONEY, TAKE_MONEY)
    with pytest.raises(IllegalAction):
        choose(s, DRAW, WAIT)


def test_exploded_never_rolls_and_ruby_still_applies():
    s = resolve_state(2, p1_field=8, exploded=("p1",))  # scoring field 9 is a ruby
    r = resolve(s, "orange_1")
    assert all(c["seat"] != "p1" for c in r.chance)
    assert r.state.players["p1"].droplet_halves == 1


def test_round_9_money_becomes_points():
    r = resolve(resolve_state(9), "orange_1")
    p = r.state.players["p1"]
    assert (p.money, p.points) == (0, 27 // 5 + 10)


def test_round_9_die_money_is_summed_before_division():
    r = resolve(resolve_state(9), "money_1")
    assert r.state.players["p1"].points == 28 // 5 + 10  # 5 + 10; (27//5)+(1//5) would be the same
    s = resolve_state(9)
    s.players["p1"].final_field = s.players["p1"].field = 38  # scoring field 39
    money_39 = RS.money[39]
    r = resolve(s, "money_1")
    assert r.state.players["p1"].points == (money_39 + 1) // 5 + RS.points[39]


def test_round_9_exploded_take_money_and_take_points():
    s = resolve(resolve_state(9, exploded=("p1",)), "orange_1").state
    assert s.phase is Phase.CHOICE
    r = choose(s, TAKE_MONEY, WAIT)
    p = r.state.players["p1"]
    assert (p.money, p.points) == (0, 5)
    r = choose(s, TAKE_POINTS, WAIT)
    p = r.state.players["p1"]
    assert (p.money, p.points) == (0, 10)


def test_v1_1_keeps_halving_and_no_choice():
    s = new_game(RS_V11)
    s.phase = Phase.RESOLVE
    for seat in ("p1", "p2"):
        p = s.players[seat]
        p.field = p.final_field = 21
        p.placed = ["white_1"]
        p.status = Status.EXPLODED if seat == "p1" else Status.STOPPED
    r = step(s, RS_V11, None, ScriptedChance(["orange_1"]))
    assert r.state.phase is Phase.SHOP
    assert r.state.players["p1"].money == RS_V11.money[22] // 2
    assert r.state.players["p1"].points == 0


def test_v1_8_game_plays_to_the_end():
    import random

    for seed in range(5):
        rng = random.Random(seed)
        s = new_game(RS)
        chance = RngChance(seed)
        for _ in range(5000):
            if s.phase is Phase.GAME_OVER:
                break
            if s.phase is Phase.RESOLVE:
                acts = None
            else:
                acts = {seat: rng.choice(legal_actions(s, RS, seat)) for seat in ("p1", "p2")}
            s = step(s, RS, acts, chance).state
        assert s.phase is Phase.GAME_OVER and s.winner is not None
        assert s.round == RS.rounds
