"""Tests for reading run folders for the monitor notebook (`quack_rl.rl.monitor`)."""

import json
import subprocess
import sys
from pathlib import Path

from quack_rl.rl.monitor import RunData, load_experiment, load_run

PPO_HEADER = (
    "steps,mean_reward,games,policy_loss,value_loss,entropy,approx_kl,clip_fraction,"
    "explained_variance,wall_seconds\n"
)
BC_HEADER = "epoch,loss,entropy,wall_seconds\n"
EVAL_HEADER = "step,opponent,mode,games,wins,draws,losses,win_rate,ci_low,ci_high\n"
EVAL_ROWS = (
    "2048,random,greedy,10,6,0,4,0.6,0.31,0.83\n"
    "2048,random,sampled,10,5,1,4,0.5,0.24,0.76\n"
    "4096,random,greedy,10,7,0,3,0.7,0.40,0.89\n"
)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def ppo_folder(run: Path) -> Path:
    write(run / "config.json", json.dumps({"seed": 0, "config": {"kind": "ppo"}}))
    write(
        run / "ppo.csv",
        PPO_HEADER
        + "2048,1.5,12,-0.01,0.5,1.2,0.01,0.1,0.2,10.0\n"
        + "4096,,0,-0.02,0.4,1.1,0.02,0.2,0.3,20.0\n",
    )
    write(run / "eval.csv", EVAL_HEADER + EVAL_ROWS)
    write(run / "final_eval.csv", EVAL_HEADER + "4096,random,greedy,100,70,0,30,0.7,0.6,0.78\n")
    write(run / "done.json", "{}")
    return run


def test_full_ppo_folder(tmp_path):
    run = load_run(ppo_folder(tmp_path / "seed0"))
    assert isinstance(run, RunData)
    assert run.kind == "ppo"
    assert run.done is True
    assert run.config["seed"] == 0
    assert run.train.height == 2
    assert run.train["steps"].to_list() == [2048, 4096]
    assert run.train["mean_reward"].to_list() == [1.5, None]  # an empty cell is null
    assert run.train["explained_variance"].to_list() == [0.2, 0.3]
    assert run.evals.height == 3
    assert run.evals["win_rate"].to_list() == [0.6, 0.5, 0.7]
    assert set(run.evals["mode"].to_list()) == {"greedy", "sampled"}
    assert run.final.height == 1
    assert run.final["games"].to_list() == [100]


def test_full_bc_folder(tmp_path):
    run_dir = tmp_path / "seed1"
    write(run_dir / "config.json", json.dumps({"seed": 1}))
    write(run_dir / "bc.csv", BC_HEADER + "1,2.0,1.5,3.0\n2,1.5,1.2,6.0\n")
    write(run_dir / "eval.csv", EVAL_HEADER + EVAL_ROWS)
    run = load_run(run_dir)
    assert run.kind == "bc"
    assert run.done is False
    assert run.train["epoch"].to_list() == [1, 2]
    assert run.train["loss"].to_list() == [2.0, 1.5]
    assert run.evals.height == 3
    assert run.final.is_empty()


def test_empty_folder(tmp_path):
    run = load_run(tmp_path)
    assert run.kind is None
    assert run.done is False
    assert run.config == {}
    assert run.train.is_empty()
    assert run.evals.is_empty()
    assert run.final.is_empty()


def test_missing_folder(tmp_path):
    run = load_run(tmp_path / "nope")
    assert run.kind is None
    assert run.train.is_empty() and run.evals.is_empty() and run.final.is_empty()


def test_unreadable_config_is_empty(tmp_path):
    write(tmp_path / "config.json", '{"seed": ')
    assert load_run(tmp_path).config == {}


def test_header_only_csv(tmp_path):
    write(tmp_path / "ppo.csv", PPO_HEADER)
    write(tmp_path / "eval.csv", EVAL_HEADER)
    run = load_run(tmp_path)
    assert run.kind == "ppo"
    assert run.train.is_empty()
    assert run.train.columns == PPO_HEADER.strip().split(",")
    assert run.evals.is_empty()
    assert run.evals.columns == EVAL_HEADER.strip().split(",")


def test_empty_file_gives_empty_frame(tmp_path):
    write(tmp_path / "eval.csv", "")
    write(tmp_path / "bc.csv", "epoch,lo")  # cut off inside the header
    run = load_run(tmp_path)
    assert run.kind == "bc"
    assert run.evals.is_empty()
    assert run.train.is_empty()


def test_cut_off_last_line_in_eval_csv(tmp_path):
    write(tmp_path / "eval.csv", EVAL_HEADER + EVAL_ROWS + "6144,random,gre")
    run = load_run(tmp_path)
    assert run.evals.height == 3
    assert run.evals["step"].to_list() == [2048, 2048, 4096]


def test_cut_off_last_line_in_bc_csv(tmp_path):
    write(tmp_path / "bc.csv", BC_HEADER + "1,2.0,1.5,3.0\n2,1.5,1.")
    run = load_run(tmp_path)
    assert run.train["epoch"].to_list() == [1]
    assert run.train["entropy"].to_list() == [1.5]


def test_load_run_writes_nothing(tmp_path):
    run_dir = ppo_folder(tmp_path / "seed0")
    before = sorted((p.name, p.stat().st_mtime_ns) for p in run_dir.iterdir())
    load_run(run_dir)
    assert sorted((p.name, p.stat().st_mtime_ns) for p in run_dir.iterdir()) == before


def test_load_experiment_seed_folders_only(tmp_path):
    ppo_folder(tmp_path / "seed0")
    ppo_folder(tmp_path / "seed2")
    ppo_folder(tmp_path / "notes")
    (tmp_path / "seedx").mkdir()
    write(tmp_path / "seed5", "a file, not a folder")
    write(tmp_path / "summary.txt", "x")
    runs = load_experiment(tmp_path)
    assert sorted(runs) == [0, 2]
    assert runs[2].kind == "ppo"


def test_load_experiment_missing_or_empty(tmp_path):
    assert load_experiment(tmp_path / "missing") == {}
    assert load_experiment(tmp_path) == {}


def test_monitor_imports_only_stdlib_and_polars():
    code = (
        "import sys, quack_rl.rl.monitor\n"
        "bad = [m for m in ('marimo', 'altair', 'torch') if m in sys.modules]\n"
        "print(','.join(bad))\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == ""
