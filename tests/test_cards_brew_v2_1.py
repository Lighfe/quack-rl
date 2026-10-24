"""Cards 10 and 17 of v2.1 (issue #188): the cards that act in the brew."""

import random

import numpy as np
import pytest
from helpers import RS

from quack_rl.engine import (
    DRAW,
    STOP,
    USE_FLASK,
    WAIT,
    RngChance,
    ScriptedChance,
    legal_actions,
    needs_actions,
    new_game,
    step,
)
from quack_rl.engine.actions import DONE, USE_CARD_17, action_names
from quack_rl.engine.chance import IllegalChance
from quack_rl.engine.state import SEATS, Phase, Status
from quack_rl.rl import QuackEnv
from quack_rl.rules import Ruleset

PLAY0 = "play:0"


def go(state, p1, p2, *chance):
    return step(state, RS, {"p1": p1, "p2": p2}, ScriptedChance(chance))


def brew(card, bag1, bag2=None):
    """A new game after the card step of `card`, both bags set."""
    s = new_game(RS)
    s.players["p1"].bag = dict(bag1)
    s.players["p2"].bag = dict(bag2 if bag2 is not None else bag1)
    s = step(s, RS, None, ScriptedChance([card])).state
    assert s.phase is Phase.BREW
    return s


def to_card_10(bag1, first1, bag2, first2, drawn1, drawn2):
    """Both players draw one chip and stop; the 5 (or fewer) chips are drawn: the choice phase."""
    s = brew("card_10", bag1, bag2)
    s = go(s, DRAW, DRAW, first1, first2).state
    out = go(s, STOP, STOP, *drawn1, *drawn2)
    return out


# --- card 10 ----------------------------------------------------------------------

BAG_A = {"white_1": 4, "white_2": 2, "green_1": 2}
P2_DRAW = ["white_1", "white_1", "white_1", "white_2", "white_2"]  # from BAG_A after a white_1


def test_card_10_draws_5_for_each_stopped_player_and_offers_each_distinct_chip():
    drawn1 = ["green_1", "green_1", "white_1", "white_2", "white_2"]
    drawn2 = ["white_1", "white_2", "white_1", "green_1", "white_1"]
    out = to_card_10(BAG_A, "white_1", BAG_A, "white_1", drawn1, drawn2)
    s = out.state
    assert s.phase is Phase.CARD_CHOICE
    draws = [(c["seat"], c["value"]) for c in out.chance]
    assert draws == [("p1", v) for v in drawn1] + [("p2", v) for v in drawn2]
    assert s.players["p1"].card_draw == drawn1
    assert legal_actions(s, RS, "p1") == ["card_place:green_1", "card_place:white_1", "card_place:white_2"]
    assert legal_actions(s, RS, "p2") == ["card_place:white_1", "card_place:white_2", "card_place:green_1"]
    # the drawn chips stay in the bag until one is placed
    assert sum(s.players["p1"].bag.values()) == sum(BAG_A.values()) - 1


def test_card_10_green_chip_is_placed_as_a_normal_placement_and_the_rest_stays_in_the_bag():
    drawn = ["green_1", "green_1", "white_1", "white_2", "white_2"]
    drawn2 = ["white_1", "white_1", "white_2", "white_2", "white_1"]
    s = to_card_10(BAG_A, "white_1", BAG_A, "green_1", drawn, drawn2).state
    before = s.players["p1"].field
    out = go(s, "card_place:green_1", "card_place:white_2")
    p1, p2 = out.state.players["p1"], out.state.players["p2"]
    assert out.chance == []
    assert p1.placed == ["white_1", "green_1"] and p1.status is Status.STOPPED
    assert p1.field > before and p1.white_total == 1
    assert p1.bag == {"white_1": 3, "white_2": 2, "green_1": 1}
    assert p1.card_draw == [] and p2.card_draw == []
    # p2's first chip was green: the white chip placed by card 10 is its first white chip
    assert p2.placed == ["green_1", "white_2"] and p2.first_white_placed
    assert out.state.phase is Phase.RESOLVE
    assert (p1.final_field, p2.final_field) == (p1.field, p2.field)
    kinds = [e["kind"] for e in out.events]
    assert kinds.count("card_place") == 2 and kinds.count("place") == 2


def test_card_10_blue_chip_draws_its_hand_from_a_bag_that_holds_the_four_returned_chips():
    bag = {"white_1": 1, "blue_2": 1, "green_1": 1, "white_2": 2, "white_3": 1}
    drawn = ["blue_2", "green_1", "white_2", "white_2", "white_3"]
    s = to_card_10(bag, "white_1", BAG_A, "white_1", drawn, P2_DRAW).state
    assert s.players["p1"].bag == {"blue_2": 1, "green_1": 1, "white_2": 2, "white_3": 1}
    # the chosen blue chip is out of the bag: it cannot be drawn into the hand
    with pytest.raises(IllegalChance):
        go(s, "card_place:blue_2", "card_place:white_1", "blue_2", "green_1")
    out = go(s, "card_place:blue_2", "card_place:white_1", "white_3", "green_1")
    p1 = out.state.players["p1"]
    assert [c["value"] for c in out.chance] == ["white_3", "green_1"]
    assert p1.hand == ["white_3", "green_1"] and p1.status is Status.BREWING
    assert p1.bag == {"white_2": 2}
    assert out.state.phase is Phase.BREW
    assert legal_actions(out.state, RS, "p1") == ["play:0", "play:1", "put_back_draw", "put_back_stop"]
    assert legal_actions(out.state, RS, "p2") == [WAIT]
    # the player picks as usual and may then stop; the step is not offered again
    done = go(out.state, "play:1", WAIT)
    assert done.state.players["p1"].placed == ["white_1", "blue_2", "green_1"]
    assert done.state.phase is Phase.BREW
    end = go(done.state, STOP, WAIT)
    assert end.state.phase is Phase.RESOLVE and end.chance == []
    assert end.state.players["p1"].final_field == end.state.players["p1"].field


def test_card_10_a_chip_that_makes_the_player_explode():
    bag = {"white_3": 3, "white_2": 3, "white_1": 2}
    s = brew("card_10", bag, BAG_A)
    s = go(s, DRAW, DRAW, "white_3", "white_1").state
    s = go(s, DRAW, STOP, "white_3").state
    assert s.players["p1"].white_total == 6 and s.players["p1"].status is Status.BREWING
    out = go(s, STOP, WAIT, "white_3", "white_2", "white_2", "white_1", "white_1", *P2_DRAW)
    assert out.state.phase is Phase.CARD_CHOICE
    out = go(out.state, "card_place:white_2", "card_place:white_1")
    p1 = out.state.players["p1"]
    assert p1.status is Status.EXPLODED and p1.white_total == 8
    assert out.state.phase is Phase.RESOLVE and p1.final_field == p1.field
    assert any(e["kind"] == "explode" for e in out.events)
    # an explosion by card 10 has the usual consequences: the CHOICE phase follows Resolve
    nxt = step(out.state, RS, None, ScriptedChance(["droplet_1"] * 2))  # the die of p2
    assert nxt.state.phase is Phase.CHOICE
    assert legal_actions(nxt.state, RS, "p1") == ["take_money", "take_points"]


def test_card_10_with_fewer_than_5_chips_draws_all_that_are_left():
    bag = {"white_1": 3, "green_1": 1}
    out = to_card_10(bag, "white_1", BAG_A, "white_1", ["white_1", "white_1", "green_1"], P2_DRAW)
    assert [c["seat"] for c in out.chance] == ["p1"] * 3 + ["p2"] * 5
    s = out.state
    assert legal_actions(s, RS, "p1") == ["card_place:white_1", "card_place:green_1"]
    done = go(s, "card_place:green_1", "card_place:white_1")
    assert done.state.players["p1"].bag == {"white_1": 2}
    assert done.state.phase is Phase.RESOLVE


def test_card_10_empty_bag_skips_the_step_for_that_player():
    s = brew("card_10", {"white_1": 1}, BAG_A)
    s = go(s, DRAW, DRAW, "white_1", "white_1").state
    assert s.players["p1"].status is Status.STOPPED  # the bag is empty: stopped by itself
    out = go(s, WAIT, STOP, *P2_DRAW)
    assert [c["seat"] for c in out.chance] == ["p2"] * 5  # nothing is drawn for p1
    assert legal_actions(out.state, RS, "p1") == [WAIT]
    assert out.state.players["p1"].card_draw == []
    done = go(out.state, WAIT, "card_place:white_1")
    assert done.state.phase is Phase.RESOLVE and done.state.players["p1"].placed == ["white_1"]


def test_card_10_nobody_with_a_chip_left_goes_straight_to_resolve():
    s = brew("card_10", {"white_1": 1})
    out = go(s, DRAW, DRAW, "white_1", "white_1")
    assert out.state.phase is Phase.RESOLVE and len(out.chance) == 2  # the two brew draws only


def test_card_10_an_exploded_player_is_not_affected():
    bag = {"white_3": 3, "white_1": 3}
    s = brew("card_10", bag, BAG_A)
    s = go(s, DRAW, DRAW, "white_3", "white_1").state
    s = go(s, DRAW, STOP, "white_3").state
    s = go(s, DRAW, WAIT, "white_3", *P2_DRAW).state  # 3 + 3 + 3 = 9 > 7; then p2 draws 5
    p1 = s.players["p1"]
    assert p1.status is Status.EXPLODED
    assert s.phase is Phase.CARD_CHOICE
    assert p1.card_draw == [] and legal_actions(s, RS, "p1") == [WAIT]
    assert len(s.players["p2"].card_draw) == 5
    bag_before = dict(p1.bag)
    done = go(s, WAIT, "card_place:white_1")
    assert done.state.players["p1"].bag == bag_before and done.state.phase is Phase.RESOLVE


def test_card_10_is_not_played_with_another_card():
    s = brew("card_16", BAG_A)
    s = go(s, DRAW, DRAW, "white_1", "white_1").state
    out = go(s, STOP, STOP)
    assert out.state.phase is Phase.RESOLVE and out.chance == []


# --- card 17 ----------------------------------------------------------------------


def test_card_17_first_white_chip_goes_back_with_the_flask_untouched():
    s = brew("card_17", BAG_A)
    for p in s.players.values():
        p.flask_full = False
    start = s.players["p1"].field
    s = go(s, DRAW, DRAW, "white_2", "white_1").state
    assert legal_actions(s, RS, "p1") == [DRAW, STOP, USE_CARD_17]
    r = go(s, USE_CARD_17, DRAW, "white_1")
    p = r.state.players["p1"]
    assert (p.field, p.white_total, p.placed, p.placed_fields) == (start, 0, [], [])
    assert p.bag == BAG_A and p.status is Status.BREWING and p.flask_full is False
    ev = next(e for e in r.events if e["kind"] == "use_card_17")
    assert ev == {"seat": "p1", "kind": "use_card_17", "chip": "white_2", "field": start, "white_total": 0}
    assert not any(e["kind"] == "use_flask" for e in r.events)
    # offered once: the chip is back, so the next white chip is not the first one
    assert not p.first_white_open and p.first_white_placed


def test_card_17_is_gone_after_the_player_draws_on():
    s = brew("card_17", BAG_A)
    s = go(s, DRAW, DRAW, "white_1", "white_1").state
    assert USE_CARD_17 in legal_actions(s, RS, "p1")
    s = go(s, DRAW, DRAW, "white_1", "white_1").state  # the second white chip
    assert legal_actions(s, RS, "p1") == [DRAW, STOP, USE_FLASK]


def test_card_17_after_use_a_later_white_chip_does_not_offer_it_again():
    s = brew("card_17", BAG_A)
    for p in s.players.values():
        p.flask_full = False
    s = go(s, DRAW, DRAW, "white_1", "white_1").state
    s = go(s, USE_CARD_17, STOP).state
    s = go(s, DRAW, WAIT, "white_1").state
    assert legal_actions(s, RS, "p1") == [DRAW, STOP]


def test_card_17_a_green_chip_placed_first_does_not_use_it_up():
    s = brew("card_17", BAG_A)
    for p in s.players.values():
        p.flask_full = False
    s = go(s, DRAW, DRAW, "green_1", "green_1").state
    assert legal_actions(s, RS, "p1") == [DRAW, STOP]  # green is not white
    s = go(s, DRAW, DRAW, "white_2", "white_1").state
    assert legal_actions(s, RS, "p1") == [DRAW, STOP, USE_CARD_17]
    r = go(s, USE_CARD_17, STOP)
    p = r.state.players["p1"]
    assert p.placed == ["green_1"] and p.white_total == 0
    assert p.field == p.placed_fields[-1]  # back to the landing field of the green chip


def test_card_17_both_offered_with_a_full_flask_and_the_flask_stays_full():
    s = brew("card_17", BAG_A)
    s = go(s, DRAW, DRAW, "white_2", "white_1").state
    assert s.players["p1"].flask_full
    assert legal_actions(s, RS, "p1") == [DRAW, STOP, USE_FLASK, USE_CARD_17]
    r = go(s, USE_CARD_17, USE_FLASK)
    assert r.state.players["p1"].flask_full and r.state.players["p1"].placed == []
    assert r.state.players["p2"].flask_full is False  # p2 used the flask: its card 17 is not touched
    assert r.state.players["p2"].placed == []


def test_card_17_is_not_offered_after_an_explosion_or_without_the_card():
    s = brew("card_17", BAG_A)
    s = go(s, DRAW, DRAW, "white_2", "white_1").state
    s.players["p1"].status = Status.EXPLODED
    assert legal_actions(s, RS, "p1") == [WAIT]
    s = brew("card_16", BAG_A)
    s = go(s, DRAW, DRAW, "white_2", "white_1").state
    assert USE_CARD_17 not in legal_actions(s, RS, "p1")


def test_card_17_first_white_chip_placed_by_card_10_sets_the_flag():
    s = brew("card_10", BAG_A)
    s = go(s, DRAW, DRAW, "green_1", "green_1").state
    drawn = ["white_1", "white_1", "white_2", "white_1", "green_1"]
    s = go(s, STOP, STOP, *drawn, *drawn).state
    assert not s.players["p1"].first_white_placed
    s = go(s, "card_place:white_2", "card_place:green_1").state
    assert s.players["p1"].first_white_placed and not s.players["p2"].first_white_placed


def test_the_card_17_flags_are_reset_every_round():
    s = brew("card_17", BAG_A)
    s = go(s, DRAW, DRAW, "white_1", "white_1").state
    s = go(s, STOP, STOP).state  # Resolve follows; the reset is checked from the shop
    for p in s.players.values():
        assert p.first_white_placed
        p.card_place_done = True
    s.phase = Phase.SHOP
    out = go(s, DONE, DONE)
    for p in out.state.players.values():
        assert not (p.first_white_placed or p.first_white_open or p.card_place_done)


# --- the actions and the mask -------------------------------------------------------


def test_the_new_actions_are_at_the_end_of_the_list():
    names = action_names(RS)
    assert names[-len(RS.chips) - 1 :] == [*(f"card_place:{c.id}" for c in RS.chips), USE_CARD_17]
    assert len(names) == len(set(names))


def _only(*cards):
    data = RS.model_dump()
    data["cards"] = [
        {"id": c, "effect": RS.card(c).effect, "count": 5} for c in cards
    ]
    return Ruleset.model_validate(data)


def test_the_mask_equals_legal_actions_in_games_with_only_cards_10_and_17():
    rs = _only("card_10", "card_17")
    names = action_names(rs)
    seen = set()
    for seat in ("p1", "p2"):
        env = QuackEnv(seat=seat, rules=rs)
        for seed in range(6):
            obs, info = env.reset(seed=seed)
            rng = np.random.default_rng(seed)
            done = False
            while not done:
                legal = set(legal_actions(env.state, env.rs, env.agent_seat))
                assert {names[i] for i in np.flatnonzero(info["action_mask"])} == legal
                seen |= legal
                _, _, done, _, info = env.step(int(rng.choice(np.flatnonzero(info["action_mask"]))))
    assert USE_CARD_17 in seen and any(a.startswith("card_place:") for a in seen)


def test_random_games_with_cards_10_and_17_keep_the_bags_consistent():
    rs = _only("card_10", "card_17")
    for seed in range(4):
        rng, chance = random.Random(seed), RngChance(seed)
        s = new_game(rs)
        for _ in range(4000):
            if s.phase is Phase.GAME_OVER:
                break
            acts = None
            if needs_actions(s):
                acts = {seat: rng.choice(legal_actions(s, rs, seat)) for seat in SEATS}
            s = step(s, rs, acts, chance).state
            for seat in SEATS:
                p = s.players[seat]
                assert all(n > 0 for n in p.bag.values())
                assert not p.card_draw or s.phase is Phase.CARD_CHOICE
        assert s.phase is Phase.GAME_OVER
