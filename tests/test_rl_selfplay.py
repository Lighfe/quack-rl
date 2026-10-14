import csv
import json
from collections import Counter
from pathlib import Path

import pytest

from quack_rl.bots import RandomBot
from quack_rl.rl import PolicyBot, random_policy
from quack_rl.rl.runs import load_run
from quack_rl.rl.selfplay import (
    MAX_LOADED,
    SELFPLAY_COLUMNS,
    PoolOpponent,
    SnapshotCache,
    evaluate_update,
    train_selfplay,
)
from quack_rl.rules import load_ruleset

RS = load_ruleset("v1.1")


def fake_loader(path):
    return PolicyBot(random_policy(1), RS, name=f"fake:{Path(path).name}")


def shares(pool_size, draws=4000, seed=3):
    opp = PoolOpponent(fake_loader, seed=seed)
    for i in range(pool_size):
        opp.add(Path(f"step_{i}.zip"))
    return Counter("random" if (d := opp.draw()) is None else d.name for _ in range(draws))


def test_empty_pool_is_always_random():
    assert shares(0) == {"random": 4000}


def test_one_snapshot_older_falls_back_to_newest():
    c = shares(1)
    assert abs(c["step_0.zip"] / 4000 - 0.8) < 0.03
    assert abs(c["random"] / 4000 - 0.2) < 0.03


def test_pool_shares_are_half_third_fifth():
    c = shares(4, draws=10000)
    newest = c["step_3.zip"] / 10000
    older = sum(c[f"step_{i}.zip"] for i in range(3)) / 10000
    assert abs(newest - 0.5) < 0.03
    assert abs(older - 0.3) < 0.03
    assert abs(c["random"] / 10000 - 0.2) < 0.03
    # older snapshots are uniform
    for i in range(3):
        assert abs(c[f"step_{i}.zip"] / 10000 - 0.1) < 0.03


def test_snapshot_loaded_only_when_drawn_and_cache_is_bounded():
    loads = []

    def loader(path):
        loads.append(path)
        return fake_loader(path)

    opp = PoolOpponent(loader, seed=0)
    for i in range(10):
        opp.add(Path(f"step_{i}.zip"))
    assert loads == []  # adding loads nothing
    for _ in range(300):
        opp.new_episode()
    assert 0 < len(loads)
    assert len(opp.cache.loaded) <= MAX_LOADED


def test_cache_evicts_oldest_used():
    cache = SnapshotCache(fake_loader, max_loaded=2)
    a, b, c = Path("a"), Path("b"), Path("c")
    cache(a), cache(b), cache(a), cache(c)
    assert cache.loaded == [a, c]


def test_new_episode_with_empty_pool_is_random():
    opp = PoolOpponent(fake_loader, seed=0)
    opp.new_episode()
    assert opp.last_draw == "random"


def test_evaluate_update_row_has_the_documented_columns():
    pool = [Path("step_10.zip"), Path("step_20.zip")]
    row = evaluate_update(
        random_policy(0), pool, pool[-1], fake_loader, "v1.1", 2,
        ("draw20-pts1-points",), 30, "step_30.zip",
    )  # fmt: skip
    assert tuple(row) == SELFPLAY_COLUMNS
    assert row["timestep"] == 30 and row["snapshot"] == "step_30.zip" and row["games"] == 2
    assert set(json.loads(row["vs_heuristics"])) == {"draw20-pts1-points"}
    assert set(json.loads(row["vs_snapshots"])) == {"step_10.zip", "step_20.zip"}
    assert 0 <= row["vs_previous_newest"] <= 1 and 0 <= row["vs_random"] <= 1


def test_evaluate_update_first_update_has_no_snapshots():
    row = evaluate_update(random_policy(0), [], None, fake_loader, "v1.1", 2, (), 10, "step_10.zip")
    assert json.loads(row["vs_snapshots"]) == {} and row["vs_previous_newest"] == ""


def test_bad_input_fails_before_the_folder_exists(tmp_path):
    with pytest.raises(ValueError):
        train_selfplay("x", 100, update_every=0, runs_dir=tmp_path)
    with pytest.raises(ValueError):
        train_selfplay("x", 100, eval_bots=("nonsense",), runs_dir=tmp_path)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.slow
def test_selfplay_run_folder(tmp_path):
    pytest.importorskip("sb3_contrib", reason="needs the train group: uv sync --group train")
    train_selfplay("sp", 400, update_every=128, seed=1, eval_games=2, runs_dir=tmp_path)
    run = tmp_path / "sp"
    files = sorted(p.name for p in (run / "checkpoints").iterdir())
    assert files == ["step_128.zip", "step_256.zip", "step_384.zip", "step_512.zip"]
    with (run / "selfplay.csv").open(newline="") as f:
        rows = list(csv.DictReader(f))
    assert tuple(rows[0]) == SELFPLAY_COLUMNS and len(rows) == 4  # one row per update
    assert [r["snapshot"] for r in rows] == files
    assert json.loads(rows[2]["vs_snapshots"]).keys() == {"step_128.zip", "step_256.zip"}
    for name in ("config.json", "episodes.csv", "metrics.csv", "eval.json", "model.zip"):
        assert (run / name).exists()
    config, episodes, metrics, evaluation = load_run(run)
    assert config["mode"] == "selfplay" and config["update_every"] == 128
    assert config["pool_shares"] == {"newest": 0.5, "older": 0.3, "random": 0.2}
    assert episodes
    bot = PolicyBot.from_run(run, "v1.1")
    from quack_rl.engine import Phase, RngChance
    from quack_rl.runner import play_game

    assert play_game(RS, {"p1": bot, "p2": RandomBot(1)}, RngChance(1)).phase is Phase.GAME_OVER
    with pytest.raises(FileExistsError):
        train_selfplay("sp", 100, eval_games=1, runs_dir=tmp_path)
