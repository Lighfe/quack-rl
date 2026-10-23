"""Moved from tests/test_engine_v2_rat_tail.py (#170): rulesets without a point board (v1.11)."""

from quack_rl.engine import new_game, step, ScriptedChance
from quack_rl.engine.board import set_rat_tails
from quack_rl.rules import load_ruleset

V111 = load_ruleset("v1.11")
# card_state, draw, add_points: as in tests/test_engine_v2_rat_tail.py


def test_set_rat_tails_without_a_board_does_nothing():
    s = new_game(V111)
    s.players["p1"].points = 0
    s.players["p2"].points = 40
    events = []
    set_rat_tails(s, V111, events)
    assert events == []
    assert s.players["p1"].rat_tail == 0


def test_v111_game_has_no_rat_tail():
    s = card_state(0, 40, rs=V111)
    out = draw(s, "card_8_to_12", rs=V111)
    assert out.state.players["p1"].rat_tail == 0
    assert out.state.players["p1"].field == 0
    assert not any(e["kind"] == "rat_tail" for e in out.events)
