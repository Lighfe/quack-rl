import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import quack_rl
from quack_rl.rl.encode import OBSERVATION_LAYOUT, vector_names
from quack_rl.rl.evaluate import EvalResult
from quack_rl.rl.runs import (
    LayoutMismatch,
    RunFolder,
    load_model,
    load_run,
    run_path,
    save_run,
)
from quack_rl.rl.train import TrainingLog, TrainResult, train
from quack_rl.rules import load_ruleset

CONFIG = {"steps": 256, "rules": "v1.1", "opponent": "random", "seed": 3, "eval_games": 10}


def ev(wins=3):
    return EvalResult(10, wins, 1, 10 - wins - 1, 1.5, 2.25, 0.5, wins / 10, 0.1, 0.6)


class FakeModel:
    def save(self, path):
        Path(path).write_bytes(b"fake model")


def episode_row(i):
    return {
        "episode": i, "timestep": 40 * i, "result": "win", "points_own": 3.5,
        "points_opponent": 2, "explosions_own": 1, "decisions": 41,
    }  # fmt: skip


def metric_row(t):
    return {
        "timestep": t, "policy_gradient_loss": -0.0123456789012345, "value_loss": 1.5,
        "entropy_loss": -2.0, "approx_kl": 0.001, "explained_variance": 0.25,
    }  # fmt: skip


def fake_result(vs_random=False):
    log = TrainingLog(
        episodes=[episode_row(1), episode_row(2)], metrics=[metric_row(128), metric_row(256)]
    )
    extra = {f"{n}_vs_random": ev(1) for n in ("baseline_random", "baseline_untrained",
             "trained_sampled", "trained_greedy")} if vs_random else {}  # fmt: skip
    return TrainResult(
        model=FakeModel(), log=log, baseline_random=ev(1), baseline_untrained=ev(2),
        trained_sampled=ev(3), trained_greedy=ev(4), games_played=2, **extra,
    )  # fmt: skip


def test_folder_appears_only_at_start(tmp_path):
    path = tmp_path / "r1"
    sink = RunFolder(path)
    assert not path.exists()
    sink.start(CONFIG)
    assert path.exists()


def test_start_writes_config(tmp_path):
    sink = RunFolder(tmp_path / "r1")
    sink.start(CONFIG)
    config = json.loads((tmp_path / "r1" / "config.json").read_text())
    assert {k: config[k] for k in CONFIG} == CONFIG
    assert config["package_version"] == quack_rl.__version__
    assert config["layout"] == OBSERVATION_LAYOUT
    assert config["vector_names"] == vector_names(load_ruleset("v1.1"))
    assert (tmp_path / "r1" / "episodes.csv").read_text().startswith("episode,timestep")
    assert (tmp_path / "r1" / "metrics.csv").read_text().startswith("timestep,")


def test_csv_rows_are_on_disk_before_finish(tmp_path):
    sink = RunFolder(tmp_path / "r1")
    sink.start(CONFIG)
    sink.episode(episode_row(1))
    sink.metrics(metric_row(128))
    assert len((tmp_path / "r1" / "episodes.csv").read_text().splitlines()) == 2
    assert len((tmp_path / "r1" / "metrics.csv").read_text().splitlines()) == 2
    sink.episode(episode_row(2))
    assert len((tmp_path / "r1" / "episodes.csv").read_text().splitlines()) == 3
    assert not (tmp_path / "r1" / "model.zip").exists()
    assert not (tmp_path / "r1" / "eval.json").exists()


def test_finish_writes_eval_and_model(tmp_path):
    sink = RunFolder(tmp_path / "r1")
    sink.start(CONFIG)
    sink.finish(fake_result())
    data = json.loads((tmp_path / "r1" / "eval.json").read_text())
    assert set(data) == {"baseline_random", "baseline_untrained", "trained_sampled",
                         "trained_greedy"}  # fmt: skip
    assert data["trained_greedy"]["wins"] == 4
    assert (tmp_path / "r1" / "model.zip").read_bytes() == b"fake model"


def test_eval_json_has_vs_random_when_present(tmp_path):
    save_run(tmp_path / "r1", fake_result(vs_random=True), CONFIG)
    assert len(json.loads((tmp_path / "r1" / "eval.json").read_text())) == 8


def test_checkpoint_file(tmp_path):
    sink = RunFolder(tmp_path / "r1")
    sink.start(CONFIG)
    sink.checkpoint(FakeModel(), 128)
    assert (tmp_path / "r1" / "checkpoints" / "step_128.zip").exists()


def test_save_run_has_no_checkpoints(tmp_path):
    save_run(tmp_path / "r1", fake_result(), CONFIG)
    assert not (tmp_path / "r1" / "checkpoints").exists()


def test_round_trip_values(tmp_path):
    result = fake_result(vs_random=True)
    save_run(tmp_path / "r1", result, CONFIG)
    config, episodes, metrics, evaluation = load_run(tmp_path / "r1")
    assert config["seed"] == 3 and config["steps"] == 256
    assert episodes == result.log.episodes
    assert metrics == result.log.metrics
    assert isinstance(episodes[0]["points_own"], float) and isinstance(episodes[0]["episode"], int)
    assert evaluation["trained_greedy"]["win_rate"] == 0.4
    assert evaluation["baseline_random_vs_random"]["wins"] == 1


def test_save_run_refuses_existing_folder(tmp_path):
    (tmp_path / "r1").mkdir()
    with pytest.raises(FileExistsError, match="r1"):
        save_run(tmp_path / "r1", fake_result(), CONFIG)
    with pytest.raises(FileExistsError):
        RunFolder(tmp_path / "r1")


@pytest.mark.parametrize("name", ["a/b", "../x", "..", "a\\b", "", "x..y"])
def test_bad_run_names_are_refused(tmp_path, name):
    with pytest.raises(ValueError):
        run_path(tmp_path, name)


def test_train_refuses_existing_run_and_keeps_files(tmp_path):
    (tmp_path / "r1").mkdir()
    marker = tmp_path / "r1" / "marker.txt"
    marker.write_text("keep")
    with pytest.raises(FileExistsError, match="r1"):
        train(256, eval_games=1, rules="v1.1", run="r1", runs_dir=tmp_path)
    assert marker.read_text() == "keep"
    assert [p.name for p in (tmp_path / "r1").iterdir()] == ["marker.txt"]


def test_train_refuses_path_name(tmp_path):
    with pytest.raises(ValueError):
        train(256, eval_games=1, rules="v1.1", run="../x", runs_dir=tmp_path / "runs")
    assert list(tmp_path.iterdir()) == []


def test_train_without_run_creates_nothing(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "sb3_contrib", None)  # no SB3: train stops after the checks
    with pytest.raises(ImportError):
        train(256, eval_games=1, rules="v1.1", runs_dir=tmp_path)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.slow
def test_real_train_without_run_creates_nothing(tmp_path):
    pytest.importorskip("sb3_contrib", reason="needs the train group: uv sync --group train")
    train(256, eval_games=2, rules="v1.1", runs_dir=tmp_path)
    assert list(tmp_path.iterdir()) == []


def _saved(tmp_path):
    save_run(tmp_path / "r1", fake_result(), CONFIG)
    return tmp_path / "r1"


def test_load_model_refuses_changed_layout(tmp_path):
    path = _saved(tmp_path)
    cfg = json.loads((path / "config.json").read_text())
    cfg["layout"] = OBSERVATION_LAYOUT + 1
    (path / "config.json").write_text(json.dumps(cfg))
    (path / "model.zip").unlink()  # the check comes before the model file is opened
    with pytest.raises(LayoutMismatch):
        load_model(path, "v1.1")


def test_load_model_refuses_changed_vector_names(tmp_path):
    path = _saved(tmp_path)
    cfg = json.loads((path / "config.json").read_text())
    cfg["vector_names"] = cfg["vector_names"][:-1] + ["other"]
    (path / "config.json").write_text(json.dumps(cfg))
    (path / "model.zip").unlink()
    with pytest.raises(LayoutMismatch):
        load_model(path, "v1.1")


@pytest.mark.slow
def test_real_train_run_folder_and_load_model(tmp_path):
    pytest.importorskip("sb3_contrib", reason="needs the train group: uv sync --group train")
    train(256, eval_games=2, rules="v1.1", run="real", runs_dir=tmp_path, checkpoint_every=128)
    path = tmp_path / "real"
    assert (path / "model.zip").exists()
    assert (path / "checkpoints" / "step_128.zip").exists()
    config, episodes, metrics, evaluation = load_run(path)
    assert len(episodes) >= 1 and len(metrics) >= 1 and "trained_greedy" in evaluation
    assert load_model(path, "v1.1") is not None


@pytest.mark.slow
def test_real_train_checkpoints_at_multiples_not_rollout_ends(tmp_path):
    pytest.importorskip("sb3_contrib", reason="needs the train group: uv sync --group train")
    train(256, eval_games=1, rules="v1.1", run="odd", runs_dir=tmp_path, checkpoint_every=100)
    names = sorted(p.name for p in (tmp_path / "odd" / "checkpoints").iterdir())
    assert names == ["step_100.zip", "step_200.zip"]


def test_new_code_uses_no_record_paths():
    src = Path(__file__).parents[1] / "src/quack_rl/rl"
    for name in ("runs.py", "train.py"):
        text = (src / name).read_text()
        assert "data/records" not in text and "data/tournaments" not in text


def test_data_runs_is_git_ignored():
    if shutil.which("git") is None:
        pytest.skip("git missing")
    out = subprocess.run(["git", "check-ignore", "data/runs/example"], capture_output=True,
                         text=True, cwd=Path(__file__).parents[1])  # fmt: skip
    assert out.stdout.strip() == "data/runs/example"


# ---- resume: refusals and log truncation (no SB3 needed) ----


def _interrupted(tmp_path, steps=1000, checkpoints=(100, 500)):
    """A run folder as an interrupted run leaves it: logs, checkpoints, no model.zip/eval.json."""
    from quack_rl.rl.runs import EPISODE_COLUMNS, METRIC_COLUMNS, _write_csv, full_config

    path = tmp_path / "cut"
    (path / "checkpoints").mkdir(parents=True)
    cfg = {**CONFIG, "steps": steps}
    (path / "config.json").write_text(json.dumps(full_config(cfg)))
    _write_csv(path / "episodes.csv", EPISODE_COLUMNS, [episode_row(i) for i in range(1, 6)])
    _write_csv(path / "metrics.csv", METRIC_COLUMNS, [metric_row(t) for t in (128, 256, 384)])
    for n in checkpoints:
        (path / "checkpoints" / f"step_{n}.zip").write_bytes(b"x")
    return path


def _snapshot(path):
    return {p.relative_to(path): p.read_bytes() for p in sorted(path.rglob("*")) if p.is_file()}


def test_check_resumable_takes_the_newest_checkpoint_as_a_number(tmp_path):
    from quack_rl.rl.runs import check_resumable

    _interrupted(tmp_path, steps=200_000, checkpoints=(50_000, 100_000, 9_000))
    state = check_resumable(tmp_path, "cut")
    assert state.n == 100_000 and state.checkpoint.name == "step_100000.zip"
    assert state.config["seed"] == 3


def test_truncate_logs_cuts_rows_after_n(tmp_path):
    from quack_rl.rl.runs import truncate_logs

    path = _interrupted(tmp_path)
    episodes, metrics = truncate_logs(path, 200)  # episode timesteps are 40, 80, ..., 200
    assert [r["episode"] for r in episodes] == [1, 2, 3, 4, 5]
    episodes, metrics = truncate_logs(path, 100)
    assert [r["episode"] for r in episodes] == [1, 2]
    assert [r["timestep"] for r in metrics] == []
    assert len(load_rows(path / "episodes.csv")) == 2
    assert load_rows(path / "metrics.csv") == []


def load_rows(file):
    import csv

    with file.open(newline="") as f:
        return list(csv.DictReader(f))


def test_truncate_logs_keeps_rows_up_to_n_unchanged(tmp_path):
    from quack_rl.rl.runs import truncate_logs

    path = _interrupted(tmp_path)
    before = (path / "metrics.csv").read_text().splitlines()
    truncate_logs(path, 256)
    assert (path / "metrics.csv").read_text().splitlines() == before[:3]  # header + 128 + 256


def _no_step_files(p):
    for f in (p / "checkpoints").glob("step_*.zip"):
        f.unlink()
    (p / "checkpoints" / "notes.txt").write_text("x")


@pytest.mark.parametrize(
    "setup, error, text",
    [
        (lambda p: shutil.rmtree(p), FileNotFoundError, "does not exist"),
        (lambda p: (p / "config.json").unlink(), FileNotFoundError, "config.json"),
        (lambda p: (p / "config.json").write_text("{}"), ValueError, "steps"),
        (lambda p: shutil.rmtree(p / "checkpoints"), FileNotFoundError, "checkpoints"),
        (_no_step_files, FileNotFoundError, "checkpoint"),
        (lambda p: (p / "model.zip").write_bytes(b"m"), ValueError, "finished"),
        (lambda p: (p / "eval.json").write_text("{}"), ValueError, "finished"),
        (lambda p: (p / "selfplay.csv").write_text("a\n"), ValueError, "self-play"),
        (lambda p: (p / "checkpoints" / "step_1000.zip").write_bytes(b"x"), ValueError,
         "no steps left"),
    ],
)  # fmt: skip
def test_resume_refusals(tmp_path, setup, error, text):
    from quack_rl.rl.train import resume

    path = _interrupted(tmp_path)
    setup(path)
    before = _snapshot(path) if path.exists() else None
    with pytest.raises(error, match=text) as exc:
        resume("cut", runs_dir=tmp_path)
    assert "\n" not in str(exc.value)
    if before is not None:
        assert _snapshot(path) == before


@pytest.mark.parametrize("key", ["layout", "vector_names"])
def test_resume_refuses_changed_layout_before_opening_the_checkpoint(tmp_path, key):
    from quack_rl.rl.train import resume

    path = _interrupted(tmp_path)
    cfg = json.loads((path / "config.json").read_text())
    cfg[key] = OBSERVATION_LAYOUT + 1 if key == "layout" else ["other"]
    (path / "config.json").write_text(json.dumps(cfg))
    before = _snapshot(path)
    with pytest.raises(LayoutMismatch):
        resume("cut", runs_dir=tmp_path)
    assert _snapshot(path) == before


@pytest.mark.parametrize("name", ["../x", "a/b", "..", ""])
def test_resume_refuses_a_bad_run_name(tmp_path, name):
    from quack_rl.rl.train import resume

    with pytest.raises(ValueError, match="plain folder name"):
        resume(name, runs_dir=tmp_path)


def test_resume_keeps_the_original_config_and_names_a_garbage_checkpoint(tmp_path):
    pytest.importorskip("sb3_contrib", reason="needs the train group: uv sync --group train")
    from quack_rl.rl.train import resume

    path = _interrupted(tmp_path)
    (path / "checkpoints" / "step_500.zip").write_bytes(b"garbage")
    before = _snapshot(path)
    with pytest.raises(ValueError, match="step_500.zip") as exc:
        resume("cut", runs_dir=tmp_path)
    assert "\n" not in str(exc.value)
    assert _snapshot(path) == before


@pytest.mark.slow
def test_resume_end_to_end(tmp_path):
    pytest.importorskip("sb3_contrib", reason="needs the train group: uv sync --group train")
    from quack_rl.rl.train import resume

    train(384, eval_games=1, rules="v1.1", run="e2e", runs_dir=tmp_path, checkpoint_every=128, seed=1)
    path = tmp_path / "e2e"
    config_before = (path / "config.json").read_text()
    (path / "model.zip").unlink()
    (path / "eval.json").unlink()
    (path / "checkpoints" / "step_256.zip").unlink()
    (path / "checkpoints" / "step_384.zip").unlink()
    result = resume("e2e", runs_dir=tmp_path, checkpoint_every=128)
    assert (path / "model.zip").is_file() and (path / "eval.json").is_file()
    assert (path / "config.json").read_text() == config_before
    _, episodes, metrics, evaluation = load_run(path)
    numbers = [r["episode"] for r in episodes]
    assert numbers == list(range(1, len(numbers) + 1))
    stamps = [r["timestep"] for r in metrics]
    assert stamps == sorted(set(stamps)) and stamps and stamps[-1] >= 384
    # The first new row of each log lies after the checkpoint (n=128); only metrics must reach
    # steps, an episode row is written at an episode end and may lie below it.
    for rows in (episodes, metrics):
        stamps_all = [r["timestep"] for r in rows]
        assert stamps_all == sorted(set(stamps_all))
        new_rows = [t for t in stamps_all if t > 128]
        assert new_rows and stamps_all[len(stamps_all) - len(new_rows) :] == new_rows
    assert {"baseline_random", "baseline_untrained", "trained_sampled", "trained_greedy"} <= set(
        evaluation
    )
    assert (path / "checkpoints" / "step_256.zip").is_file()
    assert result.games_played == len(episodes)
