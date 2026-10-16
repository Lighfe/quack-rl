"""Tests for `finetune_online` (issue #94). Light: at most 256 steps, at most 4 games."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import pytest

pytest.importorskip("sb3_contrib", reason="needs the train group: uv sync --group train")
import torch  # noqa: E402

from quack_rl.rl import PolicyBot, evaluate  # noqa: E402
from quack_rl.rl.finetune import finetune_online  # noqa: E402
from quack_rl.rl.offline import train_offline_run  # noqa: E402
from quack_rl.rl.runs import load_model  # noqa: E402

SAMPLE = Path(__file__).parent / "fixtures" / "dataset" / "sample.parquet"


@pytest.fixture(scope="module")
def source(tmp_path_factory):
    runs = tmp_path_factory.mktemp("source")
    train_offline_run(SAMPLE, "bc", runs, seed=0, steps=20, log_every=10)
    return runs / "bc"


@pytest.fixture(scope="module")
def tuned(source, tmp_path_factory):
    out = tmp_path_factory.mktemp("tuned") / "ft"
    before = _hash(source / "model.zip")
    finetune_online(source, out, 256, "random", seed=1)
    return out, before


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _params(model):
    return {k: v.clone() for k, v in model.policy.state_dict().items()}


def test_new_run_folder_loads_as_a_policy_bot(source, tuned):
    out, _ = tuned
    assert (out / "model.zip").is_file()
    config = json.loads((out / "config.json").read_text())
    source_config = json.loads((source / "config.json").read_text())
    assert config.pop("finetune") == {
        "steps": 256,
        "opponent": "random",
        "seed": 1,
        "learning_rate": 1e-4,
    }
    assert config == source_config
    bot = PolicyBot.from_run(out, "v1.1")
    result = evaluate(bot.policy, "random", "v1.1", 2, 0)
    assert result.wins + result.draws + result.losses == 2


def test_start_point_is_the_source_policy(source):
    # right after loading, before any update, the greedy actions are the source's
    obs = np.stack(pq.read_table(SAMPLE, columns=["obs"])["obs"].to_pylist()[:20]).astype(
        np.float32
    )
    mask = np.stack(pq.read_table(SAMPLE, columns=["action_mask"])["action_mask"].to_pylist()[:20])
    a, b = load_model(source, "v1.1"), load_model(source, "v1.1")
    for o, m in zip(obs, mask, strict=True):
        m = m.astype(bool)
        assert a.predict(o, action_masks=m, deterministic=True)[0] == b.predict(
            o, action_masks=m, deterministic=True
        )[0]
    assert all(torch.equal(v, _params(b)[k]) for k, v in _params(a).items())


def test_parameters_change_and_source_stays(source, tuned):
    out, hash_before = tuned
    old, new = _params(load_model(source, "v1.1")), _params(load_model(out, "v1.1"))
    assert any(not torch.equal(old[k], new[k]) for k in old)
    assert _hash(source / "model.zip") == hash_before


@pytest.mark.parametrize(
    "kwargs, error",
    [
        ({"opponent": "no-such-bot"}, ValueError),
        ({"steps": 0}, ValueError),
    ],
)
def test_refusals_before_training(source, tmp_path, kwargs, error):
    args = {"steps": 128, "opponent": "random", **kwargs}
    out = tmp_path / "out"
    with pytest.raises(error):
        finetune_online(source, out, **args)
    assert not out.exists()


def test_existing_non_empty_out_dir_is_refused(source, tmp_path):
    (tmp_path / "keep.txt").write_text("x")
    with pytest.raises(FileExistsError):
        finetune_online(source, tmp_path, 128, "random")
    assert [p.name for p in tmp_path.iterdir()] == ["keep.txt"]
