from helpers import RS, auto, play

from quack_rl.engine import DRAW, STOP, Phase, Status, new_game


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
    assert r.state.players["p1"].money == 17 + 1
    assert r.state.players["p2"].money == 12
    assert r.chance == [{"seat": "p1", "kind": "die", "value": "money_1"}]


def test_exploded_gets_half_money_rounded_down_and_never_rolls():
    r = auto(brewed(21, 4, exploded=("p1",)), "point_1")
    assert r.state.players["p1"].money == 18 // 2
    assert r.chance == [{"seat": "p2", "kind": "die", "value": "point_1"}]
    assert r.state.players["p2"].points == 1


def test_both_exploded_nobody_rolls():
    r = auto(brewed(21, 11, exploded=("p1", "p2")))
    assert r.chance == []
    assert (r.state.players["p1"].money, r.state.players["p2"].money) == (9, 5)


def test_tied_furthest_both_roll():
    r = auto(brewed(10, 10), "droplet_1", "droplet_half")
    assert [c["seat"] for c in r.chance] == ["p1", "p2"]
    assert r.state.players["p1"].droplet_halves == 2
    assert r.state.players["p2"].droplet_halves == 1


def test_ruby_field_gives_half_step_also_after_explosion():
    r = auto(brewed(9, 9, exploded=("p1",)), "money_1")
    assert r.state.players["p1"].droplet_halves == 1
    assert {"seat": "p1", "kind": "ruby", "halves": 1} in r.events


def test_green_in_last_two_gives_half_step_each():
    r = auto(brewed(4, 3, p1_placed=("green_1", "orange_1", "green_2")), "money_1")
    assert r.state.players["p1"].droplet_halves == 1  # only green_2 is in the last two
    r = auto(brewed(4, 3, p1_placed=("white_1", "green_1", "green_2")), "money_1")
    assert r.state.players["p1"].droplet_halves == 2


def test_die_orange_chip_goes_into_the_bag():
    r = auto(brewed(4, 3), "orange_1")
    assert r.state.players["p1"].bag["orange_1"] == 2


def test_full_round_flow_brew_then_resolve():
    s = play(new_game(RS), DRAW, DRAW, "white_2", "orange_1").state
    s = play(s, STOP, STOP).state
    r = auto(s, "money_1")
    assert r.state.phase is Phase.SHOP
    assert r.state.players["p1"].money == 2 + 1
    assert r.state.players["p2"].money == 1


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
    r = auto(brewed(4, 3), "droplet_1")
    assert r.state.players["p1"].droplet_halves == 2
    r = auto(brewed(4, 3), "droplet_half")
    assert r.state.players["p1"].droplet_halves == 1
    r = auto(brewed(4, 3), "money_1")
    assert r.state.players["p1"].money == 4 + 1
    r = auto(brewed(4, 3), "point_1")
    assert r.state.players["p1"].points == 1
    assert r.state.players["p1"].money == 4


def test_green_third_from_last_gives_nothing():
    r = auto(brewed(4, 3, p1_placed=("green_1", "white_1", "orange_1")), "money_1")
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
    r = auto(brewed(20, 12, p1_placed=("white_1", "green_1")), "droplet_1")
    assert r.events == [
        {"seat": "p1", "kind": "ruby", "halves": 1},
        {"seat": "p1", "kind": "round_end_bonus", "chip": "green_1", "halves": 1},
        {"seat": "p1", "kind": "die", "face": "droplet_1"},
        {"seat": "p1", "kind": "money", "amount": 17},
        {"seat": "p2", "kind": "money", "amount": 12},
    ]
    money = [e for e in r.events if e["kind"] == "money"]
    assert [e["seat"] for e in money] == ["p1", "p2"]
