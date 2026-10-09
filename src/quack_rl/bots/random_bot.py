import random
from typing import Any

from quack_rl.engine import GameState


class RandomBot:
    """Chooses uniformly among the legal actions."""

    kind = "bot"
    name = "random"

    def __init__(self, seed: int | None = None):
        self._rng = random.Random(seed)
        self.params: dict[str, Any] = {"seed": seed}

    def choose(self, state: GameState, seat: str, legal: list[str]) -> str:
        return self._rng.choice(legal)
