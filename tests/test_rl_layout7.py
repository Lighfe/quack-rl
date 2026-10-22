"""Observation layout 7 (rules v2): layout choice, points in the map, refusals."""

import json
import random

import numpy as np
import pytest

from quack_rl.engine import RngChance, legal_actions, needs_actions, new_game, step
from quack_rl.engine.state import Phase
from quack_rl.rl import (
    PolicyBot,
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
from quack_rl.rl.encode import BOARD_LAYOUT, LayoutRefused, map_colours
from quack_rl.rl.finetune import finetune_online
from quack_rl.rl.offline import train_offline_run
from quack_rl.rl.selfplay import train_selfplay
from quack_rl.rl.train import train
from quack_rl.rules import load_ruleset

RS2 = load_ruleset("v2")
RS11 = load_ruleset("v1.11")
SEATS = ("p1", "p2")


def states(seed, rs=RS2):
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


def test_layout_numbers():
    assert BOARD_LAYOUT == 7
    assert observation_layout(RS2) == 7
    assert observation_layout(RS11) == 6
    # the board is checked before the cards
    assert RS2.cards
    assert observation_layout(RS2.model_copy(update={"point_board": None})) == 6


def test_layout_7_uses_what_layout_6_uses():
    assert map_colours(RS2) == map_colours(RS11) == 8
    assert map_channels(RS2) == map_channels(RS11) + 1
    names2, names11 = vector_names(RS2), vector_names(RS11)
    assert "phase.card" in names2 and "card.ruby_double" in names2
    assert len(set(names2)) == len(names2)


def test_map_points_names_and_values_equal_the_table():
    names = vector_names(RS2)
    sl = map_slice(RS2)
    assert sl.stop == len(names)
    assert sl.stop - sl.start == (RS2.track_end + 1) * map_channels(RS2)
    state = new_game(RS2)
    v = dict(zip(names, vectorize(observe(state, RS2, "p1"), RS2), strict=True))
    for f in range(RS2.track_end + 1):
        i = names.index(f"map.{f}.money")
        assert names[i + 1] == f"map.{f}.points"
        assert names[i + 2] == f"map.{f}.ruby"
        assert v[f"map.{f}.points"] == RS2.points[f]


def test_map_points_are_zero_without_a_points_table():
    rs = RS2.model_copy(update={"points": None})
    names = vector_names(rs)
    v = dict(zip(names, vectorize(observe(new_game(rs), rs, "p1"), rs), strict=True))
    assert all(v[f"map.{f}.points"] == 0 for f in range(rs.track_end + 1))
    lo, hi = observation_bounds(rs)
    assert len(lo) == len(hi) == len(names)


def test_bounds_cover_masked_games():
    names = vector_names(RS2)
    lo, hi = observation_bounds(RS2)
    assert len(lo) == len(hi) == len(names)
    i = names.index("map.3.points")
    assert hi[i] == max(RS2.points)
    for seed in range(4):
        for state in states(seed):
            for seat in SEATS:
                vec = vectorize(observe(state, RS2, seat), RS2)
                assert len(vec) == len(names)
                assert np.all(vec >= lo) and np.all(vec <= hi)


def test_older_layouts_are_unchanged():
    for version in ("v1", "v1.1", "v1.8", "v1.9", "v1.10", "v1.11"):
        rs = load_ruleset(version)
        assert not any(n.endswith(".points") and n.startswith("map.") for n in vector_names(rs))
        assert map_channels(rs) == 2 + 2 * (map_colours(rs) + 2)


def test_baseline_bots_evaluate_on_v2():
    result = evaluate(random_policy(0), "draw20-pts1-points", rules="v2", games=2, seed=0, reads_observation=False)
    assert result.games == 2 == result.wins + result.draws + result.losses


def test_evaluate_with_a_policy_is_refused_on_layout_7():
    with pytest.raises(LayoutRefused, match="layout 7") as err:
        evaluate(random_policy(0), "random", rules="v2", games=1)
    assert isinstance(err.value, ValueError)


def test_policy_bot_is_refused_on_layout_7(tmp_path):
    with pytest.raises(LayoutRefused, match="layout 7"):
        PolicyBot(lambda o, m: 0, "v2")
    run = tmp_path / "r"
    run.mkdir()
    (run / "config.json").write_text(json.dumps({"rules": "v2"}))
    with pytest.raises(LayoutRefused, match="layout 7"):
        PolicyBot.from_run(run, "v2")


def test_selfplay_is_refused_on_layout_7(tmp_path):
    with pytest.raises(LayoutRefused, match="layout 7"):
        train_selfplay("x", 100, rules="v2", runs_dir=tmp_path)
    assert not list(tmp_path.iterdir())


def test_finetune_is_refused_on_layout_7(tmp_path):
    with pytest.raises(LayoutRefused, match="layout 7"):
        finetune_online(tmp_path / "src", tmp_path / "out", 10, "random", rules="v2")
    assert not (tmp_path / "out").exists()


def test_offline_is_refused_on_layout_7(tmp_path):
    with pytest.raises(LayoutRefused, match="layout 7"):
        train_offline_run(tmp_path / "d.parquet", "x", runs_dir=tmp_path, rules="v2", steps=1)
    assert not list(tmp_path.iterdir())


def test_train_is_refused_on_layout_7():
    with pytest.raises(LayoutRefused, match="layout 7"):
        train(10, rules="v2")
