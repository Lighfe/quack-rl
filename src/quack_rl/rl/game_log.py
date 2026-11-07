"""Training games stored as chance seed and actions, and the offline dataset rebuilt from them.

A `games.jsonl` file has one JSON line per finished game:
`{"step": int, "chance_seed": int, "agent_seat": "p1" | "p2", "opponent": spec,
"actions": [[p1_action, p2_action], ...]}`, the joint actions (action indices) of every
parallel-env step of the game (`QuackEnv.chance_seed` and `QuackEnv.joint_actions`). The engine
is deterministic for a chance seed, so the line fixes the game: `rebuild_dataset` replays it and
gives the rows that `QuackEnv` showed the agent seat, in the form of `build_dataset`.
"""

import json
from pathlib import Path

import numpy as np

from quack_rl.engine import SEATS, Phase
from quack_rl.rl.dataset import Dataset
from quack_rl.rl.parallel_env import QuackParallelEnv
from quack_rl.rl.reward import REWARDS


def _replay(env: QuackParallelEnv, line: dict, number: int) -> dict[str, np.ndarray]:
    """The agent seat's rows of one game line (`number` counted from 1, for the errors)."""
    seat = line["agent_seat"]
    if seat not in SEATS:
        raise ValueError(f"line {number}: agent_seat must be 'p1' or 'p2', not {seat!r}")
    actions = line["actions"]
    env.reset(seed=int(line["chance_seed"]))
    pos = 0

    def wait_only(mask: np.ndarray) -> bool:
        return bool(mask[env._wait]) and int(mask.sum()) == 1

    def play() -> tuple[float, bool]:
        """One parallel-env step with the next joint action of the line."""
        nonlocal pos
        if pos >= len(actions):
            raise ValueError(f"line {number}: the actions end before the game is over")
        joint = {s: int(a) for s, a in zip(SEATS, actions[pos], strict=True)}
        obs = env._obs()
        for s, a in joint.items():
            if not (0 <= a < len(env._names)) or not obs[s]["action_mask"][a]:
                raise ValueError(f"line {number}: action {a} of {s} at step {pos + 1} is not legal")
        pos += 1
        _, rewards, terms, _, _ = env.step(joint)
        return rewards[seat], terms[seat]

    def view() -> tuple[np.ndarray, np.ndarray]:
        obs = env._obs()[seat]
        mask = obs["action_mask"]
        if env.state.phase is Phase.GAME_OVER:
            mask = np.zeros_like(mask)
        return obs["observation"], mask

    rows: dict[str, list] = {"obs": [], "action": [], "reward": [], "mask": [], "next_mask": []}
    done = False
    while not done and wait_only(env._obs()[seat]["action_mask"]):  # as `QuackEnv.reset`
        _, done = play()
    obs, mask = view()
    while not done:
        action = int(actions[pos][SEATS.index(seat)]) if pos < len(actions) else None
        total, done = play()
        while not done and wait_only(env._obs()[seat]["action_mask"]):
            reward, done = play()
            total += reward
        next_obs, next_mask = view()
        for name, value in zip(rows, (obs, action, total, mask, next_mask), strict=True):
            rows[name].append(value)
        obs, mask = next_obs, next_mask
    if pos < len(actions):
        raise ValueError(
            f"line {number}: {len(actions) - pos} actions are left after the game is over"
        )
    return {
        "obs": np.asarray(rows["obs"], dtype=np.float32).reshape(-1, env._obs_len),
        "last_obs": np.asarray(obs, dtype=np.float32),
        "action": np.asarray(rows["action"], dtype=np.int64),
        "reward": np.asarray(rows["reward"], dtype=np.float32),
        "mask": np.asarray(rows["mask"], dtype=np.int8).reshape(-1, len(env._names)),
        "next_mask": np.asarray(rows["next_mask"], dtype=np.int8).reshape(-1, len(env._names)),
    }


def rebuild_dataset(games_file: Path, rules: str = "v2.3", reward: str = "win_loss") -> Dataset:
    """Replay each line of `games_file` with the engine and its chance seed, and return the agent
    seat's transitions; the n-th line (counted from 1) is `episode` n-1. `reward` is a key of
    `REWARDS`. Raise ValueError on an unknown reward, and naming the line number for an action
    that is not legal at its step, actions that end before the game is over, or actions left
    after it."""
    if reward not in REWARDS:
        raise ValueError(f"unknown reward {reward!r}: known are {sorted(REWARDS)}")
    env = QuackParallelEnv(rules=rules, reward_fn=REWARDS[reward])
    obs_dim, n_actions = env._obs_len, len(env._names)
    parts: dict[str, list[np.ndarray]] = {
        name: []
        for name in ("obs", "action", "reward", "next_obs", "terminated", "mask", "next_mask")
    }
    parts["episode"] = []
    with Path(games_file).open(encoding="utf-8") as handle:
        for number, text in enumerate(handle, start=1):
            chunk = _replay(env, json.loads(text), number)
            k = len(chunk["action"])
            terminated = np.zeros(k, dtype=bool)
            if k:
                terminated[-1] = True
            next_obs = np.concatenate([chunk["obs"][1:], chunk["last_obs"][None]])[:k]
            for name, value in (
                ("obs", chunk["obs"]),
                ("action", chunk["action"]),
                ("reward", chunk["reward"]),
                ("next_obs", next_obs),
                ("terminated", terminated),
                ("mask", chunk["mask"]),
                ("next_mask", chunk["next_mask"]),
                ("episode", np.full(k, number - 1, dtype=np.int32)),
            ):
                parts[name].append(value)
    empty = {
        "obs": np.empty((0, obs_dim), np.float32),
        "action": np.empty(0, np.int64),
        "reward": np.empty(0, np.float32),
        "next_obs": np.empty((0, obs_dim), np.float32),
        "terminated": np.empty(0, bool),
        "mask": np.empty((0, n_actions), np.int8),
        "next_mask": np.empty((0, n_actions), np.int8),
        "episode": np.empty(0, np.int32),
    }
    return Dataset(
        **{
            name: np.concatenate([empty[name], *chunks]).astype(empty[name].dtype)
            for name, chunks in parts.items()
        }
    )
