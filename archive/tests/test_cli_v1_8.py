"""Human CLI under ruleset v1.8: explosion choice and the v1.8 board."""

import io
import itertools

import pytest
from rich.console import Console
from test_cli_play import text_of
from typer.testing import CliRunner

from quack_rl.cli import human
from quack_rl.cli.human import HumanSeat
from quack_rl.cli.main import app
from quack_rl.cli.render import render_board, render_step
from quack_rl.engine import Phase, Status, StepResult, new_game
from quack_rl.record import read_games, verify_game
from quack_rl.rules import load_ruleset

RS = load_ruleset("v1.8")
runner = CliRunner()


def choice_state(field: int = 53):
    s = new_game(RS)
    s.phase = Phase.CHOICE
    s.players["p1"].status = Status.EXPLODED
    s.players["p1"].field = field
    s.players["p1"].final_field = field
    return s


def seat_with(keys, rs=RS):
    stream = io.StringIO()
    it = iter(keys)
    seat = HumanSeat(
        "Player 1", Console(file=stream, width=120), True, rs, read_key=lambda: next(it)
    )
    return seat, stream


def test_choice_prompt_shows_money_and_points_and_keys_return_actions():
    s = choice_state(53)
    assert RS.money[53] == 35 and RS.points[53] == 15
    for key, action in (("m", "take_money"), ("p", "take_points")):
        seat, stream = seat_with(key)
        assert seat.choose(s, "p1", ["take_money", "take_points"]) == action
        out = stream.getvalue()
        assert "[m] take_money ($35)" in out
        assert "[p] take_points (+15pt)" in out


def test_hot_seat_only_exploded_seat_consumes_keys(monkeypatch):
    s = choice_state()
    keys = iter(["m"])
    calls = []

    def read():
        calls.append(1)
        return next(keys)

    from quack_rl.engine import WAIT, legal_actions

    seats = {
        seat: HumanSeat(seat, Console(file=io.StringIO()), True, RS, read_key=read)
        for seat in ("p1", "p2")
    }
    chosen = {}
    for seat in ("p1", "p2"):
        legal = legal_actions(s, RS, seat)
        if legal == [WAIT]:
            chosen[seat] = WAIT
            continue
        chosen[seat] = seats[seat].choose(s, seat, legal)
    assert chosen == {"p1": "take_money", "p2": "wait"}
    assert len(calls) == 1


def test_board_v1_8_shows_points_and_round_9_conversion():
    s = new_game(RS)
    s.players["p1"].field = 52
    s.round = 9
    text = board_text(s)
    assert "score 53 $35 +15pt" in text
    assert "money // 5" in text and "money becomes points" in text
    s.round = 8
    assert "money // 5" not in board_text(s)


def board_text(s):
    return text_of(render_board(s, RS, False), 120)


def test_v1_and_v1_1_board_unchanged():
    for version in ("v1", "v1.1"):
        rs = load_ruleset(version)
        s = new_game(rs)
        s.round = rs.rounds
        text = text_of(render_board(s, rs, False), 120)
        assert "pt" not in text.replace("points", "")
        assert "money //" not in text


def test_shop_menu_on_v1_8_has_no_points_item():
    s = new_game(RS)
    s.phase = Phase.SHOP
    for p in s.players.values():
        p.money = 100
    from quack_rl.engine import legal_actions

    seat, stream = seat_with("0")
    seat.choose(s, "p1", legal_actions(s, RS, "p1"))
    out = stream.getvalue()
    for item in ("points_2", "points_5", "points_10"):
        assert item not in out
    assert "[0] done" in out


@pytest.mark.parametrize(("kind", "amount"), [("take_money", 35), ("take_points", 15)])
def test_render_step_choice_events(kind, amount):
    result = StepResult(
        new_game(RS),
        1,
        1,
        Phase.SHOP,
        None,
        None,
        [],
        [{"seat": "p1", "kind": kind, "amount": amount}],
    )
    text = render_step(result, RS)
    assert kind in text and str(amount) in text


@pytest.mark.parametrize("choice", ["take_money", "take_points"])
def test_cli_play_v1_8_with_explosion_and_choice(tmp_path, monkeypatch, choice):
    key = "m" if choice == "take_money" else "p"
    it = itertools.cycle(f"d{key}0")
    monkeypatch.setattr(human, "default_read_key", lambda: next(it))
    result = runner.invoke(
        app,
        ["play", "--rules", "v1.8", "--seed", "4", "--out", str(tmp_path), "--p2", "bot:random"],
    )
    assert result.exit_code == 0, result.output
    assert "Traceback" not in result.output
    (path,) = (tmp_path / "v1.8" / "play").glob("*.jsonl")
    (game,) = read_games(path)
    assert verify_game(game) == []
    human_actions = [s.actions["p1"] for s in game.steps if s.actions]
    assert choice in human_actions
