import importlib.util
from pathlib import Path

import pytest

from quack_rl.rl.evaluate import EvalResult
from quack_rl.rl.train import TrainingLog, TrainResult

_spec = importlib.util.spec_from_file_location(
    "train_script", Path(__file__).parent.parent / "scripts" / "train.py"
)
assert _spec and _spec.loader
train_script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(train_script)


def _eval(wins: int, draws: int, losses: int) -> EvalResult:
    games = wins + draws + losses
    return EvalResult(games, wins, draws, losses, 1.0, 1.0, 0.1, wins / games, draws / games,
                      losses / games)  # fmt: skip


def _stub_result(vs_random: bool) -> TrainResult:
    extra = {}
    if vs_random:
        extra = {
            "baseline_random_vs_random": _eval(1, 2, 7),
            "baseline_untrained_vs_random": _eval(2, 2, 6),
            "trained_sampled_vs_random": _eval(6, 1, 3),
            "trained_greedy_vs_random": _eval(7, 1, 2),
        }
    return TrainResult(
        model=None,
        log=TrainingLog(),
        baseline_random=_eval(1, 1, 8),
        baseline_untrained=_eval(2, 1, 7),
        trained_sampled=_eval(5, 1, 4),
        trained_greedy=_eval(6, 1, 3),
        games_played=77,
        **extra,
    )


def test_help_shows_the_steps_default(capsys):
    with pytest.raises(SystemExit) as exc:
        train_script.main(["--help"])
    assert exc.value.code == 0
    out = " ".join(capsys.readouterr().out.split())
    assert "--steps" in out and f"default: {train_script.DEFAULT_STEPS}" in out


def test_missing_run_fails_and_trains_nothing(monkeypatch, tmp_path, capsys):
    calls = []
    monkeypatch.setattr(train_script, "train", lambda *a, **k: calls.append(k))
    with pytest.raises(SystemExit) as exc:
        train_script.main(["--runs-dir", str(tmp_path)])
    assert exc.value.code != 0
    assert "--run" in capsys.readouterr().err
    assert calls == [] and list(tmp_path.iterdir()) == []


def test_bad_opponent_fails_with_known_forms(tmp_path, capsys):
    code = train_script.main(["--run", "r", "--rules", "v1.1", "--opponent", "nonsense", "--runs-dir", str(tmp_path)])
    err = capsys.readouterr().err
    assert code != 0
    assert "random" in err and "draw<percent>-pts<round>-<strategy>" in err
    assert "Traceback" not in err
    assert list(tmp_path.iterdir()) == []


def test_existing_run_fails_and_stays_unchanged(tmp_path, capsys):
    folder = tmp_path / "old"
    folder.mkdir()
    (folder / "model.zip").write_text("keep")
    code = train_script.main(["--run", "old", "--rules", "v1.1", "--runs-dir", str(tmp_path)])
    err = capsys.readouterr().err
    assert code != 0 and str(folder) in err and "Traceback" not in err
    assert [p.name for p in folder.iterdir()] == ["model.zip"]
    assert (folder / "model.zip").read_text() == "keep"


def test_bad_run_name_fails_and_writes_nothing(tmp_path, capsys):
    runs = tmp_path / "runs"
    runs.mkdir()
    code = train_script.main(["--run", "../x", "--runs-dir", str(runs)])
    err = capsys.readouterr().err
    assert code != 0 and "Traceback" not in err and err.strip()
    assert list(runs.iterdir()) == []
    assert not (tmp_path / "x").exists()


def test_options_go_to_train(monkeypatch, tmp_path):
    calls = []

    def stub(*args, **kwargs):
        calls.append((args, kwargs))
        return _stub_result(False)

    monkeypatch.setattr(train_script, "train", stub)
    code = train_script.main([
        "--run", "r1", "--steps", "300", "--opponent", "draw20-pts4-blue", "--rules", "v1",
        "--seed", "3", "--eval-games", "11", "--checkpoint-every", "100",
        "--runs-dir", str(tmp_path),
    ])  # fmt: skip
    assert code == 0
    ((args, kwargs),) = calls
    assert args == (300,)
    assert kwargs == {
        "rules": "v1", "opponent": "draw20-pts4-blue", "seed": 3, "eval_games": 11,
        "run": "r1", "runs_dir": tmp_path, "checkpoint_every": 100,
    }  # fmt: skip


def test_defaults_go_to_train(monkeypatch):
    calls = []
    monkeypatch.setattr(
        train_script, "train", lambda *a, **k: calls.append((a, k)) or _stub_result(False)
    )
    assert train_script.main(["--run", "r"]) == 0
    ((args, kwargs),) = calls
    assert args == (train_script.DEFAULT_STEPS,)
    assert kwargs == {
        "rules": "v1.10", "opponent": "random", "seed": 0, "eval_games": 500,
        "run": "r", "runs_dir": Path("data/runs"), "checkpoint_every": None,
    }  # fmt: skip


def test_prints_folder_and_table_against_random(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(train_script, "train", lambda *a, **k: _stub_result(False))
    assert train_script.main(["--run", "r", "--runs-dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert str(tmp_path / "r") in out
    assert "games_played: 77" in out
    lines = {line.split("  ")[0].strip(): line.split() for line in out.splitlines()}
    for label in ("random agent", "untrained network", "trained (sampled)", "trained (greedy)"):
        assert label in lines
    assert "wins" in out and "draws" in out and "losses" in out
    assert "vs RandomBot" not in out
    assert lines["trained (greedy)"][-3:] == ["6", "1", "3"]


def test_prints_randombot_rows_for_other_opponents(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(train_script, "train", lambda *a, **k: _stub_result(True))
    code = train_script.main(
        ["--run", "r", "--opponent", "draw20-pts4-blue", "--runs-dir", str(tmp_path)]
    )
    out = capsys.readouterr().out
    assert code == 0 and "vs RandomBot" in out
    section = out.split("vs RandomBot")[1]
    assert "trained (greedy)" in section
    assert [ln for ln in section.splitlines() if "trained (greedy)" in ln][0].split()[-3:] == [
        "7", "1", "2",
    ]  # fmt: skip


@pytest.mark.slow
def test_real_run_writes_the_run_folder(tmp_path, capsys):
    pytest.importorskip("sb3_contrib", reason="needs the train group: uv sync --group train")
    code = train_script.main([
        "--run", "smoke", "--rules", "v1.1", "--steps", "256", "--eval-games", "10", "--checkpoint-every", "128",
        "--runs-dir", str(tmp_path),
    ])  # fmt: skip
    assert code == 0
    folder = tmp_path / "smoke"
    for name in ("config.json", "episodes.csv", "metrics.csv", "eval.json", "model.zip"):
        assert (folder / name).is_file(), name
    assert (folder / "checkpoints" / "step_128.zip").is_file()
    assert str(folder) in capsys.readouterr().out


def test_resume_of_a_missing_run_exits_2(tmp_path, capsys):
    code = train_script.main(["--resume", "nope", "--runs-dir", str(tmp_path)])
    err = capsys.readouterr().err
    assert code == 2 and err.startswith("error: ") and "nope" in err and "Traceback" not in err


@pytest.mark.parametrize(
    "extra",
    [["--run", "a"], ["--steps", "5"], ["--opponent", "random"], ["--rules", "v1.1"],
     ["--seed", "0"], ["--eval-games", "3"]],
)  # fmt: skip
def test_resume_with_config_flags_is_refused(extra, monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(train_script, "resume", lambda *a, **k: calls.append(k))
    with pytest.raises(SystemExit) as exc:
        train_script.main(["--resume", "r", "--runs-dir", str(tmp_path), *extra])
    assert exc.value.code == 2 and calls == []


def test_resume_goes_to_resume_and_prints_the_report(monkeypatch, tmp_path, capsys):
    (tmp_path / "r").mkdir()
    (tmp_path / "r" / "config.json").write_text('{"opponent": "random"}')
    calls = []
    monkeypatch.setattr(
        train_script, "resume", lambda *a, **k: calls.append((a, k)) or _stub_result(False)
    )
    code = train_script.main(
        ["--resume", "r", "--runs-dir", str(tmp_path), "--checkpoint-every", "64"]
    )
    assert code == 0 and calls == [(("r",), {"runs_dir": tmp_path, "checkpoint_every": 64})]
    assert str(tmp_path / "r") in capsys.readouterr().out


def test_help_shows_resume(capsys):
    with pytest.raises(SystemExit):
        train_script.main(["--help"])
    assert "--resume" in capsys.readouterr().out


def test_default_rules_are_refused_with_the_hint_to_name_an_older_version(tmp_path, capsys):
    code = train_script.main(["--run", "r", "--runs-dir", str(tmp_path)])
    err = capsys.readouterr().err
    assert code != 0 and "older rules version" in err and "Traceback" not in err
    assert list(tmp_path.iterdir()) == []
