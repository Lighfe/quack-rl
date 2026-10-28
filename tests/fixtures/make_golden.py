"""Regenerate the golden files. Run this only on purpose: the files pin rules behavior.

uv run python tests/fixtures/make_golden.py          # v2.3: the game record, the bots results.csv and the layout 9 sample
uv run python tests/fixtures/make_golden.py v2.3     # the same
uv run python tests/fixtures/make_golden.py layout9  # only the layout 9 sample (from the v2.3 record)

The generator of the archived v2.1 and v2.2 files is in the git history; the files are in
`archive/tests/fixtures/golden/`.
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

from typer.testing import CliRunner

from quack_rl.cli.main import app

from quack_rl import __version__
from quack_rl.bots import RandomBot
from quack_rl.engine import RngChance, new_game, step
from quack_rl.record import read_games
from quack_rl.record.replay import RecordedChance
from quack_rl.rl import observe, vector_names, vectorize
from quack_rl.record import RECORD_SCHEMA_VERSION, GameRecorder, HeaderLine, SeatInfo
from quack_rl.rules import load_ruleset
from quack_rl.runner import play_game

GOLDEN = Path(__file__).parent / "golden"
BOTS = (
    "bot:draw20-pts1-points,bot:draw20-pts1-cleaner,bot:draw20-pts4-blue,"
    "bot:draw30-pts3-green,bot:draw20-pts6-cleaner,bot:draw30-pts4-balanced"
)


def write_record(version: str, out: Path) -> None:
    rs = load_ruleset(version)
    out.parent.mkdir(parents=True, exist_ok=True)
    header = HeaderLine(
        game_id=f"golden-{version}-seed7",
        schema_version=RECORD_SCHEMA_VERSION,
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


def write_bots_results(version: str, out: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        args = ["tournament", "--bots", BOTS, "--rules", version, "--games", "10"]
        args += ["--seed", "7", "--name", "v2golden", "--out", tmp]
        result = CliRunner().invoke(app, args)
        assert result.exit_code == 0, result.output
        (results,) = Path(tmp).glob("*/results.csv")
        shutil.copyfile(results, out)


SAMPLE_STEP = 30  # a brew step of round 3 in the golden record
SAMPLE_SEAT = "p1"


def write_layout9_sample(record: Path, out: Path) -> None:
    """The state after step SAMPLE_STEP of the golden record, as seen by SAMPLE_SEAT: names and values."""
    (game,) = read_games(record)
    rs = load_ruleset(game.header.rules_version)
    state = new_game(rs)
    for line in game.steps[:SAMPLE_STEP]:
        state = step(state, rs, line.actions, RecordedChance(line.chance)).state
    sample = {
        "layout": 9,
        "record": record.name,
        "after_step": SAMPLE_STEP,
        "seat": SAMPLE_SEAT,
        "names": vector_names(rs),
        "values": [float(v) for v in vectorize(observe(state, rs, SAMPLE_SEAT), rs)],
    }
    out.write_text(json.dumps(sample, indent=0) + "\n", encoding="utf-8")


def main(argv: list[str]) -> None:
    mode = argv[0] if argv else "v2.3"
    if mode == "v2.3":
        write_record("v2.3", GOLDEN / "v2_3_random_seed7.jsonl")
        write_bots_results("v2.3", GOLDEN / "v2_3_bots_results.csv")
        write_layout9_sample(GOLDEN / "v2_3_random_seed7.jsonl", GOLDEN / "layout9_sample.json")
    elif mode == "layout9":
        write_layout9_sample(GOLDEN / "v2_3_random_seed7.jsonl", GOLDEN / "layout9_sample.json")
    else:
        raise SystemExit("usage: make_golden.py [v2.3|layout9]")


if __name__ == "__main__":
    main(sys.argv[1:])
