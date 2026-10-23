"""Human CLI under ruleset v1.10: black, yellow and purple, minimum buy round, round-end text."""

import io
import re

import pytest
from rich.console import Console
from test_cli_play import text_of
from typer.testing import CliRunner

from quack_rl.cli import human
from quack_rl.cli.human import BUY_KEYS, HumanSeat, key_map
from quack_rl.cli.main import app
from quack_rl.cli.render import CHIP_STYLE, chip_text, render_board, render_step
from quack_rl.engine import (
    BUY_PREFIX,
    Phase,
    ScriptedChance,
    Status,
    legal_actions,
    new_game,
    step,
)
from quack_rl.record import read_games, verify_game
from quack_rl.rules import load_ruleset

RS = load_ruleset("v1.10")
RS19 = load_ruleset("v1.9")
runner = CliRunner()
NEW = ("black_1", "yellow_1", "yellow_2", "yellow_4", "purple_1")
LABELS = {"black_1": "K1", "yellow_1": "Y1", "yellow_2": "Y2", "yellow_4": "Y4", "purple_1": "P1"}


def seat_with(keys, label="Player 1"):
    stream = io.StringIO()
    it = iter(keys)
    seat = HumanSeat(label, Console(file=stream, width=2000), True, RS, read_key=lambda: next(it))
    return seat, stream


def shop(round_):
    s = new_game(RS)
    s.phase, s.round = Phase.SHOP, round_
    for p in s.players.values():
        p.money, p.status = 1000, Status.STOPPED
        p.field = p.final_field = 3
    return s


# --- board -------------------------------------------------------------------------------


def test_new_colours_have_distinct_labels_and_styles():
    labels = {c: chip_text(c, RS).plain for c in NEW}
    assert labels == LABELS
    old = {chip_text(c.id, RS19).plain for c in RS19.chips}
    assert not (set(labels.values()) & old)
    assert len(set(labels.values())) == 5
    colours = ["white", "orange", "blue", "green", "red", "black", "yellow", "purple"]
    styles = [CHIP_STYLE[c] for c in colours]
    assert len(set(styles)) == len(styles)


def test_board_shows_new_chips_in_pot_and_bag():
    s = new_game(RS)
    s.players["p1"].placed = list(NEW)
    s.players["p1"].bag = {c: 1 for c in NEW}
    lines = text_of(render_board(s, RS, True), 2000).splitlines()
    bag_line = next(line for line in lines if line.startswith("p1 bag:"))
    pot = "\n".join(line for line in lines if not line.startswith("p1 bag:"))
    for label in LABELS.values():
        assert label in pot
        assert f"1×{label}" in bag_line


# --- shop --------------------------------------------------------------------------------


def menu(round_):
    seat, stream = seat_with("0")
    s = shop(round_)
    seat.choose(s, "p1", legal_actions(s, RS, "p1"))
    return stream.getvalue()


@pytest.mark.parametrize(
    "round_,shown",
    [
        (1, {"black_1"}),
        (2, {"black_1", "yellow_1", "yellow_2", "yellow_4"}),
        (3, set(NEW)),
    ],
)
def test_menu_offers_new_items_from_their_minimum_round(round_, shown):
    out = menu(round_)
    for item in NEW:
        assert (f"buy {item} (" in out) == (item in shown), (item, round_)


def test_item_below_minimum_round_is_never_bought_by_a_key():
    s = shop(1)
    legal = legal_actions(s, RS, "p1")
    for key in BUY_KEYS + "dsmprt0":
        seat, _ = seat_with(key + "0")
        got = seat.choose(s, "p1", legal)
        assert got in legal and got not in (BUY_PREFIX + "yellow_1", BUY_PREFIX + "purple_1")


def test_round_3_keys_are_unique_and_fit():
    s = shop(3)
    legal = legal_actions(s, RS, "p1")
    buys = [a for a in legal if a.startswith(BUY_PREFIX)]
    assert len(buys) == len(RS.shop) == 16
    assert len(buys) <= len(BUY_KEYS)
    keys = key_map(legal)
    assert len(set(keys.values())) == len(keys) == len(legal)
    assert not set(keys) & set("dsmprt")
    assert sum(a.startswith(BUY_PREFIX) for a in keys.values()) == len(buys)


def test_key_shown_in_menu_buys_the_shown_item():
    s = shop(2)
    legal = legal_actions(s, RS, "p1")
    out = menu(2)
    key = re.search(r"\[(.)\] buy yellow_2 \(", out).group(1)
    seat, _ = seat_with(key)
    assert seat.choose(s, "p1", legal) == "buy:yellow_2"


# --- round-end text ----------------------------------------------------------------------


def resolve_text(p1_placed, p2_placed):
    s = new_game(RS)
    s.phase = Phase.RESOLVE
    for seat, fld, placed in (("p1", 3, p1_placed), ("p2", 2, p2_placed)):
        p = s.players[seat]
        p.field = p.final_field = fld
        p.placed = list(placed)
        p.status = Status.STOPPED
    r = step(s, RS, None, ScriptedChance(["money_1"]))
    return render_step(r, RS)


def test_round_end_black_text():
    # one black each: both seats get 2 halves
    text = resolve_text(["black_1"], ["black_1"])
    assert "p1: -  kind=pot_round_end component=black@1 points=0 halves=2" in text
    assert "p2: -  kind=pot_round_end component=black@1 points=0 halves=2" in text


def test_round_end_purple_text():
    text = resolve_text(["purple_1"], [])
    assert "p1: -  kind=pot_round_end component=purple@1 points=" in text
    line = next(x for x in text.splitlines() if "purple@1" in x)
    assert line.startswith("p1: ")
    assert "p2: -  kind=pot_round_end" not in text


def test_put_back_text():
    s = new_game(RS)
    s.players["p1"].bag = {"white_2": 1, "yellow_1": 1}
    s.players["p2"].bag = {"white_1": 2}
    r = step(s, RS, {"p1": "draw", "p2": "draw"}, ScriptedChance(["white_2", "white_1"]))
    r = step(r.state, RS, {"p1": "draw", "p2": "stop"}, ScriptedChance(["yellow_1"]))
    text = render_step(r, RS)
    assert "p1: draw  kind=place" in text
    assert "kind=pot_put_back chip=white_2 white_total=0" in text


# --- full game ---------------------------------------------------------------------------


def test_cli_play_v1_10_full_game_with_new_colours(tmp_path, monkeypatch):
    calls = []
    last = {}
    original = HumanSeat.choose

    def spy(self, state, seat, legal):
        last["legal"] = legal
        calls.append((state.players["p2"].hand[:], state.players["p1"].hand[:], list(legal)))
        return original(self, state, seat, legal)

    monkeypatch.setattr(HumanSeat, "choose", spy)
    wanted = ["buy:yellow_1", "buy:purple_1", "buy:black_1", "buy:yellow_2", "buy:blue_1"]
    owned: set[str] = set()
    cycle = iter("dds" * 500)

    def read():
        legal = last["legal"]
        keys = {a: k for k, a in key_map(legal).items()}
        for a in wanted:
            if a == "buy:blue_1" and len(owned) < 3:
                continue
            if a in keys:
                owned.add(a.split("_")[0])
                return keys[a]
        if "done" in legal:
            return "0"
        if "draw" in legal:
            return next(cycle)
        if any(a.startswith("play:") for a in legal):
            return "0"
        if "take_money" in legal:
            return "m"
        return keys[legal[0]]

    monkeypatch.setattr(human, "default_read_key", read)
    result = runner.invoke(
        app,
        ["play", "--rules", "v1.10", "--seed", "2", "--out", str(tmp_path), "--p2", "bot:random"]
        + [x for i in ("black_1", "yellow_1", "purple_1") for x in ("--set", f"shop.{i}.price=3")],
    )
    out = result.output
    assert result.exit_code == 0, out
    assert "Traceback" not in out and re.search(r"^winner: ", out, re.M)
    (path,) = (tmp_path / "v1.10" / "play").glob("*.jsonl")
    (game,) = read_games(path)
    assert verify_game(game) == []
    bought = {
        a.removeprefix("buy:").split("_")[0]
        for s in game.steps
        if s.actions
        for a in [s.actions["p1"]]
        if a.startswith("buy:")
    }
    assert {"black", "yellow", "purple"} <= bought
    # a bought colour shows up as its chip label on the board
    assert re.search(r"\bK1\b", out) and re.search(r"\bP1\b", out)
    assert "kind=pot_round_end" in out
    # hidden hand: every "hand:" line is the human's own hand at that moment
    expected = [
        "hand: " + " ".join(chip_text(c, RS).plain for c in mine)
        for _, mine, legal in calls
        if any(a.startswith("play:") or a.startswith("put_back") for a in legal)
    ]
    shown = [line for line in out.splitlines() if line.startswith("hand:")]
    assert shown == expected
    assert any(theirs for theirs, _, _ in calls), "the bot never held a hand: pick another seed"


def test_own_hand_is_shown_and_the_other_hand_is_not():
    s = new_game(RS)
    s.phase = Phase.BREW
    s.players["p1"].hand = ["blue_2", "black_1"]
    s.players["p2"].hand = ["yellow_2", "purple_1"]
    seat, stream = seat_with("r")
    seat.choose(s, "p1", ["play:0", "play:1", "put_back_draw", "put_back_stop"])
    out = stream.getvalue()
    assert "hand: B2 K1" in out
    assert "Y2" not in out and "P1" not in out
