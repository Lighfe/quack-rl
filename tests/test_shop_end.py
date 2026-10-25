from types import SimpleNamespace

import pytest
from helpers import RS, brew_start, play

from quack_rl.engine import (
    DONE,
    RUBY_DROP,
    WAIT,
    GameOver,
    Phase,
    RngChance,
    Status,
    action_names,
    buy,
    legal_actions,
    new_game,
    step,
)
from quack_rl.engine.shop import end_game


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
    # v2.1: one chip of each colour per round, so the second orange_1 is not legal
    assert buy("orange_1") not in legal_actions(s, RS, "p1")
    r = play(s, buy("green_1"), WAIT)
    # no chip purchase is left and no rubies: p1's shop closes without asking, and with p2
    # already done the round ends in this step
    assert {"seat": "p1", "kind": "done", "auto": True} in r.events
    # the round reset puts all chips back: the start bag plus the 2 bought
    bag = r.state.players["p1"].bag
    assert (bag["orange_1"], bag["green_1"]) == (RS.start_bag["orange_1"] + 1, RS.start_bag["green_1"] + 1)
    assert {"seat": "p1", "kind": "buy", "item": "green_1", "price": 4} in r.events
    assert r.state.phase is Phase.CARD  # both done: the next round starts with its card
    assert r.state.round == 2


def test_last_chip_purchase_leaves_only_done_while_other_player_shops():
    s = shop_state(p1_money=7, p2_money=20)
    s.players["p1"].chip_purchases = RS.max_chip_purchases - 1
    r = play(s, buy("orange_1"), buy("orange_1"))
    p1 = r.state.players["p1"]
    assert p1.chip_purchases == RS.max_chip_purchases
    assert r.state.phase is Phase.SHOP  # p2 has not finished yet
    # nothing but done is left: p1's shop closes without asking (issue #203)
    assert legal_actions(r.state, RS, "p1") == [WAIT]
    assert {"seat": "p1", "kind": "done", "auto": True} in r.events


def test_done_player_only_waits_and_nothing_of_theirs_changes():
    s = shop_state(p1_money=20, p2_money=20)
    s.players["p2"].rubies = RS.ruby_cost  # p2 keeps a ruby drop, so p2 still shops after 2 buys
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
    assert r.state.round == 2 and r.state.phase is Phase.CARD  # v2.1: the card step comes first
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
    """The end of the last round (it has no shop): `end_game` on a state with no rubies."""
    s = shop_state()
    s.round = RS.rounds
    s.players["p1"].points, s.players["p2"].points = p1_points, p2_points
    s.players["p1"].final_field, s.players["p2"].final_field = p1_final, p2_final
    for p in s.players.values():
        p.rubies = 0
    events = []
    end_game(s, RS, events)
    return SimpleNamespace(state=s, events=events)


@pytest.mark.parametrize(
    ("p1_points", "p2_points", "p1_final", "p2_final", "winner"),
    [(10, 8, 3, 30, "p1"), (8, 8, 20, 12, "p1"), (8, 8, 12, 20, "p2"), (8, 8, 12, 12, "draw")],
)
def test_game_end_winner(p1_points, p2_points, p1_final, p2_final, winner):
    r = last_round(p1_points, p2_points, p1_final, p2_final)
    assert r.state.phase is Phase.GAME_OVER
    assert r.state.winner == winner
    assert r.events[-1]["kind"] == "game_end" and r.events[-1]["winner"] == winner


def test_game_end_event_and_no_reset_after_the_last_round():
    r = last_round(10, 8, 3, 30)
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
    r = last_round(1, 0, 3, 3)
    with pytest.raises(GameOver):
        step(r.state, RS, {"p1": WAIT, "p2": WAIT}, RngChance(0))


def test_tie_break_compares_scoring_fields_so_52_and_53_draw():
    r = last_round(8, 8, 52, 53)
    assert r.state.winner == "draw"
    assert r.events[-1]["final_fields"] == {"p1": 52, "p2": 53}


# Rubies as a currency: the action ruby_drop


def with_rubies(p1_rubies):
    s = shop_state(p1_money=0)
    s.players["p1"].rubies = p1_rubies
    return s


@pytest.mark.parametrize(("rubies", "offered"), [(0, False), (1, False), (2, True), (3, True)])
def test_ruby_drop_is_offered_from_ruby_cost(rubies, offered):
    assert (RUBY_DROP in legal_actions(with_rubies(rubies), RS, "p1")) is offered


def test_ruby_drop_is_not_offered_when_the_player_is_done():
    s = with_rubies(4)
    s.players["p1"].shop_done = True
    assert legal_actions(s, RS, "p1") == [WAIT]


def test_ruby_drop_costs_rubies_adds_a_droplet_and_stays_in_the_shop():
    r = play(with_rubies(3), RUBY_DROP, DONE)
    p1 = r.state.players["p1"]
    assert (p1.rubies, p1.droplet_halves, p1.shop_done) == (1, 2, False)
    assert {"seat": "p1", "kind": "ruby_drop", "rubies": 2, "halves": 2, "total": 1} in r.events
    assert RUBY_DROP not in legal_actions(r.state, RS, "p1")  # 1 ruby left


def test_ruby_drop_twice_with_four_rubies():
    r = play(with_rubies(4), RUBY_DROP, DONE)
    r = play(r.state, RUBY_DROP, WAIT)
    p1 = r.state.players["p1"]
    assert (p1.rubies, p1.droplet_halves) == (0, 4)
    assert RUBY_DROP not in legal_actions(r.state, RS, "p1")


def test_rubies_carry_over_into_the_next_round_and_the_droplet_moves_the_start():
    r = play(with_rubies(3), RUBY_DROP, DONE)
    # 1 ruby and no money left: p1's shop closes without asking and the round ends (issue #203)
    assert {"seat": "p1", "kind": "done", "auto": True} in r.events
    assert r.state.round == 2
    p1 = r.state.players["p1"]
    assert (p1.rubies, p1.droplet_halves, p1.field) == (1, 2, 1)


def test_ruby_drop_is_followed_only_by_the_flask_actions():
    names = action_names(RS)
    i = names.index(RUBY_DROP)
    assert names[i : i + 3] == [RUBY_DROP, "use_flask", "refill_flask"]


# --- idle shops close without asking (issue #203) ---------------------------------

from quack_rl.engine import REFILL_FLASK, TAKE_POINTS, ScriptedChance  # noqa: E402


def choice_state(p2_money=20, round_=1):
    """CHOICE phase: p1 exploded on field 0 (no money), p2 stopped with `p2_money`."""
    s = brew_start()
    s.round = round_
    s.phase = Phase.CHOICE
    for seat in ("p1", "p2"):
        p = s.players[seat]
        p.final_field = p.field = 0
        p.rubies = 0
        p.flask_full = True
        p.money = 0
    s.players["p1"].status = Status.EXPLODED
    s.players["p2"].status = Status.STOPPED
    s.players["p2"].money = p2_money
    return s


def auto_done_events(events):
    return [e for e in events if e["kind"] == "done" and e.get("auto")]


def test_shop_legal_actions_order_is_done_buys_ruby_drop_refill():
    s = shop_state(p1_money=20)
    p1 = s.players["p1"]
    p1.rubies, p1.flask_full = 2, False
    legal = legal_actions(s, RS, "p1")
    assert legal[0] == DONE and legal[-2:] == [RUBY_DROP, REFILL_FLASK]
    buys = legal[1:-2]
    assert buys and all(a.startswith("buy:") for a in buys)


def test_idle_player_on_entering_the_shop_is_never_asked():
    r = play(choice_state(p2_money=20), TAKE_POINTS, WAIT)
    s = r.state
    assert s.phase is Phase.SHOP
    assert s.players["p1"].shop_done
    assert legal_actions(s, RS, "p1") == [WAIT]
    assert auto_done_events(r.events) == [{"seat": "p1", "kind": "done", "auto": True}]
    # p2 shops on, p1 only waits through the whole shop
    r = play(s, WAIT, buy("orange_1"))
    assert legal_actions(r.state, RS, "p1") == [WAIT]
    assert auto_done_events(r.events) == []
    r = play(r.state, WAIT, DONE)
    assert r.state.phase is Phase.CARD


def test_second_chip_buy_with_one_ruby_leaves_only_wait():
    s = shop_state(p1_money=20, p2_money=20)
    s.players["p1"].rubies = 1
    s.players["p2"].rubies = RS.ruby_cost
    s = play(s, buy("orange_1"), buy("orange_1")).state
    r = play(s, buy("green_1"), buy("green_1"))
    assert r.state.phase is Phase.SHOP  # p2 also has no chip buy left, but 2 rubies
    assert legal_actions(r.state, RS, "p1") == [WAIT]
    assert {"seat": "p1", "kind": "done", "auto": True} in r.events


def test_second_chip_buy_with_two_rubies_still_asks():
    s = shop_state(p1_money=20, p2_money=20)
    s.players["p1"].rubies = 2
    s = play(s, buy("orange_1"), DONE).state
    r = play(s, buy("green_1"), WAIT)
    assert r.state.phase is Phase.SHOP
    assert legal_actions(r.state, RS, "p1") == [DONE, RUBY_DROP]
    assert auto_done_events(r.events) == []


def test_both_idle_on_entering_the_shop_ends_the_round():
    r = play(choice_state(p2_money=0), TAKE_POINTS, WAIT)
    assert r.state.phase is Phase.CARD
    assert r.state.round == 2
    assert auto_done_events(r.events) == [
        {"seat": "p1", "kind": "done", "auto": True},
        {"seat": "p2", "kind": "done", "auto": True},
    ]
    assert not any(e["kind"] in ("buy", "ruby_drop", "refill_flask") for e in r.events)


def test_both_idle_after_resolve_ends_the_round():
    s = brew_start()
    s.phase = Phase.RESOLVE
    for seat in ("p1", "p2"):
        p = s.players[seat]
        p.status = Status.STOPPED
        p.final_field = p.field = 0
        p.placed = []
        p.rubies = 0
        p.flask_full = True
    r = step(s, RS, None, ScriptedChance(["point_1", "point_1"]))  # both tie on field 0 and roll
    assert r.state.phase is Phase.CARD
    assert r.state.round == 2
    assert len(auto_done_events(r.events)) == 2


def test_last_shop_step_with_the_other_player_idle_ends_the_round():
    s = shop_state(p1_money=20, p2_money=20)
    s = play(s, buy("orange_1"), DONE).state
    r = play(s, buy("green_1"), WAIT)  # p1 idle after the second buy, p2 already done
    assert r.state.phase is Phase.CARD
    assert r.state.round == 2
    assert auto_done_events(r.events) == [{"seat": "p1", "kind": "done", "auto": True}]
