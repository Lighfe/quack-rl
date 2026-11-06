"""Self-play: train MaskablePPO against a pool of its own earlier checkpoints.

SB3 and torch are imported inside the functions, so this module imports without the `rl`
dependency group (`uv run --group rl ...`). Nothing here prints or exits: progress goes through
`on_progress`.
"""

import csv
import json
import os
import random
import re
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from quack_rl.bots import RandomBot
from quack_rl.bots.presets import PRESET_BOTS
from quack_rl.engine import GameState
from quack_rl.rl.evaluate import EvalResult, evaluate
from quack_rl.rl.policy_bot import PolicyBot
from quack_rl.rl.single_env import QuackEnv
from quack_rl.rl.train import RANDOM_OPPONENT, library_versions
from quack_rl.rules import Ruleset, load_ruleset

N_STEPS = 1000  # decisions per PPO rollout; 20000 steps per round are then exactly 20 rollouts
BATCH_SIZE = 50
Loader = Callable[[Path], Any]
CSV_HEADER = ["round", "steps", "mean_reward", "pool_size"]
CHECKPOINT_RE = re.compile(r"checkpoint_(\d+)\.zip")


class ResumeError(ValueError):
    """A run folder that cannot be resumed (no `config.json` or no checkpoint)."""


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
        rules: Ruleset | str = "v2.3",
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
    against_first: EvalResult | None = None  # None with one round
    against_presets: dict[str, EvalResult] = field(default_factory=dict)  # by spec


def _require_sb3() -> tuple[Any, Any]:
    try:
        from sb3_contrib import MaskablePPO
        from stable_baselines3.common.callbacks import BaseCallback
    except ImportError as err:
        raise ImportError(
            "self-play needs stable-baselines3, sb3-contrib and torch: run with `uv run --group rl`"
        ) from err
    return MaskablePPO, BaseCallback


def newest_checkpoint(out: Path | str) -> int | None:
    """The highest i of the files `checkpoint_<i>.zip` in `out` (by number), None if there is none.

    Only names that match `checkpoint_<int>.zip` count, so a temporary file of an interrupted save
    (`checkpoint_<i>.tmp.zip`) is not found.
    """
    numbers = [
        int(m.group(1))
        for p in Path(out).iterdir()
        if p.is_file() and (m := CHECKPOINT_RE.fullmatch(p.name))
    ]
    return max(numbers, default=None)


def _write_csv(path: Path, rows: list[list[str]]) -> None:
    """Write `selfplay.csv` (header and `rows`) through a temporary file, then rename it."""
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_HEADER)
        writer.writerows(rows)
    os.replace(tmp, path)


def _append_csv(path: Path, point: RoundPoint) -> None:
    with path.open("a", newline="") as handle:
        csv.writer(handle).writerow(
            [
                point.round,
                point.steps,
                "" if point.mean_reward is None else point.mean_reward,
                point.pool_size,
            ]
        )


def _point(row: list[str]) -> RoundPoint:
    return RoundPoint(int(row[0]), int(row[1]), float(row[2]) if row[2] else None, int(row[3]))


def run_selfplay(
    out: Path | str,
    rounds: int = 5,
    steps_per_round: int = 20_000,
    pool_size: int = 4,
    seed: int = 0,
    eval_games: int = 500,
    rules: str = "v2.3",
    on_progress: Callable[[RoundPoint], None] | None = None,
) -> SelfplayResult:
    """Train for `rounds` rounds, each against the pool, and evaluate the last checkpoint.

    One model is trained over all rounds (the step counter keeps growing). After round i the model
    is saved as `checkpoint_<i>.zip` in `out`, added to the pool, and its row is added to
    `selfplay.csv` (round, steps, mean_reward, pool_size). The agent plays both seats. `out` also
    gets `config.json` (at the start) and `result.json` (the last checkpoint against `bot:random`,
    each of `PRESET_BOTS` (under `against_presets`, keyed by spec) and, with more than one round,
    the first checkpoint; win rates with the 95% Wilson interval). An interrupted run is continued
    with `resume_selfplay`.
    """
    if rounds < 1:
        raise ValueError(f"rounds must be at least 1, not {rounds}")
    if steps_per_round < 1:
        raise ValueError(f"steps_per_round must be at least 1, not {steps_per_round}")
    MaskablePPO, _ = _require_sb3()
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
    _write_csv(out / "selfplay.csv", [])
    pool = CheckpointPool(pool_size)
    env = QuackEnv(seat="random", opponent=PoolOpponent(pool, rules, seed), rules=rules)
    model = MaskablePPO(
        "MlpPolicy", env, n_steps=N_STEPS, batch_size=BATCH_SIZE, seed=seed, device="cpu"
    )
    return _train_and_evaluate(out, config, model, pool, 0, [], on_progress)


def resume_selfplay(
    out: Path | str, on_progress: Callable[[RoundPoint], None] | None = None
) -> SelfplayResult:
    """Continue the self-play run in `out` from its newest checkpoint, with its `config.json`.

    With the newest checkpoint i, the pool gets the last `pool_size` checkpoints up to i (oldest
    first), `selfplay.csv` is cut back to the rows of rounds 1 to i, and rounds i+1 to `rounds`
    are trained; then `result.json` is written as in a fresh run. With i = `rounds` nothing is
    trained. Raises `ResumeError` (before any training) when `config.json` or every checkpoint is
    missing.
    """
    out = Path(out)
    if not (out / "config.json").is_file():
        raise ResumeError(f"cannot resume {out}: no config.json")
    newest = newest_checkpoint(out)
    if newest is None:
        raise ResumeError(f"cannot resume {out}: no checkpoint_<i>.zip")
    config = json.loads((out / "config.json").read_text())
    rounds, pool_size, seed, rules = (
        config["rounds"],
        config["pool_size"],
        config["seed"],
        config["rules"],
    )
    if newest > rounds:
        raise ResumeError(f"cannot resume {out}: checkpoint_{newest}.zip but rounds is {rounds}")
    MaskablePPO, _ = _require_sb3()
    pool = CheckpointPool(pool_size)
    for i in range(max(1, newest - pool_size + 1), newest + 1):
        pool.add(out / f"checkpoint_{i}.zip")
    csv_path = out / "selfplay.csv"
    rows = list(csv.reader(csv_path.open(newline=""))) if csv_path.is_file() else []
    kept = [r for r in rows[1:] if r and int(r[0]) <= newest]
    _write_csv(csv_path, kept)
    points = [_point(r) for r in kept]
    env = QuackEnv(seat="random", opponent=PoolOpponent(pool, rules, seed), rules=rules)
    model = MaskablePPO.load(str(out / f"checkpoint_{newest}.zip"), env=env, device="cpu")
    return _train_and_evaluate(out, config, model, pool, newest, points, on_progress)


def _train_and_evaluate(
    out: Path,
    config: dict[str, Any],
    model: Any,
    pool: CheckpointPool,
    done: int,
    points: list[RoundPoint],
    on_progress: Callable[[RoundPoint], None] | None,
) -> SelfplayResult:
    """Train rounds `done`+1 to `rounds` of `config`, then evaluate and write `result.json`."""
    _, BaseCallback = _require_sb3()
    rounds, steps_per_round, seed = config["rounds"], config["steps_per_round"], config["seed"]
    eval_games, rules = config["eval_games"], config["rules"]

    class Finished(BaseCallback):
        def __init__(self) -> None:
            super().__init__()
            self.rewards: list[float] = []

        def _on_step(self) -> bool:
            for reward, ended in zip(self.locals["rewards"], self.locals["dones"], strict=True):
                if ended:  # the reward is paid once, at the end of the game
                    self.rewards.append(float(reward))
            return True

    started = time.monotonic()
    for i in range(done + 1, rounds + 1):
        finished = Finished()
        model.learn(total_timesteps=steps_per_round, callback=finished, reset_num_timesteps=False)
        path = out / f"checkpoint_{i}.zip"
        tmp = out / f"checkpoint_{i}.tmp.zip"  # does not match checkpoint_<int>.zip
        model.save(str(tmp))
        os.replace(tmp, path)
        pool.add(path)
        mean = sum(finished.rewards) / len(finished.rewards) if finished.rewards else None
        point = RoundPoint(i, int(model.num_timesteps), mean, len(pool))
        points.append(point)
        _append_csv(out / "selfplay.csv", point)
        if on_progress is not None:
            on_progress(point)
    train_seconds = time.monotonic() - started

    first_path, last_path = out / "checkpoint_1.zip", out / f"checkpoint_{rounds}.zip"
    last = PolicyBot(load_checkpoint(last_path), rules, last_path.stem)
    result = SelfplayResult(out, train_seconds, points)
    result.against_random = evaluate(last, RANDOM_OPPONENT, eval_games, seed, rules)
    result.against_presets = {
        spec: evaluate(last, spec, eval_games, seed, rules) for spec in PRESET_BOTS
    }
    data: dict[str, Any] = {
        "train_seconds": round(train_seconds, 1),
        "against_random": result.against_random.to_dict(),
        "against_presets": {spec: ev.to_dict() for spec, ev in result.against_presets.items()},
    }
    if rounds > 1:
        first = PolicyBot(load_checkpoint(first_path), rules, first_path.stem)
        result.against_first = evaluate(last, first, eval_games, seed, rules)
        data["against_first"] = result.against_first.to_dict()
    (out / "result.json").write_text(json.dumps(data, indent=2) + "\n")
    return result
