import math

import numpy as np
import pytest

pytest.importorskip("torch")

from quack_rl.rl.dataset import ARRAYS, Dataset, build_dataset, concat_files  # noqa: E402
from quack_rl.rl.evaluate import evaluate  # noqa: E402
from quack_rl.rl.offline import train_bc, train_cql  # noqa: E402

BOT = "bot:draw20-pts1-points"


@pytest.fixture(scope="module")
def data() -> Dataset:
    return build_dataset(BOT, "bot:random", 10, seed=0)


def test_shapes_and_terminal_rewards(data):
    n = len(data)
    assert n > 10 and data.obs.shape == data.next_obs.shape and data.obs.shape[0] == n
    assert data.mask.shape == data.next_mask.shape == (n, 88)
    assert data.action.shape == data.reward.shape == data.terminated.shape == (n,)
    last = np.append(data.episode[1:] != data.episode[:-1], True)
    assert (data.terminated == last).all() and last.sum() == 10
    assert set(data.reward[last]) <= {-1.0, 0.0, 1.0}
    assert (data.reward[~last] == 0).all()
    assert (data.next_mask[last] == 0).all() and (data.next_mask[~last].sum(1) > 0).all()


def test_stored_actions_are_legal(data):
    assert data.mask[np.arange(len(data)), data.action].all()
    assert (
        data.mask[1:][~data.terminated[:-1]] == data.next_mask[:-1][~data.terminated[:-1]]
    ).all()


def test_save_load_round_trip_and_same_seed(data, tmp_path):
    data.save(tmp_path / "d.npz")
    back = Dataset.load(tmp_path / "d.npz")
    again = build_dataset(BOT, "bot:random", 10, seed=0)
    for name in ARRAYS:
        assert np.array_equal(getattr(back, name), getattr(data, name))
        assert np.array_equal(getattr(again, name), getattr(data, name))
    with pytest.raises(FileNotFoundError):
        Dataset.load(tmp_path / "missing.npz")


def test_concat_and_stats(data):
    both = data.concat(data)
    assert len(both) == 2 * len(data)
    stats = both.stats()
    assert stats["games"] == 20 and stats["steps"] == 2 * len(data)
    assert sum(stats["action_histogram"]) == stats["steps"]
    assert stats["mean_return"] == pytest.approx(data.stats()["mean_return"])


def test_bc_and_cql_train_and_play(data):
    bc = train_bc(data, epochs=1, seed=0)
    cql = train_cql(data, steps=20, seed=0)
    assert len(bc.curve) == 1 and len(cql.curve) == 20
    assert all(math.isfinite(x) for x in bc.curve + cql.curve)
    for policy in (bc, cql):
        result = evaluate(policy, "bot:random", games=4, seed=0)
        assert result.wins + result.draws + result.losses == 4


def test_concat_files_equals_load_concat(data, tmp_path):
    data.save(tmp_path / "a.npz")
    other = build_dataset(BOT, BOT, 3, seed=50)
    other.save(tmp_path / "b.npz")
    concat_files([tmp_path / "a.npz", tmp_path / "b.npz"], tmp_path / "ab.npz")
    joined, expected = Dataset.load(tmp_path / "ab.npz"), data.concat(other)
    for name in ARRAYS:
        assert np.array_equal(getattr(joined, name), getattr(expected, name))
