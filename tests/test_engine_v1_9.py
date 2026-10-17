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

