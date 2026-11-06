import csv
import json
from pathlib import Path

import pytest

from quack_rl.bots import RandomBot
from quack_rl.bots.presets import PRESET_BOTS
from quack_rl.rl import QuackEnv
from quack_rl.rl.selfplay import CheckpointPool, PoolOpponent


def test_pool_keeps_the_last_size_checkpoints():
    pool = CheckpointPool(2)
    for name in ("a", "b", "c"):
        pool.add(Path(name))
    assert pool.checkpoints == [Path("b"), Path("c")] and len(pool) == 2
    assert CheckpointPool().size == 4
    with pytest.raises(ValueError):
        CheckpointPool(0)


def test_env_calls_reset_of_the_opponent_and_works_without_it():
    class Counting(RandomBot):
        resets = 0

        def reset(self):
            self.resets += 1

    bot = Counting(0)
    env = QuackEnv(opponent=bot)
    for i in range(3):
        env.reset(seed=i)
    assert bot.resets == 3
    QuackEnv(opponent=RandomBot(0)).reset(seed=0)  # no reset method: as before


def test_pool_opponent_is_random_while_empty_and_picks_per_episode():
    loaded = []

    class Fake:
        def predict(self, obs, action_masks, deterministic):
            return int(action_masks.argmax()), None

    def loader(path):
        loaded.append(path)
        return Fake()

    pool = CheckpointPool(4)
    opp = PoolOpponent(pool, "v2.3", seed=0, loader=loader)
    env = QuackEnv(seat="random", opponent=opp)
    env.reset(seed=0)
    assert opp.current is None and not loaded
    for name in ("c1", "c2", "c3"):
        pool.add(Path(name))
    used = set()
    for i in range(50):
        env.reset(seed=i)
        used.add(opp.current)
    assert len(used) > 1 and used <= set(pool.checkpoints)
    assert set(loaded) == used  # each used checkpoint is loaded once


def test_selfplay_two_rounds(tmp_path):
    pytest.importorskip("sb3_contrib")
    import numpy as np

    from quack_rl.rl.selfplay import load_checkpoint, run_selfplay

    seen = []
    result = run_selfplay(
        tmp_path, rounds=2, steps_per_round=1000, seed=0, eval_games=2, on_progress=seen.append
    )
    for name in (
        "config.json",
        "selfplay.csv",
        "result.json",
        "checkpoint_1.zip",
        "checkpoint_2.zip",
    ):
        assert (tmp_path / name).is_file(), name
    rows = list(csv.reader((tmp_path / "selfplay.csv").open()))
    assert rows[0] == ["round", "steps", "mean_reward", "pool_size"] and len(rows) == 3
    assert [int(r[1]) for r in rows[1:]] == [1000, 2000]  # the counter keeps growing
    assert [r[3] for r in rows[1:]] == ["1", "2"] and len(seen) == 2
    data = json.loads((tmp_path / "result.json").read_text())
    assert set(data) == {"train_seconds", "against_random", "against_first", "against_presets"}
    assert data["against_first"]["games"] == 2 and result.against_first is not None
    assert list(data["against_presets"]) == list(PRESET_BOTS)
    assert list(result.against_presets) == list(PRESET_BOTS)
    keys = {"games", "wins", "draws", "losses", "win_rate", "ci_low", "ci_high"}
    for spec in PRESET_BOTS:
        entry = data["against_presets"][spec]
        assert set(entry) == keys and entry["games"] == 2
        assert entry == result.against_presets[spec].to_dict()

    pool = CheckpointPool()
    pool.add(tmp_path / "checkpoint_2.zip")
    opp = PoolOpponent(pool, "v2.3", seed=1, loader=load_checkpoint)
    env = QuackEnv(seat="random", opponent=opp)
    rng = np.random.default_rng(0)
    for i in range(2):
        _, info = env.reset(seed=i)
        done = False
        while not done:
            _, _, done, _, info = env.step(int(rng.choice(np.flatnonzero(info["action_mask"]))))
        assert opp.current == tmp_path / "checkpoint_2.zip"


def test_selfplay_one_round_has_no_entry_against_the_first(tmp_path):
    pytest.importorskip("sb3_contrib")
    from quack_rl.rl.selfplay import run_selfplay

    result = run_selfplay(tmp_path, rounds=1, steps_per_round=1000, eval_games=2)
    assert result.against_first is None
    assert "against_first" not in json.loads((tmp_path / "result.json").read_text())


# --- resume (#85) ------------------------------------------------------------------------------

REPO = Path(__file__).resolve().parents[1]
TINY = {"rounds": 4, "steps_per_round": 1000, "eval_games": 2}


class Stop(Exception):
    pass


def stop_after(n):
    def on_progress(point):
        if point.round == n:
            raise Stop

    return on_progress


def csv_rows(folder):
    return list(csv.reader((folder / "selfplay.csv").open()))


def run_script(monkeypatch, *args):
    """Run `scripts/train_selfplay.py` with `args`; return the exit code (0 if it did not exit)."""
    import runpy
    import sys

    monkeypatch.setattr(sys, "argv", ["train_selfplay.py", *args])
    try:
        runpy.run_path(str(REPO / "scripts" / "train_selfplay.py"), run_name="__main__")
    except SystemExit as stop:
        return stop.code
    return 0


def test_newest_checkpoint_is_by_number_and_skips_temporary_saves(tmp_path):
    from quack_rl.rl.selfplay import newest_checkpoint

    assert newest_checkpoint(tmp_path) is None
    for name in ("checkpoint_9.zip", "checkpoint_10.zip", "checkpoint_11.tmp.zip", "other.zip"):
        (tmp_path / name).write_bytes(b"")
    assert newest_checkpoint(tmp_path) == 10


def test_resume_without_config_or_checkpoint_stops_with_one_line(tmp_path, monkeypatch, capsys):
    run = tmp_path / "run"
    run.mkdir()
    (run / "checkpoint_1.zip").write_bytes(b"")
    assert run_script(monkeypatch, "--resume", str(run)) not in (0, None)
    err = capsys.readouterr().err
    assert err.strip() == f"train_selfplay: cannot resume {run}: no config.json"
    assert "Traceback" not in err

    (run / "checkpoint_1.zip").unlink()
    (run / "config.json").write_text(json.dumps({"rounds": 2}))
    assert run_script(monkeypatch, "--resume", str(run)) not in (0, None)
    err = capsys.readouterr().err
    assert err.strip() == f"train_selfplay: cannot resume {run}: no checkpoint_<i>.zip"


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["--out", "a", "--resume", "b"],
        ["--resume", "b", "--rounds", "3"],
        ["--resume", "b", "--steps-per-round", "3"],
        ["--resume", "b", "--pool-size", "3"],
        ["--resume", "b", "--seed", "3"],
        ["--resume", "b", "--eval-games", "3"],
    ],
)
def test_resume_flags_are_checked_by_argparse(tmp_path, monkeypatch, capsys, args):
    monkeypatch.chdir(tmp_path)
    assert run_script(monkeypatch, *args) == 2  # argparse error
    assert "error:" in capsys.readouterr().err
    assert not any(tmp_path.iterdir())


@pytest.mark.slow
def test_resumed_run_matches_an_uninterrupted_run(tmp_path):
    pytest.importorskip("sb3_contrib")
    from quack_rl.rl.selfplay import resume_selfplay, run_selfplay

    whole, cut = tmp_path / "whole", tmp_path / "cut"
    run_selfplay(whole, seed=0, **TINY)
    with pytest.raises(Stop):
        run_selfplay(cut, seed=0, on_progress=stop_after(2), **TINY)
    assert [r[0] for r in csv_rows(cut)] == ["round", "1", "2"]  # one row per finished round
    assert not (cut / "result.json").exists()

    seen = []
    result = resume_selfplay(cut, on_progress=seen.append)
    assert [p.round for p in seen] == [3, 4]
    for i in range(1, 5):
        assert (cut / f"checkpoint_{i}.zip").is_file()
    assert not list(cut.glob("*.tmp*"))
    rows = csv_rows(cut)
    assert len(rows) == 5

    def columns(rows):
        return [(r[0], r[1], r[3]) for r in rows]  # round, steps, pool_size

    assert columns(rows) == columns(csv_rows(whole))
    assert [p.round for p in result.rounds] == [1, 2, 3, 4]
    assert set(json.loads((cut / "result.json").read_text())) >= {"against_first"}


@pytest.mark.slow
def test_resume_cuts_the_csv_back_and_fills_the_pool(tmp_path, monkeypatch):
    pytest.importorskip("sb3_contrib")
    from quack_rl.rl import selfplay

    with pytest.raises(Stop):
        selfplay.run_selfplay(tmp_path, pool_size=2, on_progress=stop_after(3), **TINY)
    with (tmp_path / "selfplay.csv").open("a") as handle:
        handle.write("4,4000,,2\n")  # a row of a round whose checkpoint was never saved
    pools = []

    class Watching(selfplay.CheckpointPool):
        def add(self, path):
            super().add(path)
            pools.append(self.checkpoints)

    monkeypatch.setattr(selfplay, "CheckpointPool", Watching)
    seen = []
    selfplay.resume_selfplay(tmp_path, on_progress=seen.append)
    # the pool before round 4 is the last 2 checkpoints up to 3, oldest first
    assert pools[1] == [tmp_path / "checkpoint_2.zip", tmp_path / "checkpoint_3.zip"]
    assert [r[0] for r in csv_rows(tmp_path)] == ["round", "1", "2", "3", "4"]
    assert seen[0].pool_size == 2 and seen[0].steps == 4000


@pytest.mark.slow
def test_resume_of_a_trained_run_only_evaluates_and_saves_the_agent(tmp_path, monkeypatch):
    pytest.importorskip("sb3_contrib")
    from quack_rl.rl.agents import read_manifest
    from quack_rl.rl.selfplay import run_selfplay

    monkeypatch.chdir(tmp_path)
    run = tmp_path / "run"
    run_selfplay(run, rounds=2, steps_per_round=1000, eval_games=2)
    (run / "result.json").unlink()
    saved = {p.name: p.stat().st_mtime_ns for p in run.glob("checkpoint_*.zip")}
    rows = csv_rows(run)

    assert run_script(monkeypatch, "--resume", "run", "--agent-name", "resumed") == 0
    assert {p.name: p.stat().st_mtime_ns for p in run.glob("checkpoint_*.zip")} == saved
    assert csv_rows(run) == rows  # nothing trained
    assert (run / "result.json").is_file()
    folder = tmp_path / "data" / "agents" / "resumed"
    assert (folder / "model.zip").read_bytes() == (run / "checkpoint_2.zip").read_bytes()
    assert read_manifest(folder).settings["rounds"] == 2
