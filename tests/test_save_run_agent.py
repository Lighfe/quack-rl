"""`scripts/save_run_agent.py`: a finished experiment run folder (PPO or BC) becomes an agent folder
under the agents root the owner names (#307). The tests that train need the `rl` group."""

import json
import runpy
import sys
from pathlib import Path

import pytest

from quack_rl.rl.agents import load_agent, read_manifest
from quack_rl.rl.experiment import ExperimentConfig
from quack_rl.rules import load_ruleset

REPO = Path(__file__).resolve().parents[1]
RS = load_ruleset("v2.3")


def run_script(monkeypatch, *args: str) -> int | str | None:
    script = REPO / "scripts" / "save_run_agent.py"
    monkeypatch.setattr(sys, "argv", [str(script), *args])
    try:
        runpy.run_path(str(script), run_name="__main__")
    except SystemExit as stop:
        return stop.code
    return 0


def tiny_ppo() -> ExperimentConfig:
    return ExperimentConfig.model_validate(
        {
            "id": "P0",
            "kind": "ppo",
            "baseline": None,
            "changes": "tiny",
            "steps": 128,
            "opponents": [{"spec": "bot:random"}],
            "hidden": 32,
            "checkpoint_every": 64,
            "n_steps": 64,
            "batch_size": 32,
            "target_kl": 0.03,
        }
    )


@pytest.fixture(scope="module")
def ppo_run(tmp_path_factory) -> Path:
    pytest.importorskip("sb3_contrib")
    from quack_rl.rl.ppo_run import run_ppo_seed

    return run_ppo_seed(tiny_ppo(), 0, tmp_path_factory.mktemp("ppo") / "seed0")


@pytest.fixture(scope="module")
def bc_run(tmp_path_factory) -> Path:
    pytest.importorskip("torch")
    from quack_rl.rl.bc_run import run_bc_seed
    from quack_rl.rl.dataset import build_dataset

    data = tmp_path_factory.mktemp("data") / "dataset.npz"
    build_dataset("bot:random", "bot:random", 3, seed=0).save(data)
    config = ExperimentConfig.model_validate(
        {
            "id": "B0",
            "kind": "bc",
            "baseline": None,
            "changes": "tiny",
            "hidden": 32,
            "bc": {"dataset": str(data), "epochs": 1},
        }
    )
    return run_bc_seed(config, 0, tmp_path_factory.mktemp("bc") / "seed0")


def test_ppo_run_saves_the_final_checkpoint_as_an_agent(ppo_run, tmp_path, monkeypatch):
    root = tmp_path / "agents"
    assert run_script(monkeypatch, str(ppo_run), "--agent-name", "p", "--agents-root", str(root)) == 0
    manifest = read_manifest(root / "p")
    assert manifest.kind == "ppo"
    assert manifest.settings["checkpoint_step"] == 128
    assert manifest.settings["run_dir"] == str(ppo_run)
    assert (root / "p" / "model.zip").read_bytes() == (
        ppo_run / "checkpoints" / "step_128.zip"
    ).read_bytes()
    assert load_agent("p", RS, root=root).name == "agent:p"


def test_ppo_run_saves_a_chosen_checkpoint(ppo_run, tmp_path, monkeypatch):
    root = tmp_path / "agents"
    code = run_script(
        monkeypatch, str(ppo_run), "--agent-name", "p", "--agents-root", str(root), "--step", "64"
    )
    assert code == 0
    assert read_manifest(root / "p").settings["checkpoint_step"] == 64
    load_agent("p", RS, root=root)


def test_missing_checkpoint_step_gives_exit_1_and_writes_nothing(ppo_run, tmp_path, monkeypatch):
    root = tmp_path / "agents"
    code = run_script(
        monkeypatch, str(ppo_run), "--agent-name", "p", "--agents-root", str(root), "--step", "99"
    )
    assert code == 1
    assert not root.exists()


def test_bc_run_saves_model_pt_as_an_agent(bc_run, tmp_path, monkeypatch):
    root = tmp_path / "agents"
    assert run_script(monkeypatch, str(bc_run), "--agent-name", "b", "--agents-root", str(root)) == 0
    manifest = read_manifest(root / "b")
    assert manifest.kind == "bc"
    assert manifest.settings["hidden"] == 32
    load_agent("b", RS, root=root)


def test_step_is_refused_for_a_bc_run(bc_run, tmp_path, monkeypatch):
    root = tmp_path / "agents"
    code = run_script(
        monkeypatch, str(bc_run), "--agent-name", "b", "--agents-root", str(root), "--step", "1"
    )
    assert code == 1
    assert not root.exists()


def test_run_without_done_json_gives_exit_1_and_writes_nothing(tmp_path, monkeypatch):
    run = tmp_path / "run"
    run.mkdir()
    (run / "config.json").write_text(json.dumps({"config": {"kind": "ppo"}, "rules": "v2.3"}))
    root = tmp_path / "agents"
    assert run_script(monkeypatch, str(run), "--agent-name", "x", "--agents-root", str(root)) == 1
    assert not root.exists()


def test_existing_agent_gives_exit_1(ppo_run, tmp_path, monkeypatch):
    root = tmp_path / "agents"
    args = (str(ppo_run), "--agent-name", "p", "--agents-root", str(root))
    assert run_script(monkeypatch, *args) == 0
    assert run_script(monkeypatch, *args) == 1


def test_agents_root_is_required(ppo_run, monkeypatch):
    assert run_script(monkeypatch, str(ppo_run), "--agent-name", "p") == 2
