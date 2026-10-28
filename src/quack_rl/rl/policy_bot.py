"""A trained MaskablePPO model as a bot: `choose(state, seat, legal)` like every seat."""

from typing import Any

import numpy as np

from quack_rl.engine import GameState, action_names
from quack_rl.rl.encode import action_mask, observe, vectorize
from quack_rl.rules import Ruleset, load_ruleset


class PolicyBot:
    """Plays the action the model finds most likely among the legal ones (deterministic).

    The observation comes from the same encoder as the env (`observe` and `vectorize`), and the
    mask of `legal` is passed to the model, so the choice is always a legal action.
    """

    kind = "bot"

    def __init__(self, model: Any, rules: Ruleset | str = "v2.3", name: str = "policy"):
        self.rs = load_ruleset(rules) if isinstance(rules, str) else rules
        self.model = model
        self.name = name
        self.params: dict[str, Any] = {"deterministic": True}
        self._names = action_names(self.rs)

    def choose(self, state: GameState, seat: str, legal: list[str]) -> str:
        obs = vectorize(observe(state, self.rs, seat), self.rs)
        mask = np.asarray(action_mask(state, self.rs, seat), dtype=bool)
        allowed = set(legal)
        mask &= np.asarray([name in allowed for name in self._names], dtype=bool)
        if not mask.any():
            raise ValueError("no legal action to choose from")
        action, _ = self.model.predict(obs, action_masks=mask, deterministic=True)
        return self._names[int(action)]
