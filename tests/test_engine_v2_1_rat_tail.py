"""Ruleset v2.1: the rat tail bonus at the round start (issue #156)."""

from quack_rl.engine import (
    CARD_DROP_2,
    DONE,
    RESTART,
    Phase,
    ScriptedChance,
    new_game,
    calculate_rat_tails,
    start_field,
    state_from_dict,
    state_to_dict,
    step,
)
from quack_rl.rules import load_ruleset

RS = load_ruleset("v2.1")


def card_state(p1=0, p2=10, rs=RS):
    s = new_game(rs)
    s.players["p1"].points = p1
    s.players["p2"].points = p2
    return s


def draw(s, card, rs=RS):
    return step(s, rs, None, ScriptedChance([card]))


def test_rat_tail_survives_the_state_dict():
    s = new_game(RS)
    s.players["p1"].rat_tail = 3
    assert state_from_dict(state_to_dict(s)).players["p1"].rat_tail == 3


def test_start_field_adds_the_bonus_and_caps_at_track_end():
    p = new_game(RS).players["p1"]
    p.droplet_halves = 6
    p.rat_tail = 2
    assert start_field(p, RS) == 5
    p.droplet_halves = 2 * (RS.track_end - 1)
    p.rat_tail = 5
    assert start_field(p, RS) == RS.track_end


def test_card_step_sets_rat_tails_and_fields():
    out = draw(card_state(0, 10), "card_16")
    assert out.state.phase is Phase.BREW
    p1, p2 = out.state.players["p1"], out.state.players["p2"]
    assert (p1.rat_tail, p2.rat_tail) == (3, 0)
    assert (p1.field, p2.field) == (3, 0)
    assert {"seat": "p1", "kind": "rat_tail", "bonus": 3} in out.events
    assert not any(e["seat"] == "p2" and e["kind"] == "rat_tail" for e in out.events)


def test_round_one_and_tied_totals_give_zero():
    for p1, p2 in [(0, 0), (30, 30)]:
        out = draw(card_state(p1, p2), "card_16")
        assert [out.state.players[s].rat_tail for s in ("p1", "p2")] == [0, 0]
        assert not any(e["kind"] == "rat_tail" for e in out.events)


def test_card_3_gives_drop_plus_bonus():
    out = draw(card_state(0, 10), "card_3")
    p1, p2 = out.state.players["p1"], out.state.players["p2"]
    assert (p1.field, p2.field) == (1 + 3, 1)


def test_card_6_choice_sets_rat_tails_after_the_choice():
    s = draw(card_state(0, 10), "card_6").state
    assert s.phase is Phase.CARD_CHOICE
    assert s.players["p1"].rat_tail == 0
    out = step(s, RS, {"p1": CARD_DROP_2, "p2": "card_purple"}, ScriptedChance([]))
    p1 = out.state.players["p1"]
    assert p1.rat_tail == 3
    assert p1.field == 2 + 3


def test_card_5_choice_sets_rat_tails():
    s = draw(card_state(0, 10), "card_5").state
    out = step(s, RS, {"p1": "card_black", "p2": "card_black"}, ScriptedChance([]))
    assert out.state.players["p1"].rat_tail == 3
    assert out.state.players["p1"].field == 3


def test_restart_returns_to_the_boosted_start():
    s = draw(card_state(0, 10), "card_2").state
    p1 = s.players["p1"]
    p1.placed = ["white_1"] * 5
    p1.field = 20
    p1.restart_pending = True
    s.phase = Phase.RESTART
    out = step(s, RS, {"p1": RESTART, "p2": "wait"}, ScriptedChance([]))
    assert out.state.players["p1"].field == 3


def test_a_drop_during_the_round_keeps_the_bonus():
    s = draw(card_state(0, 10), "card_16").state
    p1 = s.players["p1"]
    p1.droplet_halves += 4
    p1.field = start_field(p1, RS)
    assert p1.field == 2 + 3
    assert p1.rat_tail == 3


def test_next_round_recalculates_and_drops_the_old_bonus():
    s = draw(card_state(0, 10), "card_16").state
    p1, p2 = s.players["p1"], s.players["p2"]
    # both stop at once, resolve, then the shop ends the round
    s.phase = Phase.SHOP
    for p in (p1, p2):
        p.final_field = 0
    p1.points = 10  # points earned in the round do not change this round's bonus
    assert p1.rat_tail == 3
    out = step(s, RS, {"p1": DONE, "p2": DONE}, ScriptedChance([]))
    n1, n2 = out.state.players["p1"], out.state.players["p2"]
    assert (n1.rat_tail, n2.rat_tail) == (0, 0)
    assert n1.field == 0
    assert out.state.phase is Phase.CARD
    again = draw(out.state, "card_13").state
    assert again.players["p1"].rat_tail == 0  # tied at 10


def test_drop_near_track_end_plus_bonus_stays_at_track_end():
    s = card_state(0, 40)
    s.players["p1"].droplet_halves = 2 * (RS.track_end - 1)
    out = draw(s, "card_16")
    assert out.state.players["p1"].rat_tail == calculate_rat_tails({"p1": 0, "p2": 40}, RS)["p1"]
    assert out.state.players["p1"].field == RS.track_end




