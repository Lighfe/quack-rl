"""Tests for the replay-buffer DQN (issue #95). Light: at most 20 offline and 40 online steps."""

from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

pytest.importorskip("torch", reason="needs the train group: uv sync --group train")
import torch  # noqa: E402

from quack_rl.rl.encode import vector_names  # noqa: E402
from quack_rl.rl.replay_dqn import (  # noqa: E402
    FIELDS,
    ReplayBuffer,
    greedy_action,
    make_policy,
    td_target,
    train_dqn,
    transitions_from_dataset,
)
from quack_rl.rules import load_ruleset  # noqa: E402

SAMPLE = Path(__file__).parent / "fixtures" / "dataset" / "sample.parquet"
OBS_DIM = len(vector_names(load_ruleset("v1.1")))


@pytest.fixture(scope="module")
def trans():
    return transitions_from_dataset(SAMPLE, OBS_DIM)


def test_transitions_match_the_rows(trans):
    t = pq.read_table(SAMPLE, columns=["episode", "step", "terminal"])
    episode = t["episode"].to_numpy()
    n = t.num_rows
    assert set(trans) == set(FIELDS)
    assert all(len(trans[k]) == n for k in FIELDS)
    done = trans["done"]
    for e in np.unique(episode):
        assert done[episode == e].sum() == 1
    assert (done == t["terminal"].to_numpy(zero_copy_only=False)).all()
    inside = ~done
    idx = np.flatnonzero(inside)
    assert (trans["next_obs"][idx] == trans["obs"][idx + 1]).all()
    assert (trans["next_mask"][idx] == trans["mask"][idx + 1]).all()
    assert not trans["next_obs"][done].any() and not trans["next_mask"][done].any()
    assert trans["obs"].shape == (n, OBS_DIM) and trans["mask"].shape == (n, 15)


def test_rows_out_of_order_are_sorted(trans, tmp_path):
    table = pq.read_table(SAMPLE)
    perm = np.random.default_rng(0).permutation(table.num_rows)
    shuffled = tmp_path / "shuffled.parquet"
    pq.write_table(table.take(pa.array(perm)), shuffled)
    again = transitions_from_dataset(shuffled, OBS_DIM)
    for k in FIELDS:
        assert (again[k] == trans[k]).all()


def test_wrong_obs_length_is_a_value_error():
    with pytest.raises(ValueError, match="expected"):
        transitions_from_dataset(SAMPLE, 10)


def fill(buf, n, start=0):
    for i in range(start, start + n):
        buf.add(
            np.full(4, i, np.float32), np.ones(3, np.int8), i % 3, float(i),
            np.full(4, i + 1, np.float32), np.ones(3, np.int8), False,
        )  # fmt: skip


def small_offline(n=5):
    return {
        "obs": np.full((n, 4), -1, np.float32), "mask": np.ones((n, 3), np.int8),
        "action": np.zeros(n, np.int64), "reward": np.zeros(n, np.float32),
        "next_obs": np.full((n, 4), -1, np.float32), "next_mask": np.ones((n, 3), np.int8),
        "done": np.zeros(n, bool),
    }  # fmt: skip


def test_ring_never_overwrites_the_offline_part():
    buf = ReplayBuffer(4, 10, small_offline(5), n_actions=3)
    assert (buf.n_offline, buf.n_online, len(buf)) == (5, 0, 5)
    fill(buf, 25)
    assert buf.n_offline == 5 and buf.n_online == 10 and len(buf) == 15
    assert (buf._off["obs"] == -1).all()
    # the ring holds the newest 10 online transitions
    assert sorted(buf._on["reward"].tolist()) == [float(i) for i in range(15, 25)]
    batch = buf.sample(64, np.random.default_rng(0))
    stored = {-1.0, *map(float, range(15, 25))}
    assert set(batch["obs"][:, 0].tolist()) <= stored
    assert all(len(batch[k]) == 64 for k in FIELDS)


def test_partly_filled_ring_samples_only_stored_rows():
    buf = ReplayBuffer(4, 10, small_offline(2), n_actions=3)
    fill(buf, 3, start=100)
    batch = buf.sample(200, np.random.default_rng(1))
    assert set(batch["obs"][:, 0].tolist()) <= {-1.0, 100.0, 101.0, 102.0}
    only = buf.sample(50, np.random.default_rng(1), offline_only=True)
    assert (only["obs"] == -1).all()


def test_empty_offline_part_cannot_be_sampled():
    buf = ReplayBuffer(4, 3, None, n_actions=3)
    with pytest.raises(ValueError):
        buf.sample(4, np.random.default_rng(0), offline_only=True)
    with pytest.raises(ValueError):
        buf.sample(4, np.random.default_rng(0))


def test_target_and_policy_ignore_an_illegal_action():
    next_q = torch.tensor([[1.0, 2.0, 1e6], [1.0, 2.0, 1e6]])
    next_mask = torch.tensor([[1, 1, 0], [1, 1, 0]], dtype=torch.int8)
    reward = torch.tensor([0.5, 0.5])
    done = torch.tensor([False, True])
    target = td_target(next_q, reward, done, next_mask, gamma=0.9)
    assert target[0].item() == pytest.approx(0.5 + 0.9 * 2.0)
    assert target[1].item() == pytest.approx(0.5)  # done: no bootstrap
    assert greedy_action([1.0, 2.0, 1e6], [1, 1, 0]) == 1


def test_policy_of_a_network_masks_illegal_actions():
    net = torch.nn.Linear(4, 3)
    with torch.no_grad():
        net.weight.zero_()
        net.bias.copy_(torch.tensor([0.0, 1.0, 1e6]))
    policy = make_policy(net)
    assert policy(np.zeros(4, np.float32), np.array([1, 1, 0])) == 1
    assert policy(np.zeros(4, np.float32), np.array([1, 0, 1])) == 2


def test_short_run_finishes_with_finite_losses():
    seen = []
    q_net, rows, policy = train_dqn(
        SAMPLE, "random", offline_steps=20, online_steps=40, seed=0,
        after_offline=lambda p: seen.append(p),
    )  # fmt: skip
    assert len(rows) == 60 and [r["step"] for r in rows] == list(range(1, 61))
    assert all(np.isfinite(r["loss"]) for r in rows)
    assert [r["phase"] for r in rows] == ["offline"] * 20 + ["online"] * 40
    assert rows[19]["online_count"] == 0 and rows[-1]["online_count"] == 40
    assert rows[-1]["offline_count"] == pq.read_metadata(SAMPLE).num_rows
    assert len(seen) == 1 and callable(seen[0])
    assert tuple(q_net[-1].weight.shape) == (15, 256)

    from quack_rl.rl import QuackEnv, make_opponent

    env = QuackEnv(seat="p1", opponent=make_opponent("random", 3, "v1.1"))
    obs, info = env.reset(seed=3)
    done = False
    while not done:
        action = policy(obs, info["action_mask"])
        assert info["action_mask"][action]
        obs, _, done, _, info = env.step(action)
        assert not info["illegal_action"]


def test_same_seed_same_losses():
    a = train_dqn(SAMPLE, "random", 5, 5, seed=2)[1]
    b = train_dqn(SAMPLE, "random", 5, 5, seed=2)[1]
    assert [r["loss"] for r in a] == [r["loss"] for r in b]


def test_bad_arguments_fail_before_training(tmp_path):
    bad = tmp_path / "bad.parquet"
    pq.write_table(
        pa.table(
            {
                "obs": pa.array([[0.0] * 10], pa.list_(pa.float32())),
                "action_mask": pa.array([[1] * 15], pa.list_(pa.int8())),
                "action": pa.array([0], pa.int16()),
            }
        ),
        bad,
    )
    with pytest.raises(ValueError):
        train_dqn(bad, "random", 1, 1)
    with pytest.raises(ValueError):
        train_dqn(SAMPLE, "no-such-bot", 1, 1)
    with pytest.raises(ValueError):
        train_dqn(SAMPLE, "random", -1, 1)
