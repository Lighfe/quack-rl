"""The dataset manifest: `dataset_sha256`, `write_dataset_manifest` and `build_dataset.py`."""

import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

from quack_rl.rl.dataset import dataset_sha256, write_dataset_manifest
from quack_rl.rl.encode import BOARD_LAYOUT

ROOT = Path(__file__).parent.parent
A, B = "bot:topchip-draw20-pts6", "bot:spendmost-draw0-pts4"
KEYS = {"bots", "games_per_pairing", "seed", "rules", "command", "layout", "sha256"}


def run_build(monkeypatch, argv: list[str]) -> None:
    spec = importlib.util.spec_from_file_location(
        "build_dataset_script", ROOT / "scripts" / "build_dataset.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(sys, "argv", argv)
    module.main()


def test_dataset_sha256_is_the_hex_digest_of_the_file_bytes(tmp_path):
    path = tmp_path / "dataset.npz"
    path.write_bytes(b"some bytes")
    digest = dataset_sha256(path)
    assert digest == hashlib.sha256(b"some bytes").hexdigest()
    assert re.fullmatch(r"[0-9a-f]{64}", digest)


def test_write_dataset_manifest_writes_exactly_the_keys_and_overwrites(tmp_path):
    (tmp_path / "dataset.npz").write_bytes(b"data")
    (tmp_path / "manifest.json").write_text('{"old": true}\n')
    path = write_dataset_manifest(
        tmp_path,
        bots=[A, B],
        games_per_pairing=4,
        seed=3,
        rules="v2.3",
        command=["build_dataset.py", "--out", "x"],
    )
    assert path == tmp_path / "manifest.json"
    data = json.loads(path.read_text())
    assert set(data) == KEYS
    assert data == {
        "bots": [A, B],
        "games_per_pairing": 4,
        "seed": 3,
        "rules": "v2.3",
        "command": ["build_dataset.py", "--out", "x"],
        "layout": BOARD_LAYOUT,
        "sha256": hashlib.sha256(b"data").hexdigest(),
    }
    assert BOARD_LAYOUT == 10


def check_manifest(out: Path, bots: list[str], games: int, seed: int, argv: list[str]) -> None:
    data = json.loads((out / "manifest.json").read_text())
    assert set(data) == KEYS
    assert data["sha256"] == dataset_sha256(out / "dataset.npz")
    assert data["bots"] == bots
    assert data["games_per_pairing"] == games
    assert data["seed"] == seed
    assert data["rules"] == "v2.3"
    assert data["layout"] == 10
    assert data["command"] == argv
    assert sorted(p.name for p in out.iterdir()) == [
        "dataset-stats.json",
        "dataset.npz",
        "manifest.json",
    ]


def test_field_mode_writes_the_manifest(tmp_path, monkeypatch):
    out = tmp_path / "field"
    argv = ["build_dataset.py", "--bots", f"{B},{A}", "--games-per-pairing", "2"]
    argv += ["--seed", "5", "--out", str(out)]
    run_build(monkeypatch, argv)
    check_manifest(out, [B, A], 2, 5, argv)


def test_single_mode_writes_the_manifest(tmp_path, monkeypatch):
    out = tmp_path / "single"
    argv = ["build_dataset.py", "--agent", A, "--games", "2", "--out", str(out)]
    run_build(monkeypatch, argv)
    check_manifest(out, [A, "bot:random"], 2, 0, argv)


def test_single_mode_with_the_same_spec_twice_lists_it_twice(tmp_path, monkeypatch):
    out = tmp_path / "same"
    argv = ["build_dataset.py", "--agent", A, "--opponent", A, "--games", "2"]
    argv += ["--seed", "1", "--out", str(out)]
    run_build(monkeypatch, argv)
    check_manifest(out, [A, A], 2, 1, argv)
