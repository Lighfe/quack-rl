"""Every web game is saved as a game record, step by step (spec 2026-10-27, section 2)."""

import json

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from typer.testing import CliRunner  # noqa: E402

from quack_rl.cli.main import app as cli_app  # noqa: E402
from quack_rl.engine import Phase  # noqa: E402
from quack_rl.record import (  # noqa: E402
    RECORD_SCHEMA_VERSION,
    LocalRecordStore,
    read_games,
    verify_game,
    verify_seed,
)
from quack_rl.web.app import create_app  # noqa: E402


def web_files(root):
    return sorted((root / "v2.3" / "web").glob("*.jsonl"))


def only_game(root):
    files = web_files(root)
    assert len(files) == 1, files
    games = list(read_games(files[0]))
    assert len(games) == 1
    return files[0], games[0]


def test_post_games_writes_a_web_record_with_the_header(tmp_path):
    client = TestClient(create_app(tmp_path))
    r = client.post("/games", json={"p1": "human", "p2": "bot:random", "rounds": 2, "seed": None})
    assert r.status_code == 200, r.text
    gid = r.json()["game_id"]
    _, game = only_game(tmp_path)
    h = game.header
    session = client.app.state.games[gid]
    assert h.game_id == gid
    assert h.mode == "web"
    assert h.schema_version == RECORD_SCHEMA_VERSION == 3
    assert isinstance(h.seed, int)
    assert h.seed == session.seed
    assert h.rounds == 2
    assert h.rules_version == "v2.3"
    assert h.seats["p1"].kind == "human"
    assert h.seats["p2"].kind == "bot"
    assert h.seats["p2"].name == "random"
    assert h.ui == {}
    assert h.overrides == {}
    assert h.started_at


def test_header_seed_is_the_request_seed(tmp_path):
    client = TestClient(create_app(tmp_path))
    r = client.post("/games", json={"p1": "bot:random", "p2": "human", "seed": 41})
    assert r.status_code == 200, r.text
    _, game = only_game(tmp_path)
    assert game.header.seed == 41
    assert game.header.rounds == 9
    assert game.header.seats["p1"].kind == "bot"
    assert game.header.seats["p2"].kind == "human"


def test_failed_post_games_writes_no_record(tmp_path):
    client = TestClient(create_app(tmp_path))
    r = client.post("/games", json={"p1": "human", "p2": "bot:nope"})
    assert r.status_code == 400
    assert not (tmp_path / "v2.3").exists()
    assert list(tmp_path.rglob("*.jsonl")) == []


def test_open_game_has_one_flushed_step_line_per_revision_and_no_footer(tmp_path):
    client = TestClient(create_app(tmp_path))
    r = client.post("/games", json={"p1": "human", "p2": "bot:random", "seed": 12})
    gid = r.json()["game_id"]
    session = client.app.state.games[gid]
    # p1 acts a few times, then stops acting mid-round
    for _ in range(3):
        if session.state.phase is Phase.GAME_OVER or "p1" not in session.to_act():
            break
        rev = session.revision
        action = session.legal("p1")[0]
        resp = client.post(
            f"/games/{gid}/actions", json={"seat": "p1", "action": action, "revision": rev}
        )
        assert resp.status_code == 200, resp.text
    assert session.state.phase is not Phase.GAME_OVER
    assert session.revision > 0
    path, _ = only_game(tmp_path)
    lines = [json.loads(t) for t in path.read_text(encoding="utf-8").splitlines() if t.strip()]
    assert lines[0]["type"] == "header"
    steps = [ln for ln in lines if ln["type"] == "step"]
    assert len(lines) == 1 + len(steps)
    assert [ln["n"] for ln in steps] == list(range(1, session.revision + 1))
    assert not any(ln["type"] == "footer" for ln in lines)


@pytest.mark.parametrize("rounds", [1, 3])
def test_finished_bot_game_has_a_footer_and_verifies(tmp_path, rounds):
    client = TestClient(create_app(tmp_path))
    r = client.post(
        "/games",
        json={"p1": "bot:random", "p2": "bot:draw30-pts3-blue", "rounds": rounds, "seed": 5},
    )
    assert r.status_code == 200, r.text
    session = client.app.state.games[r.json()["game_id"]]
    assert session.state.phase is Phase.GAME_OVER
    path, game = only_game(tmp_path)
    assert game.footer is not None
    assert game.footer.winner == (session.state.winner or "")
    assert len(game.steps) == session.revision
    assert verify_game(game) == []
    assert verify_seed(game) == []
    assert session.record_file is None or session.record_file.closed


def test_new_web_path_is_under_the_web_folder(tmp_path):
    path = LocalRecordStore(tmp_path).new_web_path("v2.3")
    assert path.parent == tmp_path / "v2.3" / "web"
    assert path.suffix == ".jsonl"


def test_a_game_whose_record_cannot_be_created_is_not_started(tmp_path):
    # a file where the rules version folder must go: the web folder cannot be made
    (tmp_path / "v2.3").write_text("a file, not a folder", encoding="utf-8")
    client = TestClient(create_app(tmp_path), raise_server_exceptions=False)
    r = client.post("/games", json={"p1": "human", "p2": "bot:random"})
    assert r.status_code == 500
    assert client.app.state.games == {}


def test_serve_passes_out_to_create_app(monkeypatch, tmp_path):
    import uvicorn

    import quack_rl.web.app as web_app

    seen = {}
    monkeypatch.setattr(
        web_app,
        "create_app",
        lambda record_root, extra_origins=(): seen.update(root=record_root) or "app",
    )
    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: None)
    result = CliRunner().invoke(cli_app, ["serve", "--out", str(tmp_path / "recs")])
    assert result.exit_code == 0, result.output
    assert seen["root"] == tmp_path / "recs"


def test_serve_help_names_out_and_its_default():
    out = CliRunner().invoke(cli_app, ["serve", "--help"], terminal_width=200).output
    assert "--out" in out
    assert "data/records" in out
