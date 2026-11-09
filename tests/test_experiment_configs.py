"""The experiment configs in `experiments/`: each changes exactly one thing against its
baseline. The screening configs S0-S2 share one step budget."""

from pathlib import Path

import pytest

from quack_rl.rl.experiment import config_diff, load_config

EXPERIMENTS = Path(__file__).resolve().parent.parent / "experiments"

# id -> (baseline, the settings in which it differs from the baseline)
EXPECTED: dict[str, tuple[str | None, list[str] | None]] = {
    "S0": (None, None),
    "S1": ("S0", ["opponents"]),
    "S2": ("S0", ["reward"]),
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


SCREENING = sorted(name for name in EXPECTED if name.startswith("S"))


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
