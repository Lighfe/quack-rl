import pytest
from helpers import RS, brew_start, play

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
    s = brew_start()
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
    assert (p1.money, p1.purchases, p1.bag["blue_2"]) == (10, 1, 1)
    assert {"seat": "p1", "kind": "buy", "item": "blue_2", "price": 10} in r.events






def test_second_chip_purchase_ends_shopping_and_one_chip_of_each_colour_per_round():
    s = play(shop_state(p1_money=9), buy("orange_1"), DONE).state
    # v2: one chip of each colour per round, so the second orange_1 is not legal
    assert buy("orange_1") not in legal_actions(s, RS, "p1")
    r = play(s, buy("green_1"), WAIT)
    assert legal_actions(r.state, RS, "p1") == [DONE]  # no chip purchase is left
    events = r.events
    r = play(r.state, DONE, WAIT)
    # the round reset puts all chips back: the start bag plus the 2 bought
    bag = r.state.players["p1"].bag
    assert (bag["orange_1"], bag["green_1"]) == (RS.start_bag["orange_1"] + 1, RS.start_bag["green_1"] + 1)
    assert {"seat": "p1", "kind": "buy", "item": "green_1", "price": 4} in events
    assert r.state.phase is Phase.CARD  # both done: the next round starts with its card
    assert r.state.round == 2


def test_last_chip_purchase_leaves_only_done_while_other_player_shops():
    s = shop_state(p1_money=7, p2_money=20)
    s.players["p1"].chip_purchases = RS.max_chip_purchases - 1
    r = play(s, buy("orange_1"), buy("orange_1"))
    p1 = r.state.players["p1"]
    assert p1.chip_purchases == RS.max_chip_purchases
    assert r.state.phase is Phase.SHOP  # p2 has not finished yet
    assert legal_actions(r.state, RS, "p1") == [DONE]  # v2: the seat still says done itself


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






def test_reset_returns_chips_and_starts_next_round_at_droplet():
    s = shop_state()
    s.players["p1"].droplet_halves = 3
    r = play(s, DONE, DONE)
    p1 = r.state.players["p1"]
    assert r.state.round == 2 and r.state.phase is Phase.CARD  # v2: the card step comes first
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




def test_step_after_game_over_raises():
    r = play(last_round(1, 0, 3, 3), DONE, DONE)
    with pytest.raises(GameOver):
        step(r.state, RS, {"p1": WAIT, "p2": WAIT}, RngChance(0))


def test_tie_break_compares_scoring_fields_so_52_and_53_draw():
    r = play(last_round(8, 8, 52, 53), DONE, DONE)
    assert r.state.winner == "draw"
    assert r.events[-1]["final_fields"] == {"p1": 52, "p2": 53}
