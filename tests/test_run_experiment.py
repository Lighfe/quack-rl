"""Tests for the experiment command `scripts/run_experiment.py`."""

import csv
import importlib.util
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "run_experiment.py"

spec = importlib.util.spec_from_file_location("run_experiment", SCRIPT)
assert spec is not None and spec.loader is not None
rx = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rx)


def write_config(folder: Path, **overrides) -> Path:
    data = {
        "id": "T0",
        "kind": "ppo",
        "baseline": None,
        "changes": "test baseline",
        "seeds": [0, 1, 2],
        "steps": 2048,
        "opponents": [{"spec": "bot:random"}],
        "hidden": 32,
        "live_eval_games": 1,
        "final_eval_games": 1,
    }
    data.update(overrides)
    path = folder / f"{data['id']}.json"
    path.write_text(json.dumps(data))
    return path


def bc_config(folder: Path, dataset: Path, **overrides) -> Path:
    data = {
        "kind": "bc",
        "id": "B0",
        "steps": None,
        "opponents": [],
        "bc": {"dataset": str(dataset), "epochs": 1},
    }
    data.update(overrides)
    return write_config(folder, **data)


def run(args: list[str], cwd: Path, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        **kwargs,
    )


def processes_naming(text: str) -> list[str]:
    """The command lines of the running processes that contain `text` (Linux /proc)."""
    found = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            raw = (entry / "cmdline").read_bytes()
            state = (entry / "stat").read_text().rsplit(")", 1)[1].split()[0]
        except OSError:
            continue
        if state == "Z":
            continue
        cmdline = raw.replace(b"\0", b" ").decode(errors="replace")
        if text in cmdline:
            found.append(cmdline)
    return found


# --- argument and folder checks: no process starts -------------------------------------------


def test_a_seed_not_in_the_config_gives_exit_2(tmp_path):
    config = write_config(tmp_path, seeds=[0, 1])
    done = rx.main(["--config", str(config), "--out", str(tmp_path / "out"), "--seeds", "0,5"])
    assert done == 2
    assert not (tmp_path / "out").exists()


def test_steps_with_a_bc_config_gives_exit_2(tmp_path, capsys):
    config = bc_config(tmp_path, tmp_path / "data.npz")
    done = rx.main(["--config", str(config), "--out", str(tmp_path / "out"), "--steps", "1024"])
    assert done == 2
    assert "--steps" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


def test_fresh_run_on_an_existing_config_gives_exit_1_naming_the_folder(tmp_path, capsys):
    config = write_config(tmp_path)
    folder = tmp_path / "out" / "T0" / "seed1"
    folder.mkdir(parents=True)
    (folder / "config.json").write_text("{}")
    done = rx.main(["--config", str(config), "--out", str(tmp_path / "out")])
    assert done == 1
    assert str(folder) in capsys.readouterr().err
    assert sorted(p.name for p in (tmp_path / "out" / "T0").iterdir()) == ["seed1"]


def test_resume_of_an_unfinished_bc_seed_gives_exit_1_and_asks_to_delete(tmp_path, capsys):
    config = bc_config(tmp_path, tmp_path / "data.npz")
    folder = tmp_path / "out" / "B0" / "seed2"
    folder.mkdir(parents=True)
    (folder / "config.json").write_text("{}")
    done = rx.main(["--config", str(config), "--out", str(tmp_path / "out"), "--resume"])
    assert done == 1
    err = capsys.readouterr().err
    assert str(folder) in err and "delete" in err


def test_seed_folders_and_default_seeds(tmp_path):
    config = rx.load_config(write_config(tmp_path, seeds=[3, 4]))
    assert rx.pick_seeds(config, None) == [3, 4]
    assert rx.pick_seeds(config, [4]) == [4]
    assert rx.seed_dir(tmp_path, config, 4) == tmp_path / "T0" / "seed4"


# --- the children ----------------------------------------------------------------------------


def test_child_env_sets_the_thread_counts():
    env = rx.child_env(3, {"PATH": "/bin", "OMP_NUM_THREADS": "8"})
    assert env == {"PATH": "/bin", "OMP_NUM_THREADS": "3", "MKL_NUM_THREADS": "3"}


def test_each_child_gets_the_threads_and_the_config_file_as_loaded(tmp_path):
    path = write_config(tmp_path, live_eval_games=7)
    config = rx.load_config(path)
    children = rx.run_children_for(
        config, path, 1, tmp_path / "seed1", steps=1024, resume=True, threads=2, eval_poll=0.1
    )
    assert [c.role for c in children] == ["training", "evaluator"]
    for child in children:
        assert child.env["OMP_NUM_THREADS"] == "2" and child.env["MKL_NUM_THREADS"] == "2"
        assert child.seed == 1
    train, evaluator = (c.cmd for c in children)
    assert train[train.index("--config") + 1] == str(path)
    assert train[train.index("--steps") + 1] == "1024" and "--resume" in train
    assert evaluator[evaluator.index("--games") + 1] == "7"
    assert evaluator[evaluator.index("--modes") + 1] == "greedy,sampled"
    final = rx.final_child(config, 1, tmp_path / "seed1", 2)
    assert final.env["OMP_NUM_THREADS"] == "2" and "--final" in final.cmd
    assert final.cmd[final.cmd.index("--games") + 1] == str(config.final_eval_games)
    assert final.cmd[final.cmd.index("--seed") + 1] == str(config.final_eval_seed)


def test_a_finished_bc_seed_gets_only_an_evaluator(tmp_path):
    path = bc_config(tmp_path, tmp_path / "data.npz")
    (tmp_path / "seed0").mkdir()
    (tmp_path / "seed0" / "done.json").write_text("{}")
    children = rx.run_children_for(
        rx.load_config(path),
        path,
        0,
        tmp_path / "seed0",
        steps=None,
        resume=True,
        threads=1,
        eval_poll=0.1,
    )
    assert [c.role for c in children] == ["evaluator"]


def test_a_child_gets_its_env(tmp_path):
    out = tmp_path / "env.json"
    code = f"import json, os; json.dump(dict(os.environ), open({str(out)!r}, 'w'))"
    child = rx.Child(0, "training", [sys.executable, "-c", code], rx.child_env(4))
    assert rx.run_children([child]) is None
    env = json.loads(out.read_text())
    assert env["OMP_NUM_THREADS"] == "4" and env["MKL_NUM_THREADS"] == "4"


def test_a_failing_child_stops_the_others(tmp_path):
    marker = str(tmp_path / "sleeper")
    sleeper = rx.Child(
        1, "evaluator", [sys.executable, "-c", "import time; time.sleep(600)", marker], {}
    )
    failing = rx.Child(0, "training", [sys.executable, "-c", "raise SystemExit(3)"], {})
    started = time.monotonic()
    message = rx.run_children([sleeper, failing])
    assert time.monotonic() - started < 30
    assert message is not None and "seed 0" in message and "training" in message
    assert sleeper.proc is not None and sleeper.proc.poll() is not None
    assert processes_naming(marker) == []


# --- whole runs ------------------------------------------------------------------------------


@pytest.mark.slow
def test_ppo_run_of_two_seeds(tmp_path):
    pytest.importorskip("sb3_contrib")
    config = write_config(tmp_path)
    out = tmp_path / "out"
    args = ["--config", str(config), "--out", str(out), "--seeds", "0,1", "--steps", "1024"]
    done = run([*args, "--eval-poll", "0.2"], tmp_path, timeout=900)
    assert done.returncode == 0, done.stderr
    assert sorted(p.name for p in (out / "T0").iterdir()) == ["seed0", "seed1"]
    for seed in (0, 1):
        folder = out / "T0" / f"seed{seed}"
        for name in ("done.json", "eval.csv", "final_eval.csv"):
            assert (folder / name).is_file(), (seed, name)
        assert json.loads((folder / "config.json").read_text())["steps"] == 1024
        with (folder / "final_eval.csv").open(newline="") as handle:
            modes = {row["mode"] for row in csv.DictReader(handle)}
        assert modes == {"greedy", "sampled"}
    lines = done.stdout.splitlines()
    table = [line for line in lines if line.split()[:1] in (["0"], ["1"])]
    assert len(table) == 2 * 4 * 2  # seeds x opponents x modes
    assert all("[" in line for line in table)
    assert processes_naming(str(out)) == []

    # resume: done seeds are not trained again, the final evaluation is redone
    before = (out / "T0" / "seed0" / "done.json").read_text()
    (out / "T0" / "seed0" / "final_eval.csv").unlink()
    again = run([*args, "--resume", "--eval-poll", "0.2"], tmp_path, timeout=900)
    assert again.returncode == 0, again.stderr
    assert (out / "T0" / "seed0" / "done.json").read_text() == before
    assert (out / "T0" / "seed0" / "final_eval.csv").is_file()


@pytest.mark.slow
def test_bc_run_with_a_missing_dataset_gives_exit_1_and_no_child(tmp_path):
    pytest.importorskip("torch")
    config = bc_config(tmp_path, tmp_path / "missing.npz")
    out = tmp_path / "out"
    done = run(
        ["--config", str(config), "--out", str(out), "--eval-poll", "0.2"], tmp_path, timeout=300
    )
    assert done.returncode == 1
    assert "training" in done.stderr and "seed" in done.stderr
    assert processes_naming(str(out)) == []


@pytest.mark.slow
def test_sigint_stops_all_children(tmp_path):
    pytest.importorskip("sb3_contrib")
    config = write_config(tmp_path, steps=10_000_000)
    out = tmp_path / "out"
    proc = subprocess.Popen(
        [
            sys.executable,
            str(SCRIPT),
            "--config",
            str(config),
            "--out",
            str(out),
            "--seeds",
            "0,1",
            "--eval-poll",
            "0.2",
        ],
        cwd=tmp_path,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if all((out / "T0" / f"seed{s}" / "config.json").is_file() for s in (0, 1)):
                break
            time.sleep(0.2)
        else:
            pytest.fail("the trainings did not start")
        assert len(processes_naming(str(out))) >= 4
        os.kill(proc.pid, signal.SIGINT)
        code = proc.wait(60)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    assert code != 0
    assert processes_naming(str(out)) == []
