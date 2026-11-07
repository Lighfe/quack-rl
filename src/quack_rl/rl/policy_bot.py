"""A trained MaskablePPO model as a bot: `choose(state, seat, legal)` like every seat."""

from typing import Any, Literal

import numpy as np

from quack_rl.engine import GameState, action_names
from quack_rl.rl.encode import action_mask, observe, vectorize
from quack_rl.rules import Ruleset, load_ruleset

MODES: tuple[str, ...] = ("greedy", "sampled")
Mode = Literal["greedy", "sampled"]


def mode_params(mode: str, seed: int | None) -> dict[str, Any]:
    """The `params` of a policy bot in `mode`; raise ValueError on an unknown mode."""
    if mode == "greedy":
        return {"deterministic": True}
    if mode == "sampled":
        return {"deterministic": False, "seed": seed}
    raise ValueError(f"mode must be one of {MODES}, not {mode!r}")


def sample_legal(probs: np.ndarray, mask: np.ndarray, rng: np.random.Generator) -> int:
    """Draw an action index from `probs` renormalised over the legal actions (`mask` True)."""
    p = np.where(mask, np.asarray(probs, dtype=np.float64), 0.0)
    total = p.sum()
    if not total > 0.0:  # every legal action got probability 0: uniform over the legal ones
        p = mask.astype(np.float64)
        total = p.sum()
    return int(rng.choice(len(p), p=p / total))


class PolicyBot:
    """Plays an action of the model among the legal ones.

    `mode="greedy"` plays the action the model finds most likely (deterministic); `"sampled"`
    draws from the model's softmax over the legal actions only, with a generator seeded by
    `seed`. The observation comes from the same encoder as the env (`observe` and `vectorize`),
    and the mask of `legal` is passed to the model, so the choice is always a legal action.
    """

    kind = "bot"

    def __init__(
        self,
        model: Any,
        rules: Ruleset | str = "v2.3",
        name: str = "policy",
        mode: Mode = "greedy",
        seed: int | None = None,
    ):
        self.params: dict[str, Any] = mode_params(mode, seed)
        self.rs = load_ruleset(rules) if isinstance(rules, str) else rules
        self.model = model
        self.name = name
        self.mode = mode
        self._rng = np.random.default_rng(seed)
        self._names = action_names(self.rs)

    def choose(self, state: GameState, seat: str, legal: list[str]) -> str:
        obs = vectorize(observe(state, self.rs, seat), self.rs)
        mask = np.asarray(action_mask(state, self.rs, seat), dtype=bool)
        allowed = set(legal)
        mask &= np.asarray([name in allowed for name in self._names], dtype=bool)
        if not mask.any():
            raise ValueError("no legal action to choose from")
        if self.mode == "greedy":
            action, _ = self.model.predict(obs, action_masks=mask, deterministic=True)
            return self._names[int(action)]
        return self._names[sample_legal(self._probs(obs, mask), mask, self._rng)]

    def _probs(self, obs: Any, mask: np.ndarray) -> np.ndarray:
        import torch

        policy = self.model.policy
        obs_tensor, _ = policy.obs_to_tensor(np.asarray(obs, dtype=np.float32))
        with torch.no_grad():
            dist = policy.get_distribution(obs_tensor, action_masks=mask)
        return dist.distribution.probs[0].cpu().numpy()
