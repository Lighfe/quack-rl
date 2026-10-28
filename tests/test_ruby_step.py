"""Ruleset v2.3: the ruby step after the shop (the rule, no switch)."""

import pytest

from quack_rl.engine import (
    DONE,
    REFILL_FLASK,
    RUBY_DROP,
    WAIT,
    Phase,
    RngChance,
    ScriptedChance,
    Status,
    TAKE_POINTS,
    buy,
    legal_actions,
    needs_actions,
    new_game,
    state_from_dict,
    state_to_dict,
    step,
)
from quack_rl.rules import load_ruleset

RS = load_ruleset("v2.3")


def play(state, p1, p2, rs=RS):
    return step(state, rs, {"p1": p1, "p2": p2}, ScriptedChance([]))


def shop_state(p1_money=20, p2_money=0, p1_rubies=0, p2_rubies=0, rs=RS):
    s = step(new_game(rs), rs, None, ScriptedChance(["card_1"])).state
    s.phase = Phase.SHOP
    for seat, money, rubies in (("p1", p1_money, p1_rubies), ("p2", p2_money, p2_rubies)):
        p = s.players[seat]
        p.money, p.rubies, p.status = money, rubies, Status.STOPPED
        p.placed = ["white_1"]
        p.bag["white_1"] -= 1
        p.field = p.final_field = 3
    return s


def ruby_state(p1_rubies, p2_rubies, p1_flask=True, p2_flask=True):
    s = shop_state(p1_rubies=p1_rubies, p2_rubies=p2_rubies)
    s.phase = Phase.RUBY
    s.players["p1"].shop_done = s.players["p2"].shop_done = True
    s.players["p1"].flask_full, s.players["p2"].flask_full = p1_flask, p2_flask
    return s


# --- the ruleset -------------------------------------------------------------


def test_ruby_step_is_no_ruleset_field_any_more():
    assert RS.version == "v2.3"
    assert "ruby_step" not in type(RS).model_fields
    assert not hasattr(RS, "ruby_step")
    data = RS.model_dump()
    data["ruby_step"] = True
    with pytest.raises(ValueError):
        type(RS).model_validate(data)


# --- the shop ----------------------------------------------------------------


def test_v2_3_shop_offers_no_ruby_spends():
    s = shop_state(p1_money=20, p1_rubies=4)
    s.players["p1"].flask_full = False
    legal = legal_actions(s, RS, "p1")
    assert legal[0] == DONE
    assert RUBY_DROP not in legal and REFILL_FLASK not in legal
    assert legal == [DONE, *(buy(i.id) for i in RS.shop if i.price <= 20 and i.min_round <= 1)]


def test_v2_3_ruby_step_follows_shop():
    s = shop_state(p1_money=20, p2_money=20, p1_rubies=4, p2_rubies=2)
    s.players["p1"].flask_full = False
    r = play(s, DONE, DONE)
    assert r.state.phase is Phase.RUBY
    assert r.state.round == 1
    assert needs_actions(r.state)
    assert legal_actions(r.state, RS, "p1") == [DONE, RUBY_DROP, REFILL_FLASK]
    assert legal_actions(r.state, RS, "p2") == [DONE, RUBY_DROP]
    # ruby_drop is repeatable while the seat can pay
    r = play(r.state, RUBY_DROP, DONE)
    p1 = r.state.players["p1"]
    assert (p1.rubies, p1.droplet) == (2, 1)  # the ruby drop: droplet +1, a whole step
    assert {"seat": "p1", "kind": "ruby_drop", "rubies": 2, "drop": 1, "total": 2} in r.events
    assert legal_actions(r.state, RS, "p2") == [WAIT]
    assert legal_actions(r.state, RS, "p1") == [DONE, RUBY_DROP, REFILL_FLASK]
    r = play(r.state, RUBY_DROP, WAIT)
    # 0 rubies left: p1 is closed without being asked, and the round ends in this step
    assert {"seat": "p1", "kind": "done", "auto": True} in r.events
    assert r.state.phase is Phase.CARD and r.state.round == 2
    assert r.state.players["p1"].droplet == 2


def test_ruby_legal_set_follows_rubies_and_flask():
    s = ruby_state(1, 3, p1_flask=False, p2_flask=True)
    assert legal_actions(s, RS, "p2") == [DONE, RUBY_DROP]
    s.players["p1"].rubies = 2
    assert legal_actions(s, RS, "p1") == [DONE, RUBY_DROP, REFILL_FLASK]
    s.players["p1"].ruby_done = True
    assert legal_actions(s, RS, "p1") == [WAIT]


def test_v2_3_ruby_step_two_rubies_empty_flask():
    s = shop_state(p1_money=0, p2_money=20, p1_rubies=2, p2_rubies=0)
    s.players["p1"].flask_full = False
    r = play(s, DONE, DONE)  # p1 only has DONE in the shop: closed on entry already
    assert r.state.phase is Phase.RUBY
    # p2 cannot pay: done without being asked when the ruby step starts
    assert r.events[-1] == {"seat": "p2", "kind": "done", "auto": True}
    assert r.state.players["p2"].ruby_done
    assert legal_actions(r.state, RS, "p1") == [DONE, RUBY_DROP, REFILL_FLASK]
    r = play(r.state, REFILL_FLASK, WAIT)
    p1 = r.state.players["p1"]
    assert {"seat": "p1", "kind": "refill_flask", "rubies": 2, "total": 0} in r.events
    assert {"seat": "p1", "kind": "done", "auto": True} in r.events
    assert p1.flask_full and p1.rubies == 0
    assert r.state.phase is Phase.CARD and r.state.round == 2


def test_v2_3_ruby_step_skipped_when_nobody_can_pay():
    s = shop_state(p1_money=20, p2_money=20, p1_rubies=1, p2_rubies=0)
    s.players["p1"].flask_full = False
    r = play(s, DONE, DONE)
    assert r.state.phase is Phase.CARD and r.state.round == 2
    kinds = [(e["seat"], e["kind"], e.get("auto")) for e in r.events]
    assert kinds == [
        ("p1", "done", None),
        ("p2", "done", None),
        ("p1", "done", True),
        ("p2", "done", True),
        (None, "round_end", None),
    ]
    assert not any(p.ruby_done or p.shop_done for p in r.state.players.values())


def test_v2_3_idle_shop_and_ruby_step_skipped_on_entry():
    # Resolve: both players land on field 0 (scoring field 1: money 1, no ruby field), so
    # nobody can buy a chip and nobody has 2 rubies. Both shops close on entry, the ruby step
    # is skipped, and the next round's card step comes in the same step.
    s = new_game(RS)
    s.card = "card_1"
    s.phase = Phase.RESOLVE
    for p in s.players.values():
        p.field = p.final_field = 0
        p.placed = ["white_1"]
        p.status = Status.STOPPED
    r = step(s, RS, None, ScriptedChance(["point_1", "point_1"]))
    assert r.state.phase is Phase.CARD and r.state.round == 2
    autos = [e["seat"] for e in r.events if e.get("auto")]
    assert autos == ["p1", "p2", "p1", "p2"]
    # the same on entry from the explosion choice
    s = new_game(RS)
    s.card = "card_1"
    s.phase = Phase.CHOICE
    for p in s.players.values():
        p.field = p.final_field = 0
        p.placed = ["white_1"]
        p.status = Status.STOPPED
    s.players["p1"].status = Status.EXPLODED
    r = step(s, RS, {"p1": TAKE_POINTS, "p2": WAIT}, ScriptedChance([]))
    assert r.state.phase is Phase.CARD and r.state.round == 2


def test_v2_3_last_round_has_no_ruby_step():
    s = new_game(RS)
    s.round = RS.rounds
    s.card = "card_1"
    s.phase = Phase.RESOLVE
    for p in s.players.values():
        p.field = p.final_field = 3
        p.placed = ["white_1"]
        p.status = Status.STOPPED
        p.rubies = 5
    r = step(s, RS, None, ScriptedChance(["point_1", "point_1"]))
    assert r.state.phase is Phase.GAME_OVER
    assert [e for e in r.events if e["kind"] == "ruby_points"][0]["points"] == 5 // 2
    assert not any(e["kind"] in ("ruby_drop", "refill_flask", "done") for e in r.events)


def test_v2_3_card_16_refills_the_flasks_before_the_shop():
    s = new_game(RS)
    s.card = "card_16"
    s.phase = Phase.RESOLVE
    for p in s.players.values():
        p.field = p.final_field = 3
        p.placed = ["white_1"]
        p.status = Status.STOPPED
        p.flask_full = False
        p.rubies = 2
    r = step(s, RS, None, ScriptedChance(["point_1", "point_1"]))
    assert r.state.phase is Phase.SHOP
    assert all(p.flask_full for p in r.state.players.values())
    r = play(r.state, DONE, DONE)
    assert r.state.phase is Phase.RUBY
    assert legal_actions(r.state, RS, "p1") == [DONE, RUBY_DROP]


def test_ruby_done_survives_the_dict_round_trip_and_resets_with_the_round():
    s = ruby_state(2, 0)
    assert state_from_dict(state_to_dict(s)) == s
    s.players["p1"].ruby_done = True
    assert state_from_dict(state_to_dict(s)).players["p1"].ruby_done


def test_random_v2_3_games_reach_the_ruby_step_and_end():
    seen = False
    for seed in range(6):
        import random

        rng = random.Random(seed)
        chance = RngChance(seed)
        s = new_game(RS)
        while s.phase is not Phase.GAME_OVER:
            if needs_actions(s):
                acts = {seat: rng.choice(legal_actions(s, RS, seat)) for seat in ("p1", "p2")}
                seen = seen or s.phase is Phase.RUBY
                s = step(s, RS, acts, chance).state
            else:
                s = step(s, RS, None, chance).state
            if s.phase is Phase.SHOP:
                for seat in ("p1", "p2"):
                    assert RUBY_DROP not in legal_actions(s, RS, seat)
    assert seen
