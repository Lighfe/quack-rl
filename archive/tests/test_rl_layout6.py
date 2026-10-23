"""Observation layout 6 (rules v1.11): layout choice, vector, card block, actions, envs, refusals."""

import json

import random

import numpy as np

import pytest

from gymnasium.utils.env_checker import check_env

from pettingzoo.test import parallel_api_test

from quack_rl.engine import (
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

from quack_rl.rl.encode import CARD_COLOURS, LAYOUT_COLOURS, LayoutRefused, map_colours

from quack_rl.rl.finetune import finetune_online

from quack_rl.rl.offline import train_offline_run

from quack_rl.rl.opponents import make_opponent

from quack_rl.rl.runs import LayoutMismatch, load_model

from quack_rl.rl.selfplay import train_selfplay

from quack_rl.rl.train import train

from quack_rl.rules import load_ruleset

RS11 = load_ruleset("v1.11")

RS10 = load_ruleset("v1.10")

SEATS = ("p1", "p2")

KINDS = [
    "ruby_double",
    "restart_after_5",
    "drop_all_1",
    "explosion_limit_plus_2",
    "choice_black_or_value2_or_drop",
    "choice_drop2_or_purple",
    "fewest_points_green",
    "no_effect",
]

CARD_ACTIONS = [
    "continue",
    "restart",
    "card_drop_2",
    "card_purple",
    "card_black",
    "card_chip:white_2",
    "card_chip:green_2",
    "card_chip:blue_2",
    "card_chip:red_2",
    "card_chip:yellow_2",
    "card_drop_end",
]

def states(seed, rs=RS11):
    rng = random.Random(seed)
    chance = RngChance(seed)
    state = new_game(rs)
    yield state
    while state.phase is not Phase.GAME_OVER:
        actions = (
            {s: rng.choice(legal_actions(state, rs, s)) for s in SEATS}
            if needs_actions(state)
            else None
        )
        state = step(state, rs, actions, chance).state
        yield state

def _first_state(phase, effect=None):
    for seed in range(200):
        for state in states(seed):
            if state.phase is phase and (effect is None or RS11.card(state.card).effect == effect):
                return state
    pytest.fail(f"no state in phase {phase}")


def test_baseline_bots_evaluate_on_v1_11():
    for opp in ("draw20-pts1-points", "draw40-pts4-blue"):
        result = evaluate(random_policy(0), opp, rules="v1.11", games=6, seed=0, reads_observation=False)
        assert result.games == 6 == result.wins + result.draws + result.losses


def test_evaluate_with_a_policy_is_refused_on_layout_6():
    with pytest.raises(LayoutRefused, match="layout 6") as err:
        evaluate(random_policy(0), "random", rules="v1.11", games=1)
    assert isinstance(err.value, ValueError)


def test_policy_bot_is_refused_on_layout_6(tmp_path):
    with pytest.raises(LayoutRefused, match="layout 6"):
        PolicyBot(lambda o, m: 0, "v1.11")
    run = tmp_path / "r"
    run.mkdir()
    (run / "config.json").write_text(json.dumps({"rules": "v1.11"}))
    with pytest.raises(LayoutRefused, match="layout 6"):
        PolicyBot.from_run(run, "v1.11")


def test_selfplay_is_refused_on_layout_6(tmp_path):
    with pytest.raises(LayoutRefused, match="layout 6"):
        train_selfplay("x", 100, rules="v1.11", runs_dir=tmp_path)
    assert not list(tmp_path.iterdir())


def test_finetune_is_refused_on_layout_6(tmp_path):
    with pytest.raises(LayoutRefused, match="layout 6"):
        finetune_online(tmp_path / "src", tmp_path / "out", 10, "random", rules="v1.11")
    assert not (tmp_path / "out").exists()


def test_offline_is_refused_on_layout_6(tmp_path):
    with pytest.raises(LayoutRefused, match="layout 6"):
        train_offline_run(tmp_path / "d.parquet", "x", runs_dir=tmp_path, rules="v1.11", steps=1)
    assert not list(tmp_path.iterdir())


def test_train_is_refused_on_layout_6():
    with pytest.raises(LayoutRefused, match="layout 6"):
        train(10, rules="v1.11")



@pytest.mark.parametrize(("rules", "made_layout"), [("v1.11", 2), ("v1.11", 5), ("v1.10", 6)])
def test_run_with_another_layout_is_rejected(tmp_path, rules, made_layout):
    run = tmp_path / "r"
    run.mkdir()
    rs = load_ruleset(rules)
    config = {"rules": rules, "layout": made_layout, "vector_names": vector_names(rs)}
    (run / "config.json").write_text(json.dumps(config))
    with pytest.raises(LayoutMismatch) as err:
        load_model(run, rules)
    assert f"layout {made_layout}" in str(err.value)
    assert f"layout {observation_layout(rs)}" in str(err.value)
