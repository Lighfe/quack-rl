"""Moved from tests/test_resolve.py (#170): the last-round money factor of v1 (v2: money becomes points).

`brewed`, `last_round` and `auto` are as in tests/test_resolve.py; RS is load_ruleset("v1").
"""

from quack_rl.engine import ScriptedChance, step
from quack_rl.rules import load_ruleset

RS = load_ruleset("v1")


def test_last_round_money_is_multiplied():
    # landing 34 -> scoring field 35 -> money 25
    r = auto(last_round(brewed(34, 0)), "point_1")
    assert r.state.players["p1"].money == 25 * 150 // 100 == 37


def test_last_round_exploded_halves_first_then_multiplies():
    r = auto(last_round(brewed(34, 0, exploded=("p1",))), "point_1")
    assert r.state.players["p1"].money == 12 * 150 // 100 == 18


def test_last_round_die_money_is_multiplied_too():
    r = auto(last_round(brewed(34, 0)), "money_1")
    assert r.state.players["p1"].money == 26 * 150 // 100 == 39


def test_last_round_both_exploded_both_halved_and_multiplied_nobody_rolls():
    r = auto(last_round(brewed(34, 34, exploded=("p1", "p2"))))
    assert r.chance == []
    assert (r.state.players["p1"].money, r.state.players["p2"].money) == (18, 18)


def test_last_round_money_event_carries_multiplied_amount():
    r = auto(last_round(brewed(34, 0)), "point_1")
    assert {"seat": "p1", "kind": "money", "amount": 37} in r.events


def test_factor_comes_from_the_ruleset():
    rs = RS.model_copy(update={"last_round_money_percent": 200})
    s = last_round(brewed(34, 0))
    r = step(s, rs, None, ScriptedChance(("point_1",)))
    assert r.state.players["p1"].money == 50


# ---- Moved from tests/test_resolve.py (#170), original text ----

def test_exploded_gets_half_money_rounded_down_and_never_rolls():
    r = auto(brewed(21, 4, exploded=("p1",)), "point_1")
    assert r.state.players["p1"].money == 18 // 2
    assert r.chance == [{"seat": "p2", "kind": "die", "value": "point_1"}]
    assert r.state.players["p2"].points == 1


def test_field_53_exploded_gives_17():
    r = auto(brewed(53, 3, exploded=("p1",)), "point_1")
    assert r.state.players["p1"].money == 17
    assert r.chance == [{"seat": "p2", "kind": "die", "value": "point_1"}]


def test_exploded_potion_halves_scoring_field_money_and_keeps_ruby():
    r = auto(brewed(51, 0, exploded=("p1",)), "point_1")
    assert r.state.players["p1"].money == 33 // 2
    assert r.state.players["p1"].droplet_halves == 1
