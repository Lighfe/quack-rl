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
