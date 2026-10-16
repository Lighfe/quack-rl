"""A small DQN with a replay buffer that starts with the offline dataset (issue #95).

`transitions_from_dataset` turns the Parquet dataset of `quack_rl.rl.dataset` into transitions
(state, action, reward, next state, done). `ReplayBuffer` keeps an offline part (filled once,
never overwritten) and an online part (a ring). `train_dqn` first learns from the offline part
only, then plays `QuackEnv` games, adds each step to the online part and learns from the whole
buffer. Illegal actions are masked everywhere: the greedy choice and the maximum over the next
state's Q-values only see legal actions. No conservative penalty is used, so plain Q-learning on
bot data can overrate actions the bots never took.

torch is imported inside `train_dqn` (the `train` group).
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

from quack_rl.rl.encode import vector_names
from quack_rl.rl.offline import MASK_FILL, N_ACTIONS, load_offline_data
from quack_rl.rl.opponents import make_opponent
from quack_rl.rl.single_env import QuackEnv
from quack_rl.rules import load_ruleset

FIELDS = ("obs", "mask", "action", "reward", "next_obs", "next_mask", "done")
GAMMA = 0.99
BATCH_SIZE = 64
HIDDEN = 256
LEARNING_RATE = 5e-4
TARGET_EVERY = 100  # gradient steps between two copies of the Q-network to the target network
EPSILON_START = 0.3
EPSILON_END = 0.05
LOSS_COLUMNS = ("step", "phase", "loss", "offline_count", "online_count")

Transitions = dict[str, np.ndarray]


def transitions_from_dataset(path: Path | str, obs_dim: int) -> Transitions:
    """Read the dataset as transitions, rows ordered by (`episode`, `step`).

    For a row that is not the last of its episode the next values are those of the next row. For
    the last row `done` is true and `next_obs` and `next_mask` are zeros. Raise
    FileNotFoundError for a missing file and ValueError for a bad layout or `obs` length."""
    import pyarrow.parquet as pq

    data = load_offline_data(path, obs_dim)
    names = set(pq.ParquetFile(path).schema_arrow.names)
    for col in ("episode", "step", "reward", "terminal"):
        if col not in names:
            raise ValueError(f"dataset {path} has no column {col!r}")
    t = pq.read_table(path, columns=["episode", "step", "reward", "terminal"])
    episode = t["episode"].to_numpy()
    step = t["step"].to_numpy()
    reward = t["reward"].to_numpy().astype(np.float32)
    terminal = t["terminal"].to_numpy(zero_copy_only=False).astype(bool)
    obs, mask, action = data.obs, data.mask, data.action
    order = np.lexsort((step, episode))
    if (order != np.arange(len(order))).any():
        obs, mask, action = obs[order], mask[order], action[order]
        episode, reward, terminal = episode[order], reward[order], terminal[order]
    n = len(action)
    last = np.ones(n, bool)  # the last row of each episode is the last one in its run of rows
    last[:-1] = episode[1:] != episode[:-1]
    done = last | terminal
    next_obs = np.zeros_like(obs)
    next_mask = np.zeros_like(mask)
    if n > 1:
        next_obs[:-1] = obs[1:]
        next_mask[:-1] = mask[1:]
    next_obs[done] = 0.0
    next_mask[done] = 0
    return {
        "obs": obs, "mask": mask, "action": action, "reward": reward,
        "next_obs": next_obs, "next_mask": next_mask, "done": done,
    }  # fmt: skip


class ReplayBuffer:
    """Seven fields per transition, an offline part and an online part.

    The offline part is filled once at construction and never overwritten. The online part is a
    ring of `online_capacity` transitions: `add` overwrites the oldest one when it is full."""

    def __init__(
        self,
        obs_dim: int,
        online_capacity: int,
        offline: Transitions | None = None,
        n_actions: int = N_ACTIONS,
    ):
        if online_capacity < 1:
            raise ValueError(f"online_capacity must be at least 1, not {online_capacity}")
        self.online_capacity = online_capacity
        n_off = 0 if offline is None else len(offline["action"])
        # the offline arrays are kept as they are (no copy): the dataset can be large
        self._off = offline
        self._on: dict[str, np.ndarray] = {
            "obs": np.zeros((online_capacity, obs_dim), np.float32),
            "mask": np.zeros((online_capacity, n_actions), np.int8),
            "action": np.zeros(online_capacity, np.int64),
            "reward": np.zeros(online_capacity, np.float32),
            "next_obs": np.zeros((online_capacity, obs_dim), np.float32),
            "next_mask": np.zeros((online_capacity, n_actions), np.int8),
            "done": np.zeros(online_capacity, bool),
        }
        self.n_offline = n_off
        self.n_online = 0
        self._next = 0  # ring position inside the online part

    def __len__(self) -> int:
        return self.n_offline + self.n_online

    def add(self, obs, mask, action, reward, next_obs, next_mask, done) -> None:
        """Add one online transition."""
        values = (obs, mask, action, reward, next_obs, next_mask, done)
        for name, value in zip(FIELDS, values, strict=True):
            self._on[name][self._next] = value
        self._next = (self._next + 1) % self.online_capacity
        self.n_online = min(self.n_online + 1, self.online_capacity)

    def sample(
        self, batch_size: int, rng: np.random.Generator, offline_only: bool = False
    ) -> Transitions:
        """`batch_size` stored transitions drawn at random (with replacement).

        `offline_only` draws from the offline part only. Raise ValueError when that part (or,
        without the flag, the whole buffer) is empty."""
        if offline_only:
            if self.n_offline == 0:
                raise ValueError("the offline part of the buffer is empty")
            idx = rng.integers(self.n_offline, size=batch_size)
        else:
            if len(self) == 0:
                raise ValueError("the buffer is empty")
            idx = rng.integers(len(self), size=batch_size)
        from_off = idx < self.n_offline
        batch = {}
        for name in FIELDS:
            out = np.empty((batch_size, *self._on[name].shape[1:]), self._on[name].dtype)
            if from_off.any():
                assert self._off is not None
                out[from_off] = self._off[name][idx[from_off]]
            if not from_off.all():
                out[~from_off] = self._on[name][idx[~from_off] - self.n_offline]
            batch[name] = out
        return batch


def masked_q(q, mask):
    """Q-values with illegal actions set to -1e9 (`q` and `mask` are torch tensors)."""
    return q.masked_fill(mask == 0, MASK_FILL)


def td_target(next_q, reward, done, next_mask, gamma: float = GAMMA):
    """`reward + gamma * max over legal next actions of next_q`, with no bootstrap when done.

    All arguments are torch tensors of one batch; `next_q` is (batch, actions). An illegal
    action never counts, whatever its Q-value; a state without a legal action counts as 0."""
    import torch

    legal_any = next_mask.sum(1) > 0
    best = masked_q(next_q, next_mask).max(1).values
    best = torch.where(legal_any & ~done.bool(), best, torch.zeros_like(best))
    return reward + gamma * best


def greedy_action(q_values, mask) -> int:
    """The legal action with the highest Q-value (numpy arrays or lists of one state)."""
    q = np.where(np.asarray(mask) != 0, np.asarray(q_values, np.float64), -np.inf)
    return int(np.argmax(q))


def _q_network(obs_dim: int, n_actions: int = N_ACTIONS, hidden: int = HIDDEN):
    from torch import nn

    return nn.Sequential(
        nn.Linear(obs_dim, hidden), nn.Tanh(),
        nn.Linear(hidden, hidden), nn.Tanh(),
        nn.Linear(hidden, n_actions),
    )  # fmt: skip


def make_policy(q_net) -> Callable[[np.ndarray, np.ndarray], int]:
    """`policy(obs, mask) -> int`: the legal action with the highest Q of `q_net`."""
    import torch

    def policy(obs: np.ndarray, mask: np.ndarray) -> int:
        with torch.no_grad():
            q = q_net(torch.as_tensor(np.asarray(obs, np.float32)).unsqueeze(0))[0]
        return greedy_action(q.numpy(), mask)

    return policy


def train_dqn(
    dataset_path: Path | str,
    opponent: str,
    offline_steps: int,
    online_steps: int,
    seed: int = 0,
    rules: str = "v1.1",
    online_capacity: int | None = None,
    after_offline: Callable[[Callable[[np.ndarray, np.ndarray], int]], Any] | None = None,
) -> tuple[Any, list[dict], Callable[[np.ndarray, np.ndarray], int]]:
    """Phase 1: `offline_steps` gradient steps on batches from the offline part only.
    Phase 2: `online_steps` environment steps against `opponent` (the agent's seat is random),
    epsilon-greedy over the legal actions; each step adds one transition to the online part and
    takes one gradient step on a batch from the whole buffer.

    Return (q_net, rows, policy). `rows` has one dict per gradient step with `step`, `phase`
    (`offline` or `online`), `loss`, `offline_count`, `online_count`. `after_offline`, when
    given, is called with the policy at the end of phase 1 (before the online games).
    `online_capacity` defaults to `online_steps` (nothing is overwritten). Raise ValueError for
    negative steps, an empty dataset, a bad `obs` length or an unknown opponent, all before
    training."""
    import torch
    import torch.nn.functional as F

    if offline_steps < 0 or online_steps < 0:
        raise ValueError("offline_steps and online_steps must not be negative")
    make_opponent(opponent, seed=seed, rules=rules)  # ValueError on an unknown name
    obs_dim = len(vector_names(load_ruleset(rules)))
    offline = transitions_from_dataset(dataset_path, obs_dim)
    if len(offline["action"]) == 0:
        raise ValueError("the dataset has no rows")
    capacity = max(1, online_capacity if online_capacity is not None else online_steps)
    buffer = ReplayBuffer(obs_dim, capacity, offline)
    del offline

    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    q_net = _q_network(obs_dim)
    target_net = _q_network(obs_dim)
    target_net.load_state_dict(q_net.state_dict())
    opt = torch.optim.Adam(q_net.parameters(), lr=LEARNING_RATE)
    policy = make_policy(q_net)
    rows: list[dict] = []

    def gradient_step(phase: str, offline_only: bool) -> None:
        batch = {
            k: torch.from_numpy(v) for k, v in buffer.sample(BATCH_SIZE, rng, offline_only).items()
        }
        with torch.no_grad():
            target = td_target(
                target_net(batch["next_obs"]), batch["reward"], batch["done"], batch["next_mask"]
            )
        q = q_net(batch["obs"]).gather(1, batch["action"].unsqueeze(1)).squeeze(1)
        loss = F.smooth_l1_loss(q, target)
        opt.zero_grad()
        loss.backward()
        opt.step()
        n = len(rows) + 1
        if n % TARGET_EVERY == 0:
            target_net.load_state_dict(q_net.state_dict())
        rows.append(
            {
                "step": n,
                "phase": phase,
                "loss": float(loss.item()),
                "offline_count": buffer.n_offline,
                "online_count": buffer.n_online,
            }
        )

    for _ in range(offline_steps):
        gradient_step("offline", True)
    if after_offline is not None:
        after_offline(policy)

    if online_steps:
        env = QuackEnv(seat="random", rules=rules)
        game = 0

        def new_game():
            env.opponent = make_opponent(opponent, seed + game, rules)
            env._default_opponent = False
            return env.reset(seed=seed + game)

        obs, info = new_game()
        for i in range(online_steps):
            mask = info["action_mask"]
            eps = EPSILON_START + (EPSILON_END - EPSILON_START) * i / max(1, online_steps - 1)
            if rng.random() < eps:
                action = int(rng.choice(np.flatnonzero(mask)))
            else:
                action = policy(obs, mask)
            next_obs, reward, done, _, info = env.step(action)
            next_mask = info["action_mask"]
            if done:
                next_obs, next_mask = np.zeros_like(next_obs), np.zeros_like(next_mask)
            buffer.add(obs, mask, action, reward, next_obs, next_mask, done)
            gradient_step("online", False)
            if done:
                game += 1
                obs, info = new_game()
            else:
                obs = next_obs
    return q_net, rows, policy
