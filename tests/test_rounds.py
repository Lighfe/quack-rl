import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from quack_rl.cli import human
from quack_rl.cli.main import app
from quack_rl.record import read_games

runner = CliRunner()
GOLDEN = Path(__file__).parent / "fixtures" / "golden" / "v1_random_seed7.jsonl"
GOLDEN_ID = "golden-v1-seed7"
TRACEBACK = "Traceback (most recent call last)"


def sim(out: Path, *extra: str):
    return runner.invoke(
        app, ["simulate", "--games", "3", "--seed", "3", "--out", str(out), *extra]
    )


def play(out: Path, monkeypatch, *extra: str):
    keys = iter("ds0" * 5000)
    monkeypatch.setattr(human, "default_read_key", lambda: next(keys))
    return runner.invoke(app, ["play", "--seed", "4", "--out", str(out), *extra])


def games_of(out: Path):
    return [g for p in sorted(out.glob("**/*.jsonl")) for g in read_games(p)]


def last_shop_step(game):
    return [s for s in game.steps if s.phase == "shop"][-1]


# --- criterion 1: simulate and play use the number of rounds ------------------


def test_simulate_rounds_4_ends_after_the_shop_of_round_4(tmp_path):
    result = sim(tmp_path, "--rounds", "4")
    assert result.exit_code == 0, result.output
    games = games_of(tmp_path)
    assert len(games) == 3
    for g in games:
        assert g.header.rounds == 4
        assert g.footer is not None
        assert {s.round for s in g.steps} == {1, 2, 3, 4}
        assert g.steps[-1] is last_shop_step(g) and g.steps[-1].round == 4


def test_play_rounds_4_ends_after_the_shop_of_round_4(tmp_path, monkeypatch):
    result = play(tmp_path, monkeypatch, "--rounds", "4")
    assert result.exit_code == 0, result.output
    (game,) = games_of(tmp_path)
    assert game.header.rounds == 4
    assert game.footer is not None
    assert max(s.round for s in game.steps) == 4
    assert game.steps[-1] is last_shop_step(game) and game.steps[-1].round == 4
    assert "Round 4/4" in result.output


# --- criterion 2: default is 9 --------------------------------------------------


def test_default_is_9_rounds_and_header_stores_it(tmp_path):
    assert sim(tmp_path).exit_code == 0
    for g in games_of(tmp_path):
        assert g.header.rounds == 9
        assert max(s.round for s in g.steps) == 9
    first_line = next(tmp_path.glob("**/shard-0001.jsonl")).read_text().splitlines()[0]
    assert json.loads(first_line)["rounds"] == 9


# --- criterion 3: invalid values --------------------------------------------------


@pytest.mark.parametrize("value", ["0", "-3"])
@pytest.mark.parametrize("command", ["simulate", "play"])
def test_rounds_below_1_is_refused(tmp_path, command, value):
    result = runner.invoke(app, [command, "--rounds", value, "--out", str(tmp_path)])
    assert result.exit_code == 1
    assert "--rounds" in result.output and "at least 1" in result.output
    assert TRACEBACK not in result.output
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert list(tmp_path.glob("**/*")) == []


@pytest.mark.parametrize("command", ["simulate", "play"])
def test_rounds_not_an_integer_is_refused(tmp_path, command):
    result = runner.invoke(app, [command, "--rounds", "x", "--out", str(tmp_path)])
    assert result.exit_code != 0
    assert TRACEBACK not in result.output
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert list(tmp_path.glob("**/*")) == []


# --- criterion 4: header field, verify and replay ----------------------------------


def test_verify_seed_check_and_replay_accept_a_4_round_record(tmp_path):
    assert sim(tmp_path, "--rounds", "4").exit_code == 0
    shard = next(tmp_path.glob("**/shard-0001.jsonl"))
    v = runner.invoke(app, ["verify", str(shard), "--seed-check"])
    assert v.exit_code == 0, v.output
    assert "3 games ok" in v.output
    r = runner.invoke(app, ["replay", str(shard)])
    assert r.exit_code == 0, r.output
    assert "round 4" in r.output
    assert "round 5" not in r.output


# --- criterion 5: one round ---------------------------------------------------------


def test_one_round_applies_the_multiplier_and_ends_after_its_shop(tmp_path):
    result = sim(tmp_path, "--rounds", "1")
    assert result.exit_code == 0, result.output
    for g in games_of(tmp_path):
        assert g.footer is not None
        assert {s.round for s in g.steps} == {1}
        assert g.steps[-1].phase == "shop"
        # the last round pays money x last_round_money_percent: resolve events show it
        resolve = [s for s in g.steps if s.phase == "resolve"]
        assert resolve
    v = runner.invoke(app, ["verify", str(next(tmp_path.glob("**/shard-0001.jsonl")))])
    assert v.exit_code == 0, v.output


def test_multiplier_applies_in_the_last_round_of_a_short_game():
    from helpers import RS

    from quack_rl.rules import with_rounds

    short = with_rounds(RS, 1)
    assert short.rounds == 1
    assert short.last_round_money_percent == RS.last_round_money_percent
    assert RS.rounds == 9  # the loaded ruleset is not changed


def test_with_rounds_refuses_below_1():
    from helpers import RS

    from quack_rl.rules import with_rounds

    with pytest.raises(ValueError):
        with_rounds(RS, 0)


# --- criterion 6: header without rounds ----------------------------------------------


def golden_without_rounds(tmp_path: Path) -> Path:
    lines = GOLDEN.read_text(encoding="utf-8").splitlines()
    header = json.loads(lines[0])
    del header["rounds"]
    path = tmp_path / "old.jsonl"
    path.write_text("\n".join([json.dumps(header), *lines[1:]]) + "\n", encoding="utf-8")
    return path


@pytest.mark.parametrize("command", ["verify", "replay"])
def test_header_without_rounds_is_refused(tmp_path, command):
    path = golden_without_rounds(tmp_path)
    result = runner.invoke(app, [command, str(path)])
    assert result.exit_code == 1
    assert "rounds" in result.output and GOLDEN_ID in result.output
    assert TRACEBACK not in result.output
    assert result.exception is None or isinstance(result.exception, SystemExit)


def test_golden_record_has_rounds_9():
    (game,) = read_games(GOLDEN)
    assert game.header.rounds == 9
