"""Agent folders (`data/agents/<name>/`) and the seat `agent:<name>`.

The tests that train a model need the `rl` group (`uv run --group rl --with pytest pytest
tests/test_rl_agents.py`); they skip without it. Every agent is written under `tmp_path`.
"""

import csv
import json
import runpy
import sys
from pathlib import Path

import pytest
import typer

from quack_rl.bots import RandomBot
from quack_rl.cli.seats import check_seat, parse_seat
from quack_rl.rl import agents
from quack_rl.rl.agents import (
    AgentError,
    AgentManifest,
    list_agents,
    load_agent,
    save_agent,
    write_agent,
)
from quack_rl.rl.encode import BOARD_LAYOUT
from quack_rl.rules import load_ruleset
from quack_rl.simgame import play_sim_game

RS = load_ruleset("v2.3")
REPO = Path(__file__).resolve().parents[1]


def manifest(name: str, kind: str = "ppo", **changes) -> AgentManifest:
    data = {
        "name": name,
        "kind": kind,
        "rules": RS.version,
        "layout": BOARD_LAYOUT,
        "weights": None if kind == "planner" else agents.WEIGHTS_FILES[kind],
        "settings": {"obs_dim": 4, "n_actions": 2},
        "created_at": "2026-11-05T00:00:00+00:00",
    }
    data.update(changes)
    return AgentManifest(**data)


def fake_agent(root: Path, name: str, kind: str = "ppo", **changes) -> Path:
    """An agent folder whose weights file is a few bytes (enough for every check before torch)."""
    folder = root / name
    folder.mkdir(parents=True)
    m = manifest(name, kind, **changes)
    if m.weights is not None:
        (folder / m.weights).write_bytes(b"not a real model")
    save_agent(folder, m)
    return folder


# --- the folder format and its checks (no `rl` group needed) ---------------------------------


def test_save_agent_writes_the_manifest_with_the_weights_hash(tmp_path):
    import hashlib

    folder = fake_agent(tmp_path, "a1")
    data = json.loads((folder / "agent.json").read_text())
    assert data["weights_sha256"] == hashlib.sha256(b"not a real model").hexdigest()
    assert data["kind"] == "ppo" and data["rules"] == "v2.3" and data["layout"] == BOARD_LAYOUT


def test_missing_folder_names_the_path(tmp_path):
    with pytest.raises(AgentError, match=str(tmp_path / "nobody")):
        load_agent("nobody", RS, root=tmp_path)


def test_other_rules_version_is_refused(tmp_path):
    fake_agent(tmp_path, "old", rules="v2.2")
    with pytest.raises(AgentError, match="rules v2.2"):
        load_agent("old", RS, root=tmp_path)


def test_other_layout_is_refused(tmp_path):
    fake_agent(tmp_path, "wide", layout=BOARD_LAYOUT + 1)
    with pytest.raises(AgentError, match=f"layout {BOARD_LAYOUT + 1}"):
        load_agent("wide", RS, root=tmp_path)


def test_changed_weights_do_not_match_the_hash(tmp_path):
    folder = fake_agent(tmp_path, "changed")
    (folder / "model.zip").write_bytes(b"other bytes")
    with pytest.raises(AgentError, match="hash"):
        load_agent("changed", RS, root=tmp_path)


def test_planner_without_a_factory_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(agents, "PLANNER_FACTORY", None)
    fake_agent(tmp_path, "plan", kind="planner")
    with pytest.raises(AgentError, match="planner"):
        load_agent("plan", RS, root=tmp_path)


def test_planner_factory_builds_the_seat(tmp_path, monkeypatch):
    seen = []

    def factory(rs, m, seed):
        seen.append((rs.version, m.name, seed))
        return RandomBot(seed)

    monkeypatch.setattr(agents, "PLANNER_FACTORY", factory)
    fake_agent(tmp_path, "plan", kind="planner")
    assert isinstance(load_agent("plan", RS, 7, root=tmp_path), RandomBot)
    assert seen == [("v2.3", "plan", 7)]


def test_list_agents_skips_a_broken_folder_with_a_warning(tmp_path):
    fake_agent(tmp_path, "good1")
    fake_agent(tmp_path, "good2", kind="planner")
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "agent.json").write_text("{not json")
    with pytest.warns(UserWarning, match="broken"):
        found = list_agents(tmp_path)
    assert [m.name for m in found] == ["good1", "good2"]


@pytest.mark.parametrize("kind", ["ppo", "bc", "cql"])
def test_without_torch_the_error_names_the_rl_group(tmp_path, monkeypatch, kind):
    fake_agent(tmp_path, "net", kind=kind)
    monkeypatch.setitem(sys.modules, "torch", None)  # `import torch` raises ImportError
    with pytest.raises(AgentError, match="`rl` dependency group"):
        load_agent("net", RS, root=tmp_path)


# --- the seat `agent:<name>` ------------------------------------------------------------------


def test_check_seat_accepts_an_existing_agent_and_names_a_missing_one(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fake_agent(tmp_path / "data" / "agents", "here")
    check_seat("agent:here")
    with pytest.raises(typer.BadParameter, match="'gone'"):
        check_seat("agent:gone")


@pytest.mark.parametrize("spec", ["agent:", "agent:../x", "agent:A/b"])
def test_check_seat_rejects_bad_names(tmp_path, monkeypatch, spec):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "agent.json").write_text("{}")
    with pytest.raises(typer.BadParameter, match="not valid"):
        check_seat(spec)


def test_parse_seat_returns_the_loaded_agent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(agents, "PLANNER_FACTORY", lambda rs, m, seed: RandomBot(seed))
    fake_agent(tmp_path / "data" / "agents", "plan", kind="planner")
    seat = parse_seat("agent:plan", 5, rs=RS)
    assert isinstance(seat, RandomBot)


# --- the scripts refuse an existing agent before training -------------------------------------


@pytest.mark.parametrize(
    "script, args",
    [
        ("train_ppo.py", ["--steps", "1"]),
        ("train_selfplay.py", ["--rounds", "1", "--steps-per-round", "1"]),
        ("train_offline.py", ["--dataset", "nothing.npz", "--method", "bc"]),
    ],
)
def test_script_stops_before_training_when_the_agent_exists(tmp_path, monkeypatch, script, args):
    monkeypatch.chdir(tmp_path)
    folder = fake_agent(tmp_path / "data" / "agents", "taken")
    before = {p.name: p.read_bytes() for p in folder.iterdir()}
    argv = [script, *args, "--out", "run", "--agent-name", "taken"]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as stop:
        runpy.run_path(str(REPO / "scripts" / script), run_name="__main__")
    assert stop.value.code != 0
    assert not (tmp_path / "run").exists()  # no training started
    assert {p.name: p.read_bytes() for p in folder.iterdir()} == before


# --- trained agents (the `rl` group) ----------------------------------------------------------


@pytest.fixture(scope="module")
def trained(tmp_path_factory) -> Path:
    """An agents root with a tiny PPO, BC and CQL agent (`tiny-ppo`, `tiny-bc`, `tiny-cql`)."""
    pytest.importorskip("sb3_contrib")
    import torch

    from quack_rl.rl.dataset import build_dataset
    from quack_rl.rl.offline import train_bc, train_cql
    from quack_rl.rl.train import train_ppo

    root = tmp_path_factory.mktemp("agents")
    work = tmp_path_factory.mktemp("work")
    model = train_ppo("bot:random", 256, seed=0).model
    model.save(str(work / "model.zip"))
    write_agent("tiny-ppo", "ppo", work / "model.zip", "v2.3", {"steps": 256}, root)
    data = build_dataset("bot:random", "bot:random", 3, seed=0)
    shape = {"obs_dim": int(data.obs.shape[1]), "n_actions": int(data.mask.shape[1]), "hidden": 32}
    for kind, policy in (
        ("bc", train_bc(data, 1, hidden=32)),
        ("cql", train_cql(data, 5, hidden=32, batch_size=16)),
    ):
        torch.save(policy.net.state_dict(), work / f"{kind}.pt")
        write_agent(f"tiny-{kind}", kind, work / f"{kind}.pt", "v2.3", shape, root)
    return root


@pytest.mark.slow
@pytest.mark.parametrize("name", ["tiny-ppo", "tiny-bc", "tiny-cql"])
def test_tiny_agent_plays_four_games_to_the_end(trained, tmp_path, monkeypatch, name):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "agents").symlink_to(trained)
    for game in range(4):  # an illegal action would raise IllegalAction in the engine
        p1, p2 = (f"agent:{name}", "bot:random")[:: 1 if game % 2 == 0 else -1]
        final, _, _ = play_sim_game(
            RS, rules="v2.3", rounds=RS.rounds, overrides={}, p1=p1, p2=p2, game_seed=game
        )
        assert final.winner is not None


@pytest.mark.slow
def test_loaded_ppo_trains_further(trained):
    from sb3_contrib import MaskablePPO

    from quack_rl.rl import QuackEnv
    from quack_rl.rl.opponents import make_opponent

    seat = load_agent("tiny-ppo", RS, root=trained)
    assert seat.name == "agent:tiny-ppo"
    env = QuackEnv(seat="random", opponent=make_opponent("bot:random", 0))
    model = MaskablePPO.load(str(trained / "tiny-ppo" / "model.zip"), env=env, device="cpu")
    before = model.num_timesteps
    model.learn(total_timesteps=64, reset_num_timesteps=False)
    assert model.num_timesteps > before


@pytest.mark.slow
def test_loaded_bc_network_has_the_saved_weights(trained):
    import torch

    seat = load_agent("tiny-bc", RS, root=trained)
    saved = torch.load(trained / "tiny-bc" / "model.pt", weights_only=True)
    loaded = seat.net.state_dict()
    assert saved.keys() == loaded.keys()
    assert all(torch.equal(saved[k], loaded[k]) for k in saved)


@pytest.mark.slow
@pytest.mark.parametrize("workers", [1, 2])
def test_tournament_with_an_agent_seat(trained, tmp_path, monkeypatch, workers):
    import pyarrow.parquet as pq

    from quack_rl.tournament import TournamentConfig, write_run

    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "agents").symlink_to(trained)
    config = TournamentConfig(
        bots=("agent:tiny-ppo", "bot:random"), games=4, seed=3, workers=workers, sample_size=0
    )
    run_dir, rows = write_run(config, tmp_path / "runs")
    assert len(rows) == 4 and all(r["winner"] != "?" for r in rows)
    with (run_dir / "results.csv").open() as handle:
        table = list(csv.DictReader(handle))
    assert {(r["p1"], r["p2"]) for r in table} == {("agent:tiny-ppo", "random")}
    assert table[0]["pairing"] == "agent:tiny-ppo vs random"
    bots = pq.read_table(run_dir / "seats.parquet").column("bot").to_pylist()
    assert sorted(set(bots)) == ["agent:tiny-ppo", "random"]
    recorded = json.loads((run_dir / "config.json").read_text())["agents"]
    sha = json.loads((trained / "tiny-ppo" / "agent.json").read_text())["weights_sha256"]
    assert recorded["agent:tiny-ppo"]["weights_sha256"] == sha
    assert recorded["agent:tiny-ppo"]["kind"] == "ppo"
