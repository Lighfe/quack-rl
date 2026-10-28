from helpers import RS, brew_start, play

from quack_rl.engine import (
    DONE,
    DRAW,
    REFILL_FLASK,
    STOP,
    USE_FLASK,
    WAIT,
    Phase,
    Status,
    action_names,
    legal_actions,
    refill_all_flasks,
    start_field,
    state_from_dict,
    state_to_dict,
)


def test_flask_is_full_at_the_start_and_survives_the_dict_round_trip():
    s = brew_start()
    assert all(p.flask_full for p in s.players.values())
    s.players["p1"].flask_full = False
    assert state_from_dict(state_to_dict(s)).players["p1"].flask_full is False


def test_actions_are_appended_after_ruby_drop():
    names = action_names(RS)
    i = names.index("ruby_drop")
    assert names[i : i + 3] == ["ruby_drop", USE_FLASK, REFILL_FLASK]
    assert names[i + 3].startswith("card_tails:")  # the actions of the later cards follow


def test_use_after_the_first_white_chip_goes_back_to_the_start_field():
    s = brew_start()
    s.players["p1"].rat_tail = 2
    s.players["p1"].field = start_field(s.players["p1"], RS)
    start = s.players["p1"].field
    s = play(s, DRAW, DRAW, "white_2", "white_1").state
    assert legal_actions(s, RS, "p1") == [DRAW, STOP, USE_FLASK]
    r = play(s, USE_FLASK, DRAW, "white_1")
    p = r.state.players["p1"]
    assert (p.field, p.white_total, p.placed, p.placed_fields) == (start, 0, [], [])
    assert p.flask_full is False and p.status is Status.BREWING
    assert p.bag["white_2"] == RS.start_bag["white_2"]
    ev = next(e for e in r.events if e["kind"] == "use_flask")
    assert ev == {"seat": "p1", "kind": "use_flask", "chip": "white_2", "field": start, "white_total": 0}


def test_use_after_a_later_white_chip_goes_back_to_the_previous_landing_field():
    s = brew_start()
    s = play(s, DRAW, DRAW, "white_1", "white_1").state
    s = play(s, DRAW, DRAW, "white_2", "white_1").state
    before = s.players["p1"].placed_fields[0]
    r = play(s, USE_FLASK, STOP)
    p = r.state.players["p1"]
    assert (p.field, p.white_total, p.placed) == (before, 1, ["white_1"])
    assert p.placed_fields == [before]
    assert legal_actions(r.state, RS, "p1") == [DRAW, STOP]  # the flask is empty


def test_not_offered_after_a_green_chip():
    s = play(brew_start(), DRAW, DRAW, "green_1", "white_1").state
    assert USE_FLASK not in legal_actions(s, RS, "p1")


def test_not_offered_after_an_explosion_or_a_stop():
    s = brew_start()
    s = play(s, DRAW, DRAW, "white_3", "white_1").state
    s = play(s, DRAW, DRAW, "white_2", "white_1").state
    s = play(s, DRAW, DRAW, "white_2", "white_1").state  # 7
    s = play(s, DRAW, DRAW, "white_1", "white_1").state  # 8 > 7
    assert s.players["p1"].status is Status.EXPLODED
    assert legal_actions(s, RS, "p1") == [WAIT]
    s2 = play(brew_start(), DRAW, DRAW, "white_1", "white_1").state
    s2 = play(s2, STOP, DRAW, "white_1").state
    assert legal_actions(s2, RS, "p1") == [WAIT]


def test_not_offered_with_an_empty_flask():
    s = brew_start()
    s.players["p1"].flask_full = False
    s = play(s, DRAW, DRAW, "white_1", "white_1").state
    assert legal_actions(s, RS, "p1") == [DRAW, STOP]


def _shop(rubies, full):
    s = brew_start()
    s.phase = Phase.SHOP
    for p in s.players.values():
        p.status, p.rubies, p.flask_full = Status.STOPPED, rubies, full
        p.placed, p.placed_fields = ["white_1"], [1]
        p.bag["white_1"] -= 1
    return s


def _ruby(rubies, full):
    """The ruby step after the shop: both shops are closed."""
    s = _shop(rubies, full)
    s.phase = Phase.RUBY
    for p in s.players.values():
        p.shop_done = True
    return s


def test_refill_is_offered_only_in_the_ruby_step_with_an_empty_flask_and_two_rubies():
    assert REFILL_FLASK not in legal_actions(_shop(5, False), RS, "p1")  # not in the shop
    assert REFILL_FLASK not in legal_actions(_ruby(5, True), RS, "p1")
    assert REFILL_FLASK not in legal_actions(_ruby(1, False), RS, "p1")
    assert REFILL_FLASK in legal_actions(_ruby(2, False), RS, "p1")
    s = _ruby(2, False)
    s.players["p1"].ruby_done = True
    assert legal_actions(s, RS, "p1") == [WAIT]


def test_refill_costs_two_rubies_and_fills_the_flask():
    r = play(_ruby(3, False), REFILL_FLASK, DONE)
    p = r.state.players["p1"]
    assert (p.rubies, p.flask_full) == (1, True)
    assert {"seat": "p1", "kind": "refill_flask", "rubies": 2, "total": 1} in r.events
    assert REFILL_FLASK not in legal_actions(r.state, RS, "p1")


def test_the_flask_is_kept_between_rounds():
    s = play(_shop(0, False), DONE, DONE).state
    assert s.round == 2 and s.players["p1"].flask_full is False


def test_refill_all_flasks():
    s = brew_start()
    for p in s.players.values():
        p.flask_full = False
    refill_all_flasks(s)
    assert all(p.flask_full for p in s.players.values())
