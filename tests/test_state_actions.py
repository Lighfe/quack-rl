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
    assert (s.rules_version, s.round, s.phase, s.step, s.winner) == ("v2.1", 1, Phase.CARD, 0, None)
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


def test_action_names_v2_1():
    names = action_names(RS)
    assert names[:6] == [WAIT, DRAW, STOP, DONE, "take_money", "take_points"]
    assert names[6:8] == [buy("orange_1"), buy("orange_6")]
    assert names == [
        "wait",
        "draw",
        "stop",
        "done",
        "take_money",
        "take_points",
        "buy:orange_1",
        "buy:orange_6",
        "buy:green_1",
        "buy:green_2",
        "buy:green_4",
        "buy:blue_1",
        "buy:blue_2",
        "buy:blue_4",
        "buy:red_1",
        "buy:red_2",
        "buy:red_4",
        "play:0",
        "play:1",
        "play:2",
        "play:3",
        "put_back_draw",
        "put_back_stop",
        "buy:black_1",
        "buy:yellow_1",
        "buy:yellow_2",
        "buy:yellow_4",
        "buy:purple_1",
        "continue",
        "restart",
        "card_drop_2",
        "card_purple",
        "card_black",
        "card_chip:white_2",
        "card_chip:green_2",
        "card_chip:blue_2",
        "card_chip:red_2",
        "card_chip:yellow_2",
        "card_rubies",
        "ruby_drop",
        "use_flask",
        "refill_flask",
    ]
    assert len(names) == 42
    assert buy("blue_2") == "buy:blue_2"
    assert {buy(i.id) for i in RS.shop} <= set(names)


def brewing():
    s = new_game(RS)
    s.phase = Phase.BREW
    return s


def test_new_game_waits_for_the_first_card():
    assert legal_actions(new_game(RS), RS, "p1") == []


def test_first_brew_action_must_be_draw():
    s = brewing()
    assert legal_actions(s, RS, "p1") == [DRAW]


def test_brewing_player_after_first_chip_may_draw_or_stop():
    s = brewing()
    s.players["p1"].placed = ["white_1"]
    assert legal_actions(s, RS, "p1") == [DRAW, STOP, "use_flask"]
    s.players["p1"].placed = ["green_1"]
    assert legal_actions(s, RS, "p1") == [DRAW, STOP]


def test_stopped_or_exploded_player_waits():
    s = brewing()
    s.players["p1"].status = Status.STOPPED
    s.players["p2"].status = Status.EXPLODED
    assert legal_actions(s, RS, "p1") == [WAIT]
    assert legal_actions(s, RS, "p2") == [WAIT]


def test_shop_legal_actions_follow_money():
    s = new_game(RS)
    s.phase = Phase.SHOP
    s.players["p1"].money = 5
    assert legal_actions(s, RS, "p1") == [DONE, buy("orange_1"), buy("green_1"), buy("blue_1")]


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
