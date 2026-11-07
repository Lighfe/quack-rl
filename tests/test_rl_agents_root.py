"""`--agents-root PATH` of the training scripts: agents are saved under PATH, not `data/agents/`.

Every test changes the working folder to an empty tmp folder `work`, so a script that ignored
`--agents-root` would leave `work/data/agents`. The tests that train need the `rl` group.
"""

import runpy
import sys
from pathlib import Path

import pytest

from quack_rl.rl.agents import AgentManifest, save_agent
from quack_rl.rl.encode import BOARD_LAYOUT

REPO = Path(__file__).resolve().parents[1]


def run_script(monkeypatch, script: str, *args: str) -> int | str | None:
    monkeypatch.setattr(sys, "argv", [script, *args])
    try:
        runpy.run_path(str(REPO / "scripts" / script), run_name="__main__")
    except SystemExit as stop:
        return stop.code
    return 0


def fake_agent(root: Path, name: str) -> Path:
    folder = root / name
    folder.mkdir(parents=True)
    (folder / "model.zip").write_bytes(b"not a real model")
    manifest = AgentManifest(
        name=name,
        kind="ppo",
        rules="v2.3",
        layout=BOARD_LAYOUT,
        weights="model.zip",
        created_at="2026-11-07T00:00:00+00:00",
    )
    save_agent(folder, manifest)
    return folder


@pytest.fixture
def work(tmp_path, monkeypatch) -> Path:
    folder = tmp_path / "work"
    folder.mkdir()
    monkeypatch.chdir(folder)
    return folder


# --- an existing agent under --agents-root stops each script before training ------------------


@pytest.mark.parametrize(
    "script, args",
    [
        ("train_ppo.py", ["--steps", "1", "--out", "run"]),
        ("train_selfplay.py", ["--rounds", "1", "--steps-per-round", "1", "--out", "run"]),
        ("train_selfplay.py", ["--resume", "run"]),
        ("train_offline.py", ["--dataset", "nothing.npz", "--method", "bc", "--out", "run"]),
    ],
)
def test_existing_agent_under_the_root_stops_before_training(
    work, tmp_path, monkeypatch, script, args
):
    root = tmp_path / "agents"
    folder = fake_agent(root, "taken")
    before = {p.name: p.read_bytes() for p in folder.iterdir()}
    code = run_script(
        monkeypatch, script, *args, "--agents-root", str(root), "--agent-name", "taken"
    )
    assert code not in (0, None)
    assert not (work / "run").exists()  # no training started
    assert {p.name: p.read_bytes() for p in folder.iterdir()} == before
    assert not (work / "data" / "agents").exists()


def test_agent_name_help_does_not_name_data_agents_as_the_only_place(work, monkeypatch, capsys):
    for script in ("train_ppo.py", "train_selfplay.py", "train_offline.py"):
        assert run_script(monkeypatch, script, "--help") == 0
        text = " ".join(capsys.readouterr().out.split())
        assert "--agents-root" in text
        assert "data/agents/<name>" not in text, script


# --- the scripts save the agent under --agents-root (the `rl` group) --------------------------


@pytest.mark.slow
def test_train_ppo_saves_the_agent_under_the_root(work, tmp_path, monkeypatch):
    pytest.importorskip("sb3_contrib")
    root = tmp_path / "agents"
    code = run_script(
        monkeypatch,
        "train_ppo.py",
        *("--steps", "64", "--eval-games", "2", "--out", "run"),
        *("--agents-root", str(root), "--agent-name", "x"),
    )
    assert code == 0
    assert (root / "x" / "agent.json").is_file()
    assert not (work / "data" / "agents").exists()


@pytest.mark.slow
def test_train_selfplay_saves_the_agent_under_the_root_with_out_and_resume(
    work, tmp_path, monkeypatch
):
    pytest.importorskip("sb3_contrib")
    root = tmp_path / "agents"
    settings = ("--rounds", "1", "--steps-per-round", "64", "--pool-size", "1")
    code = run_script(
        monkeypatch,
        "train_selfplay.py",
        *settings,
        *("--eval-games", "2", "--out", "run"),
        *("--agents-root", str(root), "--agent-name", "x"),
    )
    assert code == 0
    assert (root / "x" / "agent.json").is_file()
    assert not (work / "data" / "agents").exists()

    code = run_script(
        monkeypatch,
        "train_selfplay.py",
        *("--resume", "run", "--agents-root", str(root), "--agent-name", "y"),
    )
    assert code == 0
    assert (root / "y" / "agent.json").is_file()
    assert not (work / "data" / "agents").exists()


@pytest.mark.slow
def test_train_offline_saves_the_agent_under_the_root(work, tmp_path, monkeypatch):
    pytest.importorskip("torch")
    from quack_rl.rl.dataset import build_dataset

    build_dataset("bot:random", "bot:random", 2, seed=0).save(work / "tiny.npz")
    root = tmp_path / "agents"
    code = run_script(
        monkeypatch,
        "train_offline.py",
        *("--dataset", "tiny.npz", "--method", "bc", "--epochs", "1"),
        *("--eval-games", "2", "--out", "run"),
        *("--agents-root", str(root), "--agent-name", "x"),
    )
    assert code == 0
    assert (root / "x" / "agent.json").is_file()
    assert not (work / "data" / "agents").exists()
