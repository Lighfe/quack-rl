import csv
import importlib.util
import subprocess
import sys
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

pytest.importorskip("sb3_contrib", reason="needs the train group: uv sync --group train")
import torch  # noqa: E402

from quack_rl.bots import RandomBot  # noqa: E402
from quack_rl.engine import Phase, RngChance  # noqa: E402
from quack_rl.rl import PolicyBot, QuackEnv  # noqa: E402
from quack_rl.rl.offline import (  # noqa: E402
    bc_loss,
    build_model,
    load_offline_data,
    train_bc,
    train_offline_run,
)
from quack_rl.rl.runs import load_model  # noqa: E402
from quack_rl.rules import load_ruleset  # noqa: E402
from quack_rl.runner import play_game  # noqa: E402

ROOT = Path(__file__).parent.parent
SAMPLE = ROOT / "tests" / "fixtures" / "dataset" / "sample.parquet"
SCRIPT = ROOT / "scripts" / "train_offline.py"

_spec = importlib.util.spec_from_file_location("train_offline_script", SCRIPT)
assert _spec and _spec.loader
script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(script)


@pytest.fixture(scope="module")
def data():
    return load_offline_data(SAMPLE, 848)


def play(bot, other, seed, seat):
    seats = {seat: bot, ("p2" if seat == "p1" else "p1"): other}
    return play_game(load_ruleset("v1.1"), seats, RngChance(seed))


def weights(model):
    return {k: v.clone() for k, v in model.policy.state_dict().items()}


def test_load_shapes_and_legal_actions(data):
    assert data.obs.shape == (1649, 848) and data.obs.dtype == np.float32
    assert data.mask.shape == (1649, 15)
    assert data.mask[np.arange(len(data)), data.action].all()


def test_run_folder_loads(tmp_path):
    train_offline_run(SAMPLE, "r", tmp_path, seed=0, steps=5, log_every=2)
    run = tmp_path / "r"
    assert {p.name for p in run.iterdir()} == {"config.json", "model.zip", "metrics.csv"}
    assert load_model(run, "v1.1") is not None
    bot = PolicyBot.from_run(run, "v1.1")
    assert play(bot, RandomBot(1), 3, "p1").phase is Phase.GAME_OVER
    with (run / "metrics.csv").open() as f:
        rows = list(csv.DictReader(f))
    assert [r["step"] for r in rows] == ["2", "4", "5"]


def test_reproducible(data):
    a, ra = train_bc(data, seed=1, steps=8, log_every=4)
    b, rb = train_bc(data, seed=1, steps=8, log_every=4)
    c, _ = train_bc(data, seed=2, steps=8, log_every=4)
    wa, wb, wc = weights(a), weights(b), weights(c)
    assert all(torch.equal(wa[k], wb[k]) for k in wa)
    assert [r["loss"] for r in ra] == [r["loss"] for r in rb]
    assert any(not torch.equal(wa[k], wc[k]) for k in wa)


def test_no_new_game(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("a game was started")

    for name in ("__init__", "reset", "step"):
        monkeypatch.setattr(QuackEnv, name, boom)
    train_offline_run(SAMPLE, "r", tmp_path, steps=3)
    assert (tmp_path / "r" / "model.zip").exists()
    text = (ROOT / "src" / "quack_rl" / "rl" / "offline.py").read_text() + SCRIPT.read_text()
    assert "QuackEnv" not in text


def test_loss_finite_and_illegal_logit_gradient_zero(data):
    model = build_model(848, 0)
    obs = torch.from_numpy(data.obs[:64])
    mask = torch.from_numpy(data.mask[:64])
    action = torch.from_numpy(data.action[:64])
    obs.requires_grad_(False)
    from quack_rl.rl.offline import masked_logits

    logits = masked_logits(model, obs, mask)
    logits.retain_grad()
    import torch.nn.functional as F

    loss = F.cross_entropy(logits, action)
    loss.backward()
    assert torch.isfinite(loss)
    assert (logits.grad[mask == 0] == 0).all()
    assert bc_loss(model, obs, mask, action)[0].isfinite()


@pytest.mark.parametrize("seat", ["p1", "p2"])
def test_greedy_action_legal_in_20_games(tmp_path, seat):
    train_offline_run(SAMPLE, "r", tmp_path, steps=20)
    bot = PolicyBot.from_run(tmp_path / "r", "v1.1")
    for g in range(10):
        # an illegal action would raise
        assert play(bot, RandomBot(g), g, seat).phase is Phase.GAME_OVER


def test_errors_leave_no_folder(tmp_path):
    runs = tmp_path / "runs"
    bad = tmp_path / "bad.parquet"
    pq.write_table(
        pa.table(
            {
                "obs": pa.array([[0.0] * 10], pa.list_(pa.float32())),
                "action_mask": pa.array([[1] * 15], pa.list_(pa.int8())),
                "action": pa.array([0], pa.int16()),
            }
        ),
        bad,
    )
    with pytest.raises(FileNotFoundError):
        train_offline_run(tmp_path / "none.parquet", "r", runs, steps=1)
    with pytest.raises(ValueError, match="at least 1"):
        train_offline_run(SAMPLE, "r", runs, steps=0)
    with pytest.raises(ValueError, match="length 10, expected 848"):
        train_offline_run(bad, "r", runs, steps=1)
    assert not runs.exists() or list(runs.iterdir()) == []
    train_offline_run(SAMPLE, "r", runs, steps=1)
    before = (runs / "r" / "model.zip").read_bytes()
    with pytest.raises(FileExistsError):
        train_offline_run(SAMPLE, "r", runs, steps=2)
    assert (runs / "r" / "model.zip").read_bytes() == before


def test_script_errors_exit_nonzero(tmp_path):
    cmd = [sys.executable, str(SCRIPT), "--runs-dir", str(tmp_path)]
    bad = subprocess.run(
        [*cmd, "--dataset", str(tmp_path / "x.parquet"), "--run", "r", "--steps", "1"],
        capture_output=True, text=True,
    )  # fmt: skip
    assert bad.returncode != 0 and "error:" in bad.stderr
    assert list(tmp_path.iterdir()) == []
    assert script.main(["--dataset", str(SAMPLE), "--run", "r", "--steps", "0",
                        "--runs-dir", str(tmp_path)]) == 2  # fmt: skip
    assert script.main(["--dataset", str(SAMPLE), "--run", "r", "--steps", "2",
                        "--runs-dir", str(tmp_path)]) == 0  # fmt: skip
    assert script.main(["--dataset", str(SAMPLE), "--run", "r", "--steps", "2",
                        "--runs-dir", str(tmp_path)]) == 2  # fmt: skip
