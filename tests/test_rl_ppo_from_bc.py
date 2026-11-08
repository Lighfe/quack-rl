"""Tests for PPO from BC weights and the critic warm-up (`quack_rl.rl.ppo_run`)."""

import hashlib
import json

import numpy as np
import pytest

from quack_rl.rl.experiment import ExperimentConfig
from quack_rl.rl.ppo_run import run_ppo_seed
from quack_rl.rl.selfplay import ResumeError


def p3(**overrides) -> ExperimentConfig:
    data = {
        "id": "P3",
        "kind": "ppo",
        "baseline": "P0",
        "changes": "actor from BC with a critic warm-up",
        "steps": 2048,
        "opponents": [{"spec": "bot:random"}],
        "checkpoint_every": 1024,
    }
    data.update(overrides)
    return ExperimentConfig.model_validate(data)


def _env():
    from quack_rl.rl import QuackEnv

    return QuackEnv()


def _bc_net(seed: int = 0, hidden: int = 256):
    import torch

    from quack_rl.rl.offline import make_mlp

    env = _env()
    torch.manual_seed(seed)
    return make_mlp(env.observation_space.shape[0], int(env.action_space.n), hidden)


def _write_bc(path, seed: int = 0) -> dict:
    import torch

    state = _bc_net(seed).state_dict()
    torch.save(state, path)
    return state


def _fresh_model(hidden: int = 256, seed: int = 0):
    from sb3_contrib import MaskablePPO

    from quack_rl.rl.ppo_run import policy_kwargs

    return MaskablePPO(
        "MlpPolicy", _env(), seed=seed, device="cpu", policy_kwargs=policy_kwargs(hidden)
    )


def _load(path):
    from sb3_contrib import MaskablePPO

    return MaskablePPO.load(str(path), device="cpu")


def _actor_state(model) -> dict:
    """The actor parameters of `model` under the BC state dict keys."""
    policy = model.policy
    net = policy.mlp_extractor.policy_net
    layers = {"0": net[0], "2": net[2], "4": policy.action_net}
    return {
        f"{prefix}.{name}": getattr(layer, name).detach().clone()
        for prefix, layer in layers.items()
        for name in ("weight", "bias")
    }


def _critic_params(model) -> list:
    policy = model.policy
    return [
        p.detach().clone()
        for p in [*policy.mlp_extractor.value_net.parameters(), *policy.value_net.parameters()]
    ]


def _equal(a: dict, b: dict) -> bool:
    import torch

    return a.keys() == b.keys() and all(torch.equal(a[k], b[k]) for k in a)


def _observations(count: int = 100):
    """`count` observations with their action masks from random legal play in `QuackEnv`."""
    env = _env()
    rng = np.random.default_rng(7)
    obs, _ = env.reset(seed=0)
    observations, masks = [], []
    while len(observations) < count:
        mask = env.action_masks()
        observations.append(obs)
        masks.append(mask)
        obs, _, done, truncated, _ = env.step(int(rng.choice(np.flatnonzero(mask))))
        if done or truncated:
            obs, _ = env.reset()
    return np.array(observations, dtype=np.float32), np.array(masks, dtype=bool)


# --- load_bc_into_actor ------------------------------------------------------------------------


def test_critic_warmup_not_a_multiple_raises_before_any_file(tmp_path):
    out = tmp_path / "run"
    with pytest.raises(ValueError, match="critic_warmup_steps"):
        run_ppo_seed(p3(critic_warmup_steps=1000), 0, out)
    assert not out.exists()


def test_missing_bc_file_raises_before_any_file(tmp_path):
    out = tmp_path / "run"
    with pytest.raises(FileNotFoundError, match="nothing.pt"):
        run_ppo_seed(p3(init_from_bc=str(tmp_path / "nothing.pt")), 0, out)
    assert not out.exists()


@pytest.mark.slow
def test_loaded_actor_gives_the_bc_masked_softmax():
    pytest.importorskip("sb3_contrib")
    import torch

    from quack_rl.rl.offline import masked
    from quack_rl.rl.ppo_run import load_bc_into_actor

    bc = _bc_net(seed=3)
    model = _fresh_model()
    critic_before = _critic_params(model)
    load_bc_into_actor(model, bc.state_dict())

    obs, masks = _observations(100)
    with torch.no_grad():
        dist = model.policy.get_distribution(torch.as_tensor(obs), action_masks=masks)
        ppo = dist.distribution.probs
        mask_t = torch.as_tensor(masks)
        want = torch.softmax(masked(bc(torch.as_tensor(obs)), mask_t), dim=-1)
    assert ppo.shape == want.shape == (100, masks.shape[1])
    assert torch.allclose(ppo, want, atol=1e-5, rtol=0)
    assert all(torch.equal(a, b) for a, b in zip(critic_before, _critic_params(model), strict=True))


@pytest.mark.slow
def test_load_bc_into_actor_raises_naming_the_key_and_changes_nothing():
    pytest.importorskip("sb3_contrib")
    from quack_rl.rl.ppo_run import load_bc_into_actor

    small = _fresh_model(hidden=64)
    before = _actor_state(small)
    with pytest.raises(ValueError, match=r"0\.weight"):
        load_bc_into_actor(small, _bc_net().state_dict())
    assert _equal(before, _actor_state(small))

    model = _fresh_model()
    before = _actor_state(model)
    state = _bc_net().state_dict()
    del state["4.bias"]
    with pytest.raises(ValueError, match=r"4\.bias"):
        load_bc_into_actor(model, state)
    assert _equal(before, _actor_state(model))


# --- runs --------------------------------------------------------------------------------------


@pytest.mark.slow
def test_run_from_bc_with_critic_warmup(tmp_path, monkeypatch):
    pytest.importorskip("sb3_contrib")
    monkeypatch.chdir(tmp_path)
    bc = _write_bc(tmp_path / "bc.pt", seed=1)
    config = p3(init_from_bc="bc.pt", critic_warmup_steps=1024)
    out = run_ppo_seed(config, 5, tmp_path / "run")

    stored = json.loads((out / "config.json").read_text())
    assert (
        stored["init_from_bc_sha256"]
        == hashlib.sha256((tmp_path / "bc.pt").read_bytes()).hexdigest()
    )
    assert ExperimentConfig.model_validate(stored["config"]) == config

    import torch

    first = _load(out / "checkpoints" / "step_1024.zip")
    assert _equal(_actor_state(first), bc)
    fresh = _critic_params(_fresh_model(seed=5))
    assert any(not torch.equal(a, b) for a, b in zip(fresh, _critic_params(first), strict=True))

    second = _load(out / "checkpoints" / "step_2048.zip")
    assert not _equal(_actor_state(second), bc)


@pytest.mark.slow
def test_warmup_without_bc_freezes_the_random_actor(tmp_path):
    pytest.importorskip("sb3_contrib")
    import torch

    config = p3(critic_warmup_steps=1024, hidden=32, checkpoint_every=None)
    run_ppo_seed(config, 2, tmp_path, steps_override=1024)
    trained = _load(tmp_path / "checkpoints" / "step_1024.zip")
    fresh = _fresh_model(hidden=32, seed=2)
    assert _equal(_actor_state(trained), _actor_state(fresh))
    assert any(
        not torch.equal(a, b)
        for a, b in zip(_critic_params(fresh), _critic_params(trained), strict=True)
    )


@pytest.mark.slow
def test_resume_inside_warmup_keeps_actor_frozen_and_checks_bc_file(tmp_path, monkeypatch):
    pytest.importorskip("sb3_contrib")
    import quack_rl.rl.ppo_run as ppo_run

    monkeypatch.chdir(tmp_path)
    bc = _write_bc(tmp_path / "bc.pt", seed=2)
    config = p3(init_from_bc="bc.pt", critic_warmup_steps=2048)
    out = tmp_path / "run"
    run_ppo_seed(config, 0, out)
    assert _equal(_actor_state(_load(out / "checkpoints" / "step_2048.zip")), bc)

    (out / "done.json").unlink()
    (out / "checkpoints" / "step_2048.zip").unlink()

    def no_reload(*args, **kwargs):
        raise AssertionError("a resume from a checkpoint must not load the BC weights again")

    with monkeypatch.context() as patch:
        patch.setattr(ppo_run, "load_bc_into_actor", no_reload)
        run_ppo_seed(config, 0, out, resume=True)
    assert _equal(_actor_state(_load(out / "checkpoints" / "step_2048.zip")), bc)

    # a changed BC file is refused, before the done.json early return
    _write_bc(tmp_path / "bc.pt", seed=9)
    with pytest.raises(ResumeError, match="init_from_bc_sha256"):
        run_ppo_seed(config, 0, out, resume=True)
