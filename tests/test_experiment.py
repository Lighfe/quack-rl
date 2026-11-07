"""Tests for the experiment config (`quack_rl.rl.experiment`)."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from quack_rl.bots.presets import PRESET_BOTS
from quack_rl.rl.experiment import (
    EVAL_OPPONENTS,
    BCSettings,
    ExperimentConfig,
    OpponentShare,
    config_diff,
    load_config,
)


def p0(**overrides) -> ExperimentConfig:
    data = {
        "id": "P0",
        "kind": "ppo",
        "baseline": None,
        "changes": "PPO baseline",
        "steps": 1000,
        "opponents": [{"spec": "bot:random"}],
    }
    data.update(overrides)
    return ExperimentConfig.model_validate(data)


def b0(**bc_overrides) -> ExperimentConfig:
    bc = {"dataset": "data/bc.npz"}
    bc.update(bc_overrides)
    return ExperimentConfig.model_validate(
        {"id": "B0", "kind": "bc", "baseline": None, "changes": "BC control", "bc": bc}
    )


def test_defaults():
    cfg = p0()
    assert cfg.seeds == [0, 1, 2]
    assert cfg.reward == "win_loss"
    assert cfg.hidden == 256
    assert cfg.checkpoint_every is None
    assert cfg.live_eval_games == 50
    assert cfg.final_eval_games == 200
    assert cfg.final_eval_seed == 2026
    assert cfg.init_from_bc is None
    assert cfg.critic_warmup_steps == 0
    assert cfg.save_games is False
    assert cfg.bc is None
    assert cfg.opponents == [OpponentShare(spec="bot:random", weight=1)]
    bc = BCSettings(dataset="x")
    assert (bc.epochs, bc.label_smoothing, bc.entropy_coef) == (10, 0.0, 0.0)


def test_valid_bc_config():
    cfg = b0()
    assert cfg.kind == "bc"
    assert cfg.steps is None
    assert cfg.opponents == []


# --- validation rules -------------------------------------------------------


def test_baseline_is_required():
    data = p0().model_dump()
    del data["baseline"]
    with pytest.raises(ValidationError):
        ExperimentConfig.model_validate(data)


@pytest.mark.parametrize("steps", ["missing", None])
def test_ppo_without_steps_raises(steps):
    data = p0().model_dump()
    if steps == "missing":
        del data["steps"]
    else:
        data["steps"] = None
    with pytest.raises(ValidationError):
        ExperimentConfig.model_validate(data)


@pytest.mark.parametrize("opponents", ["missing", []])
def test_ppo_without_opponents_raises(opponents):
    data = p0().model_dump()
    if opponents == "missing":
        del data["opponents"]
    else:
        data["opponents"] = []
    with pytest.raises(ValidationError):
        ExperimentConfig.model_validate(data)


@pytest.mark.parametrize("bc", ["missing", None])
def test_bc_without_bc_settings_raises(bc):
    data = b0().model_dump()
    if bc == "missing":
        del data["bc"]
    else:
        data["bc"] = None
    with pytest.raises(ValidationError):
        ExperimentConfig.model_validate(data)


@pytest.mark.parametrize("seeds", [[], [0, 1, 0]])
def test_bad_seeds_raise(seeds):
    with pytest.raises(ValidationError):
        p0(seeds=seeds)


def test_weight_below_one_raises():
    with pytest.raises(ValidationError):
        OpponentShare(spec="bot:random", weight=0)
    with pytest.raises(ValidationError):
        p0(opponents=[{"spec": "bot:random", "weight": 0}])


def test_unknown_top_level_key_raises():
    with pytest.raises(ValidationError):
        p0(learning_rate=0.1)


def test_unknown_bc_key_raises():
    with pytest.raises(ValidationError):
        b0(dropout=0.5)


def test_unknown_opponent_key_raises():
    with pytest.raises(ValidationError):
        p0(opponents=[{"spec": "bot:random", "share": 2}])


# --- config_diff ------------------------------------------------------------


def test_diff_single_change():
    assert config_diff(p0(), p0(reward="margin")) == ["reward"]


def test_diff_ignores_id_baseline_changes():
    other = p0(id="P1", baseline="P0", changes="something else")
    assert config_diff(p0(), other) == []


def test_diff_equal_configs():
    assert config_diff(p0(), p0()) == []


def test_diff_declaration_order():
    other = p0(save_games=True, reward="margin", steps=2000)
    assert config_diff(p0(), other) == ["steps", "reward", "save_games"]


def test_diff_bc_field():
    assert config_diff(b0(), b0(label_smoothing=0.1)) == ["bc.label_smoothing"]


def test_diff_bc_fields_in_order():
    other = b0(entropy_coef=0.01, label_smoothing=0.1)
    assert config_diff(b0(), other) == ["bc.label_smoothing", "bc.entropy_coef"]


def test_diff_bc_one_side_null():
    assert config_diff(p0(), p0(bc={"dataset": "d"})) == ["bc"]


def test_diff_p3_names_two_fields():
    other = p0(init_from_bc="runs/B0/model.pt", critic_warmup_steps=500)
    assert config_diff(p0(), other) == ["init_from_bc", "critic_warmup_steps"]


# --- load_config ------------------------------------------------------------


def test_load_config_round_trip(tmp_path: Path):
    cfg = p0(opponents=[{"spec": PRESET_BOTS[0], "weight": 2}, {"spec": "bot:random"}])
    path = tmp_path / "p0.json"
    path.write_text(cfg.model_dump_json(), encoding="utf-8")
    assert load_config(path) == cfg


def test_load_config_round_trip_bc(tmp_path: Path):
    cfg = b0(label_smoothing=0.1)
    path = tmp_path / "b1.json"
    path.write_text(cfg.model_dump_json(), encoding="utf-8")
    assert load_config(path) == cfg


def test_load_config_invalid_raises(tmp_path: Path):
    path = tmp_path / "bad.json"
    path.write_text('{"id": "X", "kind": "ppo", "baseline": null, "changes": ""}')
    with pytest.raises(ValidationError):
        load_config(path)


def test_eval_opponents():
    assert EVAL_OPPONENTS == (*PRESET_BOTS, "bot:random")
    assert len(EVAL_OPPONENTS) == 4
