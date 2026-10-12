"""Tests for the logic of the marimo notebook notebooks/rl_env.py (issue #53)."""

import importlib.util
from pathlib import Path

import pytest

from quack_rl.engine import action_names
from quack_rl.rl import vector_names

NOTEBOOK = Path(__file__).resolve().parent.parent / "notebooks" / "rl_env.py"


@pytest.fixture(scope="module")
def nb():
    spec = importlib.util.spec_from_file_location("rl_env_notebook", NOTEBOOK)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cells_1_and_2_create_reset_and_step(nb):
    env = nb.make_env()
    obs, info = env.reset(seed=0)

    named = nb.named_observation(env, obs)
    assert list(named) == vector_names(env.rs)
    assert set(nb.legal_names(env, info["action_mask"])) <= set(action_names(env.rs))
    legal = nb.legal_names(env, info["action_mask"])
    assert legal

    obs2, reward, done, mask = nb.step_named(env, legal[0])
    assert list(nb.named_observation(env, obs2)) == vector_names(env.rs)
    assert reward in (0.0, 1.0, -1.0)
    assert done is False
    assert mask.shape == info["action_mask"].shape
    assert nb.legal_names(env, mask)  # a real decision follows


def test_random_steps_reach_the_end_with_a_zero_mask(nb):
    env = nb.make_env()
    _, info = env.reset(seed=1)
    mask, done, reward = info["action_mask"], False, 0.0
    while not done:
        _, reward, done, mask = nb.step_named(env, nb.legal_names(env, mask)[0])
    assert reward in (-1.0, 0.0, 1.0)
    assert nb.legal_names(env, mask) == []


def test_train_installed_is_a_bool(nb):
    assert isinstance(nb.train_installed(), bool)


def test_training_runs_for_a_few_hundred_steps(nb):
    pytest.importorskip("sb3_contrib")
    from sb3_contrib import MaskablePPO

    env = nb.make_env()
    model = MaskablePPO("MlpPolicy", env, n_steps=64, batch_size=64, seed=0, device="cpu")
    model.learn(total_timesteps=256)
    rate = nb.win_rate(nb.make_env(), model, games=3)
    assert 0.0 <= rate <= 1.0
