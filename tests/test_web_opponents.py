"""The seat `agent:<name>` in the game service and the opponent list at `GET /opponents`.

Every agent is written under `tmp_path`, passed to `create_app` as the agents root; the tests
never change the working folder. The `bc` weights test needs the `rl` group and skips without it.
"""

import logging
import sys
from pathlib import Path

import pytest

import quack_rl.rl.planner  # noqa: F401  # sets PLANNER_FACTORY before any monkeypatch

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from quack_rl.bots import RandomBot  # noqa: E402
from quack_rl.bots.presets import PRESET_BOTS, PRESET_LABELS  # noqa: E402
from quack_rl.rl import agents  # noqa: E402
from quack_rl.rl.agents import AgentManifest, save_agent  # noqa: E402
from quack_rl.rl.encode import BOARD_LAYOUT  # noqa: E402
from quack_rl.web.app import create_app  # noqa: E402

RULES = "v2.3"
PRESETS = [{"spec": s, "label": PRESET_LABELS[s], "kind": "bot"} for s in PRESET_BOTS]
TINY = {"spec": "agent:tiny", "label": "tiny (planner)", "kind": "planner"}


def fake_agent(root: Path, name: str, kind: str = "planner", **changes) -> Path:
    """An agent folder; for `ppo`, `bc` and `cql` the weights file is a few bytes."""
    folder = root / name
    folder.mkdir(parents=True)
    data = {
        "name": name,
        "kind": kind,
        "rules": RULES,
        "layout": BOARD_LAYOUT,
        "weights": None if kind == "planner" else agents.WEIGHTS_FILES[kind],
        "settings": {"obs_dim": 4, "n_actions": 2},
        "created_at": "2026-11-05T00:00:00+00:00",
    }
    data.update(changes)
    m = AgentManifest(**data)
    if m.weights is not None:
        (folder / m.weights).write_bytes(b"not a real model")
    save_agent(folder, m)  # the hash in agent.json matches the weights file
    return folder


@pytest.fixture
def root(tmp_path) -> Path:
    return tmp_path / "agents"


@pytest.fixture
def client(tmp_path, root):
    return TestClient(create_app(tmp_path / "records", agents_root=root))


@pytest.fixture
def planner_bot(monkeypatch):
    monkeypatch.setattr(agents, "PLANNER_FACTORY", lambda rs, m, seed: RandomBot(seed))


def opponents(client) -> list[dict]:
    r = client.get("/opponents")
    assert r.status_code == 200, r.text
    return r.json()


def new_game(client, p1: str, p2: str):
    return client.post("/games", json={"p1": p1, "p2": p2, "seed": 3})


def test_create_app_defaults_to_the_agents_root():
    import inspect

    default = inspect.signature(create_app).parameters["agents_root"].default
    assert default == agents.AGENTS_ROOT


# --- GET /opponents ---------------------------------------------------------------------------


def test_without_an_agents_root_only_the_presets_are_listed(client, root):
    assert not root.exists()
    assert opponents(client) == PRESETS


def test_bot_random_is_not_listed(client):
    assert "bot:random" not in [o["spec"] for o in opponents(client)]


def test_a_planner_agent_is_listed_after_the_presets(client, root):
    fake_agent(root, "tiny")
    found = opponents(client)
    assert len(found) == 4
    assert found[:3] == PRESETS
    assert found[-1] == TINY


def test_agents_are_sorted_by_name_with_their_kind(client, root):
    fake_agent(root, "zeta")
    fake_agent(root, "alpha", kind="ppo")
    fake_agent(root, "mid", kind="bc")
    found = opponents(client)[3:]
    assert found == [
        {"spec": "agent:alpha", "label": "alpha (ppo)", "kind": "ppo"},
        {"spec": "agent:mid", "label": "mid (bc)", "kind": "bc"},
        {"spec": "agent:zeta", "label": "zeta (planner)", "kind": "planner"},
    ]


def _no_manifest(root: Path) -> Path:
    folder = root / "empty"
    folder.mkdir(parents=True)
    return folder


def _invalid_manifest(root: Path) -> Path:
    folder = root / "broken"
    folder.mkdir(parents=True)
    (folder / "agent.json").write_text("{not json")
    return folder


def _other_rules(root: Path) -> Path:
    return fake_agent(root, "old", rules="v9.9")


@pytest.mark.parametrize("make_bad", [_no_manifest, _invalid_manifest, _other_rules])
def test_a_bad_agent_folder_is_left_out_with_one_warning(client, root, caplog, make_bad):
    fake_agent(root, "tiny")
    bad = make_bad(root)
    with caplog.at_level(logging.WARNING):
        r = client.get("/opponents")
    assert r.status_code == 200, r.text
    assert r.json() == [*PRESETS, TINY]
    warnings = [rec for rec in caplog.records if rec.levelno == logging.WARNING]
    assert len(warnings) == 1, [rec.getMessage() for rec in warnings]
    assert str(bad) in warnings[0].getMessage()


# --- POST /games with agent:<name> -----------------------------------------------------------


def test_a_planner_agent_plays_a_bot_game_to_the_end(client, root, planner_bot):
    fake_agent(root, "tiny")
    r = new_game(client, "bot:random", "agent:tiny")
    assert r.status_code == 200, r.text
    gid = r.json()["game_id"]
    v = client.get(f"/games/{gid}/view", params={"seat": "p1"})
    assert v.status_code == 200, v.text
    assert v.json()["game"]["winner"] is not None


def test_bot_random_is_still_accepted(client):
    r = new_game(client, "bot:random", "bot:random")
    assert r.status_code == 200, r.text


def test_a_missing_agent_gives_400_naming_it(client, root):
    root.mkdir(parents=True)
    r = new_game(client, "human", "agent:missing")
    assert r.status_code == 400, r.text
    assert "missing" in r.json()["detail"]


def test_a_bad_agent_name_gives_400(client):
    r = new_game(client, "human", "agent:Bad!")
    assert r.status_code == 400, r.text


def test_a_ppo_agent_without_torch_gives_400_naming_the_rl_group(client, root, monkeypatch):
    fake_agent(root, "net", kind="ppo")
    monkeypatch.setitem(sys.modules, "torch", None)  # `import torch` raises ImportError
    r = new_game(client, "human", "agent:net")
    assert r.status_code == 400, r.text
    assert "`rl`" in r.json()["detail"]


def test_a_bc_agent_with_a_non_torch_weights_file_gives_400(client, root):
    pytest.importorskip("torch")
    fake_agent(root, "net", kind="bc")
    r = new_game(client, "human", "agent:net")
    assert r.status_code == 400, r.text
