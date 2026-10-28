"""Human CLI under ruleset v2.3: the ruby step menu."""

import io
import re

from rich.console import Console
from typer.testing import CliRunner

from quack_rl.cli import human
from quack_rl.cli.human import HumanSeat, key_map
from quack_rl.cli.main import app
from quack_rl.engine import DONE, REFILL_FLASK, RUBY_DROP, Phase, legal_actions, new_game
from quack_rl.record import read_games, verify_game
from quack_rl.rules import load_ruleset

RS = load_ruleset("v2.3")
runner = CliRunner()


def ruby_state(rubies, flask_full):
    s = new_game(RS)
    s.phase = Phase.RUBY
    s.players["p1"].rubies, s.players["p1"].flask_full = rubies, flask_full
    return s


def choose(state, key):
    stream = io.StringIO()
    seat = HumanSeat("Player 1", Console(file=stream, width=2000), True, RS, read_key=lambda: key)
    action = seat.choose(state, "p1", legal_actions(state, RS, "p1"))
    return action, stream.getvalue()


def test_ruby_step_menu_offers_k_and_l():
    s = ruby_state(4, False)
    assert key_map(legal_actions(s, RS, "p1")) == {"0": DONE, "k": RUBY_DROP, "l": REFILL_FLASK}
    action, out = choose(s, "k")
    assert action == RUBY_DROP
    assert "ruby" in out  # the board title names the phase
    assert "[0] done" in out
    assert f"[k] ruby drop: {RS.ruby_cost} rubies, droplet +1" in out
    assert f"[l] refill flask: {RS.ruby_cost} rubies" in out
    assert choose(s, "l")[0] == REFILL_FLASK


def test_ruby_step_menu_without_refill_when_the_flask_is_full():
    s = ruby_state(4, True)
    assert key_map(legal_actions(s, RS, "p1")) == {"0": DONE, "k": RUBY_DROP}
    action, out = choose(s, "0")
    assert action == DONE and "[l]" not in out


def test_cli_play_v2_3_full_game_through_the_ruby_step(tmp_path, monkeypatch):
    last = {}
    phases = []
    original = HumanSeat.choose

    def spy(self, state, seat, legal):
        last["legal"] = legal
        phases.append(state.phase)
        return original(self, state, seat, legal)

    monkeypatch.setattr(HumanSeat, "choose", spy)
    cycle = iter("dds" * 500)

    def read():
        legal = last["legal"]
        keys = {a: k for k, a in key_map(legal).items()}
        if RUBY_DROP in legal:
            return "k"
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
        app, ["play", "--rules", "v2.3", "--seed", "2", "--out", str(tmp_path), "--p2", "bot:random"]
    )
    out = result.output
    assert result.exit_code == 0, out
    assert "Traceback" not in out and re.search(r"^winner: ", out, re.M)
    assert Phase.RUBY in phases
    (path,) = (tmp_path / "v2.3" / "play").glob("*.jsonl")
    (game,) = read_games(path)
    assert verify_game(game) == []
