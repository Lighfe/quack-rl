"""Observation layout 3 (rules v1.8): vector, mask, layout 2 unchanged, layout mismatch."""

import json
import random
from pathlib import Path

import numpy as np
import pytest

from quack_rl.engine import (
    RngChance,
    action_names,
    legal_actions,
    needs_actions,
    new_game,
    step,
)
from quack_rl.engine.state import Phase, Status
from quack_rl.rl import (
    PolicyBot,
    action_mask,
    map_slice,
    observation_bounds,
    observation_layout,
    observe,
    vector_names,
    vectorize,
)
from quack_rl.rl.derive import derived_names
from quack_rl.rl.runs import LayoutMismatch, load_model
from quack_rl.rules import load_ruleset

SAMPLE = Path(__file__).parent / "fixtures" / "layout2" / "sample.npz"
RS8 = load_ruleset("v1.8")
RS11 = load_ruleset("v1.1")


def states(rs, seed):
    rng = random.Random(seed)
    chance = RngChance(seed)
    state = new_game(rs)
    yield state
    while state.phase is not Phase.GAME_OVER:
        actions = (
            {s: rng.choice(legal_actions(state, rs, s)) for s in ("p1", "p2")}
            if needs_actions(state)
            else None
        )
        state = step(state, rs, actions, chance).state
        yield state


def test_layout_numbers():
    assert observation_layout(RS8) == 3
    assert observation_layout(RS11) == 2
    assert observation_layout(load_ruleset("v1")) == 2


def test_vector_names_v1_8_length_and_order():
    names = vector_names(RS8)
    old = vector_names(RS11)
    assert len(names) == 851 == len(old) + 3
    assert len(set(names)) == len(names)
    phase = [n for n in names if n.startswith("phase.")]
    assert phase == [f"phase.{p}" for p in ("brew", "resolve", "choice", "shop", "game_over")]
    assert names[:3] == ["round", "rounds", "explosion_limit"]
    first = names.index(derived_names(RS8)[0])
    block = names[first : first + len(derived_names(RS8))]
    assert block == [*derived_names(), "own.field_points", "last_round"]
    assert block[-3] == "point_delta"
    sl = map_slice(RS8)
    assert first + len(block) == sl.start
    assert sl.stop == len(names)
    assert names[sl.start] == "map.0.money"
    # layout 2 content stays: removing the three new entries gives the v1.1 names
    drop = {"phase.choice", "own.field_points", "last_round"}
    assert [n for n in names if n not in drop] == old


def test_new_entries_values_and_bounds():
    names = vector_names(RS8)
    lo, hi = observation_bounds(RS8)
    assert len(lo) == len(hi) == len(names)
    for state in states(RS8, 4):
        for seat in ("p1", "p2"):
            vec = vectorize(observe(state, RS8, seat), RS8)
            assert vec.shape == (len(names),)
            assert np.all(vec >= lo) and np.all(vec <= hi)
            v = dict(zip(names, vec, strict=True))
            from quack_rl.engine.state import scoring_field

            fld = scoring_field(state.players[seat].field, RS8)
            assert v["own.field_points"] == RS8.points[fld]
            assert v["last_round"] == float(state.round == RS8.rounds)
            assert v["phase.choice"] == float(state.phase is Phase.CHOICE)


def test_choice_phase_is_reached():
    assert any(s.phase is Phase.CHOICE for seed in range(10) for s in states(RS8, seed))


def test_action_space_has_two_more_actions():
    """Exactly two actions are new. The three point items of the v1.1 shop are gone in v1.8
    (rules), so the total is 14 against 15; the shop actions of v1.8 are a subset of v1.1."""
    a8, a11 = action_names(RS8), action_names(RS11)
    assert [a for a in a8 if a not in a11] == ["take_money", "take_points"]
    assert [a for a in a11 if a not in a8] == ["buy:points_2", "buy:points_5", "buy:points_10"]


def test_mask_in_choice_and_elsewhere():
    names = action_names(RS8)
    seen_choice = set()
    for seed in range(10):
        for state in states(RS8, seed):
            for seat in ("p1", "p2"):
                mask = action_mask(state, RS8, seat)
                legal = {n for n, m in zip(names, mask, strict=True) if m}
                assert legal == set(legal_actions(state, RS8, seat))
                new = legal & {"take_money", "take_points"}
                if state.phase is Phase.CHOICE:
                    if state.players[seat].status is Status.EXPLODED:
                        assert legal == {"take_money", "take_points"}
                        seen_choice.add("exploded")
                    else:
                        assert legal == {"wait"}
                        seen_choice.add("waiting")
                else:
                    assert not new
    assert seen_choice == {"exploded", "waiting"}


@pytest.mark.parametrize("version", ["v1", "v1.1", "v1.8", "v1.9"])
def test_layout2_output_equals_stored_sample(version):
    rs = load_ruleset(version)
    data = np.load(SAMPLE)
    vecs, masks = [], []
    for seed in (1, 2, 3):
        for state in states(rs, seed):
            for seat in ("p1", "p2"):
                vecs.append(vectorize(observe(state, rs, seat), rs))
                masks.append(action_mask(state, rs, seat))
    assert np.array_equal(np.stack(vecs), data[f"{version}_vectors"])
    assert np.array_equal(np.stack(masks), data[f"{version}_masks"])


def fake_run(path, rules):
    path.mkdir(parents=True)
    rs = load_ruleset(rules)
    config = {
        "rules": rules,
        "layout": observation_layout(rs),
        "vector_names": vector_names(rs),
    }
    (path / "config.json").write_text(json.dumps(config))
    return path


@pytest.mark.parametrize(("made", "loaded"), [("v1.1", "v1.8"), ("v1.8", "v1.1")])
def test_run_with_other_layout_is_refused(tmp_path, made, loaded):
    run = fake_run(tmp_path / "r", made)
    layouts = {"v1.1": 2, "v1.8": 3}
    with pytest.raises(LayoutMismatch) as err:
        load_model(run, loaded)
    assert f"layout {layouts[made]}" in str(err.value)
    assert f"layout {layouts[loaded]}" in str(err.value)
    with pytest.raises(LayoutMismatch) as err:
        PolicyBot.from_run(run, loaded)
    assert f"layout {layouts[made]}" in str(err.value)
    assert f"layout {layouts[loaded]}" in str(err.value)
