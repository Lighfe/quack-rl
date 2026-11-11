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
        "n_steps": 1024,
        "batch_size": 64,
        "target_kl": None,
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


def test_checkpoint_every_is_checked_against_the_config_n_steps(tmp_path):
    out = tmp_path / "run"
    config = p0(n_steps=4096, batch_size=64, steps=192512, checkpoint_every=96256)
    with pytest.raises(ValueError, match="4096"):
        run_ppo_seed(config, 0, out)
    assert not out.exists()
    # 192512 = 47 * 4096: the check passes (stopped right after it by an unknown opponent)
    config = p0(
        n_steps=4096,
        batch_size=64,
        steps=192512,
        checkpoint_every=192512,
        opponents=[{"spec": "bot:nobody"}],
    )
    with pytest.raises(ValueError, match="bot:nobody"):
        run_ppo_seed(config, 0, out)
    assert not out.exists()


def test_critic_warmup_is_checked_against_the_config_n_steps(tmp_path):
    out = tmp_path / "run"
    config = p0(n_steps=4096, batch_size=64, checkpoint_every=None, critic_warmup_steps=51200)
    with pytest.raises(ValueError, match="critic_warmup_steps.*4096"):
        run_ppo_seed(config, 0, out)
    assert not out.exists()


def test_ppo_run_does_not_import_the_train_constants():
    import quack_rl.rl.ppo_run as ppo_run

    assert not hasattr(ppo_run, "N_STEPS")
    assert not hasattr(ppo_run, "BATCH_SIZE")


@pytest.mark.slow
def test_run_uses_the_config_update_settings(tmp_path):
    pytest.importorskip("sb3_contrib")
    import sb3_contrib

    built = []
    original = sb3_contrib.MaskablePPO.__init__

    def spy(self, *args, **kwargs):
        original(self, *args, **kwargs)
        built.append(self)

    config = p0(
        n_steps=128, batch_size=32, target_kl=0.03, steps=256, checkpoint_every=None, hidden=32
    )
    out = tmp_path / "run"
    try:
        sb3_contrib.MaskablePPO.__init__ = spy
        run_ppo_seed(config, 0, out)
    finally:
        sb3_contrib.MaskablePPO.__init__ = original
    (model,) = built
    assert (model.n_steps, model.batch_size, model.target_kl) == (128, 32, 0.03)
    stored = json.loads((out / "config.json").read_text())
    assert stored["n_steps"] == 128 and stored["batch_size"] == 32
    inner = stored["config"]
    assert (inner["n_steps"], inner["batch_size"], inner["target_kl"]) == (128, 32, 0.03)
    assert [r["steps"] for r in rows(out)] == ["128", "256"]


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


# --- training games (games.jsonl) --------------------------------------------------------------


def _game_line(step: int) -> str:
    line = {"step": step, "chance_seed": 1, "agent_seat": "p1", "opponent": "bot:random"}
    return json.dumps({**line, "actions": [[0, 0]]}) + "\n"


def test_trim_games_drops_lines_past_the_checkpoint_and_a_broken_last_line(tmp_path):
    from quack_rl.rl.ppo_run import _trim_games

    path = tmp_path / "games.jsonl"
    path.write_text(_game_line(10) + _game_line(1024) + _game_line(1030) + '{"step": 20')
    _trim_games(path, 1024)
    assert [json.loads(t)["step"] for t in path.read_text().splitlines()] == [10, 1024]
    _trim_games(path, 0)  # resume from no checkpoint: all lines dropped
    assert path.read_text() == ""
    missing = tmp_path / "none.jsonl"
    _trim_games(missing, 5)  # no file: an empty file
    assert missing.read_text() == ""


def test_trim_games_raises_on_a_broken_line_before_the_last(tmp_path):
    from quack_rl.rl.ppo_run import _trim_games

    path = tmp_path / "games.jsonl"
    path.write_text("{broken\n" + _game_line(10))
    with pytest.raises(ValueError, match="line 1"):
        _trim_games(path, 1024)


@pytest.mark.slow
def test_save_games_writes_one_line_per_game_and_rebuilds(tmp_path):
    pytest.importorskip("sb3_contrib")
    from quack_rl.rl.game_log import rebuild_dataset

    config = p0(
        opponents=[{"spec": "bot:random"}, {"spec": "bot:topchip-draw20-pts6"}], save_games=True
    )
    out = tmp_path / "run"
    run_ppo_seed(config, 1, out)
    lines = [json.loads(t) for t in (out / "games.jsonl").read_text().splitlines()]
    assert len(lines) == sum(int(r["games"]) for r in rows(out)) > 0
    assert set(lines[0]) == {"step", "chance_seed", "agent_seat", "opponent", "actions"}
    assert {line["opponent"] for line in lines} <= {"bot:random", "bot:topchip-draw20-pts6"}
    assert {line["agent_seat"] for line in lines} <= {"p1", "p2"}
    steps = [line["step"] for line in lines]
    assert steps == sorted(steps) and 0 < steps[-1] <= 2048
    data = rebuild_dataset(out / "games.jsonl")
    assert int(data.terminated.sum()) == len(lines)

    # interrupted after the first checkpoint: the games past step 1024 are dropped and played again
    (out / "done.json").unlink()
    (out / "checkpoints" / "step_2048.zip").unlink()
    with (out / "games.jsonl").open("a") as handle:
        handle.write('{"step": 20')
    run_ppo_seed(config, 1, out, resume=True)
    again = [json.loads(t) for t in (out / "games.jsonl").read_text().splitlines()]
    assert again[: sum(s <= 1024 for s in steps)] == [
        line for line in lines if line["step"] <= 1024
    ]
    assert len(again) == sum(int(r["games"]) for r in rows(out))


@pytest.mark.slow
def test_without_save_games_no_games_file(tmp_path):
    pytest.importorskip("sb3_contrib")
    run_ppo_seed(p0(checkpoint_every=None, hidden=32), 0, tmp_path, steps_override=1024)
    assert not (tmp_path / "games.jsonl").exists()


# --- passes per update (epochs_run) ------------------------------------------------------------


def _short(**overrides) -> ExperimentConfig:
    data = {"n_steps": 128, "batch_size": 32, "steps": 384, "checkpoint_every": 128, "hidden": 32}
    data.update(overrides)
    return p0(**data)


def test_epochs_run_is_the_last_column():
    assert PPO_COLUMNS[-1] == "epochs_run"
    assert PPO_COLUMNS[-2] == "wall_seconds"


@pytest.mark.slow
def test_epochs_run_is_ten_without_target_kl(tmp_path):
    pytest.importorskip("sb3_contrib")
    run_ppo_seed(_short(), 0, tmp_path)
    got = rows(tmp_path)
    assert len(got) == 3
    assert [int(r["epochs_run"]) for r in got] == [10, 10, 10]


@pytest.mark.slow
def test_epochs_run_stops_early_with_a_tiny_target_kl(tmp_path):
    pytest.importorskip("sb3_contrib")
    run_ppo_seed(_short(target_kl=1e-6), 0, tmp_path)
    passes = [int(r["epochs_run"]) for r in rows(tmp_path)]
    assert len(passes) == 3
    assert all(n >= 1 for n in passes), passes
    assert any(n < 10 for n in passes), passes


@pytest.mark.slow
def test_epochs_run_after_a_resume_counts_only_the_new_update(tmp_path):
    pytest.importorskip("sb3_contrib")
    config = _short()
    run_ppo_seed(config, 0, tmp_path)
    (tmp_path / "done.json").unlink()
    (tmp_path / "checkpoints" / "step_384.zip").unlink()
    (tmp_path / "checkpoints" / "step_256.zip").unlink()
    run_ppo_seed(config, 0, tmp_path, resume=True)
    got = rows(tmp_path)
    assert [r["steps"] for r in got] == ["128", "256", "384"]
    assert [int(r["epochs_run"]) for r in got] == [10, 10, 10]


@pytest.mark.slow
def test_resume_of_an_old_format_ppo_csv(tmp_path):
    pytest.importorskip("sb3_contrib")
    from quack_rl.rl.monitor import load_run

    config = _short()
    run_ppo_seed(config, 0, tmp_path)
    old_columns = [c for c in PPO_COLUMNS if c != "epochs_run"]
    old_rows = [{c: r[c] for c in old_columns} for r in rows(tmp_path)]
    with (tmp_path / "ppo.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=old_columns)
        writer.writeheader()
        writer.writerows(old_rows)
    (tmp_path / "done.json").unlink()
    (tmp_path / "checkpoints" / "step_384.zip").unlink()
    run_ppo_seed(config, 0, tmp_path, resume=True)

    with (tmp_path / "ppo.csv").open(newline="") as handle:
        lines = list(csv.reader(handle))
    assert lines[0] == list(PPO_COLUMNS)
    assert all(len(line) == 11 for line in lines), lines
    body = lines[1:]
    assert [line[0] for line in body] == ["128", "256", "384"]
    assert [line[-1] for line in body[:2]] == ["", ""]
    assert int(body[2][-1]) == 10
    assert [line[:-1] for line in body[:2]] == [[r[c] for c in old_columns] for r in old_rows[:2]]
    done = json.loads((tmp_path / "done.json").read_text())
    assert done["train_seconds"] == float(body[2][PPO_COLUMNS.index("wall_seconds")])

    run = load_run(tmp_path)
    assert run.train["epochs_run"].to_list() == [None, None, 10]
