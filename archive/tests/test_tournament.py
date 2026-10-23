import csv
import gzip
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import quack_rl.cli.main as cli_main
from quack_rl.cli.main import app
from quack_rl.record import read_games
from quack_rl.tournament import (
    CSV_COLUMNS,
    TournamentConfig,
    TournamentError,
    parse_sweep,
    validate,
    verify_sample,
)

runner = CliRunner()
BOTS = "bot:draw30-pts3-blue,bot:draw15-pts8-cleaner,bot:random"
TRACEBACK = "Traceback (most recent call last)"


def tour(out: Path, *extra: str, bots: str = BOTS, games: str = "3"):
    return runner.invoke(
        app,
        ["tournament", "--rules", "v1", "--bots", bots, "--games", games, "--seed", "5", "--out", str(out), *extra],
    )


def runs(out: Path) -> list[Path]:
    return sorted(p for p in out.glob("*") if p.is_dir())


def read_rows(run: Path) -> list[dict]:
    with (run / "results.csv").open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


