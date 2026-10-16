import importlib.util
import json
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import pytest

from quack_rl.rl.dataset import DEFAULT_BOTS, build_dataset, to_table, write_dataset
from quack_rl.rl.single_env import QuackEnv

ROOT = Path(__file__).parent.parent
_spec = importlib.util.spec_from_file_location("build_dataset", ROOT / "scripts" / "build_dataset.py")
assert _spec and _spec.loader
script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(script)

BOTS = ["draw20-pts4-blue", "draw10-pts4-balanced", "random"]
SAMPLE = ROOT / "tests" / "fixtures" / "dataset" / "sample.parquet"


def _same(a, b):
    assert a.num_rows == b.num_rows
    for col in ("episode", "step", "obs", "action_mask", "action", "reward", "terminal",
                "bot", "opponent", "seat"):  # fmt: skip
        assert a[col].to_pylist() == b[col].to_pylist(), col


def test_dataset_layout(tmp_path):
    out = tmp_path / "d.parquet"
    write_dataset(out, BOTS, 20, seed=1)
    t = pq.read_table(out)
    assert str(t.schema.field("episode").type) == "int32"
    assert str(t.schema.field("step").type) == "int32"
    assert str(t.schema.field("obs").type) == "list<element: float>"
    assert str(t.schema.field("action_mask").type) == "list<element: int8>"
    assert str(t.schema.field("action").type) == "int16"
    assert str(t.schema.field("reward").type) == "float"
    assert str(t.schema.field("terminal").type) == "bool"
    space = QuackEnv().observation_space
    ep = np.array(t["episode"].to_pylist())
    term = np.array(t["terminal"].to_pylist())
    assert sorted(set(ep)) == list(range(20))
    for e in range(20):
        flags = term[ep == e]
        assert flags[-1] and flags.sum() == 1
    for obs, mask, act in zip(
        t["obs"].to_pylist(), t["action_mask"].to_pylist(), t["action"].to_pylist(), strict=True
    ):
        assert len(obs) == space.shape[0]
        o = np.array(obs, dtype=np.float32)
        assert (o >= space.low).all() and (o <= space.high).all()
        assert len(mask) == 15 and sum(mask) >= 1 and mask[act] == 1
    assert len(set(t["bot"].to_pylist()) | set(t["opponent"].to_pylist())) >= 3
    assert set(t["seat"].to_pylist()) == {"p1", "p2"}


def test_determinism(tmp_path):
    a = to_table(build_dataset(BOTS, 6, seed=3))
    b = to_table(build_dataset(BOTS, 6, seed=3))
    _same(a, b)
    c = to_table(build_dataset(BOTS, 6, seed=4))
    assert a["action"].to_pylist() != c["action"].to_pylist()


def test_error_cases(tmp_path):
    out = tmp_path / "d.parquet"
    for bots, games in ((BOTS, 0), (["nope"], 1), ([], 1), (["human"], 1), (["policy:x"], 1)):
        with pytest.raises(ValueError):
            write_dataset(out, bots, games)
        assert not out.exists() and not out.with_suffix(".json").exists()
    write_dataset(out, ["random"], 1)
    before = out.read_bytes()
    with pytest.raises(FileExistsError, match="--overwrite"):
        write_dataset(out, ["random"], 1)
    assert out.read_bytes() == before
    write_dataset(out, ["random"], 1, overwrite=True)


def test_script_exit_codes(tmp_path, capsys):
    out = tmp_path / "d.parquet"
    assert script.main(["--out", str(out), "--games", "0"]) == 2
    assert script.main(["--out", str(out), "--bots", "bot:nope", "--games", "1"]) == 2
    assert not out.exists()
    assert script.main(["--out", str(out), "--bots", "bot:random,random", "--games", "2"]) == 0
    assert script.main(["--out", str(out), "--games", "1"]) == 2
    assert "--overwrite" in capsys.readouterr().err


def test_default_mix():
    assert DEFAULT_BOTS == ("draw20-pts4-blue", "draw20-pts4-green", "draw20-pts4-balanced",
                            "draw20-pts4-cleaner", "draw10-pts4-balanced", "random")  # fmt: skip


def test_sample_reproduces(tmp_path):
    cfg = json.loads(SAMPLE.with_suffix(".json").read_text())
    out = tmp_path / "again.parquet"
    write_dataset(out, cfg["bots"], cfg["games"], cfg["seed"], cfg["rules"])
    _same(pq.read_table(SAMPLE), pq.read_table(out))
    assert set(pq.read_table(SAMPLE)["seat"].to_pylist()) == {"p1", "p2"}
