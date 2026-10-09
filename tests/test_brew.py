import copy

import pytest
from helpers import RS, play

import quack_rl.engine as engine
from quack_rl.engine import (
    DRAW,
    STOP,
    WAIT,
    ChanceLog,
    GameOver,
    IllegalAction,
    IllegalChance,
    Phase,
    RngChance,
    ScriptedChance,
    Status,
    legal_actions,
    new_game,
    step,
)


def test_draw_places_chip_and_advances_by_value():
    r = play(new_game(RS), DRAW, DRAW, "white_2", "orange_1")
    p1, p2 = r.state.players["p1"], r.state.players["p2"]
    assert (p1.field, p1.white_total, p1.placed) == (2, 2, ["white_2"])
    assert (p2.field, p2.white_total, p2.placed) == (1, 0, ["orange_1"])
    assert p1.bag["white_2"] == 1
    assert r.chance == [
        {"seat": "p1", "kind": "draw_chip", "value": "white_2"},
        {"seat": "p2", "kind": "draw_chip", "value": "orange_1"},
    ]
    assert r.events[0] == {
        "seat": "p1",
        "kind": "place",
        "chip": "white_2",
        "from": 0,
        "to": 2,
        "bonus": 0,
    }
    assert (r.n, r.round, r.phase, r.legal) == (1, 1, Phase.BREW, {"p1": [DRAW], "p2": [DRAW]})
    assert r.state.step == 1


def test_bag_key_is_removed_when_its_count_reaches_zero():
    r = play(new_game(RS), DRAW, DRAW, "white_3", "orange_1")
    assert "white_3" not in r.state.players["p1"].bag
    assert "orange_1" not in r.state.players["p2"].bag
    for p in r.state.players.values():
        assert all(n > 0 for n in p.bag.values())


def test_step_does_not_mutate_the_input_state():
    s = new_game(RS)
    play(s, DRAW, DRAW, "white_2", "orange_1")
    assert s.players["p1"].placed == [] and s.step == 0


def test_step_does_not_mutate_the_input_state_when_it_raises():
    s = new_game(RS)
    before = copy.deepcopy(s)
    with pytest.raises(IllegalAction):
        play(s, STOP, DRAW, "white_1")
    assert s == before
    with pytest.raises(IllegalChance):
        play(s, DRAW, DRAW, "white_2", "blue_4")  # p1 draw is valid, p2 draw is not
    assert s == before
    assert s.players["p1"].placed == [] and s.step == 0


def test_illegal_action_is_refused():
    with pytest.raises(IllegalAction):
        play(new_game(RS), STOP, DRAW, "white_1")


def test_action_not_in_legal_actions_is_refused():
    with pytest.raises(IllegalAction):
        play(new_game(RS), DRAW, WAIT, "white_1", "white_1")


def test_actions_with_missing_or_extra_seat_are_refused():
    with pytest.raises(IllegalAction):
        step(new_game(RS), RS, {"p1": DRAW}, ScriptedChance(["white_1"]))
    with pytest.raises(IllegalAction):
        step(
            new_game(RS),
            RS,
            {"p1": DRAW, "p2": DRAW, "p3": DRAW},
            ScriptedChance(["white_1", "white_1"]),
        )


def test_no_actions_in_brew_is_refused():
    with pytest.raises(IllegalAction):
        step(new_game(RS), RS, None, ScriptedChance([]))


def test_impossible_chance_outcome_is_refused():
    with pytest.raises(IllegalChance):
        play(new_game(RS), DRAW, DRAW, "blue_4", "white_1")


def test_unknown_die_face_is_refused():
    with pytest.raises(IllegalChance):
        ChanceLog(ScriptedChance(["no_such_face"]), RS).roll_die("p1")


def test_exhausted_scripted_chance_is_refused():
    with pytest.raises(IllegalChance):
        play(new_game(RS), DRAW, DRAW, "white_1")


def test_explosion_when_white_total_exceeds_seven():
    s = play(new_game(RS), DRAW, DRAW, "white_3", "white_1").state
    s = play(s, DRAW, STOP, "white_2").state
    s = play(s, DRAW, WAIT, "white_2").state  # 7: safe
    assert s.players["p1"].status is Status.BREWING
    r = play(s, DRAW, WAIT, "white_1")  # 8: explodes
    assert r.state.players["p1"].status is Status.EXPLODED
    assert {"seat": "p1", "kind": "explode", "white_total": 8} in r.events


def test_exploded_seat_may_only_wait_while_the_other_brews():
    s = new_game(RS)
    s.players["p1"].white_total = 6
    r = play(s, DRAW, DRAW, "white_2", "white_1")  # p1 at 8: explodes
    assert r.state.players["p1"].status is Status.EXPLODED
    assert r.state.players["p2"].status is Status.BREWING
    assert r.state.phase is Phase.BREW
    assert legal_actions(r.state, RS, "p1") == [WAIT]
    assert r.state.players["p1"].final_field is None


def test_explosion_and_empty_bag_on_same_draw_only_explodes():
    s = new_game(RS)
    s.players["p1"].bag = {"white_3": 1}
    s.players["p1"].white_total = 5
    r = play(s, DRAW, DRAW, "white_3", "white_1")
    assert r.state.players["p1"].status is Status.EXPLODED
    p1_events = [e for e in r.events if e["seat"] == "p1"]
    assert [e["kind"] for e in p1_events] == ["place", "explode"]
    assert {"seat": "p1", "kind": "explode", "white_total": 8} in r.events


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


def test_field_is_capped_at_53_and_drawing_at_53_is_allowed():
    s = new_game(RS)
    s.players["p1"].field = 52
    s = play(s, DRAW, DRAW, "white_2", "white_1").state
    assert s.players["p1"].field == 53
    assert DRAW in legal_actions(s, RS, "p1")
    r = play(s, DRAW, STOP, "white_1")
    assert r.state.players["p1"].field == 53


def test_empty_bag_stops_the_player():
    s = new_game(RS)
    s.players["p1"].bag = {"orange_1": 1}
    r = play(s, DRAW, DRAW, "orange_1", "white_1")
    assert r.state.players["p1"].status is Status.STOPPED
    assert {"seat": "p1", "kind": "bag_empty"} in r.events
    assert r.state.players["p2"].status is Status.BREWING
    assert r.state.phase is Phase.BREW


def test_stop_emits_stop_event_with_field():
    s = play(new_game(RS), DRAW, DRAW, "white_2", "orange_1").state
    r = play(s, STOP, DRAW, "white_1")
    assert r.state.players["p1"].status is Status.STOPPED
    assert {"seat": "p1", "kind": "stop", "field": 2} in r.events
    assert r.state.phase is Phase.BREW


def test_brew_ends_when_nobody_brews_and_final_fields_are_settled():
    s = play(new_game(RS), DRAW, DRAW, "white_2", "orange_1").state
    r = play(s, STOP, STOP)
    assert r.state.phase is Phase.RESOLVE
    assert r.phase is Phase.BREW
    assert r.state.players["p1"].final_field == 2
    assert r.state.players["p2"].final_field == 1


def test_brew_ends_with_one_stopped_and_one_exploded():
    s = new_game(RS)
    s.players["p1"].white_total = 6
    s = play(s, DRAW, DRAW, "white_1", "orange_1").state  # p1 at 7: safe
    r = play(s, DRAW, STOP, "white_2")  # p1 explodes, p2 stops
    assert r.state.players["p1"].status is Status.EXPLODED
    assert r.state.players["p2"].status is Status.STOPPED
    assert r.state.phase is Phase.RESOLVE
    assert r.phase is Phase.BREW
    assert r.state.players["p1"].final_field == r.state.players["p1"].field == 3
    assert r.state.players["p2"].final_field == r.state.players["p2"].field == 1


def test_step_after_game_over_raises():
    s = new_game(RS)
    s.phase = Phase.GAME_OVER
    with pytest.raises(GameOver):
        step(s, RS, None, ScriptedChance([]))


def test_rng_chance_is_deterministic_per_seed():
    def draws(seed):
        s, chance, out = new_game(RS), RngChance(seed), []
        for _ in range(3):
            r = step(s, RS, {"p1": DRAW, "p2": DRAW}, chance)
            out.append(r.chance)
            s = r.state
        return out

    assert draws(1) == draws(1)


def test_scripted_chance_gives_values_in_order():
    chance = ScriptedChance(["a", "b", "c"])
    assert chance.draw_chip({}, "p1") == "a"
    assert chance.roll_die([], "p2") == "b"
    assert chance.draw_chip({}, "p1") == "c"


def test_new_names_are_exported_from_engine():
    names = [
        "ChanceLog",
        "ChanceSource",
        "IllegalChance",
        "RngChance",
        "ScriptedChance",
        "GameOver",
        "IllegalAction",
        "StepResult",
        "needs_actions",
        "step",
    ]
    for name in names:
        assert name in engine.__all__
        assert hasattr(engine, name)
