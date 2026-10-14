"""A trained policy as a bot: `choose(state, seat, legal)` like every seat of the runner."""

from pathlib import Path
from typing import Any

import numpy as np

from quack_rl.engine import GameState, action_names
from quack_rl.rl.encode import action_mask, observe, vectorize
from quack_rl.rl.evaluate import Policy
from quack_rl.rl.runs import load_model
from quack_rl.rules import Ruleset, load_ruleset


class PolicyBot:
    """Wraps a `Policy` for a ruleset. The policy brings its own randomness, the wrapper none."""

    kind = "bot"

    def __init__(
        self, policy: Policy, rules: Ruleset | str, name: str = "policy", params: dict | None = None
    ):
        self.rs = load_ruleset(rules) if isinstance(rules, str) else rules
        self.policy = policy
        self.name = name
        self.params: dict[str, Any] = dict(params or {})
        self._names = action_names(self.rs)

    def choose(self, state: GameState, seat: str, legal: list[str]) -> str:
        obs = vectorize(observe(state, self.rs, seat), self.rs)
        mask = action_mask(state, self.rs, seat)
        index = int(self.policy(obs, mask))
        if not 0 <= index < len(self._names):
            raise ValueError(f"policy returned the index {index}, outside the action list")
        if not mask[index]:
            raise ValueError(f"policy chose the illegal action {self._names[index]!r}")
        return self._names[index]

    @classmethod
    def from_run(cls, path: Path | str, rules: Ruleset | str) -> "PolicyBot":
        """Build the bot from a run folder. `load_model` refuses another layout or vector."""
        rs = load_ruleset(rules) if isinstance(rules, str) else rules
        model = load_model(path, rs.version)

        def policy(obs: np.ndarray, mask: np.ndarray) -> int:
            action, _ = model.predict(obs, action_masks=mask, deterministic=True)
            return int(action)

        return cls(policy, rs, name=f"policy:{path}", params={"run": str(path)})
