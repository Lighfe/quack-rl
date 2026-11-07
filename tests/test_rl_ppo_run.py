"""Tests for one PPO run of one seed (`quack_rl.rl.ppo_run`)."""

import csv
import json

import pytest

from quack_rl.rl.experiment import ExperimentConfig
from quack_rl.rl.ppo_run import (
    PPO_COLUMNS,
    newest_complete_checkpoint,
    policy_kwargs,
    run_ppo_seed,
)
from quack_rl.rl.selfplay import ResumeError


def p0(**overrides) -> ExperimentConfig:
    data = {
        "id": "P0",
        "kind": "ppo",
        "baseline": None,
        "changes": "PPO baseline",
        "steps": 2048,
        "opponents": [{"spec": "bot:random"}],
        "checkpoint_every": 1024,
    }
    data.update(overrides)
    return ExperimentConfig.model_validate(data)


def rows(out) -> list[dict[str, str]]:
    with (out / "ppo.csv").open(newline="") as handle:
        return list(csv.DictReader(handle))


# --- no training -------------------------------------------------------------------------------


def test_newest_complete_checkpoint(tmp_path):
    assert newest_complete_checkpoint(tmp_path) is None
    folder = tmp_path / "checkpoints"
    folder.mkdir()
    assert newest_complete_checkpoint(tmp_path) is None
    for name in ("step_1024.zip", "step_9216.zip", "step_10240.tmp.zip", "other.zip"):
        (folder / name).write_bytes(b"")
    (folder / "step_2048.zip").write_bytes(b"")
    assert newest_complete_checkpoint(tmp_path) == folder / "step_9216.zip"


def test_opponent_specs_repeat_each_weight_times():
    from quack_rl.rl.ppo_run import _opponent_specs

    config = p0(
        opponents=[{"spec": "bot:random"}, {"spec": "bot:topchip-draw20-pts6", "weight": 3}]
    )
    assert _opponent_specs(config) == ["bot:random"] + ["bot:topchip-draw20-pts6"] * 3


def test_unknown_opponent_raises_before_any_file(tmp_path):
    out = tmp_path / "run"
    with pytest.raises(ValueError, match="bot:nobody"):
        run_ppo_seed(p0(opponents=[{"spec": "bot:nobody"}]), 0, out)
    assert not out.exists()


def test_checkpoint_every_not_a_multiple_raises_before_any_file(tmp_path):
    out = tmp_path / "run"
    with pytest.raises(ValueError, match="checkpoint_every"):
        run_ppo_seed(p0(checkpoint_every=1000), 0, out)
    assert not out.exists()


def test_fresh_run_on_existing_config_raises_and_changes_nothing(tmp_path):
    (tmp_path / "config.json").write_text("{}")
    before = sorted(p.name for p in tmp_path.iterdir())
    with pytest.raises(FileExistsError):
        run_ppo_seed(p0(), 0, tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == before
    assert (tmp_path / "config.json").read_text() == "{}"


# --- training ----------------------------------------------------------------------------------


@pytest.mark.slow
def test_policy_kwargs_build_two_relu_layers():
    pytest.importorskip("sb3_contrib")
    import torch
    from sb3_contrib import MaskablePPO

    from quack_rl.rl import QuackEnv

    model = MaskablePPO("MlpPolicy", QuackEnv(), policy_kwargs=policy_kwargs(256), device="cpu")
    extractor = model.policy.mlp_extractor
    for net in (extractor.policy_net, extractor.value_net):
        linear = [m for m in net if isinstance(m, torch.nn.Linear)]
        relu = [m for m in net if isinstance(m, torch.nn.ReLU)]
        assert [m.out_features for m in linear] == [256, 256]
        assert len(relu) == 2


@pytest.mark.slow
def test_run_checkpoints_and_resume(tmp_path):
    pytest.importorskip("sb3_contrib")
    out = tmp_path / "run"
    config = p0(
        opponents=[{"spec": "bot:random"}, {"spec": "bot:topchip-draw20-pts6", "weight": 2}]
    )
    assert run_ppo_seed(config, 3, out) == out

    stored = json.loads((out / "config.json").read_text())
    assert stored["seed"] == 3 and stored["steps"] == 2048
    assert ExperimentConfig.model_validate(stored["config"]) == config
    assert stored["git_commit"] and stored["versions"]["sb3-contrib"]
    names = sorted(p.name for p in (out / "checkpoints").iterdir())
    assert names == ["step_1024.zip", "step_2048.zip"]
    first = rows(out)
    assert [r["steps"] for r in first] == ["1024", "2048"]
    assert list(first[0]) == list(PPO_COLUMNS)
    for row in first:
        assert all(row[c] != "" for c in PPO_COLUMNS), row
        assert float(row["entropy"]) > 0 and int(row["games"]) > 0
    done = json.loads((out / "done.json").read_text())
    assert done["steps"] == 2048 and done["train_seconds"] == float(first[-1]["wall_seconds"])

    # done.json present: nothing is trained and no file changes
    snapshot = {p: p.stat().st_mtime_ns for p in out.rglob("*")}
    run_ppo_seed(config, 3, out, resume=True)
    assert {p: p.stat().st_mtime_ns for p in out.rglob("*")} == snapshot

    # resume with a different reward is refused
    with pytest.raises(ResumeError, match="reward"):
        run_ppo_seed(config.model_copy(update={"reward": "margin"}), 3, out, resume=True)
    with pytest.raises(ResumeError, match="seed"):
        run_ppo_seed(config, 4, out, resume=True)

    # interrupted after the first checkpoint, with a leftover temp file
    (out / "done.json").unlink()
    (out / "checkpoints" / "step_2048.zip").unlink()
    (out / "checkpoints" / "step_3072.tmp.zip").write_bytes(b"broken")
    run_ppo_seed(config, 3, out, resume=True)
    again = rows(out)
    assert [r["steps"] for r in again] == ["1024", "2048"]
    assert again[0] == first[0]
    assert float(again[1]["wall_seconds"]) >= float(first[0]["wall_seconds"])
    assert (out / "checkpoints" / "step_2048.zip").is_file()
    assert json.loads((out / "done.json").read_text())["steps"] == 2048


@pytest.mark.slow
def test_margin_reward_run_and_resume_without_checkpoint(tmp_path):
    pytest.importorskip("sb3_contrib")
    config = p0(reward="margin", checkpoint_every=None, hidden=32)
    run_ppo_seed(config, 0, tmp_path, steps_override=1024)
    assert sorted(p.name for p in (tmp_path / "checkpoints").iterdir()) == ["step_1024.zip"]
    assert -1 <= float(rows(tmp_path)[0]["mean_reward"]) <= 1

    # no complete checkpoint: resume starts again from step 0
    (tmp_path / "done.json").unlink()
    (tmp_path / "checkpoints" / "step_1024.zip").unlink()
    run_ppo_seed(config, 0, tmp_path, resume=True, steps_override=1024)
    assert [r["steps"] for r in rows(tmp_path)] == ["1024"]
    assert json.loads((tmp_path / "done.json").read_text())["steps"] == 1024
    with pytest.raises(ResumeError, match="steps"):
        run_ppo_seed(config, 0, tmp_path, resume=True)
