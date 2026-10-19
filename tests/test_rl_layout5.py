"""Observation layout 5 (rules v1.10): layout numbers, vector, mask, envs, refusals."""

import json
import random

import numpy as np
import pytest
from gymnasium.utils.env_checker import check_env
from pettingzoo.test import parallel_api_test

from quack_rl.engine import (
    MAX_HAND,
    PUT_BACK_STOP,
    RngChance,
    action_names,
    legal_actions,
    needs_actions,
    new_game,
    step,
)
from quack_rl.engine.state import Phase
from quack_rl.rl import (
    PolicyBot,
    QuackEnv,
    QuackParallelEnv,
    action_mask,
    evaluate,
    map_channels,
    map_slice,
    observation_bounds,
    observation_layout,
    observe,
    random_policy,
    vector_names,
    vectorize,
)
from quack_rl.rl.derive import derived_names
from quack_rl.rl.encode import LAYOUT_COLOURS, LayoutRefused, map_colours
from quack_rl.rl.finetune import finetune_online
from quack_rl.rl.offline import train_offline_run
from quack_rl.rl.opponents import make_opponent
from quack_rl.rl.runs import LayoutMismatch, load_model
from quack_rl.rl.selfplay import train_selfplay
from quack_rl.rl.train import train
from quack_rl.rules import load_ruleset

RS10 = load_ruleset("v1.10")
RS9 = load_ruleset("v1.9")
SEATS = ("p1", "p2")
NEW_COLOURS = ("black", "yellow", "purple")
NEW_ITEMS = ("black_1", "yellow_1", "yellow_2", "yellow_4", "purple_1")


def test_layout_numbers():
    assert observation_layout(RS10) == 5
    assert observation_layout(RS9) == 4
    assert observation_layout(load_ruleset("v1.8")) == 3
    assert observation_layout(load_ruleset("v1.1")) == 2
    assert observation_layout(load_ruleset("v1")) == 2


def test_colour_count_comes_from_the_layout():
    assert LAYOUT_COLOURS == {2: 4, 3: 4, 4: 5, 5: 8}
    for rs in (RS10, RS9, load_ruleset("v1.8"), load_ruleset("v1")):
        assert map_colours(rs) == LAYOUT_COLOURS[observation_layout(rs)]
    assert map_channels(RS10) == 2 + 2 * (8 + 2)


def test_vector_names_order_and_new_entries():
    names = vector_names(RS10)
    assert len(set(names)) == len(names)
    lo, hi = observation_bounds(RS10)
    assert len(lo) == len(hi) == len(names)
    sl = map_slice(RS10)
    assert sl.stop == len(names)
    assert names[sl.start] == "map.0.money"
    for colour in NEW_COLOURS:
        assert f"own.chip_colours.{colour}" in names
        assert f"opponent.chip_colours.{colour}" in names
        assert f"map.0.own.colour.{colour}" in names
        assert f"own.hand.0.colour.{colour}" in names
    for chip in ("black_1", "yellow_1", "yellow_2", "yellow_4", "purple_1"):
        assert f"own.bag.remaining.{chip}" in names and f"opponent.bag.owned.{chip}" in names
    for item in NEW_ITEMS:
        assert f"shop.{item}.min_round" in names and f"shop.{item}.open" in names
    first = names.index(derived_names(RS10)[0]) + len(derived_names(RS10))
    block = names[first : sl.start]
    assert block[0] == "own.hand.0.present" and block[MAX_HAND * (2 + 8) + 1] == f"shop.{RS10.shop[0].id}.min_round"
    assert len(block) == MAX_HAND * (2 + 8) + 1 + 2 * len(RS10.shop)


def states(seed):
    rng = random.Random(seed)
    chance = RngChance(seed)
    state = new_game(RS10)
    yield state
    while state.phase is not Phase.GAME_OVER:
        actions = (
            {s: rng.choice(legal_actions(state, RS10, s)) for s in SEATS}
            if needs_actions(state)
            else None
        )
        state = step(state, RS10, actions, chance).state
        yield state


def test_vector_in_bounds_and_new_colours_and_minimum_round_visible():
    names = vector_names(RS10)
    lo, hi = observation_bounds(RS10)
    seen_colour = set()
    for seed in range(12):
        for state in states(seed):
            for seat in SEATS:
                vec = vectorize(observe(state, RS10, seat), RS10)
                assert vec.shape == (len(names),)
                assert np.all(vec >= lo) and np.all(vec <= hi)
                v = dict(zip(names, vec, strict=True))
                for item in RS10.shop:
                    assert v[f"shop.{item.id}.min_round"] == item.min_round
                    assert v[f"shop.{item.id}.open"] == float(state.round >= item.min_round)
                for c in NEW_COLOURS:
                    if v[f"own.chip_colours.{c}"]:
                        seen_colour.add(c)
                    assert v[f"own.chip_colours.{c}"] == state.players[seat].chip_colours.count(c)
    assert seen_colour == set(NEW_COLOURS)


def test_other_players_hand_is_not_in_the_view():
    saw = False
    for state in states(3):
        for seat in SEATS:
            other = "p2" if seat == "p1" else "p1"
            saw |= bool(state.players[seat].hand)
            assert "hand" not in observe(state, RS10, other)["opponent"]
            assert "hand" not in observe(state, RS10, seat)["opponent"]
            hidden = observe(state, RS10, other)
            assert "hand" not in hidden["opponent"]
            # the vector of the other seat does not change with this seat's hand
            names = vector_names(RS10)
            vec = dict(zip(names, vectorize(hidden, RS10), strict=True))
            assert not [n for n in names if n.startswith("opponent.hand")]
            assert vec["own.hand_size"] == len(state.players[other].hand)
    assert saw


def test_action_list_appends_the_new_shop_items():
    names9 = action_names(RS9)
    names10 = action_names(RS10)
    assert names10[: len(names9)] == names9
    assert names10[len(names9) :] == [f"buy:{i}" for i in NEW_ITEMS]
    assert len(names10) == len(names9) + len(NEW_ITEMS)


def test_mask_equals_legal_actions_and_minimum_round():
    names = action_names(RS10)
    pick = early = 0
    for seed in range(10):
        for state in states(seed):
            for seat in SEATS:
                legal = set(legal_actions(state, RS10, seat))
                mask = action_mask(state, RS10, seat)
                assert {n for n, m in zip(names, mask, strict=True) if m} == legal
                pick += PUT_BACK_STOP in legal
                for item in RS10.shop:
                    if state.round < item.min_round:
                        assert f"buy:{item.id}" not in legal
                        assert not mask[names.index(f"buy:{item.id}")]
                        early += state.phase is Phase.SHOP
    assert pick > 0 and early > 0


def test_parallel_api():
    parallel_api_test(QuackParallelEnv(rules="v1.10"), num_cycles=1000)


def test_check_env():
    check_env(QuackEnv(rules="v1.10"), skip_render_check=True)


def test_parallel_env_random_masked_games_run_to_the_end():
    env = QuackParallelEnv(rules="v1.10")
    rng = random.Random(0)
    for seed in range(20):
        obs, _ = env.reset(seed=seed)
        while env.agents:
            acts = {a: rng.choice(np.flatnonzero(obs[a]["action_mask"]).tolist()) for a in env.agents}
            obs, *_ = env.step(acts)
            for a in obs:
                assert env.observation_space(a)["observation"].contains(obs[a]["observation"])
        assert env.state.phase is Phase.GAME_OVER


@pytest.mark.parametrize("seat", SEATS)
def test_single_env_random_masked_games_run_to_the_end(seat):
    for seed in range(20):
        env = QuackEnv(seat=seat, opponent=make_opponent("draw20-pts4-blue", seed, "v1.10"), rules="v1.10")
        names = action_names(env.rs)
        rng = np.random.default_rng(seed)
        _, info = env.reset(seed=seed)
        done = False
        while not done:
            legal = set(legal_actions(env.state, env.rs, env.agent_seat))
            assert {names[i] for i in np.flatnonzero(info["action_mask"])} == legal
            _, _, done, _, info = env.step(int(rng.choice(np.flatnonzero(info["action_mask"]))))
            assert not info["illegal_action"]
        assert env.state.phase is Phase.GAME_OVER


def test_baseline_bots_evaluate_on_v1_10():
    for opp in ("draw20-pts1-points", "draw40-pts4-blue"):
        result = evaluate(random_policy(0), opp, rules="v1.10", games=6, seed=0, reads_observation=False)
        assert result.games == 6 == result.wins + result.draws + result.losses


def test_evaluate_with_a_policy_is_refused_on_layout_5():
    with pytest.raises(LayoutRefused) as err:
        evaluate(random_policy(0), "random", rules="v1.10", games=1)
    assert "layout 5" in str(err.value)
    assert isinstance(err.value, ValueError)


def test_policy_bot_is_refused_on_layout_5(tmp_path):
    with pytest.raises(LayoutRefused, match="layout 5"):
        PolicyBot(lambda o, m: 0, "v1.10")
    run = tmp_path / "r"
    run.mkdir()
    (run / "config.json").write_text(json.dumps({"rules": "v1.10"}))
    with pytest.raises(LayoutRefused, match="layout 5"):
        PolicyBot.from_run(run, "v1.10")


def test_selfplay_is_refused_on_layout_5(tmp_path):
    with pytest.raises(LayoutRefused, match="layout 5"):
        train_selfplay("x", 100, rules="v1.10", runs_dir=tmp_path)
    assert not list(tmp_path.iterdir())


def test_finetune_is_refused_on_layout_5(tmp_path):
    with pytest.raises(LayoutRefused, match="layout 5"):
        finetune_online(tmp_path / "src", tmp_path / "out", 10, "random", rules="v1.10")
    assert not (tmp_path / "out").exists()


def test_offline_is_refused_on_layout_5(tmp_path):
    with pytest.raises(LayoutRefused, match="layout 5"):
        train_offline_run(tmp_path / "d.parquet", "x", runs_dir=tmp_path, rules="v1.10", steps=1)
    assert not list(tmp_path.iterdir())


def test_train_is_refused_on_layout_5():
    with pytest.raises(LayoutRefused, match="layout 5"):
        train(10, rules="v1.10")


@pytest.mark.parametrize("made_layout", [2, 3, 4])
def test_run_with_another_layout_is_rejected(tmp_path, made_layout):
    run = tmp_path / "r"
    run.mkdir()
    config = {"rules": "v1.10", "layout": made_layout, "vector_names": vector_names(RS10)}
    (run / "config.json").write_text(json.dumps(config))
    with pytest.raises(LayoutMismatch) as err:
        load_model(run, "v1.10")
    assert f"layout {made_layout}" in str(err.value) and "layout 5" in str(err.value)
