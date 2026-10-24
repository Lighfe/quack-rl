"""Observation layout 8 (rules v2.1): look-ahead window, gaps, no field table, bounds."""

import copy
import random

import numpy as np
import pytest

from quack_rl.engine import RngChance, legal_actions, needs_actions, new_game, step
from quack_rl.engine.state import Phase, scoring_field
from quack_rl.rl import (
    QuackEnv,
    QuackParallelEnv,
    map_channels,
    map_slice,
    observation_bounds,
    observation_layout,
    observe,
    vector_names,
    vectorize,
)
from quack_rl.rl.encode import BOARD_LAYOUT
from quack_rl.rules import load_ruleset

RS = load_ruleset("v2.1")
SEATS = ("p1", "p2")

# vector_names(RS) without the map block, which is last
PREFIX = [
    "round",
    "rounds",
    "explosion_limit",
    "phase.card",
    "phase.card_choice",
    "phase.restart",
    "phase.brew",
    "phase.resolve",
    "phase.choice",
    "phase.shop",
    "phase.game_over",
    "own.status.brewing",
    "own.status.stopped",
    "own.status.exploded",
    "own.chip_colours.white",
    "own.chip_colours.orange",
    "own.chip_colours.green",
    "own.chip_colours.blue",
    "own.chip_colours.red",
    "own.chip_colours.black",
    "own.chip_colours.yellow",
    "own.chip_colours.purple",
    "own.money",
    "own.rubies",
    "own.flask_full",
    "own.white_total",
    "own.points",
    "own.droplet_halves",
    "own.purchases",
    "own.chip_purchases",
    "own.shop_done",
    "own.bag.remaining.white_1",
    "own.bag.remaining.white_2",
    "own.bag.remaining.white_3",
    "own.bag.remaining.orange_1",
    "own.bag.remaining.orange_6",
    "own.bag.remaining.green_1",
    "own.bag.remaining.green_2",
    "own.bag.remaining.green_4",
    "own.bag.remaining.blue_1",
    "own.bag.remaining.blue_2",
    "own.bag.remaining.blue_4",
    "own.bag.remaining.red_1",
    "own.bag.remaining.red_2",
    "own.bag.remaining.red_4",
    "own.bag.remaining.black_1",
    "own.bag.remaining.yellow_1",
    "own.bag.remaining.yellow_2",
    "own.bag.remaining.yellow_4",
    "own.bag.remaining.purple_1",
    "own.bag.owned.white_1",
    "own.bag.owned.white_2",
    "own.bag.owned.white_3",
    "own.bag.owned.orange_1",
    "own.bag.owned.orange_6",
    "own.bag.owned.green_1",
    "own.bag.owned.green_2",
    "own.bag.owned.green_4",
    "own.bag.owned.blue_1",
    "own.bag.owned.blue_2",
    "own.bag.owned.blue_4",
    "own.bag.owned.red_1",
    "own.bag.owned.red_2",
    "own.bag.owned.red_4",
    "own.bag.owned.black_1",
    "own.bag.owned.yellow_1",
    "own.bag.owned.yellow_2",
    "own.bag.owned.yellow_4",
    "own.bag.owned.purple_1",
    "opponent.status.brewing",
    "opponent.status.stopped",
    "opponent.status.exploded",
    "opponent.chip_colours.white",
    "opponent.chip_colours.orange",
    "opponent.chip_colours.green",
    "opponent.chip_colours.blue",
    "opponent.chip_colours.red",
    "opponent.chip_colours.black",
    "opponent.chip_colours.yellow",
    "opponent.chip_colours.purple",
    "opponent.money",
    "opponent.rubies",
    "opponent.flask_full",
    "opponent.white_total",
    "opponent.points",
    "opponent.droplet_halves",
    "opponent.purchases",
    "opponent.chip_purchases",
    "opponent.shop_done",
    "opponent.bag.remaining.white_1",
    "opponent.bag.remaining.white_2",
    "opponent.bag.remaining.white_3",
    "opponent.bag.remaining.orange_1",
    "opponent.bag.remaining.orange_6",
    "opponent.bag.remaining.green_1",
    "opponent.bag.remaining.green_2",
    "opponent.bag.remaining.green_4",
    "opponent.bag.remaining.blue_1",
    "opponent.bag.remaining.blue_2",
    "opponent.bag.remaining.blue_4",
    "opponent.bag.remaining.red_1",
    "opponent.bag.remaining.red_2",
    "opponent.bag.remaining.red_4",
    "opponent.bag.remaining.black_1",
    "opponent.bag.remaining.yellow_1",
    "opponent.bag.remaining.yellow_2",
    "opponent.bag.remaining.yellow_4",
    "opponent.bag.remaining.purple_1",
    "opponent.bag.owned.white_1",
    "opponent.bag.owned.white_2",
    "opponent.bag.owned.white_3",
    "opponent.bag.owned.orange_1",
    "opponent.bag.owned.orange_6",
    "opponent.bag.owned.green_1",
    "opponent.bag.owned.green_2",
    "opponent.bag.owned.green_4",
    "opponent.bag.owned.blue_1",
    "opponent.bag.owned.blue_2",
    "opponent.bag.owned.blue_4",
    "opponent.bag.owned.red_1",
    "opponent.bag.owned.red_2",
    "opponent.bag.owned.red_4",
    "opponent.bag.owned.black_1",
    "opponent.bag.owned.yellow_1",
    "opponent.bag.owned.yellow_2",
    "opponent.bag.owned.yellow_4",
    "opponent.bag.owned.purple_1",
    "own.scoring_field",
    "own.ruby_at_scoring_field",
    "own.money_if_stop",
    "own.limit_distance",
    "own.explosion_chance",
    "own.rolls_die",
    "own.chips_placed",
    "opponent.scoring_field",
    "opponent.ruby_at_scoring_field",
    "opponent.money_if_stop",
    "opponent.limit_distance",
    "opponent.explosion_chance",
    "opponent.rolls_die",
    "opponent.chips_placed",
    "field_gap",
    "points_gap",
    "own.field_points",
    "last_round",
    "own.hand.0.present",
    "own.hand.0.value",
    "own.hand.0.colour.white",
    "own.hand.0.colour.orange",
    "own.hand.0.colour.green",
    "own.hand.0.colour.blue",
    "own.hand.0.colour.red",
    "own.hand.0.colour.black",
    "own.hand.0.colour.yellow",
    "own.hand.0.colour.purple",
    "own.hand.1.present",
    "own.hand.1.value",
    "own.hand.1.colour.white",
    "own.hand.1.colour.orange",
    "own.hand.1.colour.green",
    "own.hand.1.colour.blue",
    "own.hand.1.colour.red",
    "own.hand.1.colour.black",
    "own.hand.1.colour.yellow",
    "own.hand.1.colour.purple",
    "own.hand.2.present",
    "own.hand.2.value",
    "own.hand.2.colour.white",
    "own.hand.2.colour.orange",
    "own.hand.2.colour.green",
    "own.hand.2.colour.blue",
    "own.hand.2.colour.red",
    "own.hand.2.colour.black",
    "own.hand.2.colour.yellow",
    "own.hand.2.colour.purple",
    "own.hand.3.present",
    "own.hand.3.value",
    "own.hand.3.colour.white",
    "own.hand.3.colour.orange",
    "own.hand.3.colour.green",
    "own.hand.3.colour.blue",
    "own.hand.3.colour.red",
    "own.hand.3.colour.black",
    "own.hand.3.colour.yellow",
    "own.hand.3.colour.purple",
    "own.hand_size",
    "shop.orange_1.min_round",
    "shop.orange_1.open",
    "shop.orange_6.min_round",
    "shop.orange_6.open",
    "shop.green_1.min_round",
    "shop.green_1.open",
    "shop.green_2.min_round",
    "shop.green_2.open",
    "shop.green_4.min_round",
    "shop.green_4.open",
    "shop.blue_1.min_round",
    "shop.blue_1.open",
    "shop.blue_2.min_round",
    "shop.blue_2.open",
    "shop.blue_4.min_round",
    "shop.blue_4.open",
    "shop.red_1.min_round",
    "shop.red_1.open",
    "shop.red_2.min_round",
    "shop.red_2.open",
    "shop.red_4.min_round",
    "shop.red_4.open",
    "shop.black_1.min_round",
    "shop.black_1.open",
    "shop.yellow_1.min_round",
    "shop.yellow_1.open",
    "shop.yellow_2.min_round",
    "shop.yellow_2.open",
    "shop.yellow_4.min_round",
    "shop.yellow_4.open",
    "shop.purple_1.min_round",
    "shop.purple_1.open",
    "card.ruby_extra",
    "card.restart_after_5",
    "card.drop_all_1",
    "card.explosion_limit_plus_2",
    "card.choice_black_or_value2_or_rubies",
    "card.choice_drop2_or_purple",
    "card.fewest_points_green",
    "card.rat_tails_for_rubies",
    "card.die_twice",
    "card.draw5_choose_place",
    "card.draw4_upgrade",
    "card.ruby_for_chip",
    "card.fewest_rubies_ruby",
    "card.points_or_remove_white",
    "card.ruby_field_points",
    "card.refill_flasks",
    "card.first_white_back",
    "card.everyone_rolls",
    "card.chip4_or_tail_points",
    "card.draw5_lowest",
    "deck.ruby_extra",
    "deck.restart_after_5",
    "deck.drop_all_1",
    "deck.explosion_limit_plus_2",
    "deck.choice_black_or_value2_or_rubies",
    "deck.choice_drop2_or_purple",
    "deck.fewest_points_green",
    "deck.rat_tails_for_rubies",
    "deck.die_twice",
    "deck.draw5_choose_place",
    "deck.draw4_upgrade",
    "deck.ruby_for_chip",
    "deck.fewest_rubies_ruby",
    "deck.points_or_remove_white",
    "deck.ruby_field_points",
    "deck.refill_flasks",
    "deck.first_white_back",
    "deck.everyone_rolls",
    "deck.chip4_or_tail_points",
    "deck.draw5_lowest",
    "restart.available",
    "own.round_end_halves",
    "opponent.round_end_halves",
    "own.board.marker.0",
    "own.board.marker.1",
    "own.board.marker.2",
    "own.board.marker.3",
    "own.board.marker.4",
    "own.board.marker.5",
    "own.board.marker.6",
    "own.board.marker.7",
    "own.board.marker.8",
    "own.board.marker.9",
    "own.board.marker.10",
    "own.board.marker.11",
    "own.board.marker.12",
    "own.board.marker.13",
    "own.board.marker.14",
    "own.board.marker.15",
    "own.board.marker.16",
    "own.board.marker.17",
    "own.board.marker.18",
    "own.board.marker.19",
    "own.board.marker.20",
    "own.board.marker.21",
    "own.board.marker.22",
    "own.board.marker.23",
    "own.board.marker.24",
    "own.board.marker.25",
    "own.board.marker.26",
    "own.board.marker.27",
    "own.board.marker.28",
    "own.board.marker.29",
    "own.board.marker.30",
    "own.board.marker.31",
    "own.board.marker.32",
    "own.board.marker.33",
    "own.board.marker.34",
    "own.board.marker.35",
    "own.board.marker.36",
    "own.board.marker.37",
    "own.board.marker.38",
    "own.board.marker.39",
    "own.board.marker.40",
    "own.board.marker.41",
    "own.board.marker.42",
    "own.board.marker.43",
    "own.board.marker.44",
    "own.board.marker.45",
    "own.board.marker.46",
    "own.board.marker.47",
    "own.board.marker.48",
    "own.board.marker.49",
    "own.board.marker.50",
    "own.board.has_50pts",
    "own.rat_tail",
    "opponent.board.marker.0",
    "opponent.board.marker.1",
    "opponent.board.marker.2",
    "opponent.board.marker.3",
    "opponent.board.marker.4",
    "opponent.board.marker.5",
    "opponent.board.marker.6",
    "opponent.board.marker.7",
    "opponent.board.marker.8",
    "opponent.board.marker.9",
    "opponent.board.marker.10",
    "opponent.board.marker.11",
    "opponent.board.marker.12",
    "opponent.board.marker.13",
    "opponent.board.marker.14",
    "opponent.board.marker.15",
    "opponent.board.marker.16",
    "opponent.board.marker.17",
    "opponent.board.marker.18",
    "opponent.board.marker.19",
    "opponent.board.marker.20",
    "opponent.board.marker.21",
    "opponent.board.marker.22",
    "opponent.board.marker.23",
    "opponent.board.marker.24",
    "opponent.board.marker.25",
    "opponent.board.marker.26",
    "opponent.board.marker.27",
    "opponent.board.marker.28",
    "opponent.board.marker.29",
    "opponent.board.marker.30",
    "opponent.board.marker.31",
    "opponent.board.marker.32",
    "opponent.board.marker.33",
    "opponent.board.marker.34",
    "opponent.board.marker.35",
    "opponent.board.marker.36",
    "opponent.board.marker.37",
    "opponent.board.marker.38",
    "opponent.board.marker.39",
    "opponent.board.marker.40",
    "opponent.board.marker.41",
    "opponent.board.marker.42",
    "opponent.board.marker.43",
    "opponent.board.marker.44",
    "opponent.board.marker.45",
    "opponent.board.marker.46",
    "opponent.board.marker.47",
    "opponent.board.marker.48",
    "opponent.board.marker.49",
    "opponent.board.marker.50",
    "opponent.board.has_50pts",
    "opponent.rat_tail",
    "board.tail.0",
    "board.tail.1",
    "board.tail.2",
    "board.tail.3",
    "board.tail.4",
    "board.tail.5",
    "board.tail.6",
    "board.tail.7",
    "board.tail.8",
    "board.tail.9",
    "board.tail.10",
    "board.tail.11",
    "board.tail.12",
    "board.tail.13",
    "board.tail.14",
    "board.tail.15",
    "board.tail.16",
    "board.tail.17",
    "board.tail.18",
    "board.tail.19",
    "board.tail.20",
    "board.tail.21",
    "board.tail.22",
    "board.tail.23",
    "board.tail.24",
    "board.tail.25",
    "board.tail.26",
    "board.tail.27",
    "board.tail.28",
    "board.tail.29",
    "board.tail.30",
    "board.tail.31",
    "board.tail.32",
    "board.tail.33",
    "board.tail.34",
    "board.tail.35",
    "board.tail.36",
    "board.tail.37",
    "board.tail.38",
    "board.tail.39",
    "board.tail.40",
    "board.tail.41",
    "board.tail.42",
    "board.tail.43",
    "board.tail.44",
    "board.tail.45",
    "board.tail.46",
    "board.tail.47",
    "board.tail.48",
    "board.tail.49",
    "ahead.0.money",
    "ahead.0.points",
    "ahead.0.ruby",
    "ahead.1.money",
    "ahead.1.points",
    "ahead.1.ruby",
    "ahead.2.money",
    "ahead.2.points",
    "ahead.2.ruby",
    "ahead.3.money",
    "ahead.3.points",
    "ahead.3.ruby",
    "ahead.4.money",
    "ahead.4.points",
    "ahead.4.ruby",
    "ahead.5.money",
    "ahead.5.points",
    "ahead.5.ruby",
    "ahead.6.money",
    "ahead.6.points",
    "ahead.6.ruby",
    "ahead.7.money",
    "ahead.7.points",
    "ahead.7.ruby",
    "ahead.8.money",
    "ahead.8.points",
    "ahead.8.ruby",
    "ahead.9.money",
    "ahead.9.points",
    "ahead.9.ruby",
    "ahead.10.money",
    "ahead.10.points",
    "ahead.10.ruby",
]


def named(state, seat, k_max=10):
    obs = observe(state, RS, seat, k_max)
    return dict(zip(vector_names(RS, k_max), vectorize(obs, RS), strict=True))


def states(seed):
    rng = random.Random(seed)
    chance = RngChance(seed)
    state = new_game(RS)
    yield state
    while state.phase is not Phase.GAME_OVER:
        actions = (
            {s: rng.choice(legal_actions(state, RS, s)) for s in SEATS}
            if needs_actions(state)
            else None
        )
        state = step(state, RS, actions, chance).state
        yield state


def test_layout_number_and_pinned_names():
    assert BOARD_LAYOUT == observation_layout(RS) == 8
    names = vector_names(RS)
    sl = map_slice(RS)
    assert names[: sl.start] == PREFIX
    # the map block: per field, own then opponent: colour flags, value, order
    colours = list(dict.fromkeys(c.colour for c in RS.chips))
    cell = [
        f"map.{{f}}.{who}.{k}"
        for who in ("own", "opponent")
        for k in (*(f"colour.{c}" for c in colours), "value", "order")
    ]
    assert names[sl] == [n.format(f=f) for f in range(RS.track_end + 1) for n in cell]
    assert len(names) == 1530 == len(PREFIX) + (RS.track_end + 1) * map_channels(RS)
    assert len(set(names)) == len(names)


def test_no_static_field_table():
    names = vector_names(RS)
    assert not [
        n for n in names if n.startswith("map.") and n.endswith(("money", "points", "ruby"))
    ]
    assert not [n for n in names if "ruby_fields" in n]
    for who in ("own", "opponent"):
        for k in ("money", "points", "rubies", "flask_full", "droplet_halves", "white_total"):
            assert f"{who}.{k}" in names
    assert "explosion_limit" in names and "own.board.marker.0" in names


def test_window_at_the_start_field():
    state = new_game(RS)
    v = named(state, "p1")
    start = scoring_field(state.players["p1"].field, RS)
    for k in range(11):
        f = min(start + k, RS.track_end)
        assert v[f"ahead.{k}.money"] == RS.fields[f].money
        assert v[f"ahead.{k}.points"] == RS.fields[f].points
        assert v[f"ahead.{k}.ruby"] == float(RS.fields[f].ruby)
    assert len([n for n in vector_names(RS) if n.startswith("ahead.")]) == 33


def test_window_follows_the_own_field_only():
    state = new_game(RS)
    state.players["p1"].field = 12
    state.players["p2"].field = 30
    v = named(state, "p1")
    for k in range(11):
        assert v[f"ahead.{k}.money"] == RS.fields[13 + k].money
    w = named(state, "p2")
    for k in range(11):
        assert w[f"ahead.{k}.money"] == RS.fields[31 + k].money
    assert not [n for n in vector_names(RS) if n.startswith("opponent.ahead")]


def test_window_repeats_the_last_field():
    state = new_game(RS)
    last = RS.fields[RS.track_end]
    state.players["p1"].field = RS.track_end - 3  # scoring field track_end - 2
    v = named(state, "p1")
    assert v["ahead.0.money"] == RS.fields[RS.track_end - 2].money
    assert v["ahead.1.money"] == RS.fields[RS.track_end - 1].money
    for k in range(2, 11):
        assert v[f"ahead.{k}.money"] == last.money
        assert v[f"ahead.{k}.points"] == last.points
        assert v[f"ahead.{k}.ruby"] == float(last.ruby)
    state.players["p1"].field = RS.track_end  # the scoring field is capped at track_end
    v = named(state, "p1")
    assert all(v[f"ahead.{k}.points"] == last.points for k in range(11))


def test_window_with_changed_k():
    state = new_game(RS)
    names3 = vector_names(RS, 3)
    assert [n for n in names3 if n.startswith("ahead.")] == [
        f"ahead.{k}.{c}" for k in range(4) for c in ("money", "points", "ruby")
    ]
    assert len(vector_names(RS, 3)) == len(vector_names(RS)) - 21
    assert len(vectorize(observe(state, RS, "p1", 3), RS)) == len(names3)
    full = named(state, "p1", RS.track_end)
    start = scoring_field(0, RS)
    assert len([n for n in vector_names(RS, RS.track_end) if n.startswith("ahead.")]) == 3 * (
        RS.track_end + 1
    )
    for k in range(RS.track_end + 1):  # the whole rest of the pot, then the last field again
        assert full[f"ahead.{k}.points"] == RS.fields[min(start + k, RS.track_end)].points
    lo, hi = observation_bounds(RS, 3)
    assert len(lo) == len(hi) == len(names3)


def test_gaps_sign_and_value():
    state = new_game(RS)
    state.players["p1"].field = 20
    state.players["p2"].field = 14
    state.players["p1"].points = 7
    state.players["p2"].points = 12
    v = named(state, "p1")
    assert v["field_gap"] == 6 and v["points_gap"] == -5
    w = named(state, "p2")
    assert w["field_gap"] == -6 and w["points_gap"] == 5
    names = vector_names(RS)
    assert names.index("field_gap") == names.index("points_gap") - 1
    assert names.index("own.chips_placed") < names.index("field_gap")


def test_rubies_and_flask_in_both_views():
    state = new_game(RS)
    state.players["p1"].rubies = 3
    state.players["p2"].flask_full = False
    v = named(state, "p1")
    assert (v["own.rubies"], v["opponent.rubies"]) == (3, state.players["p2"].rubies)
    assert (v["own.flask_full"], v["opponent.flask_full"]) == (1, 0)


def test_opponent_view_has_no_hidden_values():
    for state in states(2):
        for seat, other in (("p1", "p2"), ("p2", "p1")):
            view = observe(state, RS, seat)
            assert "hand" not in view["opponent"]
            assert "ahead" in view and not [k for k in view["opponent"] if k.startswith("ahead")]
            changed = copy.deepcopy(state)
            q = changed.players[other]
            q.hand = []
            q.card_draw = []
            q.restart_pending = not q.restart_pending
            q.bag = dict(reversed(list(q.bag.items())))
            assert np.array_equal(vectorize(view, RS), vectorize(observe(changed, RS, seat), RS))


def test_bounds_hold_in_masked_games():
    lo, hi = observation_bounds(RS)
    names = vector_names(RS)
    assert len(lo) == len(hi) == len(names)
    assert hi[names.index("ahead.3.points")] == max(f.points for f in RS.fields)
    assert hi[names.index("ahead.3.ruby")] == 1
    assert (
        hi[names.index("field_gap")] == RS.track_end
        and lo[names.index("field_gap")] == -RS.track_end
    )
    assert np.isinf(hi[names.index("own.rubies")])
    for seed in range(4):
        for state in states(seed):
            for seat in SEATS:
                vec = vectorize(observe(state, RS, seat), RS)
                assert np.all(vec >= lo) and np.all(vec <= hi)


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_parallel_env_masked_game_stays_in_the_space(seed):
    env = QuackParallelEnv(rules=RS)
    rng = random.Random(seed)
    obs, _ = env.reset(seed=seed)
    space = env.observation_space("p1")
    while env.agents:
        for seat in env.agents:
            assert space.contains(obs[seat])
            legal = set(legal_actions(env.state, RS, seat))
            mask = obs[seat]["action_mask"]
            if env.state.phase is not Phase.GAME_OVER:
                assert {env._names[i] for i in np.flatnonzero(mask)} <= legal | {"wait"}
        acts = {a: rng.choice(np.flatnonzero(obs[a]["action_mask"]).tolist()) for a in env.agents}
        obs, *_ = env.step(acts)


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_single_env_masked_game_stays_in_the_space(seed):
    env = QuackEnv(rules=RS)
    rng = random.Random(seed)
    obs, info = env.reset(seed=seed)
    done = False
    while not done:
        assert env.observation_space.contains(obs)
        mask = info["action_mask"]
        assert mask.any()
        legal = set(legal_actions(env.state, RS, env.agent_seat))
        assert {env._env._names[i] for i in np.flatnonzero(mask)} == legal
        obs, _, done, _, info = env.step(rng.choice(np.flatnonzero(mask).tolist()))
        assert not info["illegal_action"]
    assert not info["action_mask"].any()  # terminal step: all zero
