"""The game service on v2.2 (the default): a view in the ruby step."""

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from quack_rl.engine import DONE, Phase, Status, legal_actions  # noqa: E402
from quack_rl.web.app import RULES, create_app  # noqa: E402


def test_service_is_on_v2_2_and_reaches_a_ruby_step_view():
    assert RULES == "v2.2"
    client = TestClient(create_app())
    r = client.post("/games", json={"p1": "human", "p2": "human", "seed": 3})
    assert r.status_code == 200, r.text
    gid = r.json()["game_id"]
    session = client.app.state.games[gid]
    assert session.rs.version == "v2.2" and session.rs.ruby_step
    # put the game into the shop with both seats able to pay a ruby spend
    s = session.state
    s.phase = Phase.SHOP
    for p in s.players.values():
        p.status, p.money, p.rubies, p.flask_full = Status.STOPPED, 0, 3, False
        p.field = p.final_field = 3
    s.players["p2"].flask_full = True
    session.pending = {}
    rev = client.get(f"/games/{gid}/view", params={"seat": "p1"}).json()["game"]["revision"]
    for seat in ("p1", "p2"):
        r = client.post(
            f"/games/{gid}/actions", json={"seat": seat, "action": DONE, "revision": rev}
        )
        assert r.status_code == 200, r.text
    for seat in ("p1", "p2"):
        v = client.get(f"/games/{gid}/view", params={"seat": seat}).json()
        assert v["game"]["phase"] == "ruby"
        want = legal_actions(session.state, session.rs, seat)
        assert [a["id"] for a in v["legal"]] == want
    assert [a["id"] for a in client.get(f"/games/{gid}/view", params={"seat": "p1"}).json()["legal"]] == [
        "done", "ruby_drop", "refill_flask"
    ]
    assert [a["id"] for a in client.get(f"/games/{gid}/view", params={"seat": "p2"}).json()["legal"]] == [
        "done", "ruby_drop"
    ]
