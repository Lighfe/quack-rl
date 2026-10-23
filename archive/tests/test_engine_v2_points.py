"""Moved from tests/test_engine_v2_points.py (#170): rulesets without a point board (v1.11)."""

from quack_rl.engine import new_game, step, ScriptedChance, Phase
from quack_rl.rules import load_ruleset

V111 = load_ruleset("v1.11")
# add_points, state_for: as in tests/test_engine_v2_points.py


def test_add_points_without_a_board_does_not_clamp():
    p = new_game(V111).players["p1"]
    p.points = 120
    assert add_points(p, 7, V111) == 7
    assert p.points == 127


def test_v1_11_is_not_clamped():
    assert V111.point_board is None
    s = state_for(V111, Phase.RESOLVE, p1_points=120, final_field=30)
    out = step(s, V111, None, ScriptedChance(["droplet_half"])).state
    assert out.players["p1"].points > 120
