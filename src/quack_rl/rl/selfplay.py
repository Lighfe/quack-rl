"""Self-play: train MaskablePPO against a pool of its own earlier checkpoints.

SB3 and torch are imported inside the functions, so this module imports without the `rl`
dependency group (`uv run --group rl ...`). Nothing here prints or exits: progress goes through
`on_progress`.
"""

import csv
import json
import random
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from quack_rl.bots import RandomBot
from quack_rl.engine import GameState
from quack_rl.rl.evaluate import EvalResult, evaluate
from quack_rl.rl.policy_bot import PolicyBot
from quack_rl.rl.single_env import QuackEnv
from quack_rl.rl.train import RANDOM_OPPONENT, library_versions
from quack_rl.rules import Ruleset, load_ruleset

N_STEPS = 1000  # decisions per PPO rollout; 20000 steps per round are then exactly 20 rollouts
BATCH_SIZE = 50
HEURISTIC_OPPONENT = "bot:draw20-pts1-points"
Loader = Callable[[Path], Any]


def load_checkpoint(path: Path | str) -> Any:
    """Load a saved `MaskablePPO` on the CPU."""
    try:
        from sb3_contrib import MaskablePPO
    except ImportError as err:
        raise ImportError(
            "self-play needs stable-baselines3, sb3-contrib and torch: run with `uv run --group rl`"
        ) from err
    return MaskablePPO.load(str(path), device="cpu")


class CheckpointPool:
    """The last `size` checkpoints (paths of saved models), oldest first."""

    def __init__(self, size: int = 4):
        if size < 1:
            raise ValueError(f"size must be at least 1, not {size}")
        self.size = size
        self._items: deque[Path] = deque(maxlen=size)

    def add(self, path: Path | str) -> None:
        self._items.append(Path(path))

    @property
    def checkpoints(self) -> list[Path]:
        return list(self._items)

    def __len__(self) -> int:
        return len(self._items)


class PoolOpponent:
    """A bot that plays each episode with one checkpoint of the pool, chosen at random.

    `reset()` (called by `QuackEnv.reset`) picks the checkpoint for the next episode; while the
    pool is empty the bot is a `RandomBot`. The checkpoint plays as a `PolicyBot`. Loaded models
    are cached while they stay in the pool. `loader` turns a path into a model.
    """

    kind = "bot"
    name = "pool"

    def __init__(
        self,
        pool: CheckpointPool,
        rules: Ruleset | str = "v2.2",
        seed: int | None = None,
        loader: Loader = load_checkpoint,
    ):
        self.pool = pool
        self.rs = load_ruleset(rules) if isinstance(rules, str) else rules
        self.params: dict[str, Any] = {"seed": seed}
        self._rng = random.Random(seed)
        self._loader = loader
        self._bots: dict[Path, PolicyBot] = {}
        self.current: Path | None = None  # the checkpoint of this episode, None for the random bot
        self._bot: Any = RandomBot(self._rng.getrandbits(32))

    def reset(self) -> None:
        checkpoints = self.pool.checkpoints
        self._bots = {p: b for p, b in self._bots.items() if p in checkpoints}
        if not checkpoints:
            self.current = None
            self._bot = RandomBot(self._rng.getrandbits(32))
            return
        self.current = self._rng.choice(checkpoints)
        if self.current not in self._bots:
            self._bots[self.current] = PolicyBot(
                self._loader(self.current), self.rs, self.current.stem
            )
        self._bot = self._bots[self.current]

    def choose(self, state: GameState, seat: str, legal: list[str]) -> str:
        return self._bot.choose(state, seat, legal)


@dataclass(frozen=True)
class RoundPoint:
    round: int  # 1-based
    steps: int  # decisions of the agent so far, over all rounds
    mean_reward: float | None  # mean episode reward of the games that ended; None if none ended
    pool_size: int  # checkpoints in the pool after the round


@dataclass
class SelfplayResult:
    out: Path
    train_seconds: float
    rounds: list[RoundPoint] = field(default_factory=list)
    against_random: EvalResult | None = None
    against_heuristic: EvalResult | None = None
    against_first: EvalResult | None = None  # None with one round


def run_selfplay(
    out: Path | str,
    rounds: int = 5,
    steps_per_round: int = 20_000,
    pool_size: int = 4,
    seed: int = 0,
    eval_games: int = 500,
    rules: str = "v2.2",
    on_progress: Callable[[RoundPoint], None] | None = None,
) -> SelfplayResult:
    """Train for `rounds` rounds, each against the pool, and evaluate the last checkpoint.

    One model is trained over all rounds (the step counter keeps growing). After round i the model
    is saved as `checkpoint_<i>.zip` in `out` and added to the pool. The agent plays both seats.
    `out` gets `config.json`, `selfplay.csv` (round, steps, mean_reward, pool_size) and
    `result.json` (the last checkpoint against `bot:random`, the heuristic bot and, with more than
    one round, the first checkpoint; win rates with the 95% Wilson interval).
    """
    if rounds < 1:
        raise ValueError(f"rounds must be at least 1, not {rounds}")
    if steps_per_round < 1:
        raise ValueError(f"steps_per_round must be at least 1, not {steps_per_round}")
    try:
        from sb3_contrib import MaskablePPO
        from stable_baselines3.common.callbacks import BaseCallback
    except ImportError as err:
        raise ImportError(
            "self-play needs stable-baselines3, sb3-contrib and torch: run with `uv run --group rl`"
        ) from err
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    config = {
        "rounds": rounds,
        "steps_per_round": steps_per_round,
        "pool_size": pool_size,
        "seed": seed,
        "eval_games": eval_games,
        "rules": rules,
        "n_steps": N_STEPS,
        "batch_size": BATCH_SIZE,
        "versions": library_versions(),
    }
    (out / "config.json").write_text(json.dumps(config, indent=2) + "\n")

    class Finished(BaseCallback):
        def __init__(self) -> None:
            super().__init__()
            self.rewards: list[float] = []

        def _on_step(self) -> bool:
            for reward, done in zip(self.locals["rewards"], self.locals["dones"], strict=True):
                if done:  # the reward is paid once, at the end of the game
                    self.rewards.append(float(reward))
            return True

    pool = CheckpointPool(pool_size)
    env = QuackEnv(seat="random", opponent=PoolOpponent(pool, rules, seed), rules=rules)
    model = MaskablePPO(
        "MlpPolicy", env, n_steps=N_STEPS, batch_size=BATCH_SIZE, seed=seed, device="cpu"
    )
    points: list[RoundPoint] = []
    checkpoints: list[Path] = []
    started = time.monotonic()
    for i in range(1, rounds + 1):
        finished = Finished()
        model.learn(total_timesteps=steps_per_round, callback=finished, reset_num_timesteps=False)
        path = out / f"checkpoint_{i}.zip"
        model.save(str(path))
        checkpoints.append(path)
        pool.add(path)
        mean = sum(finished.rewards) / len(finished.rewards) if finished.rewards else None
        point = RoundPoint(i, int(model.num_timesteps), mean, len(pool))
        points.append(point)
        if on_progress is not None:
            on_progress(point)
    train_seconds = time.monotonic() - started
    with (out / "selfplay.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["round", "steps", "mean_reward", "pool_size"])
        writer.writerows(
            (p.round, p.steps, "" if p.mean_reward is None else p.mean_reward, p.pool_size)
            for p in points
        )

    last = PolicyBot(load_checkpoint(checkpoints[-1]), rules, checkpoints[-1].stem)
    result = SelfplayResult(out, train_seconds, points)
    result.against_random = evaluate(last, RANDOM_OPPONENT, eval_games, seed, rules)
    result.against_heuristic = evaluate(last, HEURISTIC_OPPONENT, eval_games, seed, rules)
    data: dict[str, Any] = {
        "train_seconds": round(train_seconds, 1),
        "against_random": result.against_random.to_dict(),
        "against_heuristic": result.against_heuristic.to_dict(),
    }
    if rounds > 1:
        first = PolicyBot(load_checkpoint(checkpoints[0]), rules, checkpoints[0].stem)
        result.against_first = evaluate(last, first, eval_games, seed, rules)
        data["against_first"] = result.against_first.to_dict()
    (out / "result.json").write_text(json.dumps(data, indent=2) + "\n")
    return result
