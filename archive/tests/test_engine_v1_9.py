"""Engine under ruleset v1.9: red counts the orange chips in the pot, orange 6."""

import pytest

from quack_rl.components import get_component
from quack_rl.engine import ScriptedChance, new_game
from quack_rl.engine.brew import _draw
from quack_rl.engine.chance import ChanceLog
from quack_rl.rules import load_ruleset

RS = load_ruleset("v1.9")


def place(chips, field=0):
    """Place `chips` in order for p1 (bag filled with them); return p1 and the events."""
    s = new_game(RS)
    p = s.players["p1"]
    p.bag = {}
    for c in chips:
        p.bag[c] = p.bag.get(c, 0) + 1
    p.field = field
    events = []
    log = ChanceLog(ScriptedChance(chips), RS)
    for _ in chips:
        _draw(p, "p1", RS, log, events)
    return p, [e for e in events if e["kind"] == "place"]


@pytest.mark.parametrize("oranges,extra", [(0, 0), (1, 1), (2, 1), (3, 2), (4, 2)])
def test_red_extra_by_orange_chips_in_the_pot(oranges, extra):
    p, events = place(["orange_1"] * oranges + ["red_2"])
    assert events[-1]["bonus"] == extra
    assert p.field == oranges + 2 + extra


def test_orange_6_moves_6_and_counts_for_red():
    p, _ = place(["orange_6"])
    assert p.field == 6
    p, events = place(["orange_6", "red_1"])
    assert events[-1]["bonus"] == 1 and p.field == 8


def test_orange_after_red_does_not_count():
    p, events = place(["red_2", "orange_1"])
    assert events[0]["bonus"] == 0 and p.field == 3


def test_other_red_and_white_chips_do_not_count():
    _, events = place(["red_1", "white_1", "red_2"])
    assert events[-1]["bonus"] == 0


def test_bag_does_not_count():
    s = new_game(RS)
    p = s.players["p1"]
    p.bag = {"orange_1": 3, "red_1": 1}
    log = ChanceLog(ScriptedChance(["red_1"]), RS)
    events = []
    _draw(p, "p1", RS, log, events)
    assert events[0]["bonus"] == 0


def test_track_end_caps_red_with_extra():
    p, events = place(["orange_1", "red_4"], field=50)
    assert events[-1]["bonus"] == 1
    assert p.field == RS.track_end == 53


def test_place_bonus_pot_is_optional():
    chip = RS.chip("red_1")
    assert get_component("red@1").place_bonus(chip, None) == 0



# --- blue: hand and pick step -------------------------------------------------------------

import copy  # noqa: E402
import json  # noqa: E402
import random  # noqa: E402

from quack_rl.engine import (  # noqa: E402
    DRAW,
    PUT_BACK_DRAW,
    PUT_BACK_STOP,
    STOP,
    WAIT,
    IllegalAction,
    Phase,
    RngChance,
    Status,
    action_names,
    legal_actions,
    play,
    step,
)
from quack_rl.rl.encode import observe  # noqa: E402

RS8 = load_ruleset("v1.8")


def hand_state(bag, p2_bag=None):
    """A fresh game with fixed bags; p1 has placed nothing."""
    s = new_game(RS)
    s.players["p1"].bag = dict(bag)
    s.players["p2"].bag = dict(p2_bag or {"white_1": 5})
    return s


def go(s, a1, a2, *chance):
    return step(s, RS, {"p1": a1, "p2": a2}, ScriptedChance(chance))


def bag_size(s, seat):
    return sum(s.players[seat].bag.values())


def with_hand(blue, hand_chips, bag):
    """Step 1 draws `blue` for p1, which draws `hand_chips`; returns the state afterwards."""
    s = hand_state({blue: 1, **bag})
    return go(s, DRAW, DRAW, blue, *hand_chips, "white_1").state


@pytest.mark.parametrize(
    "blue,hand",
    [
        ("blue_1", ["white_1"]),
        ("blue_2", ["white_1", "white_2"]),
        ("blue_4", ["white_1", "white_2", "white_3", "orange_1"]),
    ],
)
def test_blue_draws_a_hand_of_its_value(blue, hand):
    bag = {"white_1": 1, "white_2": 1, "white_3": 1, "orange_1": 1, "green_1": 1}
    s = hand_state({blue: 1, **bag})
    r = go(s, DRAW, DRAW, blue, *hand, "white_1")
    p = r.state.players["p1"]
    assert p.hand == hand
    assert p.field == RS.chip(blue).value  # moved its value first, no placement bonus
    assert sum(p.bag.values()) == len(bag) - len(hand)  # the hand is out of the bag
    assert p.white_total == 0  # the hand does not count toward the explosion total
    assert any(e["kind"] == "hand" and e["chips"] == hand for e in r.events)
    assert [o["value"] for o in r.chance if o["seat"] == "p1"] == [blue, *hand]


def test_bag_with_fewer_chips_than_the_blue_value():
    s = hand_state({"blue_4": 1, "white_1": 1, "white_2": 1})
    p = go(s, DRAW, DRAW, "blue_4", "white_1", "white_2", "white_1").state.players["p1"]
    assert sorted(p.hand) == ["white_1", "white_2"] and p.bag == {}
    assert p.status is Status.BREWING  # empty bag with a hand does not stop the player


def test_empty_bag_after_blue_without_hand_stops():
    s = hand_state({"blue_2": 1})
    r = go(s, DRAW, DRAW, "blue_2", "white_1")
    p = r.state.players["p1"]
    assert p.hand == [] and p.status is Status.STOPPED
    assert any(e["kind"] == "bag_empty" for e in r.events)


def test_hand_is_not_in_the_other_players_view():
    s = with_hand("blue_2", ["white_1", "white_2"], {"white_1": 1, "white_2": 1, "white_3": 2})
    assert s.players["p1"].hand
    other = json.dumps(observe(s, RS, "p2"), sort_keys=True)
    t = copy.deepcopy(s)
    t.players["p1"].hand = ["green_1", "orange_1"]  # other chips in the hand: same view
    assert json.dumps(observe(t, RS, "p2"), sort_keys=True) == other
    assert "hand" not in observe(s, RS, "p2")["opponent"]
    assert "hand" not in observe(s, RS, "p1")["opponent"]


def test_legal_actions_with_a_hand():
    s = with_hand("blue_2", ["white_1", "white_2"], {"white_1": 1, "white_2": 1, "white_3": 2})
    assert legal_actions(s, RS, "p1") == [play(0), play(1), PUT_BACK_DRAW, PUT_BACK_STOP]
    assert legal_actions(s, RS, "p2") == [DRAW, STOP]  # the other player is unchanged
    for bad in (DRAW, STOP):
        with pytest.raises(IllegalAction):
            go(s, bad, DRAW, "white_1")


def test_action_names_list_pick_actions_only_with_blue_hand():
    names = action_names(RS)
    assert {play(0), play(3), PUT_BACK_DRAW, PUT_BACK_STOP} <= set(names)
    assert not {play(0), PUT_BACK_DRAW, PUT_BACK_STOP} & set(action_names(RS8))


def test_play_white_chip_that_explodes_and_returns_the_rest():
    s = hand_state({"blue_2": 1, "white_3": 2, "white_2": 1})
    s.players["p1"].white_total = 7
    s = go(s, DRAW, DRAW, "blue_2", "white_3", "white_2", "white_1").state
    r = go(s, play(0), DRAW, "white_1")
    p = r.state.players["p1"]
    assert p.status is Status.EXPLODED and p.white_total == 10
    assert p.hand == [] and p.bag == {"white_2": 1, "white_3": 1}
    assert p.placed == ["blue_2", "white_3"]


def test_play_blue_chip_chains():
    s = hand_state({"blue_2": 1, "blue_1": 1, "white_1": 3})
    s = go(s, DRAW, DRAW, "blue_2", "blue_1", "white_1", "white_1").state
    assert s.players["p1"].hand == ["blue_1", "white_1"]
    r = go(s, play(0), DRAW, "white_1", "white_1")  # blue_1 played, new hand of 1
    p = r.state.players["p1"]
    assert p.placed == ["blue_2", "blue_1"] and p.field == 3
    assert len(p.hand) == 1
    assert sum(p.bag.values()) == 2  # white_1 (old hand) went back, one drawn into the new hand
    assert [e["kind"] for e in r.events if e["seat"] == "p1"][:3] == ["place", "put_back", "hand"]


def test_play_non_blue_chip_ends_the_hand():
    s = with_hand("blue_2", ["white_1", "orange_1"], {"white_1": 1, "orange_1": 1, "white_2": 2})
    r = go(s, play(1), DRAW, "white_1")
    p = r.state.players["p1"]
    assert p.hand == [] and p.placed[-1] == "orange_1"
    assert p.bag == {"white_1": 1, "white_2": 2}


def test_put_back_and_draw_can_redraw_the_hand():
    s = with_hand("blue_2", ["white_1", "orange_1"], {"white_1": 1, "orange_1": 1, "white_2": 2})
    before = bag_size(s, "p1") + len(s.players["p1"].hand)
    r = go(s, PUT_BACK_DRAW, DRAW, "orange_1", "white_1")
    p = r.state.players["p1"]
    assert p.hand == [] and p.placed == ["blue_2", "orange_1"]
    assert bag_size(r.state, "p1") == before - 1
    assert [e["kind"] for e in r.events if e["seat"] == "p1"][:2] == ["put_back", "place"]


def test_put_back_and_stop():
    s = with_hand("blue_2", ["white_1", "orange_1"], {"white_1": 1, "orange_1": 1, "white_2": 2})
    r = go(s, PUT_BACK_STOP, DRAW, "white_1")
    p = r.state.players["p1"]
    assert p.status is Status.STOPPED and p.hand == []
    assert bag_size(r.state, "p1") == 4
    assert legal_actions(r.state, RS, "p1") == [WAIT]


def test_empty_bag_with_a_hand_gives_the_pick_step_and_put_back_draw():
    s = hand_state({"blue_2": 1, "white_1": 2})
    s = go(s, DRAW, DRAW, "blue_2", "white_1", "white_1", "white_1").state
    p = s.players["p1"]
    assert p.bag == {} and len(p.hand) == 2 and p.status is Status.BREWING
    assert PUT_BACK_DRAW in legal_actions(s, RS, "p1")
    r = go(s, PUT_BACK_DRAW, DRAW, "white_1", "white_1")
    assert r.state.players["p1"].placed == ["blue_2", "white_1"]


def test_same_bag_size_after_each_step_when_no_one_stops():
    s = hand_state({"blue_2": 1, "white_1": 3, "white_2": 2}, {"white_1": 6})
    def left(st, seat):
        return bag_size(st, seat) + len(st.players[seat].hand)

    r = go(s, DRAW, DRAW, "blue_2", "white_1", "white_2", "white_1")
    s = r.state
    assert left(s, "p1") == left(s, "p2")
    assert bag_size(s, "p1") == 3  # hand chips are out of the bag, as in a hidden hold
    r = go(s, play(1), DRAW, "white_1", "white_1")
    s = r.state
    assert bag_size(s, "p1") == bag_size(s, "p2")


def _random_game(seed):
    rng = random.Random(seed)
    s = new_game(RS)
    for p in s.players.values():
        p.bag["blue_1"] = 1
        p.bag["blue_2"] = 1
        p.bag["blue_4"] = 1
    chance = RngChance(seed)
    n = 0
    while s.phase is not Phase.GAME_OVER:
        n += 1
        assert n < 5000
        if s.phase in (Phase.BREW, Phase.CHOICE, Phase.SHOP):
            actions = {seat: rng.choice(legal_actions(s, RS, seat)) for seat in s.players}
        else:
            actions = None
        s = step(s, RS, actions, chance).state
        for p in s.players.values():
            if s.phase is not Phase.BREW:
                assert p.hand == []
        if s.phase is Phase.SHOP:
            for p in s.players.values():  # keep blue chips in the bags in later rounds
                p.bag["blue_2"] = p.bag.get("blue_2", 0) + 1
    return s


@pytest.mark.parametrize("seed", range(60))
def test_full_games_with_a_random_policy_end_without_a_hand(seed):
    s = _random_game(seed)
    assert s.phase is Phase.GAME_OVER
    assert all(p.hand == [] for p in s.players.values())
