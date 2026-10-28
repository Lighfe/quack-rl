"""Offline RL dataset: transitions of one bot playing `QuackEnv`, stored as arrays in one `.npz`.

One row is one decision of the agent seat, seen as the env shows it (same observation, action
index and reward; Wait-only steps are skipped and their reward is summed into the decision before
them). At the last row of each game `terminated` is true, `next_mask` is all zero and the reward
is the result of the game; all earlier rewards are 0. No torch here.

Game i uses the chance seed `seed + i` and the agent at p1 for even i and p2 for odd i, with the
bots built per game from their names with `seed + i` (the scheme of `evaluate`).
"""

import zipfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from quack_rl.engine import action_names, legal_actions
from quack_rl.rl.opponents import make_opponent
from quack_rl.rl.single_env import QuackEnv

ARRAYS = ("obs", "action", "reward", "next_obs", "terminated", "mask", "next_mask", "episode")


@dataclass
class Dataset:
    obs: np.ndarray  # (n, obs_dim) float32
    action: np.ndarray  # (n,) int64, index of the action taken
    reward: np.ndarray  # (n,) float32
    next_obs: np.ndarray  # (n, obs_dim) float32
    terminated: np.ndarray  # (n,) bool, true on the last row of each game
    mask: np.ndarray  # (n, n_actions) int8, legal actions of `obs`
    next_mask: np.ndarray  # (n, n_actions) int8, all zero where `terminated`
    episode: np.ndarray  # (n,) int32, game number, counted from 0 in a file

    def __len__(self) -> int:
        return len(self.action)

    def save(self, path: Path | str) -> None:
        """Write all arrays to one `.npz` file (the parent folder is made)."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as handle:
            np.savez(handle, **{name: getattr(self, name) for name in ARRAYS})

    @classmethod
    def load(cls, path: Path | str) -> "Dataset":
        """Read a file written by `save`. Raise FileNotFoundError, or ValueError on a bad file."""
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"dataset {path} does not exist")
        with np.load(path) as data:
            missing = [name for name in ARRAYS if name not in data.files]
            if missing:
                raise ValueError(f"dataset {path} has no array {missing[0]!r}")
            return cls(**{name: data[name] for name in ARRAYS})

    def concat(self, other: "Dataset") -> "Dataset":
        """The rows of `self` followed by those of `other` (its game numbers are shifted)."""
        shift = int(self.episode.max()) + 1 if len(self) else 0
        parts = {
            name: np.concatenate([getattr(self, name), getattr(other, name)]) for name in ARRAYS
        }
        parts["episode"] = np.concatenate([self.episode, other.episode + shift])
        return Dataset(**parts)

    def stats(self) -> dict[str, Any]:
        """Games, steps, the action histogram (one count per action index) and the mean return
        (the mean over games of the sum of rewards)."""
        n_actions = self.mask.shape[1]
        games = len(np.unique(self.episode))
        returns = np.bincount(self.episode, weights=self.reward) if len(self) else np.zeros(0)
        returns = returns[np.bincount(self.episode) > 0] if len(self) else returns
        return {
            "games": games,
            "steps": len(self),
            "action_histogram": np.bincount(self.action, minlength=n_actions).tolist(),
            "mean_return": float(returns.mean()) if games else 0.0,
        }


def concat_files(paths: Sequence[Path | str], out: Path | str) -> None:
    """Join dataset files into the file `out`, one array at a time, so that the peak memory is
    about twice the largest joined array and not twice the whole dataset. Same result as `load`,
    `concat` and `save`. Raise ValueError on an empty list or a file without all arrays."""
    if not paths:
        raise ValueError("no dataset file to join")
    files = [np.load(Path(p)) for p in paths]
    try:
        for path, data in zip(paths, files, strict=True):
            missing = [name for name in ARRAYS if name not in data.files]
            if missing:
                raise ValueError(f"dataset {path} has no array {missing[0]!r}")
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED, allowZip64=True) as zf:
            for name in ARRAYS:
                parts = [data[name] for data in files]
                if name == "episode":
                    shifts = np.cumsum([0] + [int(p.max()) + 1 if len(p) else 0 for p in parts])
                    parts = [p + shift for p, shift in zip(parts, shifts, strict=False)]
                joined = np.concatenate(parts)
                del parts
                with zf.open(f"{name}.npy", "w", force_zip64=True) as member:
                    np.lib.format.write_array(member, joined, allow_pickle=False)
                del joined
    finally:
        for data in files:
            data.close()


def build_dataset(
    agent: str,
    opponent: str,
    games: int,
    seed: int = 0,
    rules: str = "v2.3",
    on_progress: Callable[[int], None] | None = None,
) -> Dataset:
    """Play `games` games of the bot `agent` against the bot `opponent` (names) and store the
    agent's transitions. Raise ValueError on `games` < 1 or an unknown bot name."""
    if games < 1:
        raise ValueError(f"games must be at least 1, not {games}")
    names = action_names(QuackEnv(rules=rules).rs)
    # One chunk per game keeps the memory low: `obs` of a game plus its last `next_obs`; the
    # `next_obs` column is the `obs` column shifted by one row inside a game.
    chunks: list[dict[str, np.ndarray]] = []
    for i in range(games):
        bot = make_opponent(agent, seed + i, rules)
        env = QuackEnv(
            seat="p1" if i % 2 == 0 else "p2",
            opponent=make_opponent(opponent, seed + i, rules),
            rules=rules,
        )
        obs, _ = env.reset(seed=seed + i)
        mask = env.action_masks()
        rows: dict[str, list] = {"obs": [], "action": [], "reward": [], "mask": [], "next_mask": []}
        done = False
        while not done:
            legal = legal_actions(env.state, env.rs, env.agent_seat)
            action = names.index(bot.choose(env.state, env.agent_seat, legal))
            next_obs, reward, done, _, info = env.step(action)
            if info["illegal_action"]:
                raise ValueError(f"the bot chose {names[action]!r}, which is not legal")
            for name, value in zip(
                rows, (obs, action, reward, mask, info["action_mask"]), strict=True
            ):
                rows[name].append(value)
            obs, mask = next_obs, info["action_mask"]
        chunks.append(
            {
                "obs": np.asarray(rows["obs"], dtype=np.float32),
                "last_obs": np.asarray(obs, dtype=np.float32),
                "action": np.asarray(rows["action"], dtype=np.int64),
                "reward": np.asarray(rows["reward"], dtype=np.float32),
                "mask": np.asarray(rows["mask"], dtype=np.int8),
                "next_mask": np.asarray(rows["next_mask"], dtype=np.int8),
            }
        )
        if on_progress is not None:
            on_progress(i + 1)
    n = sum(len(c["action"]) for c in chunks)
    obs_dim, n_actions = chunks[0]["obs"].shape[1], chunks[0]["mask"].shape[1]
    data = Dataset(
        obs=np.empty((n, obs_dim), np.float32),
        action=np.empty(n, np.int64),
        reward=np.empty(n, np.float32),
        next_obs=np.empty((n, obs_dim), np.float32),
        terminated=np.zeros(n, dtype=bool),
        mask=np.empty((n, n_actions), np.int8),
        next_mask=np.empty((n, n_actions), np.int8),
        episode=np.empty(n, np.int32),
    )
    pos = 0
    for i in range(games):
        chunk = chunks[i]
        chunks[i] = {}  # free the chunk as soon as it is copied
        k = len(chunk["action"])
        sl = slice(pos, pos + k)
        data.obs[sl] = chunk["obs"]
        data.next_obs[pos : pos + k - 1] = chunk["obs"][1:]
        data.next_obs[pos + k - 1] = chunk["last_obs"]
        data.action[sl] = chunk["action"]
        data.reward[sl] = chunk["reward"]
        data.mask[sl] = chunk["mask"]
        data.next_mask[sl] = chunk["next_mask"]
        data.terminated[pos + k - 1] = True
        data.episode[sl] = i
        pos += k
    return data
