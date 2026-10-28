"""The log lines of the service view: one plain sentence per engine event (issue #246)."""

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from helpers import RS  # noqa: E402

from quack_rl.web.app import create_app  # noqa: E402
from quack_rl.web.view import event_text  # noqa: E402

KINDS = (
    "bag_empty buy card_chip card_choice card_draw card_drop card_place card_points "
    "card_refill_flasks card_remove_chip card_swap die done explode game_end hand money place "
    "pot_put_back pot_round_end put_back rat_tail refill_flask restart restart_continue "
    "round_chip round_end round_end_bonus ruby ruby_drop ruby_points stop take_money take_points "
    "use_card_17 use_flask"
).split()

# One synthetic event per kind, with the fields the engine gives it.
SAMPLES = [
    {"seat": "p1", "kind": "bag_empty"},
    {"seat": "p1", "kind": "buy", "item": "orange_1", "price": 3},
    {"seat": "p1", "kind": "card_chip", "chip": "green_1"},
    {"seat": "p1", "kind": "card_choice", "action": "card_drop_2"},
    {"seat": None, "kind": "card_draw", "card": "card_17", "effect": "first_white_back"},
    {"seat": "p2", "kind": "card_drop", "drop": 1},
    {"seat": "p1", "kind": "card_place", "chip": "red_2"},
    {"seat": "p1", "kind": "card_points", "points": 4},
    {"seat": None, "kind": "card_refill_flasks"},
    {"seat": "p1", "kind": "card_remove_chip", "chip": "white_1"},
    {"seat": "p1", "kind": "card_swap", "chip": "blue_1", "total": 2},
    {"seat": "p1", "kind": "die", "face": "droplet_1"},
    {"seat": "p1", "kind": "done", "auto": True},
    {"seat": "p1", "kind": "explode", "white_total": 8},
    {
        "seat": None,
        "kind": "game_end",
        "winner": "p1",
        "points": {"p1": 50, "p2": 0},
        "final_fields": {"p1": 20, "p2": None},
    },
    {"seat": "p1", "kind": "hand", "chips": ["blue_1", "red_2"]},
    {"seat": "p1", "kind": "money", "amount": 12},
    {"seat": "p1", "kind": "place", "chip": "orange_1", "from": 3, "to": 5, "bonus": 1},
    {"seat": "p1", "kind": "pot_put_back", "chip": "red_1", "white_total": 4},
    {
        "seat": "p1",
        "kind": "pot_round_end",
        "component": "black@1",
        "points": 0,
        "drop": 1,
        "rubies": 1,
        "total": 3,
    },
    {"seat": "p1", "kind": "put_back", "chips": ["green_2"]},
    {"seat": "p1", "kind": "rat_tail", "bonus": 3},
    {"seat": "p1", "kind": "refill_flask", "rubies": 2, "total": 1},
    {"seat": "p1", "kind": "restart", "chips": ["white_1", "orange_1"]},
    {"seat": "p1", "kind": "restart_continue"},
    {"seat": "p1", "kind": "round_chip", "chip": "yellow_1"},
    {"seat": None, "kind": "round_end", "next_round": 3},
    {"seat": "p1", "kind": "round_end_bonus", "chip": "green_1", "rubies": 1, "total": 2},
    {"seat": "p1", "kind": "ruby", "rubies": 1, "total": 2},
    {"seat": "p1", "kind": "ruby_drop", "rubies": 2, "drop": 1, "total": 0},
    {"seat": "p1", "kind": "ruby_points", "rubies": 3, "points": 1, "total": 0},
    {"seat": "p1", "kind": "stop", "field": 14},
    {"seat": "p1", "kind": "take_money", "amount": 9},
    {"seat": "p1", "kind": "take_points", "amount": 2},
    {"seat": "p1", "kind": "use_card_17", "chip": "white_1", "field": 6, "white_total": 2},
    {"seat": "p1", "kind": "use_flask", "chip": "white_3", "field": 8, "white_total": 3},
]


def clean(line: str) -> bool:
    return bool(line) and not any(ch in line for ch in "=_@")


def test_samples_cover_every_kind():
    assert sorted(e["kind"] for e in SAMPLES) == sorted(KINDS)
    assert len(KINDS) == 36


@pytest.mark.parametrize("event", SAMPLES, ids=[e["kind"] for e in SAMPLES])
def test_each_kind_gives_a_plain_line(event):
    line = event_text(event, RS)
    assert clean(line), line


def test_chip_names_come_from_the_ruleset():
    assert event_text({"seat": "p2", "kind": "hand", "chips": ["orange_1"]}, RS) == (
        "p2 drew Orange 1."
    )
    line = event_text({"seat": "p1", "kind": "buy", "item": "green_4", "price": 6}, RS)
    assert "Green 4" in line and "6" in line


@pytest.mark.parametrize(
    "event",
    [
        {
            "seat": "p1",
            "kind": "pot_round_end",
            "component": "black",
            "points": 0,
            "drop": 1,
            "rubies": 0,
            "total": 0,
        },
        {"seat": "p1", "kind": "ruby_points", "rubies": 3, "points": 1, "total": 0},
        {"seat": "p1", "kind": "ruby_points", "rubies": 1, "points": 0, "total": 0},
        {"seat": "p1", "kind": "card_points", "points": 0},
        {"seat": "p1", "kind": "take_money", "amount": 0},
        {"seat": "p1", "kind": "take_points", "amount": 0},
        {"seat": "p1", "kind": "money", "amount": 0},
        {"seat": "p1", "kind": "place", "chip": "white_1", "from": 3, "to": 4, "bonus": 0},
        {"seat": "p1", "kind": "buy", "item": "orange_1", "price": 0},
        {"seat": "p1", "kind": "restart", "chips": []},
    ],
)
def test_zero_counts_and_empty_lists_do_not_show(event):
    line = event_text(event, RS)
    assert clean(line), line
    assert "0" not in line, line


def test_zero_count_example_lines():
    pot = {
        "seat": "p1",
        "kind": "pot_round_end",
        "component": "black",
        "points": 0,
        "drop": 1,
        "rubies": 0,
        "total": 0,
    }
    assert event_text(pot, RS) == "p1: black chips, droplet +1."
    rp = {"seat": "p1", "kind": "ruby_points", "rubies": 3, "points": 1, "total": 0}
    assert event_text(rp, RS) == "p1 traded 3 rubies for 1 point."


def test_game_end_shows_scores_also_when_zero():
    line = event_text(
        {
            "seat": None,
            "kind": "game_end",
            "winner": "p2",
            "points": {"p1": 0, "p2": 7},
            "final_fields": {"p1": None, "p2": None},
        },
        RS,
    )
    assert line == "Game over: p2 wins. Points: p1 0, p2 7."
    draw = event_text(
        {"seat": None, "kind": "game_end", "winner": "draw", "points": {"p1": 5, "p2": 5}}, RS
    )
    assert draw == "Game over: a draw. Points: p1 5, p2 5."


def test_done_names_auto():
    assert event_text({"seat": "p1", "kind": "done"}, RS) == "p1 is done."
    assert event_text({"seat": "p1", "kind": "done", "auto": True}, RS) == (
        "p1 had nothing to choose."
    )


def test_card_draw_names_the_card_and_its_effect():
    line = event_text(
        {"seat": None, "kind": "card_draw", "card": "card_17", "effect": "first_white_back"}, RS
    )
    assert line.startswith("Card 17 drawn: the first white chip")


@pytest.mark.parametrize(
    "action",
    [
        "card_drop_2",
        "card_purple",
        "card_black",
        "card_chip:green_2",
        "card_rubies",
        "card_tails:0",
        "card_tails:2",
        "card_swap:blue_1",
        "card_swap_no",
        "card_points",
        "card_remove_white",
        "card_chip4:red_4",
        "card_tail_points",
        "card_upgrade:yellow_2",
        "wait",
        "some_new_choice",
    ],
)
def test_card_choice_actions_are_words(action):
    line = event_text({"seat": "p1", "kind": "card_choice", "action": action}, RS)
    assert clean(line), line
    assert line.startswith("p1 ")


def test_card_choice_names_the_chip():
    line = event_text({"seat": "p1", "kind": "card_choice", "action": "card_chip:green_2"}, RS)
    assert line == "p1 chose a Green 2 chip."


def test_unknown_kind_is_readable():
    line = event_text({"seat": "p1", "kind": "foo_bar", "x": 3}, RS)
    assert line == "p1: foo bar, x 3."
    assert clean(line)
    assert clean(event_text({"kind": "new_thing", "some_field": "a_b", "n": 0}, RS))


SEEDS = range(1, 11)


def test_bot_games_give_plain_lines_and_only_known_kinds(tmp_path):
    client = TestClient(create_app(tmp_path))
    found: set[str] = set()
    for seed in SEEDS:
        r = client.post(
            "/games", json={"p1": "bot:random", "p2": "bot:draw30-pts3-blue", "seed": seed}
        )
        assert r.status_code == 200, r.text
        gid = r.json()["game_id"]
        for seat in ("p1", "p2"):
            v = client.get(f"/games/{gid}/view", params={"seat": seat}).json()
            assert v["game"]["phase"] == "game_over"
            assert len(v["log"]["lines"]) == len(v["log"]["events"])
            for line in v["log"]["lines"]:
                assert clean(line), line
            found |= {e["kind"] for e in v["log"]["events"]}
    assert found <= set(KINDS), found - set(KINDS)
    assert {"explode", "ruby_drop", "ruby_points", "pot_round_end"} <= found
