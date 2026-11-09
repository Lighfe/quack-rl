"""`QuackEnv` emits the same games as the stored trace in `tests/fixtures/env_trace/`.

The trace pins every observation, mask, reward, flag and episode summary for 20 runs (each
preset bot and `bot:random` as opponent, seeds 0-4, 300 steps each). A speed-up of the env step
must keep it. Regenerate the files only on purpose with
`uv run python tests/fixtures/env_trace/make_trace.py`.
"""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from quack_rl.rl.planner import make_rollout_bot
from quack_rl.rl.single_env import QuackEnv
from quack_rl.rules import load_ruleset

TRACE_DIR = Path(__file__).resolve().parent / "fixtures" / "env_trace"
_spec = importlib.util.spec_from_file_location("make_trace", TRACE_DIR / "make_trace.py")
make_trace = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(make_trace)

RUNS = [(opponent, seed) for opponent in make_trace.OPPONENTS for seed in make_trace.SEEDS]


def test_trace_files_exist_and_are_small():
    paths = [make_trace.trace_path(opponent, seed) for opponent, seed in RUNS]
    assert len(paths) == 20
    assert all(p.exists() for p in paths)
    assert sum(p.stat().st_size for p in TRACE_DIR.iterdir() if p.is_file()) <= 2_000_000


def _replay_and_check(opponent: str, seed: int) -> None:
    stored = np.load(make_trace.trace_path(opponent, seed))
    rs = load_ruleset(make_trace.RULES)
    env = QuackEnv(seat="random", opponent=make_rollout_bot(rs, opponent, seed), rules=rs)
    rng = np.random.default_rng(seed)
    row = 0

    def check(obs: np.ndarray, kind: int) -> None:
        nonlocal row
        where = f"{opponent} seed {seed} row {row}"
        assert stored["kind"][row] == kind, where
        assert obs.dtype == stored["obs"].dtype, where
        np.testing.assert_array_equal(obs, stored["obs"][row], err_msg=where)
        mask = env.action_masks()
        assert mask.dtype == stored["mask"].dtype, where
        np.testing.assert_array_equal(mask, stored["mask"][row], err_msg=where)
        row += 1

    obs, _ = env.reset(seed=seed)
    check(obs, 0)
    for i in range(make_trace.STEPS):
        action = int(rng.choice(np.flatnonzero(env.action_masks())))
        assert action == stored["action"][i]
        obs, rew, term, trunc, info = env.step(action)
        check(obs, 1)
        assert rew == stored["reward"][i]
        assert term == stored["terminated"][i]
        assert trunc == stored["truncated"][i]
        if term or trunc:
            assert info["episode"] == json.loads(str(stored["episode"][i]))
            obs, _ = env.reset()
            check(obs, 0)
        else:
            assert stored["episode"][i] == ""
    assert row == len(stored["obs"])


@pytest.mark.slow
def test_env_trace_unchanged():
    for opponent, seed in RUNS:
        _replay_and_check(opponent, seed)
