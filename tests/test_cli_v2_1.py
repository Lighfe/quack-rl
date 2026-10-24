"""Human CLI under ruleset v2.1: the rat tail bonus in the board table (issue #159)."""

import re

from test_cli_play import text_of
from typer.testing import CliRunner

from quack_rl.cli import human
from quack_rl.cli.human import HumanSeat, key_map
from quack_rl.cli.main import app
from quack_rl.cli.render import chip_text, render_board, render_step
from quack_rl.engine import Phase, ScriptedChance, new_game, step
from quack_rl.record import read_games, verify_game
from quack_rl.rules import load_ruleset

RS = load_ruleset("v2.1")
runner = CliRunner()


def board(state, rs):
    return text_of(render_board(state, rs, False), 2000)


def test_board_shows_the_calculate_rat_tails():
    s = new_game(RS)
    s.players["p1"].rat_tail = 2
    text = board(s, RS)
    assert "rat tail +2" in text
    assert text.count("rat tail") == 1


def test_board_without_bonus_renders_as_before():
    s = new_game(RS)
    assert "rat tail" not in board(s, RS)


def test_rat_tail_event_prints_generically():
    s = new_game(RS)
    s.players["p1"].points = 0
    s.players["p2"].points = 10
    result = step(s, RS, None, ScriptedChance(["card_16"]))
    out = render_step(result, RS)
    assert "kind=rat_tail bonus=3" in out


def test_own_hand_is_shown_and_the_other_hand_is_not():
    import io

    from rich.console import Console

    s = new_game(RS)
    s.phase = Phase.BREW
    s.players["p1"].hand = ["blue_2"]
    s.players["p2"].hand = ["yellow_2"]
    stream = io.StringIO()
    seat = HumanSeat("Player 1", Console(file=stream, width=2000), True, RS, read_key=lambda: "r")
    seat.choose(s, "p1", ["play:0", "put_back_draw", "put_back_stop"])
    out = stream.getvalue()
    assert "hand: B2" in out and "Y2" not in out


def test_cli_simulate_v2_runs_a_full_game(tmp_path):
    result = runner.invoke(
        app,
        ["simulate", "--rules", "v2.1", "--p1", "bot:random", "--p2", "bot:random",
         "--games", "2", "--seed", "3", "--out", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    assert "Traceback" not in result.output
    assert list(tmp_path.glob("**/shard-*.jsonl"))


def test_cli_play_v2_full_game(tmp_path, monkeypatch):
    last = {}
    calls = []
    original = HumanSeat.choose

    def spy(self, state, seat, legal):
        last["legal"] = legal
        calls.append((state.players["p2"].hand[:], state.players["p1"].hand[:], list(legal)))
        return original(self, state, seat, legal)

    monkeypatch.setattr(HumanSeat, "choose", spy)
    cycle = iter("dds" * 500)

    def read():
        legal = last["legal"]
        keys = {a: k for k, a in key_map(legal).items()}
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
        app, ["play", "--rules", "v2.1", "--seed", "2", "--out", str(tmp_path), "--p2", "bot:random"]
    )
    out = result.output
    assert result.exit_code == 0, out
    assert "Traceback" not in out and re.search(r"^winner: ", out, re.M)
    (path,) = (tmp_path / "v2.1" / "play").glob("*.jsonl")
    (game,) = read_games(path)
    assert verify_game(game) == []
    expected = [
        "hand: " + " ".join(chip_text(c, RS).plain for c in mine)
        for _, mine, legal in calls
        if any(a.startswith("play:") or a.startswith("put_back") for a in legal)
    ]
    shown = [line for line in out.splitlines() if line.startswith("hand:")]
    assert shown == expected
