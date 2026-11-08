"""The seven experiment configs in `experiments/`: each changes exactly one thing against its
baseline (P3: `init_from_bc` and `critic_warmup_steps`, counted as one change)."""

from pathlib import Path

import pytest

from quack_rl.rl.experiment import config_diff, load_config

EXPERIMENTS = Path(__file__).resolve().parent.parent / "experiments"

# id -> (baseline, the settings in which it differs from the baseline)
EXPECTED: dict[str, tuple[str | None, list[str] | None]] = {
    "P0": (None, None),
    "P1": ("P0", ["opponents"]),
    "P2": ("P0", ["reward"]),
    "P3": ("P0", ["init_from_bc", "critic_warmup_steps"]),
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


def test_ppo_configs_share_the_step_budget() -> None:
    steps = {load_config(EXPERIMENTS / f"P{k}.json").steps for k in range(4)}
    assert len(steps) == 1
