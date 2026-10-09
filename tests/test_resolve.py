from helpers import RS, auto, play

from quack_rl.engine import DRAW, STOP, Phase, ScriptedChance, Status, new_game, step


def brewed(p1_field, p2_field, p1_placed=("white_1",), p2_placed=("white_1",), exploded=()):
    """A state at the start of Resolve with settled final fields."""
    s = new_game(RS)
    s.phase = Phase.RESOLVE
    for seat, fld, placed in (("p1", p1_field, p1_placed), ("p2", p2_field, p2_placed)):
        p = s.players[seat]
        p.field = p.final_field = fld
        p.placed = list(placed)
        p.status = Status.EXPLODED if seat in exploded else Status.STOPPED
    return s


def test_resolve_takes_no_actions_and_moves_to_shop():
    r = auto(brewed(4, 3), "money_1")
    assert r.phase is Phase.RESOLVE and r.legal is None and r.actions is None
    assert r.state.phase is Phase.SHOP


def test_money_of_final_field_and_bonus_die_for_furthest():
    r = auto(brewed(20, 12), "money_1")
    assert r.state.players["p1"].money == 18 + 1
    assert r.state.players["p2"].money == 13
    assert r.chance == [{"seat": "p1", "kind": "die", "value": "money_1"}]


def test_exploded_gets_half_money_rounded_down_and_never_rolls():
    r = auto(brewed(21, 4, exploded=("p1",)), "point_1")
    assert r.state.players["p1"].money == 18 // 2
    assert r.chance == [{"seat": "p2", "kind": "die", "value": "point_1"}]
    assert r.state.players["p2"].points == 1


def test_both_exploded_nobody_rolls():
    r = auto(brewed(21, 11, exploded=("p1", "p2")))
    assert r.chance == []
    assert (r.state.players["p1"].money, r.state.players["p2"].money) == (9, 6)


def test_tied_furthest_both_roll():
    r = auto(brewed(10, 10), "droplet_1", "droplet_half")
    assert [c["seat"] for c in r.chance] == ["p1", "p2"]
    assert r.state.players["p1"].droplet_halves == 2
    assert r.state.players["p2"].droplet_halves == 1


def test_ruby_field_gives_half_step_also_after_explosion():
    r = auto(brewed(8, 8, exploded=("p1",)), "money_1")
    assert r.state.players["p1"].droplet_halves == 1
    assert {"seat": "p1", "kind": "ruby", "halves": 1} in r.events


def test_green_in_last_two_gives_half_step_each():
    r = auto(brewed(3, 2, p1_placed=("green_1", "orange_1", "green_2")), "money_1")
    assert r.state.players["p1"].droplet_halves == 1  # only green_2 is in the last two
    r = auto(brewed(3, 2, p1_placed=("white_1", "green_1", "green_2")), "money_1")
    assert r.state.players["p1"].droplet_halves == 2


def test_die_orange_chip_goes_into_the_bag():
    r = auto(brewed(4, 3), "orange_1")
    assert r.state.players["p1"].bag["orange_1"] == 2


def test_full_round_flow_brew_then_resolve():
    s = play(new_game(RS), DRAW, DRAW, "white_2", "orange_1").state
    s = play(s, STOP, STOP).state
    r = auto(s, "money_1")
    assert r.state.phase is Phase.SHOP
    assert r.state.players["p1"].money == 3 + 1
    assert r.state.players["p2"].money == 2


# Extra cases from the groomed issue #8


def test_purchases_and_shop_done_are_reset():
    s = brewed(4, 3)
    for p in s.players.values():
        p.purchases = 2
        p.shop_done = True
    r = auto(s, "money_1")
    for p in r.state.players.values():
        assert p.purchases == 0
        assert p.shop_done is False


def test_field_53_gives_money_35():
    r = auto(brewed(53, 3), "point_1")
    assert r.state.players["p1"].money == 35


def test_field_53_exploded_gives_17():
    r = auto(brewed(53, 3, exploded=("p1",)), "point_1")
    assert r.state.players["p1"].money == 17
    assert r.chance == [{"seat": "p2", "kind": "die", "value": "point_1"}]


def test_die_faces_apply():
    r = auto(brewed(3, 2), "droplet_1")
    assert r.state.players["p1"].droplet_halves == 2
    r = auto(brewed(3, 2), "droplet_half")
    assert r.state.players["p1"].droplet_halves == 1
    r = auto(brewed(3, 2), "money_1")
    assert r.state.players["p1"].money == 4 + 1
    r = auto(brewed(3, 2), "point_1")
    assert r.state.players["p1"].points == 1
    assert r.state.players["p1"].money == 4


def test_green_third_from_last_gives_nothing():
    r = auto(brewed(3, 2, p1_placed=("green_1", "white_1", "orange_1")), "money_1")
    assert r.state.players["p1"].droplet_halves == 0
    assert not [e for e in r.events if e["kind"] == "round_end_bonus"]


def test_resolve_does_not_change_field_or_bag_except_orange_face():
    s = brewed(20, 12, p1_placed=("white_1", "green_1"))
    r = auto(s, "droplet_1")
    for seat in ("p1", "p2"):
        assert r.state.players[seat].field == s.players[seat].field
        assert r.state.players[seat].final_field == s.players[seat].final_field
        assert r.state.players[seat].bag == s.players[seat].bag
        assert r.state.players[seat].placed == s.players[seat].placed
    r = auto(s, "orange_1")
    assert r.state.players["p1"].bag == {**s.players["p1"].bag, "orange_1": 2}
    assert r.state.players["p2"].bag == s.players["p2"].bag
    assert r.state.players["p1"].field == 20


def test_events_kinds_and_one_money_event_per_seat():
    r = auto(brewed(19, 11, p1_placed=("white_1", "green_1")), "droplet_1")
    assert r.events == [
        {"seat": "p1", "kind": "ruby", "halves": 1},
        {"seat": "p1", "kind": "round_end_bonus", "chip": "green_1", "halves": 1},
        {"seat": "p1", "kind": "die", "face": "droplet_1"},
        {"seat": "p1", "kind": "money", "amount": 17},
        {"seat": "p2", "kind": "money", "amount": 12},
    ]
    money = [e for e in r.events if e["kind"] == "money"]
    assert [e["seat"] for e in money] == ["p1", "p2"]


# Issue #19: scoring field = min(landing + 1, track_end)


def test_landing_on_field_1_gives_money_of_field_2():
    r = auto(brewed(1, 0), "point_1")
    assert r.state.players["p1"].money == RS.money[2] == 2


def test_landing_on_4_gives_the_ruby_of_field_5():
    r = auto(brewed(4, 0), "point_1")
    assert r.state.players["p1"].droplet_halves == 1
    assert {"seat": "p1", "kind": "ruby", "halves": 1} in r.events


def test_landing_on_5_gives_no_ruby():
    r = auto(brewed(5, 0), "point_1")
    assert r.state.players["p1"].droplet_halves == 0


def test_landing_on_51_scores_field_52_ruby_and_money_33():
    r = auto(brewed(51, 0), "point_1")
    assert r.state.players["p1"].droplet_halves == 1
    assert r.state.players["p1"].money == 33


def test_last_chip_on_53_scores_field_53():
    r = auto(brewed(53, 0), "point_1")
    assert r.state.players["p1"].money == 35
    assert r.state.players["p1"].droplet_halves == 0


def test_landing_on_52_and_53_tie_and_both_roll():
    r = auto(brewed(52, 53), "point_1", "point_1")
    assert [c["seat"] for c in r.chance] == ["p1", "p2"]
    assert r.state.players["p1"].money == r.state.players["p2"].money == 35


def test_exploded_potion_halves_scoring_field_money_and_keeps_ruby():
    r = auto(brewed(51, 0, exploded=("p1",)), "point_1")
    assert r.state.players["p1"].money == 33 // 2
    assert r.state.players["p1"].droplet_halves == 1


# Issue #20: last round money x last_round_money_percent // 100


def last_round(state, rnd=None):
    state.round = RS.rounds if rnd is None else rnd
    return state


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


def test_round_1_money_is_unchanged():
    r = auto(last_round(brewed(34, 0), 1), "point_1")
    assert r.state.players["p1"].money == 25


def test_round_before_last_money_is_unchanged():
    r = auto(last_round(brewed(34, 0), RS.rounds - 1), "money_1")
    assert r.state.players["p1"].money == 26


def test_factor_comes_from_the_ruleset():
    rs = RS.model_copy(update={"last_round_money_percent": 200})
    s = last_round(brewed(34, 0))
    r = step(s, rs, None, ScriptedChance(("point_1",)))
    assert r.state.players["p1"].money == 50
