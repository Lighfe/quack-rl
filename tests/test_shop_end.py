import pytest
from helpers import RS, play

from quack_rl.engine import (
    DONE,
    WAIT,
    GameOver,
    Phase,
    RngChance,
    Status,
    buy,
    legal_actions,
    new_game,
    step,
)


def shop_state(p1_money=20, p2_money=0):
    s = new_game(RS)
    s.phase = Phase.SHOP
    for seat, money in (("p1", p1_money), ("p2", p2_money)):
        p = s.players[seat]
        p.money, p.status = money, Status.STOPPED
        p.placed = ["white_1", "white_2"]
        p.bag["white_1"] -= 1
        p.bag["white_2"] -= 1
        p.field = p.final_field = 3
    return s


def test_buying_a_chip_puts_it_into_the_bag_and_costs_money():
    r = play(shop_state(), buy("blue_2"), DONE)
    p1 = r.state.players["p1"]
    assert (p1.money, p1.purchases, p1.bag["blue_2"]) == (11, 1, 1)
    assert {"seat": "p1", "kind": "buy", "item": "blue_2", "price": 9} in r.events


def test_points_are_added_at_once():
    r = play(shop_state(p1_money=22), buy("points_10"), DONE)
    assert r.state.players["p1"].points == 10


def test_bought_droplet_moves_the_start_field_of_the_next_round():
    s = shop_state(p1_money=10)
    assert s.players["p1"].droplet_halves == 0
    s = play(s, buy("droplet_1"), DONE).state
    assert s.players["p1"].droplet_halves == 2
    r = play(s, DONE, WAIT)
    p1 = r.state.players["p1"]
    assert r.state.phase is Phase.BREW
    assert (p1.droplet_halves, p1.field) == (2, 1)


def test_same_item_may_be_bought_again_and_third_purchase_ends_shopping():
    s = play(shop_state(p1_money=9), buy("orange_1"), DONE).state
    s = play(s, buy("orange_1"), WAIT).state
    r = play(s, buy("orange_1"), WAIT)
    # purchases is reset with the round, so count the chips: 1 at start + 3 bought
    assert r.state.players["p1"].bag["orange_1"] == RS.start_bag["orange_1"] + 3
    assert {"seat": "p1", "kind": "buy", "item": "orange_1", "price": 3} in r.events
    assert r.state.phase is Phase.BREW  # both done: next round started
    assert r.state.round == 2


def test_third_purchase_sets_shop_done_while_other_player_shops():
    s = shop_state(p1_money=3, p2_money=20)
    s.players["p1"].purchases = RS.max_purchases - 1
    r = play(s, buy("orange_1"), buy("orange_1"))
    p1 = r.state.players["p1"]
    assert (p1.purchases, p1.shop_done) == (3, True)
    assert r.state.phase is Phase.SHOP  # p2 has not finished yet
    assert legal_actions(r.state, RS, "p1") == [WAIT]


def test_done_player_only_waits_and_nothing_of_theirs_changes():
    s = shop_state(p1_money=20, p2_money=20)
    s = play(s, DONE, buy("orange_1")).state
    assert legal_actions(s, RS, "p1") == [WAIT]
    before = s.players["p1"]
    r = play(s, WAIT, buy("blue_2"))
    after = r.state.players["p1"]
    assert r.state.phase is Phase.SHOP
    assert (after.money, after.bag, after.points) == (before.money, before.bag, before.points)
    assert after.placed == before.placed
    assert not [e for e in r.events if e["seat"] == "p1"]


def test_remove_white_1_takes_a_placed_chip_first():
    s = shop_state(p1_money=15)
    s = play(s, buy("remove_white_1"), DONE).state
    assert s.players["p1"].placed == ["white_2"]
    r = play(s, DONE, WAIT)
    # after the reset all chips are back in the bag: 4 white_1 at start, 1 removed
    assert r.state.players["p1"].bag["white_1"] == 3


def test_remove_white_1_without_a_placed_one_takes_it_from_the_bag():
    s = shop_state(p1_money=15)
    p1 = s.players["p1"]
    p1.placed = ["white_2"]
    p1.bag["white_1"] += 1
    assert p1.bag["white_1"] == 4
    r = play(s, buy("remove_white_1"), DONE)
    p1 = r.state.players["p1"]
    assert p1.bag["white_1"] == 3
    assert p1.placed == ["white_2"]


def test_reset_returns_chips_and_starts_next_round_at_droplet():
    s = shop_state()
    s.players["p1"].droplet_halves = 3
    r = play(s, DONE, DONE)
    p1 = r.state.players["p1"]
    assert r.state.round == 2 and r.state.phase is Phase.BREW
    assert p1.placed == [] and p1.bag == RS.start_bag
    assert (p1.field, p1.money, p1.white_total, p1.final_field) == (1, 0, 0, None)
    assert (p1.purchases, p1.shop_done) == (0, False)
    assert p1.status is Status.BREWING
    round_ends = [e for e in r.events if e["kind"] == "round_end"]
    assert round_ends == [{"seat": None, "kind": "round_end", "next_round": 2}]


def test_reset_caps_the_start_field_at_the_track_end():
    s = shop_state()
    s.players["p1"].droplet_halves = 2 * RS.track_end + 4
    r = play(s, DONE, DONE)
    assert r.state.players["p1"].field == RS.track_end


def test_unspent_money_is_lost():
    r = play(shop_state(p1_money=20), DONE, DONE)
    assert r.state.players["p1"].money == 0


def last_round(p1_points, p2_points, p1_final, p2_final):
    s = shop_state()
    s.round = RS.rounds
    s.players["p1"].points, s.players["p2"].points = p1_points, p2_points
    s.players["p1"].final_field, s.players["p2"].final_field = p1_final, p2_final
    return s


@pytest.mark.parametrize(
    ("p1_points", "p2_points", "p1_final", "p2_final", "winner"),
    [(10, 8, 3, 30, "p1"), (8, 8, 20, 12, "p1"), (8, 8, 12, 20, "p2"), (8, 8, 12, 12, "draw")],
)
def test_game_end_winner(p1_points, p2_points, p1_final, p2_final, winner):
    r = play(last_round(p1_points, p2_points, p1_final, p2_final), DONE, DONE)
    assert r.state.phase is Phase.GAME_OVER
    assert r.state.winner == winner
    assert r.events[-1]["kind"] == "game_end" and r.events[-1]["winner"] == winner


def test_game_end_event_and_no_reset_after_the_last_round():
    r = play(last_round(10, 8, 3, 30), DONE, DONE)
    assert r.events[-1] == {
        "seat": None,
        "kind": "game_end",
        "winner": "p1",
        "points": {"p1": 10, "p2": 8},
        "final_fields": {"p1": 3, "p2": 30},
    }
    assert not [e for e in r.events if e["kind"] == "round_end"]
    assert r.state.round == RS.rounds
    for seat in ("p1", "p2"):
        assert r.state.players[seat].placed == ["white_1", "white_2"]


def test_final_field_is_not_changed_by_removing_the_last_placed_chip():
    s = last_round(5, 5, 20, 12)
    s.players["p1"].money = 15
    s.players["p1"].placed = ["white_2", "white_1"]
    s = play(s, buy("remove_white_1"), DONE).state
    r = play(s, DONE, WAIT)
    assert r.state.winner == "p1"
    assert r.state.players["p1"].final_field == 20


def test_step_after_game_over_raises():
    r = play(last_round(1, 0, 3, 3), DONE, DONE)
    with pytest.raises(GameOver):
        step(r.state, RS, {"p1": WAIT, "p2": WAIT}, RngChance(0))
