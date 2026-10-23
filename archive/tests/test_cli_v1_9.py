"""Human CLI under ruleset v1.9: new colours, 14 shop items, hand and pick step."""

import io

import pytest
from rich.console import Console
from test_cli_play import text_of
from typer.testing import CliRunner

from quack_rl.cli import human
from quack_rl.cli.human import HumanSeat, key_map
from quack_rl.cli.main import app
from quack_rl.cli.render import CHIP_STYLE, chip_text, render_board
from quack_rl.engine import (
    BUY_PREFIX,
    PUT_BACK_DRAW,
    PUT_BACK_STOP,
    WAIT,
    Phase,
    Status,
    legal_actions,
    new_game,
    play,
)
from quack_rl.record import read_games, verify_game
from quack_rl.rules import load_ruleset

RS = load_ruleset("v1.9")
runner = CliRunner()
UNKNOWN = "unknown key, try again (hidden)"


def seat_with(keys, label="Player 1", bag_assist=True):
    stream = io.StringIO()
    it = iter(keys)
    seat = HumanSeat(
        label, Console(file=stream, width=200), bag_assist, RS, read_key=lambda: next(it)
    )
    return seat, stream


def pick_state(h1, h2=()):
    s = new_game(RS)
    s.phase = Phase.BREW
    s.players["p1"].hand = list(h1)
    s.players["p2"].hand = list(h2)
    return s


def pick_legal(n):
    return [*(play(i) for i in range(n)), PUT_BACK_DRAW, PUT_BACK_STOP]


def test_board_shows_red_and_orange_6_in_pot_and_bag():
    s = new_game(RS)
    s.players["p1"].placed = ["red_1", "red_2", "orange_6"]
    s.players["p1"].bag = {"red_4": 1, "orange_6": 2}
    text = text_of(render_board(s, RS, True), 200)
    for chip in ("R1", "R2", "R4", "O6"):
        assert chip in text
    assert CHIP_STYLE["red"]
    assert chip_text("red_1", RS).style == CHIP_STYLE["red"]


def rich_shop():
    s = new_game(RS)
    s.phase = Phase.SHOP
    for p in s.players.values():
        p.money = 1000
    return s


def test_buy_prompt_lists_new_items_with_prices():
    s = rich_shop()
    seat, stream = seat_with("0")
    seat.choose(s, "p1", legal_actions(s, RS, "p1"))
    out = stream.getvalue()
    for text in ("orange_6 (22)", "red_1 (6)", "red_2 (10)", "red_4 (16)", "blue_4 (19)"):
        assert f"buy {text}" in out


def test_every_legal_buy_has_its_own_key():
    s = rich_shop()
    legal = legal_actions(s, RS, "p1")
    buys = [a for a in legal if a.startswith(BUY_PREFIX)]
    assert len(buys) == len(RS.shop) == 11
    keys = key_map(legal)
    assert len([a for a in keys.values() if a.startswith(BUY_PREFIX)]) == len(buys)
    assert len(set(keys.values())) == len(keys) == len(legal)
    (last_key,) = [k for k, a in keys.items() if a == buys[-1]]
    seat, _ = seat_with(last_key)
    assert seat.choose(s, "p1", legal) == buys[-1]


def test_more_than_12_buy_actions_all_get_a_key():
    legal = ["done", *(f"buy:item{i}" for i in range(20))]
    keys = key_map(legal)
    assert len([a for a in keys.values() if a.startswith(BUY_PREFIX)]) == 20
    assert len(set(keys.values())) == len(keys) == len(legal)


@pytest.mark.parametrize(
    "hand",
    [["blue_1"], ["blue_2", "white_1"], ["blue_2", "white_1", "red_4", "green_1"]],
)
def test_pick_prompt_shows_hand_and_entries(hand):
    s = pick_state(hand)
    seat, stream = seat_with("r")
    seat.choose(s, "p1", pick_legal(len(hand)))
    out = stream.getvalue()
    chips = [f"{RS.chip(c).colour[0].upper()}{RS.chip(c).value}" for c in hand]
    assert "hand: " + " ".join(chips) in out
    for i, chip in enumerate(chips):
        assert f"play {i}: {chip}" in out
    assert "put all back and Draw" in out and "put all back and Stop" in out
    assert f"play {len(hand)}" not in out


def test_pick_prompt_never_shows_other_hand():
    s = pick_state(["blue_2", "white_1"], ["red_4", "green_1", "orange_6"])
    for name, other in (("p1", ("R4", "G1", "O6")), ("p2", ("B2", "W1"))):
        seat, stream = seat_with("r", bag_assist=False)
        seat.choose(s, name, pick_legal(len(s.players[name].hand)))
        out = stream.getvalue()
        assert out.count("hand:") == 1
        for chip in other:
            assert chip not in out
    assert "hand" not in text_of(render_board(s, RS, False), 200)


def test_pick_keys_return_actions():
    s = pick_state(["blue_2", "white_1", "red_4"])
    cases = (
        ("0", "play:0"),
        ("1", "play:1"),
        ("2", "play:2"),
        ("r", PUT_BACK_DRAW),
        ("t", PUT_BACK_STOP),
    )
    for key, action in cases:
        seat, _ = seat_with(key)
        assert seat.choose(s, "p1", pick_legal(3)) == action


def test_pick_invalid_keys_rejected_then_valid_returned():
    s = pick_state(["blue_2", "white_1"])
    seat, stream = seat_with("3xdsm1")
    assert seat.choose(s, "p1", pick_legal(2)) == "play:1"
    assert stream.getvalue().count(UNKNOWN) == 5


def test_hot_seat_each_human_sees_own_hand_only_and_wait_is_not_asked():
    s = pick_state(["blue_2"], ["red_4", "green_1"])
    seats = {n: seat_with("r", n, False) for n in ("p1", "p2")}
    chosen = {n: seats[n][0].choose(s, n, legal_actions(s, RS, n)) for n in ("p1", "p2")}
    assert chosen == {"p1": PUT_BACK_DRAW, "p2": PUT_BACK_DRAW}
    out1, out2 = seats["p1"][1].getvalue(), seats["p2"][1].getvalue()
    assert "hand: B2" in out1 and "R4" not in out1 and "G1" not in out1
    assert "hand: R4 G1" in out2 and "B2" not in out2
    # p2 without a pick (WAIT only) is not asked: the runner skips WAIT.
    s.players["p2"].status = Status.STOPPED
    assert legal_actions(s, RS, "p2") == [WAIT]


def test_cli_play_v1_9_full_game_with_all_pick_kinds(tmp_path, monkeypatch):
    last = {}
    original = HumanSeat.choose

    def spy(self, state, seat, legal):
        last["legal"] = legal
        return original(self, state, seat, legal)

    monkeypatch.setattr(HumanSeat, "choose", spy)
    picks = iter(["0", "r", "t"] * 200)

    def read():
        legal = last["legal"]
        if any(a.startswith("play:") for a in legal):
            return next(picks)
        if "done" in legal:
            blue = [k for k, a in key_map(legal).items() if a.startswith("buy:blue")]
            return blue[0] if blue else "0"
        if "take_money" in legal:
            return "m"
        return "d"

    monkeypatch.setattr(human, "default_read_key", read)
    result = runner.invoke(
        app,
        ["play", "--rules", "v1.9", "--seed", "4", "--out", str(tmp_path), "--p2", "bot:random"],
    )
    assert result.exit_code == 0, result.output
    assert "winner:" in result.output and "Traceback" not in result.output
    (path,) = (tmp_path / "v1.9" / "play").glob("*.jsonl")
    (game,) = read_games(path)
    assert verify_game(game) == []
    actions = {s.actions["p1"] for s in game.steps if s.actions}
    assert PUT_BACK_DRAW in actions and PUT_BACK_STOP in actions
    assert any(a.startswith("play:") for a in actions)
