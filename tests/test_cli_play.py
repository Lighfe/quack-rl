import io
import itertools
from pathlib import Path

import pytest
import typer
from helpers import RS
from rich.console import Console
from typer.testing import CliRunner

from quack_rl.cli import human
from quack_rl.cli.human import HumanSeat
from quack_rl.cli.main import app
from quack_rl.cli.render import render_board
from quack_rl.engine import DRAW, STOP, Phase, buy, new_game
from quack_rl.record import read_games, verify_game

runner = CliRunner()
TRACEBACK = "Traceback (most recent call last)"


def text_of(renderable) -> str:
    console = Console(file=io.StringIO(), width=120, color_system=None)
    console.print(renderable)
    return console.file.getvalue()  # type: ignore[attr-defined]


def board(state=None, bag_assist=True) -> str:
    return text_of(render_board(state or new_game(RS), RS, bag_assist))


def seat_with(keys, label="Player 1"):
    stream = io.StringIO()
    it = iter(keys)
    seat = HumanSeat(label, Console(file=stream, width=120), True, RS, read_key=lambda: next(it))
    return seat, stream


def script(monkeypatch, keys):
    it = itertools.cycle(keys)
    monkeypatch.setattr(human, "default_read_key", lambda: next(it))


def play(tmp_path, *extra, seed="4"):
    return runner.invoke(app, ["play", "--seed", seed, "--out", str(tmp_path), *extra])


def play_files(tmp_path: Path) -> list[Path]:
    return sorted((tmp_path / "v1" / "play").glob("*.jsonl"))


def only_game(tmp_path: Path):
    (path,) = play_files(tmp_path)
    (game,) = read_games(path)
    return path, game


# --- board -------------------------------------------------------------------


def test_board_new_game_shows_round_phase_seats_and_numbers():
    text = board()
    for expected in ("Round 1/9", "brew", "p1", "p2", "brewing", "start 0", "0/7"):
        assert expected in text
    assert "next ruby 5" in text
    assert "money 0" in text and "points" in text


def test_board_shows_placed_chips_and_dash_when_none():
    s = new_game(RS)
    s.players["p1"].placed = ["white_1", "orange_1"]
    text = board(s)
    assert "W1 O1" in text
    p2_line = next(line for line in text.splitlines() if "p2" in line and "brewing" in line)
    assert p2_line.rstrip(" │┃|").endswith("-")


def test_board_past_last_ruby_shows_dash_and_money():
    s = new_game(RS)
    s.players["p1"].field = 53
    text = board(s)
    assert "next ruby -" in text and "None" not in text
    assert "35" in text


def test_board_bag_lines_only_with_assist():
    s = new_game(RS)
    with_bag = board(s, True)
    assert any(line.startswith("p1 bag:") and "4×W1" in line for line in with_bag.splitlines())
    assert any(line.startswith("p2 bag:") for line in with_bag.splitlines())
    assert "bag" not in board(s, False)


# --- human seat ----------------------------------------------------------------


def test_keys_map_to_legal_actions():
    legal = ["done", buy("orange_1"), buy("blue_1"), buy("green_1")]
    s = new_game(RS)
    s.phase = Phase.SHOP
    assert seat_with("2")[0].choose(s, "p1", legal) == buy("blue_1")
    assert seat_with("0")[0].choose(s, "p1", legal) == "done"
    s.phase = Phase.BREW
    assert seat_with("d")[0].choose(s, "p1", [DRAW, STOP]) == DRAW
    assert seat_with("s")[0].choose(s, "p1", [DRAW, STOP]) == STOP


def test_buy_keys_continue_with_letters():
    legal = ["done", *[buy(i.id) for i in RS.shop]]
    assert len(legal) - 1 >= 10
    seat, _ = seat_with("a")
    assert seat.choose(new_game(RS), "p1", legal) == legal[10]


def test_unknown_and_illegal_keys_try_again():
    s = new_game(RS)
    seat, stream = seat_with(["x", "0", "s", "d"])
    assert seat.choose(s, "p1", [DRAW]) == DRAW
    assert stream.getvalue().count("try again") == 3
    legal = ["done", buy("orange_1"), buy("blue_1"), buy("green_1")]
    seat, stream = seat_with(["4", "3"])
    assert seat.choose(s, "p1", legal) == buy("green_1")
    assert stream.getvalue().count("try again") == 1


def test_default_read_key_is_hidden(monkeypatch):
    seen = {}

    def fake_getchar(echo=True):
        seen["echo"] = echo
        return "d"

    monkeypatch.setattr(typer, "getchar", fake_getchar)
    assert human.default_read_key() == "d"
    assert seen["echo"] is False


def test_choose_prints_nothing_after_a_valid_key():
    stream = io.StringIO()
    it = iter(["d"])

    def read():
        before = stream.getvalue()
        key = next(it)
        read.before = before  # type: ignore[attr-defined]
        return key

    seat = HumanSeat("Player 1", Console(file=stream, width=120), True, RS, read_key=read)
    assert seat.choose(new_game(RS), "p1", [DRAW]) == DRAW
    assert stream.getvalue() == read.before  # type: ignore[attr-defined]


def test_choose_prints_board_and_menu_with_buy_details():
    s = new_game(RS)
    s.phase = Phase.SHOP
    item = RS.shop[0]
    seat, stream = seat_with("0")
    seat.choose(s, "p1", ["done", buy(item.id)])
    out = stream.getvalue()
    assert "Round 1/9" in out and "p1 bag:" in out
    assert "Player 1 (p1)" in out
    assert "[0] done" in out
    assert f"[1] buy {item.id} ({item.price})" in out


# --- play command --------------------------------------------------------------


def test_play_human_vs_bot_records_a_verifiable_game(tmp_path, monkeypatch):
    script(monkeypatch, "ds0")
    result = play(tmp_path)
    assert result.exit_code == 0, result.output
    assert TRACEBACK not in result.output
    assert "winner:" in result.output and "points" in result.output
    path, game = only_game(tmp_path)
    assert f"record: {path}" in result.output.replace("\n", "")
    assert game.header.mode == "play" and game.header.ui == {"bag_assist": True}
    assert game.header.seats["p1"].kind == "human"
    assert game.header.seats["p2"].kind == "bot"
    assert game.footer is not None
    assert verify_game(game) == []
    v = runner.invoke(app, ["verify", str(path)])
    assert v.exit_code == 0 and "1 games ok" in v.output


def test_decision_ms_only_for_human_seats(tmp_path, monkeypatch):
    script(monkeypatch, "ds0")
    assert play(tmp_path).exit_code == 0
    _, game = only_game(tmp_path)
    assert any("p1" in (s.decision_ms or {}) for s in game.steps)
    assert all("p2" not in (s.decision_ms or {}) for s in game.steps)


def test_no_bag_assist(tmp_path, monkeypatch):
    script(monkeypatch, "ds0")
    result = play(tmp_path, "--no-bag-assist")
    assert result.exit_code == 0, result.output
    _, game = only_game(tmp_path)
    assert game.header.ui == {"bag_assist": False}
    assert " bag: " not in result.output


def test_hot_seat(tmp_path, monkeypatch):
    script(monkeypatch, "ds0")
    result = play(tmp_path, "--p2", "human")
    assert result.exit_code == 0, result.output
    assert "Player 1 (p1)" in result.output and "Player 2 (p2)" in result.output
    _, game = only_game(tmp_path)
    assert game.header.seats["p1"].kind == "human"
    assert game.header.seats["p2"].kind == "human"
    assert any({"p1", "p2"} <= set(s.decision_ms or {}) for s in game.steps)
    assert verify_game(game) == []


def test_same_seed_and_keys_give_the_same_game(tmp_path, monkeypatch):
    games = []
    for run in ("a", "b"):
        script(monkeypatch, "ds0")
        assert play(tmp_path / run).exit_code == 0
        games.append(only_game(tmp_path / run)[1])
    a, b = games
    assert [s.actions for s in a.steps] == [s.actions for s in b.steps]
    assert [s.chance for s in a.steps] == [s.chance for s in b.steps]
    assert a.footer is not None and b.footer is not None
    assert a.footer.model_dump(exclude={"game_id"}) == b.footer.model_dump(exclude={"game_id"})


def interrupting(exc, at):
    calls = itertools.count()

    def key():
        if next(calls) == at:
            raise exc
        return "d"

    return key


@pytest.mark.parametrize("exc", [KeyboardInterrupt, EOFError])
def test_abort_keeps_a_partial_record(tmp_path, monkeypatch, exc):
    monkeypatch.setattr(human, "default_read_key", interrupting(exc, 3))
    result = play(tmp_path)
    assert result.exit_code == 130, result.output
    assert TRACEBACK not in result.output
    path, game = only_game(tmp_path)
    assert f"game aborted, partial record: {path}" in result.output.replace("\n", "")
    assert game.footer is None and game.steps
    assert verify_game(game) == ["incomplete game: no footer"]


def test_abort_at_first_key_leaves_header_only(tmp_path, monkeypatch):
    monkeypatch.setattr(human, "default_read_key", interrupting(KeyboardInterrupt, 0))
    result = play(tmp_path)
    assert result.exit_code == 130, result.output
    assert "game aborted, partial record:" in result.output
    path, game = only_game(tmp_path)
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1
    assert game.steps == [] and game.footer is None
    v = runner.invoke(app, ["verify", str(path)])
    assert v.exit_code == 1 and "incomplete game" in v.output
    assert TRACEBACK not in v.output


def test_unknown_seat_writes_no_file(tmp_path):
    result = play(tmp_path, "--p1", "bot:nope")
    assert result.exit_code != 0
    assert "bot:random" in result.output and "human" in result.output
    assert TRACEBACK not in result.output
    assert play_files(tmp_path) == []


def test_unsupported_rules_writes_no_file(tmp_path):
    result = play(tmp_path, "--rules", "v9")
    assert result.exit_code != 0
    assert "v9" in result.output and TRACEBACK not in result.output
    assert play_files(tmp_path) == []
    assert not (tmp_path / "v9").exists()


def test_simulate_still_refuses_human(tmp_path):
    result = runner.invoke(app, ["simulate", "--p1", "human", "--out", str(tmp_path)])
    assert result.exit_code != 0
    assert "quack-rl play" in result.output
