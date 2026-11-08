"""Read the run folders of an experiment for the monitor notebook (`notebooks/rl_monitor.py`).

A run folder (`data/experiments/<id>/seed<k>/`) is written while it is read: any file may be
missing, header-only, or end in a cut-off line. This module only reads; it writes nothing.
It imports only the standard library and polars, so the tests need no marimo or altair.
"""

from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import polars as pl

_INT = pl.Int64
_FLOAT = pl.Float64

PPO_SCHEMA: dict[str, pl.DataType] = {
    "steps": _INT(),
    "mean_reward": _FLOAT(),
    "games": _INT(),
    "policy_loss": _FLOAT(),
    "value_loss": _FLOAT(),
    "entropy": _FLOAT(),
    "approx_kl": _FLOAT(),
    "clip_fraction": _FLOAT(),
    "explained_variance": _FLOAT(),
    "wall_seconds": _FLOAT(),
}
BC_SCHEMA: dict[str, pl.DataType] = {
    "epoch": _INT(),
    "loss": _FLOAT(),
    "entropy": _FLOAT(),
    "wall_seconds": _FLOAT(),
}
EVAL_SCHEMA: dict[str, pl.DataType] = {
    "step": _INT(),
    "opponent": pl.String(),
    "mode": pl.String(),
    "games": _INT(),
    "wins": _INT(),
    "draws": _INT(),
    "losses": _INT(),
    "win_rate": _FLOAT(),
    "ci_low": _FLOAT(),
    "ci_high": _FLOAT(),
}

_SEED_DIR = re.compile(r"seed(\d+)")


def _empty(schema: dict[str, pl.DataType]) -> pl.DataFrame:
    return pl.DataFrame(schema=schema)


@dataclass(frozen=True)
class RunData:
    """What one run folder holds right now."""

    train: pl.DataFrame = field(default_factory=pl.DataFrame)
    evals: pl.DataFrame = field(default_factory=lambda: _empty(EVAL_SCHEMA))
    final: pl.DataFrame = field(default_factory=lambda: _empty(EVAL_SCHEMA))
    config: dict = field(default_factory=dict)
    kind: Literal["ppo", "bc"] | None = None
    done: bool = False


def read_csv(path: Path, schema: dict[str, pl.DataType]) -> pl.DataFrame:
    """The complete rows of `path` with the types of `schema`.

    A missing or empty file gives an empty frame with the columns of `schema`. A last line
    without a newline is a row still being written: it is dropped.
    """
    try:
        text = path.read_text()
    except (FileNotFoundError, IsADirectoryError):
        return _empty(schema)
    if not text.endswith("\n"):
        text = text[: text.rfind("\n") + 1]  # no newline at all: nothing complete
    if not text:
        return _empty(schema)
    header = next(iter(text.splitlines()), "").split(",")
    overrides = {name: dtype for name, dtype in schema.items() if name in header}
    return pl.read_csv(io.StringIO(text), schema_overrides=overrides)


def _read_config(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def load_run(run_dir: Path) -> RunData:
    """Read one run folder. A missing folder gives empty frames and `kind` None."""
    run_dir = Path(run_dir)
    if (run_dir / "ppo.csv").is_file():
        kind, train = "ppo", read_csv(run_dir / "ppo.csv", PPO_SCHEMA)
    elif (run_dir / "bc.csv").is_file():
        kind, train = "bc", read_csv(run_dir / "bc.csv", BC_SCHEMA)
    else:
        kind, train = None, pl.DataFrame()
    return RunData(
        train=train,
        evals=read_csv(run_dir / "eval.csv", EVAL_SCHEMA),
        final=read_csv(run_dir / "final_eval.csv", EVAL_SCHEMA),
        config=_read_config(run_dir / "config.json"),
        kind=kind,
        done=(run_dir / "done.json").is_file(),
    )


def load_experiment(exp_dir: Path) -> dict[int, RunData]:
    """The runs of one experiment folder keyed by seed, from its `seed<k>` subfolders only."""
    exp_dir = Path(exp_dir)
    if not exp_dir.is_dir():
        return {}
    runs: dict[int, RunData] = {}
    for entry in sorted(exp_dir.iterdir()):
        match = _SEED_DIR.fullmatch(entry.name)
        if match and entry.is_dir():
            runs[int(match.group(1))] = load_run(entry)
    return dict(sorted(runs.items()))


def experiment_dirs(root: Path) -> list[Path]:
    """The experiment folders under `root` (folders with at least one `seed<k>` subfolder)."""
    root = Path(root)
    if not root.is_dir():
        return []
    return [
        entry
        for entry in sorted(root.iterdir())
        if entry.is_dir()
        and any(_SEED_DIR.fullmatch(sub.name) and sub.is_dir() for sub in entry.iterdir())
    ]
