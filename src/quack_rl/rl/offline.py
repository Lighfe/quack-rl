"""Offline training on a `Dataset`: behaviour cloning (BC) and discrete CQL. torch is imported
only here.

Both train a small masked MLP on the CPU and return an `OfflinePolicy`: a seat for `evaluate`
(`choose(state, seat, legal)`, always legal, deterministic) with the loss curve in `curve`.
Nothing here prints or exits: progress goes through `on_progress`.
"""

import csv
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn.functional as F
from torch import nn

from quack_rl.bots.presets import PRESET_BOTS
from quack_rl.engine import GameState, action_names
from quack_rl.rl.dataset import Dataset
from quack_rl.rl.encode import action_mask, observe, vectorize
from quack_rl.rl.evaluate import EvalResult, evaluate
from quack_rl.rl.train import library_versions
from quack_rl.rules import Ruleset, load_ruleset

MASK_FILL = -1e9
RANDOM_OPPONENT = "bot:random"


def make_mlp(obs_dim: int, n_actions: int, hidden: int = 256) -> nn.Module:
    """Two hidden layers; the output is one number per action (logit for BC, Q value for CQL)."""
    return nn.Sequential(
        nn.Linear(obs_dim, hidden),
        nn.ReLU(),
        nn.Linear(hidden, hidden),
        nn.ReLU(),
        nn.Linear(hidden, n_actions),
    )


def masked(scores: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    """`scores` with the illegal actions (mask 0) set to a very low value."""
    return scores.masked_fill(mask == 0, MASK_FILL)


class OfflinePolicy:
    """A trained network as a bot seat. Plays the legal action with the highest score."""

    kind = "bot"

    def __init__(
        self,
        net: nn.Module,
        rules: Ruleset | str = "v2.3",
        name: str = "offline",
        curve: list[float] | None = None,
    ):
        self.rs = load_ruleset(rules) if isinstance(rules, str) else rules
        self.net = net.eval()
        self.name = name
        self.params: dict[str, Any] = {"deterministic": True}
        self.curve: list[float] = curve if curve is not None else []
        self.entropy_curve: list[float] = []  # BC only: mean policy entropy of each epoch
        self._names = action_names(self.rs)

    def choose(self, state: GameState, seat: str, legal: list[str]) -> str:
        obs = vectorize(observe(state, self.rs, seat), self.rs)
        mask = np.asarray(action_mask(state, self.rs, seat), dtype=bool)
        allowed = set(legal)
        mask &= np.asarray([name in allowed for name in self._names], dtype=bool)
        if not mask.any():
            raise ValueError("no legal action to choose from")
        with torch.no_grad():
            scores = self.net(torch.from_numpy(np.asarray(obs, dtype=np.float32))[None])[0]
        scores = masked(scores, torch.from_numpy(mask))
        return self._names[int(scores.argmax())]


def _tensors(data: Dataset) -> dict[str, torch.Tensor]:
    if len(data) < 1:
        raise ValueError("the dataset has no rows")
    return {
        "obs": torch.from_numpy(data.obs),
        "action": torch.from_numpy(data.action),
        "reward": torch.from_numpy(data.reward),
        "next_obs": torch.from_numpy(data.next_obs),
        "terminated": torch.from_numpy(data.terminated.astype(np.float32)),
        "mask": torch.from_numpy(data.mask),
        "next_mask": torch.from_numpy(data.next_mask),
    }


def smoothed_target(action: torch.Tensor, mask: torch.Tensor, eps: float) -> torch.Tensor:
    """The label smoothing target, one row per sample: (1 - eps) on the stored action and eps
    spread evenly over the other legal actions; 0 on every illegal action. When the stored
    action is the only legal action, the row is 1 on it."""
    legal = (mask != 0).to(torch.float32)
    stored = F.one_hot(action, mask.shape[1]).to(torch.float32)
    others = legal - stored
    n_others = others.sum(1, keepdim=True)
    share = torch.where(n_others > 0, eps / n_others.clamp(min=1.0), torch.zeros_like(n_others))
    return stored * (1.0 - share * n_others) + others * share


def masked_entropy(logits: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    """The entropy (nats) of the softmax over the legal actions of each row of the masked
    `logits`. Illegal actions add 0, so a row with one legal action has entropy 0 (no NaN)."""
    log_p = F.log_softmax(logits, dim=1)
    terms = torch.where(mask != 0, log_p.exp() * log_p, torch.zeros_like(log_p))
    return -terms.sum(1)


def train_bc(
    dataset: Dataset,
    epochs: int,
    seed: int = 0,
    rules: str = "v2.3",
    batch_size: int = 256,
    lr: float = 1e-3,
    hidden: int = 256,
    on_progress: Callable[[int, float], None] | None = None,
    label_smoothing: float = 0.0,
    entropy_coef: float = 0.0,
    on_epoch_end: Callable[[int, nn.Module], None] | None = None,
) -> OfflinePolicy:
    """Behaviour cloning: cross entropy of the stored action over the logits of the legal
    actions.

    `label_smoothing` eps puts (1 - eps) of the target on the stored action and eps evenly on
    the other legal actions (`smoothed_target`). `entropy_coef` subtracts `entropy_coef` times
    the mean entropy of the policy over the legal actions (`masked_entropy`) from the loss.
    `curve` holds the mean minimized loss of each epoch, `entropy_curve` the mean entropy of
    each epoch. `on_epoch_end(epoch, net)` is called after each epoch (counted from 1). Raise
    ValueError on `label_smoothing` outside [0, 1) or a negative `entropy_coef`."""
    stats: list[float] = []

    def record(epoch: int, net: nn.Module, loss: float, entropy: float) -> None:
        stats.append(entropy)
        if on_progress is not None:
            on_progress(epoch, loss)
        if on_epoch_end is not None:
            on_epoch_end(epoch, net)

    net, curve = fit_bc(
        dataset, epochs, seed, batch_size, lr, hidden, label_smoothing, entropy_coef, record
    )
    policy = OfflinePolicy(net, rules, "bc", curve)
    policy.entropy_curve = stats
    return policy


def fit_bc(
    dataset: Dataset,
    epochs: int,
    seed: int = 0,
    batch_size: int = 256,
    lr: float = 1e-3,
    hidden: int = 256,
    label_smoothing: float = 0.0,
    entropy_coef: float = 0.0,
    on_epoch: Callable[[int, nn.Module, float, float], None] | None = None,
) -> tuple[nn.Module, list[float]]:
    """The training loop of `train_bc`; returns the network and the loss curve.
    `on_epoch(epoch, net, mean loss, mean entropy)` is called after each epoch."""
    if epochs < 1:
        raise ValueError(f"epochs must be at least 1, not {epochs}")
    if not 0.0 <= label_smoothing < 1.0:
        raise ValueError(f"label_smoothing must be in [0, 1), not {label_smoothing}")
    if entropy_coef < 0.0:
        raise ValueError(f"entropy_coef must not be negative, not {entropy_coef}")
    t = _tensors(dataset)
    torch.manual_seed(seed)
    gen = torch.Generator().manual_seed(seed)
    net = make_mlp(dataset.obs.shape[1], dataset.mask.shape[1], hidden)
    opt = torch.optim.Adam(net.parameters(), lr=lr)
    n = len(dataset)
    curve: list[float] = []
    for epoch in range(1, epochs + 1):
        order = torch.randperm(n, generator=gen)
        losses, entropies = [], []
        for start in range(0, n, batch_size):
            idx = order[start : start + batch_size]
            mask = t["mask"][idx]
            logits = masked(net(t["obs"][idx]), mask)
            if label_smoothing > 0.0:
                target = smoothed_target(t["action"][idx], mask, label_smoothing)
                loss = F.cross_entropy(logits, target)
            else:
                loss = F.cross_entropy(logits, t["action"][idx])
            entropy = masked_entropy(logits, mask).mean()
            if entropy_coef > 0.0:
                loss = loss - entropy_coef * entropy
            opt.zero_grad()
            loss.backward()
            opt.step()
            losses.append(loss.item())
            entropies.append(entropy.item())
        curve.append(float(np.mean(losses)))
        if on_epoch is not None:
            on_epoch(epoch, net, curve[-1], float(np.mean(entropies)))
    return net, curve


def train_cql(
    dataset: Dataset,
    steps: int,
    seed: int = 0,
    alpha: float = 1.0,
    rules: str = "v2.3",
    batch_size: int = 256,
    lr: float = 1e-3,
    hidden: int = 256,
    target_every: int = 100,
    on_progress: Callable[[int, float], None] | None = None,
) -> OfflinePolicy:
    """Discrete CQL, `gamma = 1`: loss = TD error + alpha * (logsumexp(Q masked) - Q(s, a)).

    The target is double-DQN style: the online net picks the next action among `next_mask`, a
    target net (copied every `target_every` steps) values it. At a terminated step there is no
    bootstrap (its `next_mask` is all zero, so a masked max would be meaningless). `curve` holds
    the loss of each step.
    """
    if steps < 1:
        raise ValueError(f"steps must be at least 1, not {steps}")
    t = _tensors(dataset)
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    n_actions = dataset.mask.shape[1]
    net = make_mlp(dataset.obs.shape[1], n_actions, hidden)
    target = make_mlp(dataset.obs.shape[1], n_actions, hidden)
    target.load_state_dict(net.state_dict())
    opt = torch.optim.Adam(net.parameters(), lr=lr)
    curve: list[float] = []
    for step in range(1, steps + 1):
        idx = torch.from_numpy(rng.integers(len(dataset), size=batch_size))
        q_all = masked(net(t["obs"][idx]), t["mask"][idx])
        q_sa = q_all.gather(1, t["action"][idx][:, None])[:, 0]
        with torch.no_grad():
            next_mask = t["next_mask"][idx]
            best = masked(net(t["next_obs"][idx]), next_mask).argmax(1, keepdim=True)
            next_q = target(t["next_obs"][idx]).gather(1, best)[:, 0]
            td_target = t["reward"][idx] + (1.0 - t["terminated"][idx]) * next_q
        td = F.mse_loss(q_sa, td_target)
        conservative = (torch.logsumexp(q_all, dim=1) - q_sa).mean()
        loss = td + alpha * conservative
        opt.zero_grad()
        loss.backward()
        opt.step()
        curve.append(loss.item())
        if step % target_every == 0:
            target.load_state_dict(net.state_dict())
        if on_progress is not None:
            on_progress(step, curve[-1])
    return OfflinePolicy(net, rules, "cql", curve)


@dataclass
class OfflineResult:
    out: Path
    train_seconds: float
    against_random: EvalResult
    against_presets: dict[str, EvalResult] = field(default_factory=dict)  # by spec
    curve: list[float] = field(default_factory=list)


def run_offline_experiment(
    dataset_path: Path | str,
    method: str,
    seed: int,
    eval_games: int,
    out: Path | str,
    epochs: int = 5,
    steps: int = 20_000,
    alpha: float = 1.0,
    rules: str = "v2.3",
    on_progress: Callable[[int, float], None] | None = None,
) -> OfflineResult:
    """Train `method` ("bc" or "cql") on the dataset file, evaluate against `bot:random` and
    each of `PRESET_BOTS` (`against_presets`, keyed by spec), and write `config.json`,
    `metrics.csv`, `result.json` and `model.pt` (the state dict of the network) to `out`."""
    if method not in ("bc", "cql"):
        raise ValueError(f"method must be 'bc' or 'cql', not {method!r}")
    data = Dataset.load(dataset_path)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    config: dict[str, Any] = {
        "dataset": str(dataset_path),
        "dataset_stats": data.stats(),
        "method": method,
        "seed": seed,
        "eval_games": eval_games,
        "rules": rules,
        "obs_dim": int(data.obs.shape[1]),
        "n_actions": int(data.mask.shape[1]),
        "versions": library_versions(),
    }
    if method == "bc":
        config.update(epochs=epochs, batch_size=256, lr=1e-3, hidden=256)
    else:
        config.update(steps=steps, alpha=alpha, batch_size=256, lr=1e-3, hidden=256, gamma=1.0)
    (out / "config.json").write_text(json.dumps(config, indent=2) + "\n")
    started = time.monotonic()
    if method == "bc":
        policy = train_bc(data, epochs, seed, rules, on_progress=on_progress)
    else:
        policy = train_cql(data, steps, seed, alpha, rules, on_progress=on_progress)
    train_seconds = time.monotonic() - started
    torch.save(policy.net.state_dict(), out / "model.pt")
    with (out / "metrics.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["step" if method == "cql" else "epoch", "loss"])
        writer.writerows((i + 1, loss) for i, loss in enumerate(policy.curve))
    against_random = evaluate(policy, RANDOM_OPPONENT, eval_games, seed, rules)
    against_presets = {
        spec: evaluate(policy, spec, eval_games, seed, rules) for spec in PRESET_BOTS
    }
    result = {
        "method": method,
        "train_seconds": round(train_seconds, 1),
        "final_loss": policy.curve[-1],
        "against_random": against_random.to_dict(),
        "against_presets": {spec: ev.to_dict() for spec, ev in against_presets.items()},
    }
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return OfflineResult(out, train_seconds, against_random, against_presets, policy.curve)
