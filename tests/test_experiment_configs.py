"""The experiment configs in `experiments/`: each changes exactly one thing against its
baseline. The screening configs S0-S5 share one step budget."""

import json
from pathlib import Path

import pytest

from quack_rl.rl.experiment import config_diff, load_config

EXPERIMENTS = Path(__file__).resolve().parent.parent / "experiments"

# id -> (baseline, the settings in which it differs from the baseline)
EXPECTED: dict[str, tuple[str | None, list[str] | None]] = {
    "S0": (None, None),
    "S1": ("S0", ["opponents"]),
    "S2": ("S0", ["reward"]),
    "S3": ("S2", ["init_from_bc", "critic_warmup_steps"]),
    "S4": ("S3", ["init_from_bc"]),
    "S5": ("S3", ["init_from_bc"]),
    "S6": ("S1", ["checkpoint_every", "n_steps", "batch_size"]),
    "S7": ("S1", ["target_kl"]),
    "S8": ("S7", ["n_steps", "batch_size"]),
    "S9": ("S3", ["seeds", "target_kl"]),
    "S10": ("S4", ["seeds", "target_kl"]),
    "S11": ("S5", ["seeds", "target_kl"]),
    "L": ("S11", ["steps", "checkpoint_every"]),
    "B0": (None, None),
    "B1": ("B0", ["bc.label_smoothing"]),
    "B2": ("B0", ["bc.entropy_coef"]),
}


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_experiment_configs(name: str) -> None:
    config = load_config(EXPERIMENTS / f"{name}.json")
    baseline, diff = EXPECTED[name]
    assert config.id == name
    assert config.baseline == baseline
    if baseline is not None:
        assert config_diff(load_config(EXPERIMENTS / f"{baseline}.json"), config) == diff


# The screening configs of stage #309. S6 and S7 (#321) change the update settings and S6 the
# checkpoint interval, so they are checked on their own below.
SCREENING = ["S0", "S1", "S2", "S3", "S4", "S5"]


def test_screening_configs_share_the_step_budget() -> None:
    configs = [load_config(EXPERIMENTS / f"{name}.json") for name in SCREENING]
    steps = {config.steps for config in configs}
    checkpoint_every = {config.checkpoint_every for config in configs}
    assert len(steps) == 1
    assert len(checkpoint_every) == 1
    (budget,) = steps
    (every,) = checkpoint_every
    assert budget % every == 0
    assert budget // every >= 6


PPO_CONFIGS = SCREENING


@pytest.mark.parametrize("name", PPO_CONFIGS)
def test_ppo_configs_write_the_update_settings(name: str) -> None:
    data = json.loads((EXPERIMENTS / f"{name}.json").read_text(encoding="utf-8"))
    assert data["n_steps"] == 1024
    assert data["batch_size"] == 64
    assert "target_kl" in data and data["target_kl"] is None
    config = load_config(EXPERIMENTS / f"{name}.json")
    assert (config.n_steps, config.batch_size, config.target_kl) == (1024, 64, None)


def test_screening_3_configs_keep_the_step_budget() -> None:
    for name in ("S6", "S7", "S8", "S9", "S10", "S11"):
        assert load_config(EXPERIMENTS / f"{name}.json").steps == 962560


def test_s7_target_kl_is_in_the_chosen_range() -> None:
    target_kl = load_config(EXPERIMENTS / "S7.json").target_kl
    assert target_kl is not None
    assert 0.02 <= target_kl <= 0.05


@pytest.mark.parametrize("name", ["B0", "B1", "B2"])
def test_bc_configs_have_no_update_settings(name: str) -> None:
    data = json.loads((EXPERIMENTS / f"{name}.json").read_text(encoding="utf-8"))
    assert not {"n_steps", "batch_size", "target_kl"} & set(data)
    assert load_config(EXPERIMENTS / f"{name}.json").kind == "bc"


@pytest.mark.parametrize("name", ["S9", "S10", "S11"])
def test_bc_reruns_take_s7_update_settings_and_seed_3(name: str) -> None:
    config = load_config(EXPERIMENTS / f"{name}.json")
    s7 = load_config(EXPERIMENTS / "S7.json")
    assert (config.n_steps, config.batch_size, config.target_kl) == (
        s7.n_steps,
        s7.batch_size,
        s7.target_kl,
    )
    assert config.seeds == [0, 1, 2, 3]
    assert config.critic_warmup_steps % config.n_steps == 0
    assert config.checkpoint_every % config.n_steps == 0


@pytest.mark.parametrize("name", ["B0", "B1", "B2"])
def test_bc_configs_have_the_seeds_of_the_bc_reruns(name: str) -> None:
    """PPO seed k of S9-S11 starts from BC seed k, so every BC config has seed 3."""
    assert load_config(EXPERIMENTS / f"{name}.json").seeds == [0, 1, 2, 3]


def test_long_run_budget() -> None:
    """L (experiments/README.md, "Long-run budget (L)"): at most 18,360 s at the slowest
    quarter rate of S11 (240.1 steps per second per training) plus S11's final evaluation
    (471 s), and its checkpoints up to S11's budget fall on S11's checkpoint steps."""
    long = load_config(EXPERIMENTS / "L.json")
    s11 = load_config(EXPERIMENTS / "S11.json")
    assert long.steps % long.checkpoint_every == 0
    assert long.checkpoint_every % s11.checkpoint_every == 0
    assert s11.steps % long.checkpoint_every == 0
    assert long.steps / 240.1 + 471 <= 18360
    assert long.seeds == s11.seeds
