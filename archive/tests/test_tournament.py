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


class _FirstLegalModel:
    def predict(self, obs, action_masks, deterministic=True):
        return int(action_masks.argmax()), None


def test_tournament_accepts_a_policy_seat(tmp_path, monkeypatch):
    """A `policy:<run folder>` seat goes through the tournament CLI, loader mocked."""
    run = tmp_path / "policy_run"
    run.mkdir()
    monkeypatch.setattr("quack_rl.rl.policy_bot.load_model", lambda path, rules: _FirstLegalModel())
    out = tmp_path / "out"
    result = tour(out, bots=f"policy:{run},bot:random", games="2")
    assert result.exit_code == 0, result.output
    assert TRACEBACK not in result.output
    (folder,) = runs(out)
    rows = read_rows(folder)
    assert len(rows) == 2
    assert {r["p1"] for r in rows} == {f"policy:{run}"}
    assert {r["p2"] for r in rows} == {"random"}


def test_tournament_rejects_a_missing_policy_folder(tmp_path):
    result = tour(tmp_path / "out", bots=f"policy:{tmp_path / 'missing'},bot:random")
    assert result.exit_code == 2


# --- policy seat with a read-out suffix ---


def _fake_model():
    import numpy as np

    class Probs:
        def __init__(self, p):
            self.p = p

        def __getitem__(self, i):
            return self

        def detach(self):
            return self

        def cpu(self):
            return self

        def numpy(self):
            return self.p

    class Dist:
        def __init__(self, p):
            self.distribution = type("D", (), {"probs": Probs(p)})()

    class Policy:
        def obs_to_tensor(self, obs):
            return obs, None

        def get_distribution(self, obs, action_masks=None):
            return Dist(np.asarray(action_masks, dtype=float))

    class Model:
        policy = Policy()

        def predict(self, obs, action_masks=None, deterministic=True):
            return int(np.flatnonzero(action_masks)[0]), None

    return Model()


def test_sampled_policy_seat_is_reproducible_and_named_with_the_suffix(tmp_path, monkeypatch):
    from quack_rl.rl.encode import OBSERVATION_LAYOUT, vector_names
    from quack_rl.rules import load_ruleset

    run = tmp_path / "run"
    run.mkdir()
    (run / "config.json").write_text(
        json.dumps(
            {"layout": OBSERVATION_LAYOUT, "vector_names": vector_names(load_ruleset("v1.1"))}
        )
    )
    monkeypatch.setattr("quack_rl.rl.policy_bot.load_model", lambda p, r: _fake_model())
    bots = f"policy:{run}#sampled,bot:random"
    outs = []
    for name in ("a", "b"):
        r = tour(tmp_path / name, "--keep-records", bots=bots)
        assert r.exit_code == 0, r.output
        outs.append(runs(tmp_path / name)[0])
    for out in outs:
        assert any(f"policy:{run}#sampled" in row.values() for row in read_rows(out))
        assert f"policy:{run}#sampled" in (out / "config.json").read_text()
    assert read_rows(outs[0]) == read_rows(outs[1])
