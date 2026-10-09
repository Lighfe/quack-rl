import json

from helpers import RS

import quack_rl.engine as engine
from quack_rl.engine import (
    DONE,
    DRAW,
    STOP,
    WAIT,
    Phase,
    Status,
    action_names,
    buy,
    legal_actions,
    new_game,
    state_from_dict,
    state_to_dict,
)


def test_new_game_setup():
    s = new_game(RS)
    assert (s.rules_version, s.round, s.phase, s.step, s.winner) == ("v1", 1, Phase.BREW, 0, None)
    assert set(s.players) == {"p1", "p2"}
    for p in s.players.values():
        assert p.bag == RS.start_bag
        assert p.bag is not RS.start_bag
        assert (p.field, p.droplet_halves, p.points, p.white_total) == (0, 0, 0, 0)
        assert (p.money, p.purchases, p.shop_done, p.final_field) == (0, 0, False, None)
        assert p.placed == []
        assert p.status is Status.BREWING


def test_start_bags_are_separate_copies():
    s = new_game(RS)
    p1, p2 = s.players["p1"], s.players["p2"]
    assert p1.bag is not p2.bag
    start = dict(RS.start_bag)
    p1.bag.pop("white_1")
    assert p2.bag == start
    assert RS.start_bag == start


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


def test_first_brew_action_must_be_draw():
    s = new_game(RS)
    assert legal_actions(s, RS, "p1") == [DRAW]


def test_brewing_player_after_first_chip_may_draw_or_stop():
    s = new_game(RS)
    s.players["p1"].placed = ["white_1"]
    assert legal_actions(s, RS, "p1") == [DRAW, STOP]


def test_stopped_or_exploded_player_waits():
    s = new_game(RS)
    s.players["p1"].status = Status.STOPPED
    s.players["p2"].status = Status.EXPLODED
    assert legal_actions(s, RS, "p1") == [WAIT]
    assert legal_actions(s, RS, "p2") == [WAIT]


def test_shop_legal_actions_follow_money():
    s = new_game(RS)
    s.phase = Phase.SHOP
    s.players["p1"].money = 5
    assert legal_actions(s, RS, "p1") == [DONE, buy("orange_1"), buy("blue_1"), buy("green_1")]


def test_shop_item_priced_at_money_left_is_legal():
    s = new_game(RS)
    s.phase = Phase.SHOP
    s.players["p1"].money = 3
    assert legal_actions(s, RS, "p1") == [DONE, buy("orange_1")]


def test_shop_with_no_money_only_done():
    s = new_game(RS)
    s.phase = Phase.SHOP
    s.players["p1"].money = 0
    assert legal_actions(s, RS, "p1") == [DONE]


def test_shop_after_three_purchases_waits():
    s = new_game(RS)
    s.phase = Phase.SHOP
    p = s.players["p1"]
    p.money, p.purchases, p.shop_done = 30, 3, True
    assert legal_actions(s, RS, "p1") == [WAIT]


def test_shop_done_waits_even_with_money():
    s = new_game(RS)
    s.phase = Phase.SHOP
    p = s.players["p1"]
    p.money, p.purchases, p.shop_done = 30, 0, True
    assert legal_actions(s, RS, "p1") == [WAIT]


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


def test_no_actions_in_resolve_or_after_game_over():
    s = new_game(RS)
    for phase in (Phase.RESOLVE, Phase.GAME_OVER):
        s.phase = phase
        assert legal_actions(s, RS, "p1") == []
        assert legal_actions(s, RS, "p2") == []


def test_state_round_trips_through_json():
    s = new_game(RS)
    s.players["p1"].placed = ["white_1", "green_1"]
    s.players["p1"].final_field = 2
    s.players["p2"].status = Status.EXPLODED
    s.phase = Phase.SHOP
    data = json.loads(json.dumps(state_to_dict(s)))
    restored = state_from_dict(data)
    assert restored == s
    assert type(restored.phase) is Phase
    for p in restored.players.values():
        assert type(p.status) is Status


def test_interface_names_are_importable_from_engine():
    names = [
        "SEATS",
        "Phase",
        "Status",
        "PlayerState",
        "GameState",
        "new_game",
        "start_field",
        "state_to_dict",
        "state_from_dict",
        "WAIT",
        "DRAW",
        "STOP",
        "DONE",
        "buy",
        "action_names",
        "legal_actions",
    ]
    for name in names:
        assert hasattr(engine, name), name
        assert name in engine.__all__, name
    assert engine.SEATS == ("p1", "p2")
