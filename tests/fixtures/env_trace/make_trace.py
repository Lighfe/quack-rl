"""Regenerate the env trace. Run this only on purpose: the files pin what `QuackEnv` emits.

uv run python tests/fixtures/env_trace/make_trace.py

For each opponent spec in `PRESET_BOTS` and `bot:random`, and each seed 0-4, the trace plays
`STEPS` `QuackEnv` steps (seat "random", ruleset v2.3) with uniformly random legal actions from
`np.random.default_rng(seed)` and writes one compressed npz per run. A file holds:

- `obs`, `mask`: every observation the env returned, in order (the reset observation, one per
  step, and the observation of each reset after a finished episode), with `env.action_masks()`
  read right after it
- `kind`: per row of `obs`, 0 for a reset and 1 for a step
- `action`, `reward`, `terminated`, `truncated`: per step
- `episode`: per step, `info["episode"]` as sorted JSON at a terminal step, else ""

`tests/test_env_trace.py` replays the same plan with `run_trace` and compares.
"""

import json
from pathlib import Path

import numpy as np

from quack_rl.bots.presets import PRESET_BOTS
from quack_rl.rl.planner import make_rollout_bot
from quack_rl.rl.single_env import QuackEnv
from quack_rl.rules import load_ruleset

HERE = Path(__file__).parent
RULES = "v2.3"
OPPONENTS: tuple[str, ...] = (*PRESET_BOTS, "bot:random")
SEEDS = range(5)
STEPS = 300


def trace_path(opponent: str, seed: int) -> Path:
    return HERE / f"{opponent.removeprefix('bot:')}_seed{seed}.npz"


def run_trace(opponent: str, seed: int, steps: int = STEPS) -> dict[str, np.ndarray]:
    """Play the trace plan for one (opponent, seed) run and return its arrays."""
    rs = load_ruleset(RULES)
    env = QuackEnv(seat="random", opponent=make_rollout_bot(rs, opponent, seed), rules=rs)
    rng = np.random.default_rng(seed)
    obs_rows: list[np.ndarray] = []
    mask_rows: list[np.ndarray] = []
    kinds: list[int] = []
    actions: list[int] = []
    rewards: list[float] = []
    terminated: list[bool] = []
    truncated: list[bool] = []
    episodes: list[str] = []

    def record(obs: np.ndarray, kind: int) -> None:
        obs_rows.append(obs)
        mask_rows.append(env.action_masks())
        kinds.append(kind)

    obs, _ = env.reset(seed=seed)
    record(obs, 0)
    for _ in range(steps):
        action = int(rng.choice(np.flatnonzero(env.action_masks())))
        obs, rew, term, trunc, info = env.step(action)
        record(obs, 1)
        actions.append(action)
        rewards.append(rew)
        terminated.append(term)
        truncated.append(trunc)
        episodes.append(json.dumps(info["episode"], sort_keys=True) if term or trunc else "")
        if term or trunc:
            obs, _ = env.reset()
            record(obs, 0)
    return {
        "obs": np.stack(obs_rows),
        "mask": np.stack(mask_rows),
        "kind": np.array(kinds, dtype=np.int8),
        "action": np.array(actions, dtype=np.int64),
        "reward": np.array(rewards, dtype=np.float64),
        "terminated": np.array(terminated, dtype=bool),
        "truncated": np.array(truncated, dtype=bool),
        "episode": np.array(episodes, dtype=str),
    }


def main() -> None:
    for opponent in OPPONENTS:
        for seed in SEEDS:
            path = trace_path(opponent, seed)
            np.savez_compressed(path, **run_trace(opponent, seed))
            print(f"{path.name}: {path.stat().st_size / 1000:.1f} KB")


if __name__ == "__main__":
    main()
