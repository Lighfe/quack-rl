import csv
import json
from pathlib import Path

import pytest

from quack_rl.bots import RandomBot
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
    opp = PoolOpponent(pool, "v2.1", seed=0, loader=loader)
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
    assert set(data) >= {"against_random", "against_heuristic", "against_first"}
    assert data["against_first"]["games"] == 2 and result.against_first is not None

    pool = CheckpointPool()
    pool.add(tmp_path / "checkpoint_2.zip")
    opp = PoolOpponent(pool, "v2.1", seed=1, loader=load_checkpoint)
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
