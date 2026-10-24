"""The 20-card framework of v2.1 (issue #185): the deck, the round start order, the rat tail
function and the cards that need no new decision."""

import pytest
from helpers import RS, auto

from quack_rl.engine import (
    CARD_RUBIES,
    SEATS,
    Phase,
    ScriptedChance,
    Status,
    calculate_rat_tails,
    new_game,
    step,
)
from quack_rl.engine.board import set_rat_tails, tails_between
from quack_rl.engine.cards import apply_card
from quack_rl.engine.chance import ChanceLog
from quack_rl.rules import Ruleset, with_rounds

DECK = ["card_1", "card_2", "card_3", "card_4", "card_5", "card_6", "card_7", "card_8", "card_9",
        "card_12", "card_13", "card_14", "card_15", "card_16", "card_18", "card_19"]  # fmt: skip


def draw(card, *rolls, state=None, rs=RS):
    s = state if state is not None else new_game(rs)
    return step(s, rs, None, ScriptedChance([card, *rolls]))


def resolve_state(p1_field=8, p2_field=3, exploded=()):
    s = new_game(RS)
    s.phase = Phase.RESOLVE
    for seat, fld in (("p1", p1_field), ("p2", p2_field)):
        p = s.players[seat]
        p.field = p.final_field = fld
        p.placed = ["white_1"]
        p.status = Status.EXPLODED if seat in exploded else Status.STOPPED
    return s


# --- the deck ---------------------------------------------------------------


def test_the_deck_has_the_16_cards_one_of_each():
    assert [c.id for c in RS.cards] == DECK
    assert all(c.count == 1 for c in RS.cards)
    assert sorted(new_game(RS).deck) == sorted(DECK)
    assert len(RS.cards) == 16 and RS.rounds <= 16


def test_a_ruleset_with_fewer_cards_than_rounds_is_refused():
    data = RS.model_dump()
    data["cards"] = data["cards"][:8]
    with pytest.raises(ValueError, match="fewer than the 9 rounds"):
        Ruleset.model_validate(data)


def test_with_rounds_refuses_more_rounds_than_cards():
    with pytest.raises(ValueError, match="fewer than"):
        with_rounds(RS, 17)
    assert with_rounds(RS, 16).rounds == 16


# --- the rat tail function ----------------------------------------------------


@pytest.mark.parametrize(
    ("low", "high"), [(0, 2), (1, 10), (8, 1), (15, 16), (48, 51), (50, 55), (0, 100), (3, 99)]
)
def test_calculate_rat_tails_counts_the_tails_up_to_the_leader(low, high):
    lo, hi = min(low, high), max(low, high)
    got = calculate_rat_tails({"a": low, "b": high}, RS)
    expected = tails_between(lo, hi, RS)
    assert got == ({"a": expected, "b": 0} if low < high else {"a": 0, "b": expected} if low > high else {"a": 0, "b": 0})


def test_calculate_rat_tails_is_not_capped():
    got = calculate_rat_tails({"a": 0, "b": 100}, RS)
    assert got["a"] >= 10 and got["b"] == 0
    assert got["a"] == tails_between(0, 100, RS)


def test_the_adjustment_lowers_the_bonus_and_never_below_zero():
    s = new_game(RS)
    s.players["p2"].points = 10  # p1 is 3 tails behind
    s.players["p1"].rat_tail_adjust = 1
    set_rat_tails(s, RS, [])
    assert s.players["p1"].rat_tail == 2 and s.players["p1"].field == 2
    s.players["p1"].rat_tail_adjust = 5
    set_rat_tails(s, RS, [])
    assert s.players["p1"].rat_tail == 0 and s.players["p2"].rat_tail == 0


def test_the_adjustment_is_reset_at_the_round_end():
    s = new_game(RS)
    s.players["p1"].rat_tail_adjust = 2
    s.phase = Phase.SHOP
    s.players["p2"].shop_done = True
    out = step(s, RS, {"p1": "done", "p2": "wait"}, ScriptedChance([]))
    assert out.state.players["p1"].rat_tail_adjust == 0


# --- the round start order --------------------------------------------------


def test_round_start_order_chips_then_card_then_rat_tails():
    s = new_game(RS)
    s.round = 6
    s.players["p2"].points = 10
    out = draw("card_13", state=s)
    kinds = [e["kind"] for e in out.events]
    assert kinds.index("round_chip") < kinds.index("card_draw") < kinds.index("ruby")
    assert kinds.index("ruby") < kinds.index("rat_tail")
    assert kinds[-1] == "rat_tail"


def test_the_rat_tails_are_calculated_on_the_points_after_the_card():
    # card 18: p1 rolls +2 points (and p2 nothing) before the bonus is calculated, once
    s = new_game(RS)
    s.players["p1"].points = 8
    s.players["p2"].points = 10
    out = draw("card_18", "point_2", "droplet_1", state=s)
    assert out.state.players["p1"].points == 10
    assert out.state.players["p1"].rat_tail == 0


# --- the new cards ------------------------------------------------------------


def test_card_5_option_c_gives_three_rubies():
    s = draw("card_5").state
    assert s.phase is Phase.CARD_CHOICE
    out = step(s, RS, {"p1": CARD_RUBIES, "p2": "card_black"}, ScriptedChance([]))
    assert out.state.players["p1"].rubies == RS.start_rubies + 3
    assert out.state.players["p2"].rubies == RS.start_rubies
    assert out.state.phase is Phase.BREW


def test_card_5_offers_the_rubies_and_not_the_old_drop():
    s = draw("card_5").state
    from quack_rl.engine import legal_actions

    legal = legal_actions(s, RS, "p1")
    assert legal[-1] == CARD_RUBIES and "card_drop_end" not in legal


def test_card_9_rolls_the_die_twice_for_each_roller():
    base = auto(resolve_state(), "point_1")
    s = resolve_state()
    s.card = "card_9"
    out = auto(s, "point_1", "point_2")
    p1 = out.state.players["p1"]
    assert p1.points == base.state.players["p1"].points + 2
    assert [c["value"] for c in out.chance if c["seat"] == "p1"] == ["point_1", "point_2"]
    assert [e["face"] for e in out.events if e["kind"] == "die"] == ["point_1", "point_2"]
    assert out.state.players["p2"].points == base.state.players["p2"].points  # p2 does not roll


def test_card_9_does_not_change_who_rolls():
    s = resolve_state(exploded=("p1",))
    s.card = "card_9"
    out = auto(s, "point_1", "point_1")
    assert [c["seat"] for c in out.chance] == ["p2", "p2"]


def test_card_13_gives_the_fewest_rubies_one_ruby():
    s = new_game(RS)
    s.players["p1"].rubies = 0
    s.players["p2"].rubies = 2
    out = draw("card_13", state=s)
    assert (out.state.players["p1"].rubies, out.state.players["p2"].rubies) == (1, 2)
    assert {"seat": "p1", "kind": "ruby", "rubies": 1, "total": 1} in out.events


def test_card_13_a_tie_gives_every_tied_player_a_ruby():
    out = draw("card_13")
    assert [out.state.players[s].rubies for s in SEATS] == [RS.start_rubies + 1] * 2


def test_card_15_gives_two_points_on_a_ruby_field():
    base = auto(resolve_state(8, 3), "point_1")
    s = resolve_state(8, 3)
    s.card = "card_15"
    out = auto(s, "point_1")
    assert RS.fields[8 + 1].ruby
    assert out.state.players["p1"].points == base.state.players["p1"].points + 2
    assert out.state.players["p1"].rubies == base.state.players["p1"].rubies
    assert out.state.players["p2"].points == base.state.players["p2"].points


def test_card_15_also_after_an_explosion():
    s = resolve_state(8, 3, exploded=("p1",))
    s.card = "card_15"
    out = auto(s, "point_1")
    assert out.state.players["p1"].points == 2
    assert out.state.players["p1"].rubies == RS.start_rubies + 1


def test_card_16_refills_all_flasks_at_the_end_of_the_round():
    s = resolve_state()
    s.card = "card_16"
    for p in s.players.values():
        p.flask_full = False
    out = auto(s, "point_1")
    assert all(p.flask_full for p in out.state.players.values())
    other = resolve_state()
    other.card = "card_1"
    for p in other.players.values():
        p.flask_full = False
    assert not any(p.flask_full for p in auto(other, "point_1").state.players.values())


def test_card_18_every_player_rolls_once_at_the_card_step():
    out = draw("card_18", "point_1", "point_2")
    assert [c["seat"] for c in out.chance] == ["table", "p1", "p2"]
    assert [c["kind"] for c in out.chance] == ["card", "die", "die"]
    assert [out.state.players[s].points for s in SEATS] == [1, 2]
    assert out.state.phase is Phase.BREW


def test_the_card_step_uses_apply_card_directly():
    s = new_game(RS)
    events = []
    apply_card(s, RS, ChanceLog(ScriptedChance(["card_16"]), RS), events)
    assert s.card == "card_16" and "card_16" not in s.deck
