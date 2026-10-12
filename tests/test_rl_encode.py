import copy
import random

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
from quack_rl.engine.state import Phase
from quack_rl.rl import action_mask, observe, reward, vector_names, vectorize
from quack_rl.rules import load_ruleset

VERSIONS = ["v1", "v1.1"]


def random_game(rs, seed):
    """Yield every state of a random game, the last one included."""
    rng = random.Random(seed)
    chance = RngChance(seed)
    state = new_game(rs)
    yield state
    while state.phase is not Phase.GAME_OVER:
        if needs_actions(state):
            actions = {s: rng.choice(legal_actions(state, rs, s)) for s in ("p1", "p2")}
        else:
            actions = None
        state = step(state, rs, actions, chance).state
        yield state


@pytest.mark.parametrize("version", VERSIONS)
def test_action_mask_equals_legal_actions_at_every_step(version):
    rs = load_ruleset(version)
    names = action_names(rs)
    for seed in range(5):
        for state in random_game(rs, seed):
            for seat in ("p1", "p2"):
                mask = action_mask(state, rs, seat)
                assert mask.dtype == np.int8
                assert len(mask) == len(names)
                got = [n for n, m in zip(names, mask, strict=True) if m]
                assert got == [n for n in names if n in legal_actions(state, rs, seat)]


@pytest.mark.parametrize("version", VERSIONS)
def test_vector_layout_depends_only_on_ruleset(version):
    rs = load_ruleset(version)
    names = vector_names(rs)
    assert len(set(names)) == len(names)
    for state in random_game(rs, 1):
        for seat in ("p1", "p2"):
            vec = vectorize(observe(state, rs, seat), rs)
            assert vec.dtype == np.float32
            assert vec.shape == (len(names),)


def test_layout_differs_between_rulesets_only_by_ruleset():
    assert vector_names(load_ruleset("v1")) == vector_names(load_ruleset("v1"))


@pytest.mark.parametrize("version", VERSIONS)
def test_observation_is_mirrored_between_seats(version):
    rs = load_ruleset(version)
    for state in random_game(rs, 3):
        swapped = copy.deepcopy(state)
        swapped.players = {"p1": state.players["p2"], "p2": state.players["p1"]}
        assert observe(state, rs, "p1") == observe(swapped, rs, "p2")
        o1 = observe(state, rs, "p1")
        o2 = observe(state, rs, "p2")
        assert o1["own"] == o2["opponent"]
        assert o1["opponent"] == o2["own"]


def test_observation_content():
    rs = load_ruleset("v1")
    state = new_game(rs)
    obs = observe(state, rs, "p1")
    assert obs["round"] == 1
    assert obs["phase"] == "brew"
    assert obs["own_bag"]["white_1"] == 4
    assert set(obs["own"]) >= {
        "placed",
        "field",
        "money",
        "white_total",
        "ruby_fields_ahead",
        "points",
        "status",
        "droplet_halves",
        "purchases",
        "chip_colours",
    }
    assert "own_bag" not in obs["opponent"] and "bag" not in obs["opponent"]
    assert obs["own"]["ruby_fields_ahead"] == len(rs.rubies)
    state.players["p1"].field = 12  # scoring field 13: rubies 13.. are ahead
    assert observe(state, rs, "p1")["own"]["ruby_fields_ahead"] == len(rs.rubies) - 2


@pytest.mark.parametrize("version", VERSIONS)
def test_no_hidden_information(version):
    rs = load_ruleset(version)
    for state in random_game(rs, 2):
        shuffled = copy.deepcopy(state)
        for p in shuffled.players.values():
            items = list(p.bag.items())
            random.Random(7).shuffle(items)
            p.bag = dict(reversed(items))
        for seat in ("p1", "p2"):
            a = observe(state, rs, seat)
            b = observe(shuffled, rs, seat)
            assert a == b
            assert np.array_equal(vectorize(a, rs), vectorize(b, rs))


def test_opponent_bag_is_not_in_the_vector():
    rs = load_ruleset("v1")
    state = new_game(rs)
    changed = copy.deepcopy(state)
    changed.players["p2"].bag["white_1"] = 1
    assert np.array_equal(
        vectorize(observe(state, rs, "p1"), rs), vectorize(observe(changed, rs, "p1"), rs)
    )


def test_reward_win_loss_draw():
    rs = load_ruleset("v1")
    state = new_game(rs)
    state.players["p1"].points = 10
    state.players["p2"].points = 4
    assert reward(state, "p1") == 1.0
    assert reward(state, "p2") == -1.0
    state.players["p2"].points = 10
    assert reward(state, "p1") == 0.0
    assert reward(state, "p2") == 0.0
