"""A trained policy as a bot: `choose(state, seat, legal)` like every seat of the runner."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

from quack_rl.engine import GameState, action_names
from quack_rl.rl.encode import action_mask, observe, vectorize
from quack_rl.rl.evaluate import Policy
from quack_rl.rl.runs import load_model
from quack_rl.rules import Ruleset, load_ruleset


READOUTS = ("greedy", "sampled")
DEFAULT_READOUT = "greedy"

# (observation, mask) -> probability of every action (zero where the mask is zero)
Distribution = Callable[[np.ndarray, np.ndarray], np.ndarray]


def check_readout(readout: str) -> str:
    """Return `readout` or raise ValueError naming the two values."""
    if readout not in READOUTS:
        raise ValueError(f"unknown read-out {readout!r} (known: {', '.join(READOUTS)})")
    return readout


class PolicyBot:
    """Wraps a `Policy` for a ruleset.

    `readout` is `greedy` (default: the `policy` callable decides, it brings its own randomness,
    the wrapper none) or `sampled` (draw from `distribution` over the legal actions with a
    generator seeded by `seed`, default 0; `policy` is not used). `params["readout"]` holds it.
    """

    kind = "bot"

    def __init__(
        self,
        policy: Policy,
        rules: Ruleset | str,
        name: str = "policy",
        params: dict | None = None,
        readout: str = DEFAULT_READOUT,
        seed: int = 0,
        distribution: Distribution | None = None,
    ):
        check_readout(readout)
        if readout == "sampled" and distribution is None:
            raise ValueError("the read-out 'sampled' needs a distribution")
        self.rs = load_ruleset(rules) if isinstance(rules, str) else rules
        self.policy = policy
        self.name = name
        self.readout = readout
        self.distribution = distribution
        self._rng = np.random.default_rng(seed)
        self.params: dict[str, Any] = {**(params or {}), "readout": readout}
        self._names = action_names(self.rs)

    def choose(self, state: GameState, seat: str, legal: list[str]) -> str:
        obs = vectorize(observe(state, self.rs, seat), self.rs)
        mask = action_mask(state, self.rs, seat)
        if self.readout == "sampled":
            assert self.distribution is not None
            probs = np.where(mask, np.asarray(self.distribution(obs, mask), dtype=float), 0.0)
            total = probs.sum()
            if total <= 0:  # no mass on a legal action: uniform over the legal ones
                probs = mask.astype(float)
                total = probs.sum()
            index = int(self._rng.choice(len(probs), p=probs / total))
        else:
            index = int(self.policy(obs, mask))
        if not 0 <= index < len(self._names):
            raise ValueError(f"policy returned the index {index}, outside the action list")
        if not mask[index]:
            raise ValueError(f"policy chose the illegal action {self._names[index]!r}")
        return self._names[index]

    @classmethod
    def from_run(
        cls,
        path: Path | str,
        rules: Ruleset | str,
        readout: str = DEFAULT_READOUT,
        seed: int = 0,
    ) -> "PolicyBot":
        """Build the bot from a run folder. `load_model` refuses another layout or vector."""
        check_readout(readout)
        rs = load_ruleset(rules) if isinstance(rules, str) else rules
        model = load_model(path, rs.version)

        def policy(obs: np.ndarray, mask: np.ndarray) -> int:
            action, _ = model.predict(obs, action_masks=mask, deterministic=True)
            return int(action)

        def distribution(obs: np.ndarray, mask: np.ndarray) -> np.ndarray:
            tensor, _ = model.policy.obs_to_tensor(obs)
            dist = model.policy.get_distribution(tensor, action_masks=np.asarray(mask, dtype=bool))
            return dist.distribution.probs[0].detach().cpu().numpy()

        return cls(
            policy, rs, name=f"policy:{path}", params={"run": str(path)},
            readout=readout, seed=seed, distribution=distribution,
        )  # fmt: skip
