"""Train MaskablePPO against a bot and evaluate it.

One training step is one decision of the agent (about 40 per game), not one game. SB3 and torch
are imported inside the functions, so this module imports without the `rl` dependency group
(`uv run --group rl ...`). Nothing here prints or exits: progress goes through `on_progress`.
"""

import csv
import json
import platform
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
from typing import Any

from quack_rl.rl.evaluate import EvalResult, evaluate
from quack_rl.rl.opponents import RANDOM_NAMES, OpponentMix, distinct_specs, make_opponent
from quack_rl.rl.policy_bot import PolicyBot
from quack_rl.rl.single_env import QuackEnv

N_STEPS = 1024  # decisions per PPO rollout; one curve point per rollout
BATCH_SIZE = 64
RANDOM_OPPONENT = "bot:random"
LIBRARIES = ("quack-rl", "stable-baselines3", "sb3-contrib", "torch", "gymnasium", "numpy")


@dataclass(frozen=True)
class CurvePoint:
    steps: int  # decisions of the agent so far
    mean_reward: float  # mean episode reward of the games that ended in this rollout


@dataclass
class TrainResult:
    model: Any
    curve: list[CurvePoint] = field(default_factory=list)


@dataclass
class ExperimentResult:
    out: Path
    train_seconds: float
    against_opponent: EvalResult | None  # None when trained against a list of specs
    against_random: EvalResult
    evaluations: dict[str, EvalResult] = field(default_factory=dict)  # by opponent spec


Opponent = str | list[str]


def training_opponent(opponent: Opponent, seed: int, rules: str) -> Any:
    """The bot to train against: one spec gives its bot, a list gives an `OpponentMix`."""
    if isinstance(opponent, str):
        return make_opponent(opponent, seed, rules)
    return OpponentMix(opponent, seed, rules)


def _import_sb3():
    try:
        from sb3_contrib import MaskablePPO
        from stable_baselines3.common.callbacks import BaseCallback
    except ImportError as err:
        raise ImportError(
            "training needs stable-baselines3, sb3-contrib and torch: run with `uv run --group rl`"
        ) from err
    return MaskablePPO, BaseCallback


def train_ppo(
    opponent: Opponent,
    steps: int,
    seed: int = 0,
    rules: str = "v2.3",
    on_progress: Callable[[CurvePoint], None] | None = None,
) -> TrainResult:
    """Train MaskablePPO for `steps` decisions against `opponent`, on the CPU.

    `opponent` is a bot name, or a list of bot names: then each game is played against one of
    them, sampled with a generator seeded with `seed`. The agent sits at a random seat each game.
    `on_progress` gets each curve point as it is made.
    """
    if steps < 1:
        raise ValueError(f"steps must be at least 1, not {steps}")
    MaskablePPO, BaseCallback = _import_sb3()
    curve: list[CurvePoint] = []

    class Curve(BaseCallback):
        def __init__(self) -> None:
            super().__init__()
            self.finished: list[float] = []

        def _on_step(self) -> bool:
            for reward, done in zip(self.locals["rewards"], self.locals["dones"], strict=True):
                if done:  # the reward is paid once, at the end of the game
                    self.finished.append(float(reward))
            return True

        def _on_rollout_end(self) -> None:
            if not self.finished:
                return
            point = CurvePoint(int(self.num_timesteps), sum(self.finished) / len(self.finished))
            self.finished = []
            curve.append(point)
            if on_progress is not None:
                on_progress(point)

    env = QuackEnv(seat="random", opponent=training_opponent(opponent, seed, rules), rules=rules)
    model = MaskablePPO(
        "MlpPolicy", env, n_steps=N_STEPS, batch_size=BATCH_SIZE, seed=seed, device="cpu"
    )
    model.learn(total_timesteps=steps, callback=Curve())
    return TrainResult(model=model, curve=curve)


def library_versions() -> dict[str, str]:
    versions = {"python": platform.python_version()}
    for name in LIBRARIES:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = "not installed"
    return versions


def run_ppo_experiment(
    opponent: Opponent,
    steps: int,
    seed: int,
    eval_games: int,
    out: Path | str,
    rules: str = "v2.3",
    on_progress: Callable[[CurvePoint], None] | None = None,
) -> ExperimentResult:
    """Train, evaluate against each training opponent and against `bot:random`, write the files.

    `opponent` is one bot name or a list of them (see `train_ppo`). `out` gets `config.json`
    (inputs and library versions), `metrics.csv` (the curve), `result.json` (the evaluations, with
    the 95% Wilson interval) and `model.zip`. `result.json` has `evaluations`, one entry per
    distinct opponent and `bot:random` (once); with one bot name it also has `against_opponent`
    and `against_random`.
    """
    training_opponent(opponent, seed, rules)  # raises ValueError on a bad name, before any file
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    config = {
        "opponent": opponent,
        "steps": steps,
        "seed": seed,
        "eval_games": eval_games,
        "rules": rules,
        "n_steps": N_STEPS,
        "batch_size": BATCH_SIZE,
        "versions": library_versions(),
    }
    (out / "config.json").write_text(json.dumps(config, indent=2) + "\n")
    started = time.monotonic()
    trained = train_ppo(opponent, steps, seed, rules, on_progress)
    train_seconds = time.monotonic() - started
    trained.model.save(str(out / "model.zip"))
    with (out / "metrics.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["steps", "mean_reward"])
        writer.writerows((p.steps, p.mean_reward) for p in trained.curve)
    bot = PolicyBot(trained.model, rules)
    specs = [opponent] if isinstance(opponent, str) else opponent
    evaluations = {
        spec: evaluate(bot, spec, eval_games, seed, rules) for spec in distinct_specs(specs)
    }
    against_random = next(ev for spec, ev in evaluations.items() if spec in RANDOM_NAMES)
    against_opponent = evaluations[opponent] if isinstance(opponent, str) else None
    result: dict[str, Any] = {"opponent": opponent, "train_seconds": round(train_seconds, 1)}
    if against_opponent is not None:
        result["against_opponent"] = against_opponent.to_dict()
        result["against_random"] = against_random.to_dict()
    result["evaluations"] = {spec: ev.to_dict() for spec, ev in evaluations.items()}
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return ExperimentResult(out, train_seconds, against_opponent, against_random, evaluations)
