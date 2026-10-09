import json
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

import quack_rl.simgame as simgame
from quack_rl.cli.main import app
from quack_rl.record import read_games

runner = CliRunner()
GOLDEN = Path(__file__).parent / "fixtures" / "golden" / "v1_random_seed7.jsonl"
GOLDEN_ID = "golden-v1-seed7"
TRACEBACK = "Traceback (most recent call last)"


def sim(out: Path, *extra: str, games: str = "5", seed: str = "3"):
    return runner.invoke(
        app, ["simulate", "--games", games, "--seed", seed, "--out", str(out), *extra]
    )


def run_dirs(out: Path) -> list[Path]:
    return sorted(p for p in (out / "v1" / "sim").glob("*") if p.is_dir())


def shards(out: Path) -> list[Path]:
    return sorted(out.glob("**/shard-*.jsonl"))


def assert_clean_error(result) -> None:
    """Non-zero exit, no Python traceback, no unhandled exception."""
    assert result.exit_code != 0, result.output
    assert TRACEBACK not in result.output
    assert result.exception is None or isinstance(result.exception, SystemExit), result.exception


def write_golden_head(path: Path, count: int) -> Path:
    lines = GOLDEN.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(lines[:count]) + "\n", encoding="utf-8")
    return path


# --- simulate ---------------------------------------------------------------


def test_simulate_writes_shards_of_games(tmp_path):
    result = sim(tmp_path, "--shard-size", "2")
    assert result.exit_code == 0, result.output
    (run,) = run_dirs(tmp_path)
    found = shards(tmp_path)
    assert [s.parent for s in found] == [run] * 3
    assert [s.name for s in found] == ["shard-0001.jsonl", "shard-0002.jsonl", "shard-0003.jsonl"]
    per_shard = [list(read_games(s)) for s in found]
    assert [len(g) for g in per_shard] == [2, 2, 1]
    games = [g for gs in per_shard for g in gs]
    assert all(g.footer is not None for g in games)
    assert all(g.header.mode == "sim" for g in games)
    assert [g.header.seed for g in games] == [3, 4, 5, 6, 7]


def test_simulate_one_shard_when_shard_size_covers_all_games(tmp_path):
    result = sim(tmp_path, "--shard-size", "1000")
    assert result.exit_code == 0, result.output
    found = shards(tmp_path)
    assert [s.name for s in found] == ["shard-0001.jsonl"]
    assert len(list(read_games(found[0]))) == 5


def test_simulate_output_names_run_folder_and_wins(tmp_path):
    result = sim(tmp_path, "--shard-size", "2")
    assert result.exit_code == 0, result.output
    (run,) = run_dirs(tmp_path)
    assert "5 games" in result.output
    assert str(run) in result.output
    match = re.search(r"^wins: p1 (\d+), p2 (\d+), draws (\d+)$", result.output, re.MULTILINE)
    assert match, result.output
    assert sum(int(x) for x in match.groups()) == 5
    winners = [g.footer.winner for s in shards(tmp_path) for g in read_games(s) if g.footer]
    assert match.groups() == tuple(str(winners.count(w)) for w in ("p1", "p2", "draw"))


def test_simulate_counts_engine_draw_as_draw(tmp_path, monkeypatch):
    real_play_game = simgame.play_game

    def play_draw(*args, **kwargs):
        state = real_play_game(*args, **kwargs)
        state.winner = "draw"
        return state

    monkeypatch.setattr(simgame, "play_game", play_draw)
    result = sim(tmp_path, games="3")
    assert result.exit_code == 0, result.output
    assert "wins: p1 0, p2 0, draws 3" in result.output


def _game_view(root: Path) -> list[dict]:
    view = []
    for shard in shards(root):
        for g in read_games(shard):
            assert g.footer is not None
            view.append(
                {
                    "seed": g.header.seed,
                    "seats": {s: i.model_dump() for s, i in g.header.seats.items()},
                    "steps": [
                        s.model_dump(
                            include={"n", "round", "phase", "legal", "actions", "chance", "events"}
                        )
                        for s in g.steps
                    ],
                    "footer": g.footer.model_dump(exclude={"game_id"}),
                }
            )
    return view


def test_simulate_is_reproducible(tmp_path):
    assert sim(tmp_path / "a", "--shard-size", "2").exit_code == 0
    assert sim(tmp_path / "b", "--shard-size", "2").exit_code == 0
    a, b = _game_view(tmp_path / "a"), _game_view(tmp_path / "b")
    assert len(a) == 5
    assert [[s["actions"] for s in g["steps"]] for g in a] == [
        [s["actions"] for s in g["steps"]] for g in b
    ]
    assert [[s["chance"] for s in g["steps"]] for g in a] == [
        [s["chance"] for s in g["steps"]] for g in b
    ]
    assert [g["footer"] for g in a] == [g["footer"] for g in b]
    assert a == b


def test_simulate_bot_seeds_follow_the_plan(tmp_path):
    assert sim(tmp_path, seed="3").exit_code == 0
    games = [g for s in shards(tmp_path) for g in read_games(s)]
    for i, g in enumerate(games):
        assert g.header.seats["p1"].params["seed"] == 2 * (3 + i) + 1
        assert g.header.seats["p2"].params["seed"] == 2 * (3 + i) + 2
        assert g.header.seats["p1"].kind == "bot" and g.header.seats["p1"].name == "random"


@pytest.mark.parametrize("seat_option", ["--p1", "--p2"])
def test_simulate_refuses_human_seat(tmp_path, seat_option):
    result = sim(tmp_path, seat_option, "human")
    assert_clean_error(result)
    assert "human" in result.output
    assert "quack-rl play" in result.output
    assert shards(tmp_path) == []


def test_simulate_refuses_unknown_seat(tmp_path):
    result = sim(tmp_path, "--p1", "bot:nope")
    assert_clean_error(result)
    assert "bot:nope" in result.output
    assert "bot:random" in result.output and "human" in result.output
    assert shards(tmp_path) == []


@pytest.mark.parametrize(
    "option,value",
    [("--games", "0"), ("--games", "-1"), ("--shard-size", "0"), ("--shard-size", "-1")],
)
def test_simulate_refuses_counts_below_one(tmp_path, option, value):
    args = ["simulate", "--out", str(tmp_path), option, value]
    result = runner.invoke(app, args)
    assert_clean_error(result)
    assert option in result.output
    assert shards(tmp_path) == []


def test_simulate_refuses_unsupported_rules(tmp_path):
    result = sim(tmp_path, "--rules", "v9")
    assert_clean_error(result)
    assert "v9" in result.output
    assert shards(tmp_path) == []


# --- verify -----------------------------------------------------------------


def test_verify_accepts_simulated_shard_with_seed_check(tmp_path):
    assert sim(tmp_path, "--shard-size", "2").exit_code == 0
    for shard, n in zip(shards(tmp_path), [2, 2, 1], strict=True):
        result = runner.invoke(app, ["verify", str(shard), "--seed-check"])
        assert result.exit_code == 0, result.output
        assert f"{n} games ok" in result.output


def test_verify_accepts_golden_record():
    result = runner.invoke(app, ["verify", str(GOLDEN)])
    assert result.exit_code == 0, result.output
    assert "1 games ok" in result.output


def test_verify_reports_truncated_golden_record(tmp_path):
    bad = write_golden_head(tmp_path / "bad.jsonl", 20)
    result = runner.invoke(app, ["verify", str(bad)])
    assert result.exit_code == 1
    assert "incomplete game" in result.output
    assert GOLDEN_ID in result.output
    assert TRACEBACK not in result.output


def test_verify_reports_one_broken_game_among_several(tmp_path):
    assert sim(tmp_path / "sim", games="3").exit_code == 0
    (shard,) = shards(tmp_path / "sim")
    lines = shard.read_text(encoding="utf-8").splitlines()
    games = list(read_games(shard))
    broken_id = games[1].header.game_id
    # Change the footer of the second game so its points no longer match the replay.
    for k, text in enumerate(lines):
        data = json.loads(text)
        if data["type"] == "footer" and data["game_id"] == broken_id:
            data["points"]["p1"] += 7
            lines[k] = json.dumps(data)
    bad = tmp_path / "mixed.jsonl"
    bad.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = runner.invoke(app, ["verify", str(bad)])
    assert result.exit_code == 1, result.output
    problem_lines = [ln for ln in result.output.splitlines() if ln.startswith(f"{broken_id}:")]
    assert len(problem_lines) == 1
    for g in (games[0], games[2]):
        assert g.header.game_id not in result.output
    assert "1 of 3 games have problems" in result.output


def test_verify_reports_line_that_is_not_json(tmp_path):
    bad = write_golden_head(tmp_path / "notjson.jsonl", 3)
    with bad.open("a", encoding="utf-8") as f:
        f.write("not json\n")
    result = runner.invoke(app, ["verify", str(bad)])
    assert result.exit_code == 1
    assert TRACEBACK not in result.output
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert f"{bad}:4" in result.output.replace("\n", "")


def test_verify_and_replay_report_missing_path(tmp_path):
    missing = tmp_path / "nope.jsonl"
    for command in ("verify", "replay"):
        result = runner.invoke(app, [command, str(missing)])
        assert_clean_error(result)
        assert "nope.jsonl" in result.output


def test_verify_reports_file_without_games(tmp_path):
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    result = runner.invoke(app, ["verify", str(empty)])
    assert result.exit_code == 1
    assert "no games" in result.output
    assert "0 games ok" not in result.output


# --- replay -----------------------------------------------------------------


def test_replay_prints_golden_record():
    result = runner.invoke(app, ["replay", str(GOLDEN)])
    assert result.exit_code == 0, result.output
    out = result.output.splitlines()
    (game,) = list(read_games(GOLDEN))
    assert out[0] == f"game {GOLDEN_ID} (rules v1)"
    step_lines = out[1:-1]
    assert len(step_lines) == len(game.steps)
    for text, step in zip(step_lines, game.steps, strict=True):
        assert text.startswith(f"step {step.n} round {step.round} {step.phase}:")
        for seat, action in (step.actions or {}).items():
            assert f"{seat}={action}" in text
        for c in step.chance:
            assert f"{c['seat']} {c['kind']} {c['value']}" in text
    assert out[-1].startswith("winner ")
    assert len(out) == len(game.steps) + 2


def test_replay_filters_by_game_id(tmp_path):
    assert sim(tmp_path, games="3").exit_code == 0
    (shard,) = shards(tmp_path)
    games = list(read_games(shard))
    wanted = games[1]
    result = runner.invoke(app, ["replay", str(shard), "--game", wanted.header.game_id])
    assert result.exit_code == 0, result.output
    headers = [ln for ln in result.output.splitlines() if ln.startswith("game ")]
    assert headers == [f"game {wanted.header.game_id} (rules v1)"]
    assert sum(ln.startswith("step ") for ln in result.output.splitlines()) == len(wanted.steps)


def test_replay_unknown_game_id_fails(tmp_path):
    result = runner.invoke(app, ["replay", str(GOLDEN), "--game", "no-such-game"])
    assert result.exit_code == 1
    assert "no-such-game" in result.output
    assert TRACEBACK not in result.output
    assert result.exception is None or isinstance(result.exception, SystemExit)


def test_replay_incomplete_game_prints_steps_without_winner(tmp_path):
    bad = write_golden_head(tmp_path / "bad.jsonl", 20)
    result = runner.invoke(app, ["replay", str(bad)])
    assert result.exit_code == 0, result.output
    out = result.output.splitlines()
    assert out[0] == f"game {GOLDEN_ID} (rules v1)"
    assert sum(ln.startswith("step ") for ln in out) == 19
    assert not any(ln.startswith("winner") for ln in out)
