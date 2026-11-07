"""BC variants: label smoothing over the legal actions and an entropy bonus (#290)."""

import math

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from quack_rl.rl.dataset import Dataset  # noqa: E402
from quack_rl.rl.offline import (  # noqa: E402
    masked,
    masked_entropy,
    smoothed_target,
    train_bc,
)

# train_bc(synthetic(), epochs=4, seed=3, batch_size=32).curve, computed with the code at
# commit 760850a (before the variants existed).
REFERENCE_CURVE = [1.221710443496704, 1.1399729251861572, 1.08459476629893, 1.0335424542427063]


def synthetic(n: int = 96, obs_dim: int = 12, n_actions: int = 6, seed: int = 0) -> Dataset:
    """Random observations, random masks (at least one legal action per row) and a random legal
    stored action per row."""
    rng = np.random.default_rng(seed)
    obs = rng.normal(size=(n, obs_dim)).astype(np.float32)
    mask = (rng.random((n, n_actions)) < 0.5).astype(np.int8)
    mask[np.arange(n), rng.integers(n_actions, size=n)] = 1
    action = np.array([rng.choice(np.flatnonzero(m)) for m in mask], dtype=np.int64)
    terminated = np.zeros(n, dtype=bool)
    terminated[-1] = True
    return Dataset(
        obs=obs,
        action=action,
        reward=np.zeros(n, np.float32),
        next_obs=obs.copy(),
        terminated=terminated,
        mask=mask,
        next_mask=mask.copy(),
        episode=np.zeros(n, np.int32),
    )


def test_default_curve_is_unchanged():
    policy = train_bc(synthetic(), epochs=4, seed=3, batch_size=32)
    assert policy.curve == pytest.approx(REFERENCE_CURVE, abs=1e-6)


def test_smoothed_target_sums_to_one_and_is_zero_on_illegal_actions():
    mask = torch.tensor([[1, 1, 0, 1, 0], [0, 0, 1, 0, 0], [1, 1, 1, 1, 1]], dtype=torch.int8)
    action = torch.tensor([3, 2, 0])
    target = smoothed_target(action, mask, 0.1)
    assert torch.allclose(target.sum(1), torch.ones(3, dtype=target.dtype))
    assert (target[mask == 0] == 0).all()
    assert target[0].tolist() == pytest.approx([0.05, 0.05, 0.0, 0.9, 0.0])
    assert target[1].tolist() == pytest.approx([0.0, 0.0, 1.0, 0.0, 0.0])  # only one legal
    assert target[2].tolist() == pytest.approx([0.9, 0.025, 0.025, 0.025, 0.025])
    assert smoothed_target(action, mask, 0.0)[0].tolist() == [0.0, 0.0, 0.0, 1.0, 0.0]


def test_entropy_is_finite_and_zero_with_one_legal_action():
    mask = torch.tensor([[0, 0, 1, 0], [1, 1, 1, 1], [1, 0, 1, 0]], dtype=torch.int8)
    logits = torch.tensor([[3.0, -2.0, 0.5, 9.0], [0.0, 0.0, 0.0, 0.0], [1.0, 5.0, 1.0, -4.0]])
    logits.requires_grad_(True)
    entropy = masked_entropy(masked(logits, mask), mask)
    assert torch.isfinite(entropy).all()
    assert entropy[0].item() == 0.0
    assert entropy[1].item() == pytest.approx(math.log(4))
    assert entropy[2].item() == pytest.approx(math.log(2))
    entropy.sum().backward()
    assert torch.isfinite(logits.grad).all()


def test_entropy_bonus_raises_the_policy_entropy():
    data = synthetic()
    entropies = {}
    for coef in (0.0, 0.5):
        policy = train_bc(data, epochs=6, seed=1, batch_size=32, entropy_coef=coef)
        entropies[coef] = policy.entropy_curve[-1]
        assert len(policy.entropy_curve) == 6
        assert all(math.isfinite(x) for x in policy.entropy_curve + policy.curve)
    assert entropies[0.5] > entropies[0.0]


def test_label_smoothing_trains_and_curve_is_the_minimized_loss():
    data = synthetic()
    plain = train_bc(data, epochs=2, seed=0, batch_size=32)
    smooth = train_bc(data, epochs=2, seed=0, batch_size=32, label_smoothing=0.2)
    assert len(smooth.curve) == 2 and all(math.isfinite(x) for x in smooth.curve)
    # same seed, so the same start weights and batches: the curve is the smoothed loss
    assert smooth.curve[0] != plain.curve[0]


def test_on_epoch_end_counts_epochs_from_one():
    seen = []
    train_bc(synthetic(), epochs=3, seed=0, on_epoch_end=lambda e, net: seen.append((e, net)))
    assert [e for e, _ in seen] == [1, 2, 3]
    assert all(isinstance(net, torch.nn.Module) for _, net in seen)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"label_smoothing": -0.1},
        {"label_smoothing": 1.0},
        {"label_smoothing": 1.5},
        {"entropy_coef": -0.01},
    ],
)
def test_bad_variant_settings_raise(kwargs):
    with pytest.raises(ValueError):
        train_bc(synthetic(), epochs=1, **kwargs)
