import re

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from helpers import RS, brew_start  # noqa: E402
from typer.testing import CliRunner  # noqa: E402

from quack_rl.cli.main import app as cli_app  # noqa: E402
from quack_rl.engine import ScriptedChance, explosion_limit  # noqa: E402
from quack_rl.rl.encode import observe  # noqa: E402
from quack_rl.rules.cards import get_card_effect  # noqa: E402
from quack_rl.web.app import (  # noqa: E402
    DEFAULT_ORIGINS,
    LOVABLE_ORIGINS,
    create_app,
    origin_regex,
)
from quack_rl.web.view import event_text  # noqa: E402

# A seed whose round-1 card asks no choice before the brew (human vs bot:random).
HUMAN_SEED = 12
HUMAN_SEED_CARD = "card_16"


@pytest.fixture
def client():
    return TestClient(create_app())


def create(client, p1="human", p2="human", **extra) -> str:
    r = client.post("/games", json={"p1": p1, "p2": p2, **extra})
    assert r.status_code == 200, r.text
    return r.json()["game_id"]


def view(client, gid, seat="p1") -> dict:
    r = client.get(f"/games/{gid}/view", params={"seat": seat})
    assert r.status_code == 200, r.text
    return r.json()


def post(client, gid, seat, action, revision=None):
    if revision is None:
        revision = view(client, gid, seat)["game"]["revision"]
    return client.post(
        f"/games/{gid}/actions", json={"seat": seat, "action": action, "revision": revision}
    )


def session_of(client, gid):
    return client.app.state.games[gid]


def scripted(client, gid, state, chance):
    """Put a prepared state and scripted chance into the session of a two-human game."""
    session = session_of(client, gid)
    session.state = state
    session.chance = ScriptedChance(chance)
    session.pending = {}
    return session


def joint(client, gid, p1, p2):
    rev = view(client, gid)["game"]["revision"]
    assert post(client, gid, "p1", p1, rev).status_code == 200
    r = post(client, gid, "p2", p2, rev)
    assert r.status_code == 200, r.text
    return r.json()


def seat_entry(v, seat):
    return next(s for s in v["seats"] if s["id"] == seat)


# --- serve and CORS -------------------------------------------------------------------


def test_serve_help_shows_port_with_default_8000():
    out = CliRunner().invoke(cli_app, ["serve", "--help"]).output
    assert "--port" in out
    assert "8000" in out


def test_cors_allows_localhost_only(client):
    ok = client.get("/games/x/view?seat=p1", headers={"Origin": "http://localhost:8080"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:8080"
    other = client.get("/games/x/view?seat=p1", headers={"Origin": "http://example.com"})
    assert "access-control-allow-origin" not in other.headers


def preflight(client, origin, **headers):
    return client.options(
        "/games",
        headers={"Origin": origin, "Access-Control-Request-Method": "POST", **headers},
    )


@pytest.mark.parametrize(
    "origin",
    [
        "http://192.168.1.20:8080",
        "http://10.0.0.5:8080",
        "http://172.17.0.1:8080",
        "http://172.31.255.254:3000",
        "http://192.168.0.1",
        "http://localhost:8080",
        "http://127.0.0.1:5173",
    ],
)
def test_preflight_allows_local_and_private_origins(client, origin):
    r = preflight(client, origin)
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == origin


@pytest.mark.parametrize(
    "origin",
    [
        "https://example.com",
        "http://172.32.0.1:8080",
        "http://172.15.0.1:8080",
        "http://11.0.0.1:8080",
        "http://192.168.1.20.example.com:8080",
        "http://192.169.1.20:8080",
    ],
)
def test_preflight_rejects_other_origins(client, origin):
    r = preflight(client, origin)
    assert r.status_code == 400
    assert "access-control-allow-origin" not in r.headers


LOVABLE = r"https://[a-z0-9-]+\.lovable\.app"


def test_extra_origins_add_to_the_defaults():
    client = TestClient(create_app(extra_origins=[LOVABLE]))
    ok = preflight(client, "https://foo.lovable.app")
    assert ok.status_code == 200
    assert ok.headers.get("access-control-allow-origin") == "https://foo.lovable.app"
    bad = preflight(client, "https://foo.lovable.app.evil.com")
    assert bad.status_code == 400
    assert "access-control-allow-origin" not in bad.headers
    lan = preflight(client, "http://192.168.1.20:8080")
    assert lan.status_code == 200
    assert lan.headers.get("access-control-allow-origin") == "http://192.168.1.20:8080"


PREVIEW = "https://id-preview--34424226-c265-4c0c-a695-30527093b97c.lovable.app"


def test_lovable_origins_are_exact_defaults():
    assert re.escape(PREVIEW) in LOVABLE_ORIGINS
    assert LOVABLE_ORIGINS in DEFAULT_ORIGINS
    regex = origin_regex()
    for escaped in LOVABLE_ORIGINS.split("|"):
        origin = escaped.replace("\\", "")
        assert re.escape(origin) == escaped
        assert re.fullmatch(regex, origin)
    for origin in [
        "https://evil.lovable.app",
        PREVIEW + ".evil.com",
        PREVIEW.replace("https://", "http://"),
        "https://id-preview--00000000-0000-0000-0000-000000000000.lovable.app",
    ]:
        assert not re.fullmatch(regex, origin), origin


def test_preflight_allows_the_lovable_preview_by_default():
    client = TestClient(create_app())
    r = preflight(client, PREVIEW, **{"Access-Control-Request-Private-Network": "true"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == PREVIEW
    assert r.headers.get("access-control-allow-private-network") == "true"


def test_preflight_private_network_header(client):
    pna = {"Access-Control-Request-Private-Network": "true"}
    ok = preflight(client, "http://192.168.1.20:8080", **pna)
    assert ok.status_code == 200
    assert ok.headers.get("access-control-allow-private-network") == "true"
    bad = preflight(client, "https://example.com", **pna)
    assert bad.status_code == 400
    assert "access-control-allow-origin" not in bad.headers


def test_serve_passes_allow_origin_values_to_create_app(monkeypatch):
    import uvicorn

    import quack_rl.web.app as web_app

    seen = {}
    runs = []

    def fake_create_app(extra_origins=()):
        seen["extra_origins"] = list(extra_origins)
        return "app"

    monkeypatch.setattr(web_app, "create_app", fake_create_app)
    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: runs.append((a, k)))
    result = CliRunner().invoke(
        cli_app, ["serve", "--allow-origin", LOVABLE, "--allow-origin", r"https://a\.example"]
    )
    assert result.exit_code == 0, result.output
    assert seen["extra_origins"] == [LOVABLE, r"https://a\.example"]
    assert len(runs) == 1


def test_serve_rejects_an_invalid_allow_origin_regex(monkeypatch):
    import uvicorn

    runs = []
    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: runs.append((a, k)))
    result = CliRunner().invoke(cli_app, ["serve", "--allow-origin", "["])
    assert result.exit_code != 0
    assert "'['" in result.output
    assert runs == []


def test_serve_help_lists_allow_origin_and_default_host():
    out = CliRunner().invoke(cli_app, ["serve", "--help"]).output
    assert "--allow-origin" in out
    assert "127.0.0.1" in out


# --- errors ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {"p1": "nobody", "p2": "human"},
        {"p1": "human", "p2": "bot:xyz"},
        {"p1": "human", "p2": "policy:foo"},
        {"p1": "human", "p2": "human", "rounds": 0},
    ],
)
def test_bad_new_game_is_rejected(client, body):
    assert client.post("/games", json=body).status_code in (400, 422)


def test_unknown_game_gives_404(client):
    assert client.get("/games/nope/view", params={"seat": "p1"}).status_code == 404
    r = client.post("/games/nope/actions", json={"seat": "p1", "action": "draw", "revision": 1})
    assert r.status_code == 404


def test_unknown_seat_is_rejected(client):
    gid = create(client)
    assert client.get(f"/games/{gid}/view", params={"seat": "p3"}).status_code in (400, 422)
    r = client.post(f"/games/{gid}/actions", json={"seat": "p3", "action": "draw", "revision": 1})
    assert r.status_code in (400, 422)


def test_illegal_action_gives_400_with_legal_list(client):
    gid = create(client, seed=5)
    r = post(client, gid, "p1", "take_money")
    assert r.status_code == 400
    assert r.json() == {"error": "illegal_action", "legal": ["draw"]}


def test_action_after_game_over_gives_400_with_empty_legal(client):
    gid = create(client, "bot:random", "bot:random", rounds=1, seed=2)
    v = view(client, gid)
    assert v["game"]["phase"] == "game_over"
    r = post(client, gid, "p1", "draw", v["game"]["revision"])
    assert r.status_code == 400
    assert r.json() == {"error": "illegal_action", "legal": []}


def test_stale_revision_gives_409(client):
    gid = create(client, seed=5)
    rev = view(client, gid)["game"]["revision"]
    r = post(client, gid, "p1", "draw", rev - 1)
    assert r.status_code == 409
    assert r.json() == {"error": "stale_revision", "revision": rev}


def test_duplicate_draw_is_rejected_and_draws_once(client):
    gid = create(client, "human", "bot:random", seed=HUMAN_SEED)
    before = view(client, gid)
    rev = before["game"]["revision"]
    chips = len(seat_entry(before, "p1")["pot"])
    first = post(client, gid, "p1", "draw", rev)
    second = post(client, gid, "p1", "draw", rev)
    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"] == "stale_revision"
    assert second.json()["revision"] == view(client, gid)["game"]["revision"]
    assert len(seat_entry(view(client, gid), "p1")["pot"]) == chips + 1


def test_second_action_of_a_seat_for_the_same_revision_gives_409(client):
    gid = create(client, seed=5)
    rev = view(client, gid)["game"]["revision"]
    assert post(client, gid, "p1", "draw", rev).status_code == 200
    r = post(client, gid, "p1", "draw", rev)
    assert r.status_code == 409
    assert r.json() == {"error": "stale_revision", "revision": rev}


# --- advancement ----------------------------------------------------------------------


def test_two_bot_game_ends_with_a_winner(client):
    gid = create(client, "bot:random", "bot:random", seed=11)
    g = view(client, gid)["game"]
    assert g["phase"] == "game_over"
    assert g["winner"] in ("p1", "p2", "draw")
    assert g["round"] == g["rounds"] == 9


def test_heuristic_bot_seat_plays(client):
    gid = create(client, "bot:draw20-pts6-blue", "bot:random", rounds=2, seed=4)
    v = view(client, gid)
    assert v["game"]["phase"] == "game_over"
    assert seat_entry(v, "p2")["kind"] == "random"
    assert seat_entry(v, "p1")["kind"] != "human"


def test_new_human_game_waits_at_first_decision(client):
    gid = create(client, "human", "bot:random", seed=HUMAN_SEED)
    v = view(client, gid)
    assert v["game"]["card"]["id"] == HUMAN_SEED_CARD
    assert v["to_act"] == ["p1"]
    assert v["game"]["phase"] == "brew"
    assert [a["id"] for a in v["legal"]] == ["draw"]
    assert v["game"]["revision"] >= 1


def test_bot_brews_on_after_human_stops(client):
    gid = create(client, "human", "bot:random", seed=HUMAN_SEED)
    v = post(client, gid, "p1", "draw").json()
    while "stop" not in [a["id"] for a in v["legal"]]:
        assert v["hand"], "only an open hand keeps p1 from stopping"
        v = post(client, gid, "p1", "play:0").json()
    v = post(client, gid, "p1", "stop").json()
    assert v["you"] == "p1"
    # The bot brewed on to the end of its brew: p2 is not brewing, or the game is past the
    # round-1 brew (an idle shop closes by itself, so the next round may have started).
    past_brew = v["game"]["phase"] != "brew" or v["game"]["round"] > 1
    assert seat_entry(v, "p2")["status"] != "brewing" or past_brew
    p2_end = [e["kind"] for e in v["log"]["events"] if e.get("seat") == "p2"]
    assert {"stop", "explode", "bag_empty"} & set(p2_end)


def test_revision_increases_with_each_step(client):
    gid = create(client, seed=5)
    rev = view(client, gid)["game"]["revision"]
    v = joint(client, gid, "draw", "draw")
    assert v["game"]["revision"] == rev + 1


def test_accepted_seat_is_not_in_to_act(client):
    gid = create(client, seed=5)
    v = post(client, gid, "p1", "draw").json()
    assert v["to_act"] == ["p2"]
    assert v["legal"] == []


# --- view contract ---------------------------------------------------------------------


# --- ingredients (shop catalogue) -------------------------------------------------------


def chip_entry(v, chip_id):
    for entry in v["ingredients"]:
        for c in entry["chips"]:
            if c["chip"] == chip_id:
                return c
    raise AssertionError(f"chip {chip_id} not in ingredients")


def colour_chips(v, colour):
    return next(e["chips"] for e in v["ingredients"] if e["colour"] == colour)


def test_view_ingredients_round_1(client):
    gid = create(client, "human", "human", seed=HUMAN_SEED)
    v = view(client, gid)
    assert session_of(client, gid).rs.version == "v2.2"
    assert v["game"]["round"] == 1
    for colour in ("yellow", "purple"):
        chips = colour_chips(v, colour)
        assert chips and all(c["available"] is False for c in chips)
    assert chip_entry(v, "orange_6") == {
        "chip": "orange_6", "value": 6, "price": 22, "min_round": 1, "available": True,
    }
    white = colour_chips(v, "white")
    assert white
    for c in white:
        assert c["price"] is None and c["min_round"] is None and c["available"] is False


def test_view_ingredients_round_3(client):
    gid = create(client, "human", "human", seed=HUMAN_SEED)
    session_of(client, gid).state.round = 3
    v = view(client, gid)
    assert v["game"]["round"] == 3
    for colour in ("yellow", "purple"):
        chips = colour_chips(v, colour)
        assert chips and all(c["available"] is True for c in chips)


def test_view_ingredients_same_for_both_seats(client):
    gid = create(client, "human", "human", seed=HUMAN_SEED)
    assert view(client, gid, "p1")["ingredients"] == view(client, gid, "p2")["ingredients"]


def test_view_ingredients_cover_each_colour_once_with_a_short_effect(client):
    gid = create(client, "human", "human", seed=HUMAN_SEED)
    rs = session_of(client, gid).rs
    v = view(client, gid)
    colours = list(dict.fromkeys(c.colour for c in rs.chips))
    assert [e["colour"] for e in v["ingredients"]] == colours
    for entry in v["ingredients"]:
        assert set(entry) == {"colour", "effect", "chips"}
        assert entry["effect"] and "\n" not in entry["effect"] and len(entry["effect"]) <= 60
        assert [c["chip"] for c in entry["chips"]] == [
            c.id for c in rs.chips if c.colour == entry["colour"]
        ]
        for c in entry["chips"]:
            assert set(c) == {"chip", "value", "price", "min_round", "available"}
            assert c["value"] == rs.chip(c["chip"]).value


def test_view_has_the_fixed_fields(client):
    gid = create(client, "human", "bot:random", seed=HUMAN_SEED)
    v = view(client, gid)
    assert set(v) == {
        "game", "you", "to_act", "seats", "window", "chips", "legal", "hand", "card_draw", "log",
        "ingredients",
    }
    g = v["game"]
    session = session_of(client, gid)
    assert g["rounds"] == 9 and g["round"] == 1
    assert g["explosion_limit"] == explosion_limit(session.state, RS)
    card = RS.card(HUMAN_SEED_CARD)
    assert g["card"] == {
        "id": card.id, "effect": card.effect, "text": get_card_effect(card.effect).description,
    }
    assert g["winner"] is None
    assert v["you"] == "p1"
    assert [s["id"] for s in v["seats"]] == ["p1", "p2"]
    p1 = seat_entry(v, "p1")
    assert set(p1) == {
        "id", "kind", "status", "points", "money", "rubies", "flask_full", "white_total",
        "droplet", "start_field", "rat_tail", "bag", "pot",
    }
    assert p1["kind"] == "human" and seat_entry(v, "p2")["kind"] == "random"
    assert p1["bag"] == dict(RS.start_bag)
    assert v["chips"] == [{"id": c.id, "colour": c.colour, "value": c.value} for c in RS.chips]
    assert v["legal"] == [{"id": "draw", "label": "draw"}]
    assert v["hand"] == [] and v["card_draw"] == []
    assert set(v["log"]) == {"lines", "events"}
    assert any(e["kind"] == "card_draw" for e in v["log"]["events"])


def test_window_matches_ahead_near_the_track_end(client):
    gid = create(client)
    state = brew_start()
    state.players["p1"].field = 50
    session = scripted(client, gid, state, [])
    v = view(client, gid)
    assert [w["field"] for w in v["window"]] == [51, 52] + [53] * 9
    ahead = observe(session.state, RS, "p1")["ahead"]
    assert [{k: w[k] for k in ("money", "points", "ruby")} for w in v["window"]] == ahead


def test_pot_entries_from_and_landing(client):
    gid = create(client)
    state = brew_start()
    start = state.players["p1"].field
    state.players["p1"].bag = {"white_1": 4, "green_1": 1, "yellow_1": 1}
    state.players["p2"].bag = {"white_1": 6}
    scripted(client, gid, state, ["white_1", "white_1"] * 2 + ["green_1", "white_1"])
    joint(client, gid, "draw", "draw")  # p1 white_1
    v = joint(client, gid, "draw", "draw")  # p1 white_1
    pot = seat_entry(v, "p1")["pot"]
    assert [e["order"] for e in pot] == [1, 2]
    assert pot[0]["from"] == start + 1
    assert pot[1]["from"] == pot[0]["landing"] + 1
    assert [e["landing"] for e in pot] == session_of(client, gid).state.players["p1"].placed_fields
    assert pot[0] == {
        "order": 1, "chip": "white_1", "colour": "white", "value": 1,
        "from": start + 1, "landing": start + 1,
    }
    session = session_of(client, gid)
    session.chance = ScriptedChance(["yellow_1", "white_1"])
    removed_landing = pot[1]["landing"]
    v = joint(client, gid, "draw", "draw")  # p1 yellow_1: the white chip before it goes back
    pot = seat_entry(v, "p1")["pot"]
    assert [e["chip"] for e in pot] == ["white_1", "yellow_1"]
    assert [e["order"] for e in pot] == [1, 2]
    assert pot[1]["from"] == removed_landing + 1
    assert pot[1]["landing"] == session.state.players["p1"].placed_fields[-1]


def test_pot_entry_at_the_track_end(client):
    gid = create(client)
    state = brew_start()
    p1 = state.players["p1"]
    p1.bag = {"white_1": 1, "green_1": 2}
    p1.placed, p1.placed_fields, p1.field = ["green_1"], [53], 53
    state.players["p2"].bag = {"white_1": 6}
    scripted(client, gid, state, ["green_1", "white_1"])
    v = joint(client, gid, "draw", "draw")
    entry = seat_entry(v, "p1")["pot"][-1]
    assert entry["from"] == entry["landing"] == 53


# --- hidden information -----------------------------------------------------------------


def test_hand_and_card_draw_are_hidden_from_the_other_seat(client):
    gid = create(client)
    state = brew_start()
    state.players["p1"].bag = {"blue_2": 1, "white_1": 4}
    state.players["p2"].bag = {"white_1": 6}
    session = scripted(client, gid, state, ["blue_2", "white_1", "white_1", "white_1"])
    joint(client, gid, "draw", "draw")
    session.state.players["p1"].card_draw = ["white_1", "white_1"]
    own, other = view(client, gid, "p1"), view(client, gid, "p2")
    assert own["hand"] == ["white_1", "white_1"]
    assert own["card_draw"] == ["white_1", "white_1"]
    assert other["hand"] == [] and other["card_draw"] == []
    assert seat_entry(own, "p1")["bag"] == {"white_1": 2}
    assert seat_entry(other, "p1")["bag"] == {"white_1": 4}
    session.chance = ScriptedChance(["white_1"])
    joint(client, gid, "play:0", "draw")  # the rest of the hand goes back
    own, other = view(client, gid, "p1"), view(client, gid, "p2")
    own_kinds = [(e.get("seat"), e["kind"]) for e in own["log"]["events"]]
    assert ("p1", "hand") in own_kinds and ("p1", "put_back") in own_kinds
    for e in other["log"]["events"]:
        assert not (e.get("seat") == "p1" and e["kind"] in ("hand", "put_back"))
        assert "value" not in e  # no chance outcome
    for v in (own, other):
        assert v["log"]["lines"] == [event_text(e) for e in v["log"]["events"]]


def test_pending_action_is_not_in_the_other_view(client):
    views = []
    for action in ("draw", "stop"):
        gid = create(client, seed=5)
        joint(client, gid, "draw", "draw")
        assert post(client, gid, "p1", action).status_code == 200
        views.append(view(client, gid, "p2"))
    assert views[0] == views[1]
    assert views[0]["to_act"] == ["p2"]


def test_explosion_limit_includes_card_4(client):
    gid = create(client, "human", "bot:random", seed=14)  # round-1 card: card_4
    g = view(client, gid)["game"]
    assert g["card"]["id"] == "card_4"
    assert g["explosion_limit"] == RS.explosion_limit + 2
