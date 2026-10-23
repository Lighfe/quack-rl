"""Regenerate the golden files. Run this only on purpose: the files pin rules behavior.

uv run python tests/fixtures/make_golden.py       # v1: the game record
uv run python tests/fixtures/make_golden.py v2    # v2: the game record and the bots results.csv
"""

import shutil
import sys
import tempfile
from pathlib import Path

from typer.testing import CliRunner

from quack_rl.cli.main import app

from quack_rl import __version__
from quack_rl.bots import RandomBot
from quack_rl.engine import RngChance
from quack_rl.record import GameRecorder, HeaderLine, SeatInfo
from quack_rl.rules import load_ruleset
from quack_rl.runner import play_game

GOLDEN = Path(__file__).parent / "golden"
V2_BOTS = (
    "bot:draw20-pts1-points,bot:draw20-pts1-cleaner,bot:draw20-pts4-blue,"
    "bot:draw30-pts3-green,bot:draw20-pts6-cleaner,bot:draw30-pts4-balanced"
)


def write_record(version: str, out: Path) -> None:
    rs = load_ruleset(version)
    out.parent.mkdir(parents=True, exist_ok=True)
    header = HeaderLine(
        game_id=f"golden-{version}-seed7",
        schema_version=1,
        rules_version=version,
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
    with out.open("w", encoding="utf-8", newline="\n") as f:
        rec = GameRecorder(f, header)
        final = play_game(rs, {"p1": RandomBot(15), "p2": RandomBot(16)}, RngChance(7), rec.on_step)
        rec.close(final)


def write_v2_bots_results(out: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        args = ["tournament", "--bots", V2_BOTS, "--rules", "v2", "--games", "10"]
        args += ["--seed", "7", "--name", "v2golden", "--out", tmp]
        result = CliRunner().invoke(app, args)
        assert result.exit_code == 0, result.output
        (results,) = Path(tmp).glob("*/results.csv")
        shutil.copyfile(results, out)


def main(argv: list[str]) -> None:
    mode = argv[0] if argv else "v1"
    if mode == "v1":
        write_record("v1", GOLDEN / "v1_random_seed7.jsonl")
    elif mode == "v2":
        write_record("v2", GOLDEN / "v2_random_seed7.jsonl")
        write_v2_bots_results(GOLDEN / "v2_bots_results.csv")
    else:
        raise SystemExit("usage: make_golden.py [v1|v2]")


if __name__ == "__main__":
    main(sys.argv[1:])
