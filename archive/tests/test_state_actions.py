"""Moved from tests/test_state_actions.py (#170): ruleset v2 has no `remove_white_1` shop item."""

from quack_rl.engine import Phase, buy, legal_actions, new_game
from quack_rl.rules import load_ruleset

RS = load_ruleset("v1")


def test_remove_white_1_needs_an_owned_white_1_in_bag_or_placed():
    s = new_game(RS)
    s.phase = Phase.SHOP
    p = s.players["p1"]
    p.money = 15
    p.bag.pop("white_1")
    assert buy("remove_white_1") not in legal_actions(s, RS, "p1")
    p.placed = ["white_1"]
    assert buy("remove_white_1") in legal_actions(s, RS, "p1")


def test_remove_white_1_legal_when_white_1_only_in_bag():
    s = new_game(RS)
    s.phase = Phase.SHOP
    p = s.players["p1"]
    p.money = 15
    assert p.bag.get("white_1", 0) > 0
    assert p.placed == []
    assert buy("remove_white_1") in legal_actions(s, RS, "p1")
