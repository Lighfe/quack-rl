"""Offline training: masked behaviour cloning on the Parquet dataset of `quack_rl.rl.dataset`.

The policy network of a `MaskablePPO` object (built from the observation size and the action
count, no environment) is trained with the cross-entropy of the recorded action over the logits
of the legal actions (`logits.masked_fill(mask == 0, -1e9)`). The model is saved as `model.zip`,
so `load_model` and `PolicyBot.from_run` need no change. No game is played here.

torch and sb3-contrib are imported inside the functions (the `train` group).
"""

import csv
import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from quack_rl.rl.encode import check_policy_layout, vector_names
from quack_rl.rl.runs import full_config, run_path
from quack_rl.rules import load_ruleset

N_ACTIONS = 15
METHOD = "behaviour cloning, masked cross-entropy"
METRIC_COLUMNS = ("step", "loss", "accuracy")
MASK_FILL = -1e9


@dataclass
class OfflineData:
    obs: np.ndarray  # (n, obs_dim) float32
    mask: np.ndarray  # (n, 15) int8
    action: np.ndarray  # (n,) int64

    def __len__(self) -> int:
        return len(self.action)


def load_offline_data(path: Path | str, obs_dim: int, n_actions: int = N_ACTIONS) -> OfflineData:
    """Read `obs`, `action_mask` and `action` by row group into preallocated arrays.

    Memory is one float32 array of n x obs_dim plus small ones: no list of lists, no copy.
    Raise FileNotFoundError for a missing file and ValueError for a bad `obs` length."""
    import pyarrow.parquet as pq

    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"dataset {path} does not exist")
    try:
        pf = pq.ParquetFile(path)
    except Exception as err:
        raise ValueError(f"dataset {path} is not a readable Parquet file: {err}") from err
    names = set(pf.schema_arrow.names)
    for col in ("obs", "action_mask", "action"):
        if col not in names:
            raise ValueError(f"dataset {path} has no column {col!r}")
    n = pf.metadata.num_rows
    obs = np.empty((n, obs_dim), np.float32)
    mask = np.empty((n, n_actions), np.int8)
    action = np.empty(n, np.int64)
    pos = 0
    for g in range(pf.num_row_groups):
        t = pf.read_row_group(g, columns=["obs", "action_mask", "action"])
        k = t.num_rows
        for name, width, out in (("obs", obs_dim, obs), ("action_mask", n_actions, mask)):
            col = t[name].combine_chunks()
            lengths = col.value_lengths().to_numpy(zero_copy_only=False)
            if k and (lengths != width).any():
                bad = int(lengths[lengths != width][0])
                raise ValueError(
                    f"dataset {path}: column {name!r} has length {bad}, expected {width}"
                )
            out[pos : pos + k] = col.flatten().to_numpy(zero_copy_only=False).reshape(k, width)
        action[pos : pos + k] = t["action"].to_numpy()
        pos += k
    return OfflineData(obs, mask, action)


def build_model(obs_dim: int, seed: int, hidden: int = 256, n_actions: int = N_ACTIONS) -> Any:
    """A `MaskablePPO` with an MLP policy (two layers of `hidden` units), made without an env."""
    import gymnasium as gym
    from sb3_contrib import MaskablePPO

    obs_space = gym.spaces.Box(-np.inf, np.inf, (obs_dim,), np.float32)
    act_space = gym.spaces.Discrete(n_actions)
    # No environment: SB3 only needs the two spaces to build the network, so set them by hand.
    model = MaskablePPO(
        "MlpPolicy",
        None,
        policy_kwargs={"net_arch": [hidden, hidden]},
        seed=seed,
        device="cpu",
        verbose=0,
        _init_setup_model=False,
    )
    model.observation_space = obs_space
    model.action_space = act_space
    model.n_envs = 1
    model._setup_model()
    return model


def masked_logits(model: Any, obs, mask):
    """Logits of the policy network of `model` with illegal actions set to -1e9."""
    policy = model.policy
    latent = policy.mlp_extractor.forward_actor(policy.extract_features(obs))
    return policy.action_net(latent).masked_fill(mask == 0, MASK_FILL)


def bc_loss(model: Any, obs, mask, action):
    import torch.nn.functional as F

    logits = masked_logits(model, obs, mask)
    return F.cross_entropy(logits, action), logits


def train_bc(
    data: OfflineData,
    seed: int,
    steps: int,
    batch_size: int = 256,
    lr: float = 1e-3,
    hidden: int = 256,
    log_every: int = 100,
) -> tuple[Any, list[dict]]:
    """Train for `steps` gradient steps of `batch_size` rows drawn at random.

    Return (model, rows): the model and the metrics rows (`step`, `loss`, `accuracy`: the means
    over each `log_every` steps). The same data, seed and arguments give the same weights."""
    import torch

    if steps < 1:
        raise ValueError(f"steps must be at least 1, not {steps}")
    if len(data) < 1:
        raise ValueError("the dataset has no rows")
    model = build_model(data.obs.shape[1], seed, hidden)
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    obs_t = torch.from_numpy(data.obs)  # shares memory with the array
    mask_t = torch.from_numpy(data.mask)
    action_t = torch.from_numpy(data.action)
    params = list(model.policy.mlp_extractor.policy_net.parameters()) + list(
        model.policy.action_net.parameters()
    )
    opt = torch.optim.Adam(params, lr=lr)
    model.policy.train()
    rows, losses, hits = [], [], []
    for step in range(1, steps + 1):
        idx = torch.from_numpy(rng.integers(len(data), size=batch_size))
        loss, logits = bc_loss(model, obs_t[idx], mask_t[idx], action_t[idx])
        opt.zero_grad()
        loss.backward()
        opt.step()
        losses.append(loss.item())
        hits.append(float((logits.argmax(1) == action_t[idx]).float().mean()))
        if step % log_every == 0 or step == steps:
            rows.append(
                {"step": step, "loss": float(np.mean(losses)), "accuracy": float(np.mean(hits))}
            )
            losses, hits = [], []
    model.policy.eval()
    return model, rows


def _write_run(path: Path, config: dict, model: Any, rows: list[dict]) -> None:
    (path / "config.json").write_text(json.dumps(full_config(config), indent=2) + "\n")
    with (path / "metrics.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, METRIC_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    model.save(str(path / "model.zip"))


def train_offline_run(
    dataset: Path | str,
    run: str,
    runs_dir: Path | str = "data/runs",
    seed: int = 0,
    steps: int = 20_000,
    rules: str = "v1.10",
    batch_size: int = 256,
    lr: float = 1e-3,
    hidden: int = 256,
    log_every: int = 100,
) -> dict:
    """Train on `dataset` and write the run folder `<runs_dir>/<run>`; return its config.

    Every check runs before the training; the folder is built under a temporary name and
    renamed at the end, so an error leaves no run folder. Raise FileNotFoundError (no dataset),
    FileExistsError (run folder exists), ValueError (bad steps, bad run name, bad `obs`)."""
    check_policy_layout(load_ruleset(rules))  # layout 4 (v1.9): refused
    if steps < 1:
        raise ValueError(f"steps must be at least 1, not {steps}")
    path = run_path(Path(runs_dir), run)
    if path.exists():
        raise FileExistsError(f"run folder {path} already exists; pick another run name")
    dataset = Path(dataset)
    obs_dim = len(vector_names(load_ruleset(rules)))
    t0 = time.perf_counter()
    data = load_offline_data(dataset, obs_dim)
    t_load = time.perf_counter() - t0
    t0 = time.perf_counter()
    model, rows = train_bc(data, seed, steps, batch_size, lr, hidden, log_every)
    t_train = time.perf_counter() - t0
    config = {
        "method": METHOD,
        "rules": rules,
        "seed": seed,
        "steps": steps,
        "batch_size": batch_size,
        "learning_rate": lr,
        "hidden": hidden,
        "dataset": str(dataset),
        "dataset_rows": len(data),
        "seconds_load": round(t_load, 1),
        "seconds_train": round(t_train, 1),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    try:
        _write_run(tmp, config, model, rows)
        tmp.rename(path)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return config
