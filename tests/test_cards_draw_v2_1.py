"""Cards 11 and 20 of v2.1 (issue #187): the cards that draw chips from the bag at the card step."""

import io
import random
from collections import Counter

import pytest
from helpers import RS

from rich.console import Console

from quack_rl.cli.human import HumanSeat, key_map
from quack_rl.engine import RngChance, ScriptedChance, legal_actions, needs_actions, new_game, step
from quack_rl.engine.actions import WAIT, action_names
from quack_rl.engine.chance import IllegalChance
from quack_rl.engine.state import SEATS, Phase
from quack_rl.rl.encode import observe, vectorize


def start(card, bags=None, chance=()):
    s = new_game(RS)
    for seat, bag in (bags or {}).items():
        s.players[seat].bag = dict(bag)
    return step(s, RS, None, ScriptedChance([card, *chance]))


def choose(out, p1, p2):
    return step(out.state, RS, {"p1": p1, "p2": p2}, ScriptedChance([]))


# --- card 11 ----------------------------------------------------------------------


def test_card_11_draws_p1_then_p2_as_eight_draw_chip_events():
    d1 = ["white_1", "white_2", "yellow_2", "green_1"]
    d2 = ["white_1", "white_1", "white_2", "white_3"]
    bag = {"white_1": 4, "white_2": 2, "white_3": 1, "yellow_2": 1, "green_1": 1}
    out = start("card_11", {"p1": bag, "p2": bag}, d1 + d2)
    kinds = [(c["seat"], c["kind"], c.get("value")) for c in out.chance]
    assert kinds[0] == ("table", "card", "card_11")
    draws = [c for c in out.chance if c["kind"] == "draw_chip"]
    assert [c["seat"] for c in draws] == ["p1"] * 4 + ["p2"] * 4
    assert [c["value"] for c in draws] == d1 + d2


def test_card_11_choose_yellow_2_gives_yellow_4():
    bag = {"white_1": 4, "white_2": 1, "yellow_2": 1, "green_1": 1, "white_3": 1}
    out = start("card_11", {"p1": bag}, ["white_1", "white_2", "yellow_2", "green_1"] + ["white_1"] * 4)
    assert out.state.phase is Phase.CARD_CHOICE
    assert legal_actions(out.state, RS, "p1") == ["card_upgrade:yellow_2", "card_upgrade:green_1"]
    assert legal_actions(out.state, RS, "p2") == [WAIT]
    done = choose(out, "card_upgrade:yellow_2", WAIT)
    p1, p2 = done.state.players["p1"], done.state.players["p2"]
    assert p1.bag == {"white_1": 4, "white_2": 1, "yellow_4": 1, "green_1": 1, "white_3": 1}
    assert sum(p1.bag.values()) == sum(bag.values())
    assert done.state.phase is Phase.BREW
    assert p1.card_draw == [] and p2.card_draw == []
    # p2 had nothing to upgrade: it took a green 1
    assert p2.bag["green_1"] == RS.start_bag.get("green_1", 0) + 1


def test_card_11_choose_green_1_gives_green_2():
    bag = {"white_1": 4, "white_2": 1, "yellow_2": 1, "green_1": 1, "white_3": 1}
    out = start("card_11", {"p1": bag}, ["white_1", "white_2", "yellow_2", "green_1"] + ["white_1"] * 4)
    done = choose(out, "card_upgrade:green_1", WAIT)
    p1 = done.state.players["p1"]
    assert p1.bag["green_2"] == 1 and "green_1" not in p1.bag
    assert p1.bag["yellow_2"] == 1


def test_card_11_nothing_to_upgrade_gives_green_1_and_only_the_waiting_action():
    bag = {"white_2": 1, "black_1": 1, "purple_1": 1, "orange_1": 1, "white_1": 3}
    out = start(
        "card_11",
        {"p1": bag, "p2": bag},
        ["white_2", "black_1", "purple_1", "orange_1"] * 2,
    )
    # nobody can upgrade: no question, the card step is done and the brew starts
    assert out.state.phase is Phase.BREW
    for seat in SEATS:
        p = out.state.players[seat]
        assert p.bag["green_1"] == 1
        assert sum(p.bag.values()) == sum(bag.values()) + 1


def test_card_11_only_the_waiting_action_when_the_other_seat_chooses():
    bag = {"white_2": 1, "black_1": 1, "purple_1": 1, "orange_1": 1, "white_1": 3}
    good = {"white_1": 4, "white_2": 1, "yellow_2": 1, "green_1": 1}
    out = start(
        "card_11",
        {"p1": good, "p2": bag},
        ["white_1", "white_2", "yellow_2", "green_1", "white_2", "black_1", "purple_1", "orange_1"],
    )
    assert out.state.phase is Phase.CARD_CHOICE
    assert legal_actions(out.state, RS, "p2") == [WAIT]
    done = choose(out, "card_upgrade:green_1", WAIT)
    assert done.state.players["p2"].bag["green_1"] == 1
    assert done.state.players["p1"].bag["green_2"] == 1


def test_card_11_value_4_chips_white_and_orange_are_not_upgradable():
    bag = {"green_4": 1, "blue_4": 1, "white_3": 1, "orange_6": 1, "white_1": 3}
    out = start("card_11", {"p1": bag, "p2": bag}, ["green_4", "blue_4", "white_3", "orange_6"] * 2)
    assert out.state.phase is Phase.BREW


def test_card_11_a_chip_twice_in_the_draw_is_one_action_and_one_upgrade():
    bag = {"yellow_2": 2, "white_1": 4, "white_2": 1}
    out = start("card_11", {"p1": bag}, ["yellow_2", "yellow_2", "white_1", "white_2"] + ["white_1"] * 4)
    assert legal_actions(out.state, RS, "p1") == ["card_upgrade:yellow_2"]
    done = choose(out, "card_upgrade:yellow_2", WAIT)
    assert done.state.players["p1"].bag["yellow_2"] == 1
    assert done.state.players["p1"].bag["yellow_4"] == 1


def test_card_11_a_third_copy_of_a_chip_the_bag_holds_twice_is_illegal_chance():
    bag = {"yellow_2": 2, "white_1": 4, "white_2": 1}
    with pytest.raises(IllegalChance):
        start("card_11", {"p1": bag}, ["yellow_2", "yellow_2", "yellow_2", "white_1"] + ["white_1"] * 4)


def test_card_11_a_failed_draw_leaves_the_input_state_untouched():
    s = new_game(RS)
    s.players["p1"].bag = {"yellow_2": 2, "white_1": 4}
    with pytest.raises(IllegalChance):
        step(s, RS, None, ScriptedChance(["card_11", "yellow_2", "yellow_2", "yellow_2"]))
    assert s.players["p1"].bag == {"yellow_2": 2, "white_1": 4} and s.players["p1"].card_draw == []


def test_card_11_the_bag_is_whole_after_the_draw_and_the_choice_is_permanent():
    bag = {"white_1": 4, "white_2": 1, "yellow_2": 1, "green_1": 1}
    out = start("card_11", {"p1": bag}, ["white_1", "white_2", "yellow_2", "green_1"] + ["white_1"] * 4)
    assert out.state.players["p1"].bag == bag  # the drawn chips are still in the bag
    assert out.state.players["p1"].card_draw == ["white_1", "white_2", "yellow_2", "green_1"]
    done = choose(out, "card_upgrade:yellow_2", WAIT)
    assert Counter(done.state.players["p1"].bag) == Counter({**bag, "yellow_2": 0, "yellow_4": 1}) + Counter()


def _state_with_opponent_draw(opp_draw):
    out = start("card_11", {"p1": {"white_1": 4, "yellow_2": 1, "green_1": 1, "white_2": 1}}, [
        "white_1", "white_2", "yellow_2", "green_1"] + ["white_1"] * 4)
    s = out.state
    s.players["p2"].card_draw = list(opp_draw)
    return s


def test_card_11_the_draw_is_visible_to_the_choosing_player_only():
    a = _state_with_opponent_draw(["white_1"] * 4)
    b = _state_with_opponent_draw(["white_1", "white_1", "white_2", "white_3"])
    assert a.players["p2"].card_draw != b.players["p2"].card_draw
    # the observation of p1 (layout 7) and its text render are equal
    va = vectorize(observe(a, RS, "p1"), RS)
    vb = vectorize(observe(b, RS, "p1"), RS)
    assert (va == vb).all()

    def view(s, seat):
        stream = io.StringIO()
        legal = legal_actions(s, RS, seat)
        key = next(iter(key_map(legal)))
        HumanSeat("P", Console(file=stream, width=2000), True, RS, read_key=lambda: key).choose(s, seat, legal)
        return stream.getvalue()

    assert view(a, "p1") == view(b, "p1")
    # the choosing seat's own view shows its draw: W1 W2 Y2 G1
    assert "drawn: W1 W2 Y2 G1" in view(a, "p1")


# --- card 20 ----------------------------------------------------------------------


def lowest(out):
    return out.state.players["p1"], out.state.players["p2"]


def test_card_20_clear_lowest_gets_blue_2_the_other_one_ruby():
    out = start("card_20", chance=["white_1"] * 4 + ["white_2"] + ["white_3", "white_2", "white_2", "white_1", "white_1"])
    assert out.state.phase is Phase.BREW  # no question, no choice phase
    p1, p2 = lowest(out)  # p1: 6, p2: 9
    assert p1.bag.get("blue_2") == 1 and p1.rubies == RS.start_rubies
    assert "blue_2" not in p2.bag and p2.rubies == RS.start_rubies + 1
    draws = [c for c in out.chance if c["kind"] == "draw_chip"]
    assert [c["seat"] for c in draws] == ["p1"] * 5 + ["p2"] * 5


def test_card_20_the_higher_sum_gets_the_ruby_the_lower_the_blue_2():
    bag = {"white_1": 6, "white_2": 2, "white_3": 2}
    out = start("card_20", {"p1": bag, "p2": bag}, ["white_3", "white_3", "white_2", "white_2", "white_1"] + ["white_1"] * 4 + ["white_2"])
    p1, p2 = lowest(out)  # p1: 11, p2: 6
    assert p2.bag.get("blue_2") == 1 and "blue_2" not in p1.bag
    assert p1.rubies == RS.start_rubies + 1 and p2.rubies == RS.start_rubies


def test_card_20_tie_of_the_lowest_sum_both_take_blue_2_and_nobody_gets_a_ruby():
    bag = {"white_1": 6, "white_2": 2, "white_3": 2}
    out = start("card_20", {"p1": bag, "p2": bag}, ["white_1"] * 5 + ["white_1"] * 4 + ["white_1"])
    p1, p2 = lowest(out)
    assert p1.bag["blue_2"] == 1 and p2.bag["blue_2"] == 1
    assert p1.rubies == p2.rubies == RS.start_rubies


def test_card_20_orange_6_counts_6():
    bag = {"orange_6": 1, "white_1": 4}
    out = start("card_20", {"p1": bag, "p2": bag}, ["orange_6", "white_1", "white_1", "white_1", "white_1"] + ["white_1"] * 4 + ["orange_6"])
    # both sum 10: a tie
    p1, p2 = lowest(out)
    assert p1.bag["blue_2"] == p2.bag["blue_2"] == 1
    out = start("card_20", {"p1": bag, "p2": {"white_1": 5}}, ["orange_6", "white_1", "white_1", "white_1", "white_1"] + ["white_1"] * 5)
    p1, p2 = lowest(out)  # p1: 10, p2: 5
    assert p2.bag["blue_2"] == 1 and p1.rubies == RS.start_rubies + 1


def test_card_20_the_bag_is_whole_after_the_draw_and_a_third_copy_is_illegal():
    bag = {"white_1": 5, "white_2": 1}
    out = start("card_20", {"p1": bag, "p2": bag}, ["white_1"] * 5 + ["white_1"] * 5)
    assert out.state.players["p1"].bag == {**bag, "blue_2": 1}
    with pytest.raises(IllegalChance):
        start("card_20", {"p1": {"white_1": 2, "white_2": 4}}, ["white_1", "white_1", "white_1"])


# --- the deck, the actions and replay ---------------------------------------------


def test_the_new_actions_are_appended_at_the_end():
    names = action_names(RS)
    assert len(names) == len(set(names))
    assert names[-9:] == ["card_tail_points", *(f"card_upgrade:{c}" for c in (
        "green_1", "green_2", "blue_1", "blue_2", "red_1", "red_2", "yellow_1", "yellow_2"))]


def _play(seed, deck=None, cap=4000):
    """A random game with random legal actions; the game ends at the cap (the rounds are few)."""
    rng = random.Random(seed)
    chance = RngChance(seed)
    s = new_game(RS)
    if deck is not None:
        s.deck = list(deck)
    record = []
    for _ in range(cap):
        if s.phase is Phase.GAME_OVER:
            break
        acts = None
        if needs_actions(s):
            legal = {seat: legal_actions(s, RS, seat) for seat in SEATS}
            assert all(set(v) <= set(action_names(RS)) for v in legal.values())
            acts = {seat: rng.choice(legal[seat]) for seat in SEATS}
        r = step(s, RS, acts, chance)
        record.append((acts, [c["value"] for c in r.chance], r.state))
        s = r.state
    return record


def test_a_game_with_cards_11_and_20_replays_with_equal_states():
    from quack_rl.rules import with_rounds

    rs2 = with_rounds(RS, 2)
    for seed in range(5):
        rng = random.Random(seed)
        chance = RngChance(seed)
        s = new_game(rs2)
        s.deck = ["card_11", "card_20"]  # both cards are played in the 2 rounds
        record, played = [], set()
        for _ in range(4000):
            if s.phase is Phase.GAME_OVER:
                break
            acts = None
            if needs_actions(s):
                legal = {seat: legal_actions(s, rs2, seat) for seat in SEATS}
                acts = {seat: rng.choice(legal[seat]) for seat in SEATS}
            r = step(s, rs2, acts, chance)
            played.add(r.state.card)
            record.append((acts, [c["value"] for c in r.chance], r.state))
            s = r.state
        assert s.phase is Phase.GAME_OVER and played - {None} == {"card_11", "card_20"}
        n_draws = sum(1 for _a, vals, _s in record for v in vals if v in {c.id for c in rs2.chips})
        assert n_draws >= 18  # 8 + 10 card draws, plus the brew draws
        replay = new_game(rs2)
        replay.deck = ["card_11", "card_20"]
        for acts, values, after in record:
            replay = step(replay, rs2, acts, ScriptedChance(values)).state
            assert replay == after


def test_cards_11_and_20_in_random_games_keep_the_bags_and_the_draw_consistent():
    for seed in range(3):
        for _acts, _vals, after in _play(seed, deck=["card_11", "card_20", *["card_16"] * 14]):
            for seat in SEATS:
                assert after.players[seat].card_draw == [] or after.phase is Phase.CARD_CHOICE
                assert all(n > 0 for n in after.players[seat].bag.values())
