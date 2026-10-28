"""Cards 8, 12, 14 and 19 of v2.3 (issue #186): the cards with a player decision at the card step."""

import pytest
from helpers import RS, auto  # noqa: F401

from quack_rl.engine import ScriptedChance, calculate_rat_tails, legal_actions, new_game, step
from quack_rl.engine.actions import (
    CARD_POINTS,
    CARD_REMOVE_WHITE,
    CARD_SWAP_NO,
    CARD_TAIL_POINTS,
    WAIT,
    action_names,
)
from quack_rl.engine.state import Phase


def start(card, p1_points=0, p2_points=0, **kw):
    """Draw `card` at the card step with the given points; return the step result."""
    s = new_game(RS)
    s.players["p1"].points = p1_points
    s.players["p2"].points = p2_points
    for seat, vals in kw.items():
        for k, v in vals.items():
            setattr(s.players[seat], k, v)
    return step(s, RS, None, ScriptedChance([card]))


def choose(out, p1, p2):
    return step(out.state, RS, {"p1": p1, "p2": p2}, ScriptedChance([]))


def entitlement(points):
    return calculate_rat_tails(points, RS)


# --- card 8 ---------------------------------------------------------------------


def test_card_8_entitlement_zero_is_not_asked():
    out = start("card_8")  # tie: both entitlements 0
    assert out.state.phase is Phase.BREW  # nobody has a decision: no choice step
    assert out.state.players["p1"].rat_tail == 0


def test_card_8_only_the_trailing_player_is_asked_up_to_the_entitlement():
    out = start("card_8", 0, 3)  # p1 trails by tails_between(0, 3)
    e = entitlement({"p1": 0, "p2": 3})["p1"]
    assert 0 < e < 3
    assert out.state.phase is Phase.CARD_CHOICE
    assert legal_actions(out.state, RS, "p1") == [f"card_tails:{n}" for n in range(e + 1)]
    assert legal_actions(out.state, RS, "p2") == [WAIT]


def test_card_8_entitlement_two_offers_up_to_two():
    out = start("card_8", 0, 5)
    assert entitlement({"p1": 0, "p2": 5})["p1"] == 2
    assert legal_actions(out.state, RS, "p1") == ["card_tails:0", "card_tails:1", "card_tails:2"]
    done = choose(out, "card_tails:2", WAIT)
    assert done.state.players["p1"].rat_tail == 0
    assert done.state.players["p1"].rubies == RS.start_rubies + 2


def test_card_8_gives_up_three_of_five_and_keeps_two():
    out = start("card_8", 0, 13)
    assert entitlement({"p1": 0, "p2": 13})["p1"] == 5
    assert legal_actions(out.state, RS, "p1") == ["card_tails:0", "card_tails:1", "card_tails:2", "card_tails:3"]
    done = choose(out, "card_tails:3", WAIT)
    p1 = done.state.players["p1"]
    assert p1.rat_tail_adjust == 3
    assert p1.rat_tail == 2
    assert p1.rubies == RS.start_rubies + 3
    assert done.state.phase is Phase.BREW


def test_card_8_decline_changes_nothing():
    out = start("card_8", 0, 13)
    done = choose(out, "card_tails:0", WAIT)
    p1 = done.state.players["p1"]
    assert p1.rat_tail_adjust == 0 and p1.rubies == RS.start_rubies
    assert p1.rat_tail == 5


def test_card_8_more_than_the_entitlement_is_illegal():
    from quack_rl.engine import IllegalAction

    out = start("card_8", 0, 3)
    e = entitlement({"p1": 0, "p2": 3})["p1"]
    with pytest.raises(IllegalAction):
        choose(out, f"card_tails:{e + 1}", WAIT)


# --- card 12 --------------------------------------------------------------------


def test_card_12_without_rubies_nobody_is_asked():
    out = start("card_12", p1={"rubies": 0}, p2={"rubies": 0})
    assert out.state.phase is Phase.BREW


def test_card_12_swaps_a_ruby_for_a_white_one():
    out = start("card_12", p2={"rubies": 0})
    assert out.state.phase is Phase.CARD_CHOICE
    legal = legal_actions(out.state, RS, "p1")
    assert legal[-1] == CARD_SWAP_NO
    colours = [RS.chip(a.removeprefix("card_swap:")).colour for a in legal[:-1]]
    assert colours == ["green", "blue", "red", "yellow", "orange", "white"]
    assert all(RS.chip(a.removeprefix("card_swap:")).value == 1 for a in legal[:-1])
    assert legal_actions(out.state, RS, "p2") == [WAIT]
    before = out.state.players["p1"].bag.get("white_1", 0)
    done = choose(out, "card_swap:white_1", WAIT)
    p1 = done.state.players["p1"]
    assert p1.rubies == RS.start_rubies - 1
    assert p1.bag["white_1"] == before + 1


def test_card_12_decline():
    out = start("card_12")
    done = choose(out, CARD_SWAP_NO, CARD_SWAP_NO)
    assert [done.state.players[s].rubies for s in ("p1", "p2")] == [RS.start_rubies] * 2
    assert done.state.players["p1"].bag == new_game(RS).players["p1"].bag


# --- card 14 --------------------------------------------------------------------


def test_card_14_points_or_remove_a_white():
    out = start("card_14")
    assert out.state.phase is Phase.CARD_CHOICE
    assert legal_actions(out.state, RS, "p1") == [CARD_POINTS, CARD_REMOVE_WHITE]
    whites = out.state.players["p2"].bag["white_1"]
    done = choose(out, CARD_POINTS, CARD_REMOVE_WHITE)
    assert done.state.players["p1"].points == 4
    assert done.state.players["p2"].points == 0
    assert done.state.players["p2"].bag["white_1"] == whites - 1
    assert done.state.players["p1"].bag["white_1"] == whites


def test_card_14_points_count_for_the_bonus_of_the_same_round():
    out = start("card_14", 0, 6)  # p1 takes 4 points: the lead is smaller
    done = choose(out, CARD_POINTS, CARD_POINTS)
    assert done.state.players["p1"].points == 4 and done.state.players["p2"].points == 10
    assert done.state.players["p1"].rat_tail == entitlement({"p1": 4, "p2": 10})["p1"]


def test_card_14_without_a_white_one_gets_the_points_unasked():
    out = start("card_14", p1={"bag": {"green_1": 3}})
    assert out.state.phase is Phase.CARD_CHOICE  # p2 still has a choice
    assert legal_actions(out.state, RS, "p1") == [WAIT]
    done = choose(out, WAIT, CARD_REMOVE_WHITE)
    assert done.state.players["p1"].points == 4


def test_card_14_nobody_has_a_white_one_no_step_and_both_get_the_points():
    out = start("card_14", p1={"bag": {"green_1": 3}}, p2={"bag": {"green_1": 3}})
    assert out.state.phase is Phase.BREW
    assert [out.state.players[s].points for s in ("p1", "p2")] == [4, 4]


# --- card 19 --------------------------------------------------------------------


def test_card_19_entitlement_zero_only_the_value_four_chips():
    out = start("card_19")
    legal = legal_actions(out.state, RS, "p1")
    assert CARD_TAIL_POINTS not in legal
    assert [RS.chip(a.removeprefix("card_chip4:")).colour for a in legal] == ["green", "blue", "red", "yellow"]
    assert all(RS.chip(a.removeprefix("card_chip4:")).value == 4 for a in legal)
    done = choose(out, legal[1], legal[0])
    assert done.state.players["p1"].bag[legal[1].removeprefix("card_chip4:")] == 1


def test_card_19_entitlement_five_gives_five_points_and_the_bonus_uses_them():
    out = start("card_19", 0, 13)
    assert entitlement({"p1": 0, "p2": 13})["p1"] == 5
    assert CARD_TAIL_POINTS in legal_actions(out.state, RS, "p1")
    assert CARD_TAIL_POINTS not in legal_actions(out.state, RS, "p2")
    done = choose(out, CARD_TAIL_POINTS, "card_chip4:green_4")
    assert done.state.players["p1"].points == 5
    # the bonus is calculated on the new points: 5 vs 13
    assert done.state.players["p1"].rat_tail == entitlement({"p1": 5, "p2": 13})["p1"] == 3


def test_card_19_two_passes_the_entitlements_are_read_before_any_reward_is_paid(monkeypatch):
    from quack_rl.engine import cards
    from quack_rl.engine.cards import _apply_late_choice

    s = new_game(RS)
    s.card = "card_19"
    s.phase = Phase.CARD_CHOICE
    s.players["p2"].points = 13
    seen = []
    real = cards.calculate_rat_tails

    def spy(points, rs):
        seen.append(dict(points))
        return real(points, rs)

    monkeypatch.setattr(cards, "calculate_rat_tails", spy)
    # both choose (B) (the engine takes the choices as given): p1 gets its entitlement of 5, and
    # p2 gets 0 (its entitlement before the rewards)
    _apply_late_choice(s, RS, {"p1": CARD_TAIL_POINTS, "p2": CARD_TAIL_POINTS}, [])
    # the entitlements are read once, from the points before any reward is paid
    assert seen == [{"p1": 0, "p2": 13}]
    assert s.players["p1"].points == 5
    assert s.players["p2"].points == 13
    assert s.phase is Phase.BREW
    # the standard bonus step ran once, on the new points
    assert s.players["p1"].rat_tail == 3


# --- the action list -------------------------------------------------------------


def test_the_new_actions_are_appended_at_the_end_of_the_list():
    names = action_names(RS)
    assert len(names) == len(set(names))
    tail = names[names.index("refill_flask") + 1 :]
    assert tail[:4] == ["card_tails:0", "card_tails:1", "card_tails:2", "card_tails:3"]
    assert "card_swap_no" in tail and "card_points" in tail and "card_tail_points" in tail
    assert names.index("card_rubies") < names.index("ruby_drop")


def test_the_mask_equals_legal_actions_at_every_step_of_random_games():
    import random

    from quack_rl.engine import RngChance

    names = action_names(RS)
    for seed in range(12):
        rng = random.Random(seed)
        chance = RngChance(seed)
        s = new_game(RS)
        for _ in range(4000):
            if s.phase is Phase.GAME_OVER:
                break
            from quack_rl.engine.game import needs_actions

            if needs_actions(s):
                legal = {seat: legal_actions(s, RS, seat) for seat in ("p1", "p2")}
                for seat in legal:
                    assert set(legal[seat]) <= set(names)
                acts = {seat: rng.choice(legal[seat]) for seat in legal}
                s = step(s, RS, acts, chance).state
            else:
                s = step(s, RS, None, chance).state
