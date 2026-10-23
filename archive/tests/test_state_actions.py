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


# ---- Moved from tests/test_state_actions.py (#170), original text ----

def test_action_names_v1_has_16_actions():
    names = action_names(RS)
    assert names[:4] == [WAIT, DRAW, STOP, DONE]
    assert names[4:] == [buy(i.id) for i in RS.shop]
    assert names == [
        "wait",
        "draw",
        "stop",
        "done",
        "buy:orange_1",
        "buy:blue_1",
        "buy:blue_2",
        "buy:blue_4",
        "buy:green_1",
        "buy:green_2",
        "buy:green_4",
        "buy:remove_white_1",
        "buy:droplet_1",
        "buy:points_2",
        "buy:points_5",
        "buy:points_10",
    ]
    assert len(names) == 16
    assert buy("blue_2") == "buy:blue_2"
