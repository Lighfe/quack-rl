"""Observation layout 4 (rules v1.9): layout numbers, vector, mask, envs, refusals."""

import json

import random

import numpy as np

import pytest

from gymnasium.utils.env_checker import check_env

from pettingzoo.test import parallel_api_test

from quack_rl.bots import HeuristicBot

from quack_rl.engine import (
    MAX_HAND,
    PUT_BACK_DRAW,
    PUT_BACK_STOP,
    RngChance,
    action_names,
    legal_actions,
    needs_actions,
    new_game,
    play,
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

from quack_rl.rl.encode import LayoutRefused

from quack_rl.rl.finetune import finetune_online

from quack_rl.rl.offline import train_offline_run

from quack_rl.rl.opponents import make_opponent

from quack_rl.rl.selfplay import train_selfplay

from quack_rl.rl.train import train

from quack_rl.rules import load_ruleset

RS9 = load_ruleset("v1.9")

SEATS = ("p1", "p2")

def states(seed):
    rng = random.Random(seed)
    chance = RngChance(seed)
    state = new_game(RS9)
    yield state
    while state.phase is not Phase.GAME_OVER:
        actions = (
            {s: rng.choice(legal_actions(state, RS9, s)) for s in SEATS}
            if needs_actions(state)
            else None
        )
        state = step(state, RS9, actions, chance).state
        yield state


def test_short_evaluation_of_heuristic_bots_runs_to_the_end():
    for opp in ("draw20-pts1-points", "draw40-pts4-blue"):
        result = evaluate(random_policy(0), opp, rules="v1.9", games=6, seed=0, reads_observation=False)
        assert result.games == 6 == result.wins + result.draws + result.losses
    assert HeuristicBot  # the opponents are heuristic bots of the tournament field


def test_evaluate_with_a_policy_is_refused_on_layout_4():
    with pytest.raises(LayoutRefused) as err:
        evaluate(random_policy(0), "random", rules="v1.9", games=1)
    assert "layout 4" in str(err.value)
    assert isinstance(err.value, ValueError)


def test_policy_bot_is_refused_on_layout_4(tmp_path):
    with pytest.raises(LayoutRefused, match="layout 4"):
        PolicyBot(lambda o, m: 0, "v1.9")
    run = tmp_path / "r"
    run.mkdir()
    (run / "config.json").write_text(json.dumps({"rules": "v1.9"}))
    with pytest.raises(LayoutRefused, match="layout 4"):
        PolicyBot.from_run(run, "v1.9")


def test_selfplay_is_refused_on_layout_4(tmp_path):
    with pytest.raises(LayoutRefused, match="layout 4"):
        train_selfplay("x", 100, rules="v1.9", runs_dir=tmp_path)
    assert not list(tmp_path.iterdir())


def test_finetune_is_refused_on_layout_4(tmp_path):
    with pytest.raises(LayoutRefused, match="layout 4"):
        finetune_online(tmp_path / "src", tmp_path / "out", 10, "random", rules="v1.9")
    assert not (tmp_path / "out").exists()


def test_offline_is_refused_on_layout_4(tmp_path):
    with pytest.raises(LayoutRefused, match="layout 4"):
        train_offline_run(tmp_path / "d.parquet", "x", runs_dir=tmp_path, rules="v1.9", steps=1)
    assert not list(tmp_path.iterdir())


def test_train_is_refused_on_layout_4():
    with pytest.raises(LayoutRefused, match="layout 4"):
        train(10, rules="v1.9")


# ---- Moved from tests/test_rl_layout4.py (#170), original text ----

"""Observation layout 4 (rules v1.9): layout numbers, vector, mask, envs, refusals."""

import random

import numpy as np
import pytest
from gymnasium.utils.env_checker import check_env
from pettingzoo.test import parallel_api_test

from quack_rl.engine import (
    MAX_HAND,
    PUT_BACK_DRAW,
    PUT_BACK_STOP,
    RngChance,
    action_names,
    legal_actions,
    needs_actions,
    new_game,
    play,
    step,
)
from quack_rl.engine.state import Phase
from quack_rl.rl import (
    QuackEnv,
    QuackParallelEnv,
    action_mask,
    map_channels,
    map_slice,
    observation_bounds,
    observation_layout,
    observe,
    vector_names,
    vectorize,
)
from quack_rl.rl.derive import derived_names
from quack_rl.rl.opponents import make_opponent
from quack_rl.rules import load_ruleset

RS9 = load_ruleset("v1.9")
SEATS = ("p1", "p2")


def test_layout_numbers():
    assert observation_layout(RS9) == 4
    assert observation_layout(load_ruleset("v1.8")) == 3
    assert observation_layout(load_ruleset("v1.1")) == 2
    assert observation_layout(load_ruleset("v1")) == 2


def test_vector_names_order_and_bounds():
    names = vector_names(RS9)
    assert len(set(names)) == len(names)
    lo, hi = observation_bounds(RS9)
    assert len(lo) == len(hi) == len(names)
    assert [n for n in names if n.startswith("phase.")] == [
        f"phase.{p}" for p in ("brew", "resolve", "choice", "shop", "game_over")
    ]
    first = names.index(derived_names(RS9)[0])
    after_derived = first + len(derived_names(RS9))
    sl = map_slice(RS9)
    assert map_channels(RS9) == 16
    assert sl.stop == len(names)
    assert names[sl.start] == "map.0.money"
    hand = names[after_derived : sl.start]
    assert len(hand) == MAX_HAND * 7 + 1
    assert hand[0] == "own.hand.0.present" and hand[-1] == "own.hand_size"
    assert "own.chip_colours.red" in names


def states(seed):
    rng = random.Random(seed)
    chance = RngChance(seed)
    state = new_game(RS9)
    yield state
    while state.phase is not Phase.GAME_OVER:
        actions = (
            {s: rng.choice(legal_actions(state, RS9, s)) for s in SEATS}
            if needs_actions(state)
            else None
        )
        state = step(state, RS9, actions, chance).state
        yield state


def test_hand_block_values_and_vector_in_bounds():
    names = vector_names(RS9)
    lo, hi = observation_bounds(RS9)
    saw_hand = False
    for seed in range(12):
        for state in states(seed):
            for seat in SEATS:
                vec = vectorize(observe(state, RS9, seat), RS9)
                assert vec.shape == (len(names),)
                assert np.all(vec >= lo) and np.all(vec <= hi)
                v = dict(zip(names, vec, strict=True))
                hand = state.players[seat].hand
                assert v["own.hand_size"] == len(hand)
                for i in range(MAX_HAND):
                    assert v[f"own.hand.{i}.present"] == float(i < len(hand))
                    if i < len(hand):
                        chip = RS9.chip(hand[i])
                        assert v[f"own.hand.{i}.value"] == chip.value
                        assert v[f"own.hand.{i}.colour.{chip.colour}"] == 1.0
                saw_hand |= bool(hand)
    assert saw_hand


def test_other_players_hand_is_not_in_the_view():
    for state in states(3):
        for seat in SEATS:
            if state.players[seat].hand:
                other = "p2" if seat == "p1" else "p1"
                assert "hand" not in observe(state, RS9, other)["opponent"]
                assert "hand" not in observe(state, RS9, seat)["opponent"]


def test_action_list_has_pick_actions_and_new_shop():
    names = action_names(RS9)
    assert names[-(MAX_HAND + 2) :] == [
        *(play(i) for i in range(MAX_HAND)),
        PUT_BACK_DRAW,
        PUT_BACK_STOP,
    ]
    assert "buy:orange_6" in names and "buy:red_1" in names
    assert not [n for n in names if n.startswith("buy:remove")]
    assert len(names) == 4 + 2 + len(RS9.shop) + MAX_HAND + 2


def test_mask_equals_legal_actions_in_every_step():
    names = action_names(RS9)
    pick = 0
    for seed in range(10):
        for state in states(seed):
            for seat in SEATS:
                legal = set(legal_actions(state, RS9, seat))
                mask = action_mask(state, RS9, seat)
                assert {n for n, m in zip(names, mask, strict=True) if m} == legal
                pick += PUT_BACK_STOP in legal
    assert pick > 0


def test_parallel_api():
    parallel_api_test(QuackParallelEnv(rules="v1.9"), num_cycles=1000)


def test_check_env():
    check_env(QuackEnv(rules="v1.9"), skip_render_check=True)


def test_parallel_env_random_masked_games_reach_a_pick_step():
    env = QuackParallelEnv(rules="v1.9")
    rng = random.Random(0)
    picks = 0
    for seed in range(30):
        obs, _ = env.reset(seed=seed)
        while env.agents:
            for a in env.agents:
                picks += bool(env.state.players[a].hand)
            acts = {a: rng.choice(np.flatnonzero(obs[a]["action_mask"]).tolist()) for a in env.agents}
            obs, *_ = env.step(acts)
            for a in obs:
                assert env.observation_space(a)["observation"].contains(obs[a]["observation"])
        assert env.state.phase is Phase.GAME_OVER
    assert picks > 0


@pytest.mark.parametrize("seat", SEATS)
def test_single_env_random_masked_games_reach_a_pick_step(seat):
    picks = 0
    for seed in range(12):
        env = QuackEnv(seat=seat, opponent=make_opponent("draw20-pts4-blue", seed, "v1.9"), rules="v1.9")
        names = action_names(env.rs)
        rng = np.random.default_rng(seed)
        _, info = env.reset(seed=seed)
        done = False
        while not done:
            legal = set(legal_actions(env.state, env.rs, env.agent_seat))
            assert {names[i] for i in np.flatnonzero(info["action_mask"])} == legal
            picks += bool(env.state.players[env.agent_seat].hand)
            _, _, done, _, info = env.step(int(rng.choice(np.flatnonzero(info["action_mask"]))))
            assert not info["illegal_action"]
    assert picks > 0

