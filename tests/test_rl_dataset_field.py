"""`scripts/build_dataset.py --bots`: a dataset of every ordered pair of distinct bot specs."""

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

from quack_rl.rl.dataset import ARRAYS, Dataset, build_dataset
from quack_rl.rl.encode import vector_names
from quack_rl.rules import load_ruleset

ROOT = Path(__file__).parent.parent
A, B = "bot:topchip-draw20-pts6", "bot:spendmost-draw0-pts4"


def load_script():
    spec = importlib.util.spec_from_file_location(
        "build_dataset_script", ROOT / "scripts" / "build_dataset.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(monkeypatch, *args: str) -> None:
    monkeypatch.setattr(sys, "argv", ["build_dataset.py", *args])
    load_script().main()


def test_build_dataset_from_field(tmp_path, monkeypatch):
    seed = 7
    out = tmp_path / "field"
    run(
        monkeypatch,
        "--bots",
        f"{A},{B}",
        "--games-per-pairing",
        "2",
        "--seed",
        str(seed),
        "--out",
        str(out),
    )
    data = Dataset.load(out / "dataset.npz")
    assert data.stats()["games"] == 4
    assert json.loads((out / "dataset-stats.json").read_text()) == data.stats()
    assert data.obs.shape[1] == len(vector_names(load_ruleset("v2.3")))
    expected = build_dataset(A, B, 2, seed).concat(build_dataset(B, A, 2, seed + 2))
    for name in ARRAYS:
        assert np.array_equal(getattr(data, name), getattr(expected, name)), name
    assert sorted(p.name for p in out.iterdir()) == [
        "dataset-stats.json",
        "dataset.npz",
        "manifest.json",
    ]


def test_field_pair_order_and_seeds():
    script = load_script()
    specs = ["bot:random", A, B]
    assert script.field_pairs(specs, 4, 10) == [
        ("bot:random", A, 10),
        ("bot:random", B, 14),
        (A, "bot:random", 18),
        (A, B, 22),
        (B, "bot:random", 26),
        (B, A, 30),
    ]


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--bots", A, "--games-per-pairing", "2"], "at least 2"),
        (["--bots", f"{A},{B},{A}", "--games-per-pairing", "2"], "twice"),
        (["--bots", f"{A},{B}", "--games-per-pairing", "3"], "even"),
        (["--bots", f"{A},{B}", "--games-per-pairing", "0"], "positive"),
        (["--bots", f"{A},{B}", "--games-per-pairing", "-2"], "positive"),
        (["--bots", f"{A},bot:nosuch-draw20-pts6", "--games-per-pairing", "2"], "nosuch"),
        (["--bots", f"{A},{B}", "--games-per-pairing", "2", "--agent", A], "--agent"),
        (["--bots", f"{A},{B}", "--games-per-pairing", "2", "--opponent", B], "--opponent"),
        (["--bots", f"{A},{B}"], "--games-per-pairing"),
        (["--games-per-pairing", "2"], "--bots"),
    ],
)
def test_field_errors(args, message, tmp_path, monkeypatch, capsys):
    out = tmp_path / "out"
    with pytest.raises(SystemExit) as err:
        run(monkeypatch, *args, "--out", str(out))
    assert err.value.code != 0
    assert message in capsys.readouterr().err
    assert not out.exists()


def test_old_single_part_mode_still_works(tmp_path, monkeypatch):
    run(
        monkeypatch,
        "--agent",
        A,
        "--opponent",
        "bot:random",
        "--games",
        "2",
        "--out",
        str(tmp_path),
    )
    data = Dataset.load(tmp_path / "dataset.npz")
    expected = build_dataset(A, "bot:random", 2, 0)
    for name in ARRAYS:
        assert np.array_equal(getattr(data, name), getattr(expected, name)), name
