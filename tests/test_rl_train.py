import dataclasses
import sys

import numpy as np
import pytest

from quack_rl.rl.train import TrainResult, train

EVALS = ("baseline_random", "baseline_untrained", "trained_sampled", "trained_greedy")
EPISODE_KEYS = {
    "episode", "timestep", "result", "points_own", "points_opponent", "explosions_own", "decisions",
}  # fmt: skip


def test_bad_input_fails_before_training():
    with pytest.raises(ValueError):
        train(256, opponent="nonsense", eval_games=10)
    with pytest.raises(ValueError):
        train(256, eval_games=0)


def test_missing_train_group_names_the_install_command(monkeypatch):
    monkeypatch.setitem(sys.modules, "sb3_contrib", None)
    with pytest.raises(ImportError, match="uv sync --group train"):
        train(256, eval_games=1)


def test_result_field_names():
    names = {f.name for f in dataclasses.fields(TrainResult)}
    expected = {"model", "log", "games_played", *EVALS, *(f"{e}_vs_random" for e in EVALS)}
    assert names == expected


@pytest.fixture
def needs_train():
    return pytest.importorskip("sb3_contrib", reason="needs the train group: uv sync --group train")


class Recorder:
    def __init__(self):
        self.calls = []

    def start(self, config):
        self.calls.append(("start", config))

    def episode(self, row):
        self.calls.append(("episode", row))

    def metrics(self, row):
        self.calls.append(("metrics", row))

    def finish(self, result):
        self.calls.append(("finish", result))


@pytest.fixture(scope="module")
def run():
    pytest.importorskip("sb3_contrib", reason="needs the train group: uv sync --group train")
    sink = Recorder()
    return train(256, eval_games=10, sink=sink), sink


@pytest.mark.usefixtures("needs_train")
def test_train_smoke(run):
    result, _ = run
    assert isinstance(result, TrainResult)
    assert result.games_played == len(result.log.episodes) > 0
    for name in EVALS:
        assert getattr(result, name).games == 10
        assert getattr(result, f"{name}_vs_random") is None


@pytest.mark.usefixtures("needs_train")
@pytest.mark.slow
def test_train_is_fast_enough():
    import time

    start = time.perf_counter()
    train(256, eval_games=10)
    assert time.perf_counter() - start < 60


@pytest.mark.usefixtures("needs_train")
def test_episode_and_metric_rows(run):
    result, _ = run
    eps = result.log.episodes
    assert all(set(r) == EPISODE_KEYS for r in eps)
    assert [r["episode"] for r in eps] == list(range(1, len(eps) + 1))
    stamps = [r["timestep"] for r in eps]
    assert stamps == sorted(stamps)
    assert result.log.metrics
    allowed = {"timestep", "policy_gradient_loss", "value_loss", "entropy_loss", "approx_kl",
               "explained_variance"}  # fmt: skip
    for row in result.log.metrics:
        assert "timestep" in row and set(row) <= allowed and len(row) > 1


@pytest.mark.usefixtures("needs_train")
def test_sink_order_and_rows(run):
    result, sink = run
    kinds = [k for k, _ in sink.calls]
    assert kinds[0] == "start" and kinds[-1] == "finish" and kinds.count("finish") == 1
    assert kinds.count("start") == 1
    assert [r for k, r in sink.calls if k == "episode"] == result.log.episodes
    assert [r for k, r in sink.calls if k == "metrics"] == result.log.metrics
    config = sink.calls[0][1]
    assert {"steps", "rules", "opponent", "seed", "eval_games"} <= set(config)


@pytest.mark.usefixtures("needs_train")
def test_untrained_policy_samples_and_respects_mask(run):
    from sb3_contrib import MaskablePPO

    from quack_rl.rl.single_env import QuackEnv
    from quack_rl.rl.train import sb3_policy

    env = QuackEnv()
    model = MaskablePPO("MlpPolicy", env, device="cpu", seed=0)
    obs, info = env.reset(seed=0)
    obs, _, _, _, info = env.step(int(np.flatnonzero(info["action_mask"])[0]))
    mask = info["action_mask"]
    assert mask.sum() > 1
    policy = sb3_policy(model, deterministic=False)
    actions = {policy(obs, mask) for _ in range(200)}
    assert len(actions) > 1
    assert all(mask[a] for a in actions)
    greedy = sb3_policy(model, deterministic=True)
    assert mask[greedy(obs, mask)] and np.isscalar(greedy(obs, mask))


@pytest.mark.usefixtures("needs_train")
def test_second_opponent_runs_vs_random():
    result = train(128, opponent="draw20-pts4-blue", eval_games=4)
    for name in EVALS:
        assert getattr(result, name).games == 4
        assert getattr(result, f"{name}_vs_random").games == 4


def test_baseline_wording():
    import pathlib

    text = pathlib.Path("src/quack_rl/rl/train.py").read_text().lower()
    for line in text.splitlines():
        if "baseline" in line:
            assert "argmax" not in line and "greedy" not in line
