"""Ruleset v2.1: points stop at 100 (issue #155), and the new die faces."""

import pytest

from quack_rl.engine import (
    TAKE_MONEY,
    TAKE_POINTS,
    Phase,
    ScriptedChance,
    Status,
    add_points,
    new_game,
    step,
)
from quack_rl.report import _expected_points, baseline_maximum, realistic_baseline_maximum
from quack_rl.rules import load_ruleset

RS = load_ruleset("v2.1")
CAP = 100


def state_for(rs, phase, p1_points=99, final_field=30, **p1_fields):
    """A hand-built state: p1 has stopped at `final_field`, p2 is exploded (rolls no die)."""
    s = new_game(rs)
    s.phase = phase
    p1, p2 = s.players["p1"], s.players["p2"]
    p1.points = p1_points
    p1.final_field = final_field
    p1.status = Status.STOPPED
    for name, value in p1_fields.items():
        setattr(p1, name, value)
    p2.final_field = 0
    p2.status = Status.EXPLODED
    return s


def test_add_points_clamps_and_returns_the_amount_added():
    p = new_game(RS).players["p1"]
    p.points = 98
    assert add_points(p, 1, RS) == 1
    assert p.points == 99
    assert add_points(p, 5, RS) == 1  # the 4 over the cap are lost
    assert p.points == CAP
    assert add_points(p, 3, RS) == 0
    assert p.points == CAP




def test_die_face_point_2_adds_two_points():
    s = state_for(RS, Phase.RESOLVE, p1_points=50, final_field=0)
    out = step(s, RS, None, ScriptedChance(["point_2"])).state
    assert out.players["p1"].points == 52


def test_site_die_face_stops_at_100():
    s = state_for(RS, Phase.RESOLVE, final_field=0)
    out = step(s, RS, None, ScriptedChance(["point_2"])).state
    assert out.players["p1"].points == CAP


def test_site_pot_round_end_effect_stops_at_100():
    # one purple chip: +1 point at round end; the field-1 table value is 0, p1 rolls no die
    s = state_for(RS, Phase.RESOLVE, p1_points=100, final_field=0, placed=["purple_1"])
    s.players["p1"].points = CAP
    out = step(s, RS, None, ScriptedChance(["point_1"])).state
    assert out.players["p1"].points == CAP
    s = state_for(RS, Phase.RESOLVE, p1_points=99, final_field=0, placed=["purple_1"] * 3)
    out = step(s, RS, None, ScriptedChance(["droplet_half"])).state
    assert out.players["p1"].points == CAP  # 3 purple give +2: 101 would be over


def test_site_round_end_table_stops_at_100():
    s = state_for(RS, Phase.RESOLVE, final_field=30)
    out = step(s, RS, None, ScriptedChance(["droplet_half"])).state
    assert RS.fields[31].points >= 2
    assert out.players["p1"].points == CAP


def test_site_last_round_conversion_stops_at_100():
    rs = RS
    s = state_for(rs, Phase.RESOLVE, final_field=30)
    s.round = rs.rounds
    s.players["p1"].points = 80
    out = step(s, rs, None, ScriptedChance(["droplet_half"])).state
    assert out.players["p1"].points == 80 + RS.fields[31].points + RS.fields[31].money // 5
    s.players["p1"].points = 99
    out = step(s, rs, None, ScriptedChance(["droplet_half"])).state
    assert out.players["p1"].points == CAP


def choice_state(**kw):
    s = state_for(RS, Phase.CHOICE, **kw)
    s.players["p1"].status = Status.EXPLODED
    return s


def test_site_take_points_stops_at_100_and_reports_the_amount_added():
    s = choice_state()
    res = step(s, RS, {"p1": TAKE_POINTS, "p2": TAKE_POINTS}, ScriptedChance([]))
    assert res.state.players["p1"].points == CAP
    amounts = [e["amount"] for e in res.events if e["seat"] == "p1" and e["kind"] == "take_points"]
    assert amounts == [1]


def test_site_take_money_last_round_stops_at_100():
    s = choice_state()
    s.round = RS.rounds
    assert RS.fields[31].money // 5 >= 2
    out = step(s, RS, {"p1": TAKE_MONEY, "p2": TAKE_MONEY}, ScriptedChance([])).state
    assert out.players["p1"].points == CAP


def test_report_runs_on_v2_without_a_money_face():
    assert baseline_maximum(RS) > 0
    assert realistic_baseline_maximum(RS) > 0


def test_expected_points_weights_the_points_faces_over_the_die_total():
    # one round, draw limit 0: nobody explodes, so the die points are the only term that changes
    one_round = RS.model_copy(update={"rounds": 1})
    no_points = one_round.model_copy(
        update={
            "die": [
                f.model_copy(update={"points": 0}) if f.kind == "points" else f
                for f in one_round.die
            ]
        }
    )
    got = _expected_points(one_round, 0) - _expected_points(no_points, 0)
    assert got == pytest.approx((1 * 2 + 2 * 1) / 6)
