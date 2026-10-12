"""Honest evaluation of a policy against an opponent."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from quack_rl.rl.opponents import make_opponent
from quack_rl.rl.single_env import QuackEnv

Policy = Callable[[np.ndarray, np.ndarray], int]


def random_policy(seed: int | None = None) -> Policy:
    """A baseline that picks uniformly among the actions where the mask is nonzero."""
    rng = np.random.default_rng(seed)

    def policy(observation: np.ndarray, mask: np.ndarray) -> int:
        return int(rng.choice(np.flatnonzero(mask)))

    return policy


@dataclass(frozen=True)
class EvalResult:
    games: int
    wins: int
    draws: int
    losses: int
    points_own: float  # average per game
    points_opponent: float
    explosions_own: float
    win_rate: float
    draw_rate: float
    loss_rate: float


def evaluate(
    policy: Policy,
    opponent: str | Any,
    rules: str = "v1.1",
    games: int = 500,
    seed: int = 0,
) -> EvalResult:
    """Play `games` games of `policy` against `opponent` (a name or a bot object).

    Game i uses the chance seed `seed + i`; the agent sits at p1 for even i and p2 for odd i.
    With a name, game i gets `make_opponent(name, seed=seed + i, rules=rules)`. A bot object is
    shared by all games, so the call is reproducible only if the object is fresh.
    The noise is about +-4 points of win rate for 500 games (one standard error, worst case).
    """
    if games < 1:
        raise ValueError(f"games must be at least 1, not {games}")
    envs = {s: QuackEnv(seat=s, rules=rules) for s in ("p1", "p2")}
    wins = draws = losses = 0
    own = opp = expl = 0
    for i in range(games):
        env = envs["p1" if i % 2 == 0 else "p2"]
        env.opponent = (
            make_opponent(opponent, seed=seed + i, rules=rules)
            if isinstance(opponent, str)
            else opponent
        )
        env._default_opponent = False
        obs, info = env.reset(seed=seed + i)
        done = False
        while not done:
            action = policy(obs, info["action_mask"])
            obs, _, done, _, info = env.step(action)
        ep = info["episode"]
        wins += ep["result"] == "win"
        draws += ep["result"] == "draw"
        losses += ep["result"] == "loss"
        own += ep["points"]["own"]
        opp += ep["points"]["opponent"]
        expl += ep["explosions"]["own"]
    return EvalResult(
        games, wins, draws, losses, own / games, opp / games, expl / games,
        wins / games, draws / games, losses / games,
    )  # fmt: skip
