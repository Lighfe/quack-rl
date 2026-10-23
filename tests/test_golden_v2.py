"""Golden v2: a stored game record and a stored bots results.csv pin rules v2 behaviour."""

import csv
import io
from pathlib import Path

import pytest
from typer.testing import CliRunner

from quack_rl import __version__
from quack_rl.bots import RandomBot
from quack_rl.cli.main import app
from quack_rl.engine import RngChance
from quack_rl.record import GameRecorder, HeaderLine, SeatInfo
from quack_rl.rules import load_ruleset
from quack_rl.runner import play_game

GOLDEN = Path(__file__).parent / "fixtures" / "golden"
BOTS = (
    "bot:draw20-pts1-points,bot:draw20-pts1-cleaner,bot:draw20-pts4-blue,"
    "bot:draw30-pts3-green,bot:draw20-pts6-cleaner,bot:draw30-pts4-balanced"
)


def test_golden_v2_replay():
    rs = load_ruleset("v2")
    header = HeaderLine(
        game_id="golden-v2-seed7",
        schema_version=1,
        rules_version="v2",
        rounds=rs.rounds,
        seed=7,
        mode="sim",
        seats={
            "p1": SeatInfo(kind="bot", name="random", params={"seed": 15}),
            "p2": SeatInfo(kind="bot", name="random", params={"seed": 16}),
        },
        ui={},
        engine_version=__version__,
        started_at="2026-10-08T12:00:00+02:00",
    )
    buf = io.StringIO()
    rec = GameRecorder(buf, header)
    final = play_game(rs, {"p1": RandomBot(15), "p2": RandomBot(16)}, RngChance(7), rec.on_step)
    rec.close(final)
    stored = (GOLDEN / "v2_random_seed7.jsonl").read_text(encoding="utf-8").splitlines()
    assert buf.getvalue().splitlines() == stored


@pytest.mark.slow
def test_golden_v2_bots_results(tmp_path):
    args = ["tournament", "--bots", BOTS, "--rules", "v2", "--games", "10", "--seed", "7"]
    args += ["--name", "v2golden", "--out", str(tmp_path)]
    r = CliRunner().invoke(app, args)
    assert r.exit_code == 0, r.output
    (results,) = tmp_path.glob("*/results.csv")
    with (GOLDEN / "v2_bots_results.csv").open(encoding="utf-8", newline="") as f:
        golden = list(csv.DictReader(f))
    with results.open(encoding="utf-8", newline="") as f:
        new = list(csv.DictReader(f))
    assert len(golden) == len(new) == 150
    for column in golden[0]:
        assert [row[column] for row in golden] == [row.get(column) for row in new], column
