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
