"""Evaluate a bot against an opponent by win rate."""

import math
from dataclasses import asdict, dataclass
from typing import Any

from quack_rl.engine import action_names, legal_actions
from quack_rl.rl.opponents import make_opponent
from quack_rl.rl.single_env import QuackEnv

Z95 = 1.959963984540054


@dataclass(frozen=True)
class EvalResult:
    games: int
    wins: int
    draws: int
    losses: int
    win_rate: float  # (wins + draws / 2) / games
    ci_low: float  # 95% Wilson interval of the win rate
    ci_high: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def wilson_interval(successes: float, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval of a proportion `successes / n` (`successes` may be a half count)."""
    if n < 1:
        raise ValueError(f"n must be at least 1, not {n}")
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def evaluate(
    bot: Any, opponent: str | Any, games: int = 500, seed: int = 0, rules: str = "v2.1"
) -> EvalResult:
    """Play `games` games of `bot` against `opponent` (a bot name or a bot object).

    Game i uses the chance seed `seed + i`; `bot` sits at p1 for even i and p2 for odd i, so each
    seat gets half of the games. With a name, game i gets `make_opponent(name, seed + i)`; a bot
    object is shared by all games, so the result is reproducible only if the object is fresh.
    Raise ValueError if the bot chooses an action that is not legal.
    """
    if games < 1:
        raise ValueError(f"games must be at least 1, not {games}")
    names = action_names(QuackEnv(rules=rules).rs)
    wins = draws = losses = 0
    for i in range(games):
        opp = make_opponent(opponent, seed + i, rules) if isinstance(opponent, str) else opponent
        env = QuackEnv(seat="p1" if i % 2 == 0 else "p2", opponent=opp, rules=rules)
        env.reset(seed=seed + i)
        done = False
        info: dict[str, Any] = {}
        while not done:
            legal = legal_actions(env.state, env.rs, env.agent_seat)
            choice = bot.choose(env.state, env.agent_seat, legal)
            if choice not in legal:
                raise ValueError(f"the bot chose {choice!r}, which is not legal")
            _, _, done, _, info = env.step(names.index(choice))
        result = info["episode"]["result"]
        wins += result == "win"
        draws += result == "draw"
        losses += result == "loss"
    score = wins + draws / 2
    low, high = wilson_interval(score, games)
    return EvalResult(games, wins, draws, losses, score / games, low, high)
