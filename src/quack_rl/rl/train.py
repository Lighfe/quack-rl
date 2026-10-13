"""Train a MaskablePPO agent against an opponent and record how it learns.

One training step is one decision of the agent (about 42 per game), not one game.
SB3 and torch are imported inside the functions, so this module imports without the `train`
group (`uv sync --group train`).
"""

from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np

from quack_rl.rl.evaluate import EvalResult, Policy, evaluate, random_policy
from quack_rl.rl.opponents import make_opponent
from quack_rl.rl.single_env import QuackEnv

N_STEPS = 128  # decisions per PPO rollout: train(256, ...) ends two rollouts
_METRIC_KEYS = (
    "policy_gradient_loss",
    "value_loss",
    "entropy_loss",
    "approx_kl",
    "explained_variance",
)


@dataclass
class TrainingLog:
    episodes: list[dict] = field(default_factory=list)
    metrics: list[dict] = field(default_factory=list)


@dataclass
class TrainResult:
    model: Any
    log: TrainingLog
    baseline_random: EvalResult
    baseline_untrained: EvalResult
    trained_sampled: EvalResult
    trained_greedy: EvalResult
    games_played: int
    # the same four evaluations against RandomBot; None when the opponent is `random`
    baseline_random_vs_random: EvalResult | None = None
    baseline_untrained_vs_random: EvalResult | None = None
    trained_sampled_vs_random: EvalResult | None = None
    trained_greedy_vs_random: EvalResult | None = None


class RunSink(Protocol):
    def start(self, config: dict) -> None: ...
    def episode(self, row: dict) -> None: ...
    def metrics(self, row: dict) -> None: ...
    def finish(self, result: TrainResult) -> None: ...


def sb3_policy(model: Any, deterministic: bool) -> Policy:
    """A `Policy` from a MaskablePPO model: it only returns actions where the mask is nonzero.

    `deterministic=False` samples from the network (use it for the untrained network);
    `deterministic=True` takes the most likely action.
    """

    def policy(observation: np.ndarray, mask: np.ndarray) -> int:
        action, _ = model.predict(
            observation, action_masks=np.asarray(mask, dtype=bool), deterministic=deterministic
        )
        return int(action)

    return policy


def _import_sb3():
    try:
        from sb3_contrib import MaskablePPO
        from stable_baselines3.common.callbacks import BaseCallback
        from stable_baselines3.common.logger import KVWriter, Logger
    except ImportError as err:
        raise ImportError(
            "training needs stable-baselines3, sb3-contrib and torch: run `uv sync --group train`"
        ) from err
    return MaskablePPO, BaseCallback, KVWriter, Logger


def train(
    steps: int,
    rules: str = "v1.1",
    opponent: str = "random",
    seed: int = 0,
    eval_games: int = 500,
    sink: RunSink | None = None,
) -> TrainResult:
    """Train MaskablePPO for `steps` decisions of the agent against `opponent`, on the CPU.

    The agent sits at a random seat each game. Before training it evaluates the uniform-random
    agent (`baseline_random`) and the untrained network with sampled actions
    (`baseline_untrained`); after training it evaluates the trained network, sampled and
    most-likely-action.
    These four evaluations each run `eval_games` games against the training opponent, and when
    that is not `random` also against `RandomBot` (the `*_vs_random` fields). `sink` gets the
    rows as they arrive. Memory only: nothing is written to disk.
    """
    if eval_games < 1:
        raise ValueError(f"eval_games must be at least 1, not {eval_games}")
    make_opponent(opponent, seed=seed, rules=rules)  # ValueError on an unknown name
    MaskablePPO, BaseCallback, KVWriter, Logger = _import_sb3()

    log = TrainingLog()
    config = {
        "steps": steps,
        "rules": rules,
        "opponent": opponent,
        "seed": seed,
        "eval_games": eval_games,
    }
    if sink is not None:
        sink.start(config)

    class EpisodeCallback(BaseCallback):
        def _on_step(self) -> bool:
            for info in self.locals["infos"]:
                ep = info.get("quack_episode")
                if ep is None:
                    continue
                row = {
                    "episode": len(log.episodes) + 1,
                    "timestep": int(self.num_timesteps),
                    "result": ep["result"],
                    "points_own": ep["points"]["own"],
                    "points_opponent": ep["points"]["opponent"],
                    "explosions_own": ep["explosions"]["own"],
                    "decisions": ep["decisions"],
                }
                log.episodes.append(row)
                if sink is not None:
                    sink.episode(row)
            return True

    class MetricsWriter(KVWriter):
        def write(self, key_values, key_excluded, step=0):
            row: dict[str, Any] = {"timestep": int(step)}
            for name in _METRIC_KEYS:
                if f"train/{name}" in key_values:
                    row[name] = float(key_values[f"train/{name}"])
            if len(row) == 1:
                return
            log.metrics.append(row)
            if sink is not None:
                sink.metrics(row)

        def close(self) -> None:
            pass

    import gymnasium as gym

    class KeepEpisode(gym.Wrapper):
        """Copy info["episode"] to info["quack_episode"]: SB3's Monitor overwrites the first."""

        def step(self, action):
            obs, rew, term, trunc, info = self.env.step(action)
            if "episode" in info:
                info["quack_episode"] = info["episode"]
            return obs, rew, term, trunc, info

        def action_masks(self):
            return self.env.action_masks()

    env = KeepEpisode(
        QuackEnv(seat="random", rules=rules, opponent=make_opponent(opponent, seed, rules))
    )
    env.reset(seed=seed)
    model = MaskablePPO(
        "MlpPolicy", env, n_steps=N_STEPS, batch_size=64, seed=seed, device="cpu", verbose=0
    )
    model.set_logger(Logger(None, [MetricsWriter()]))

    def run_evals(opp: str, tag: str) -> dict[str, EvalResult]:
        def one(policy: Policy) -> EvalResult:
            return evaluate(policy, opp, rules=rules, games=eval_games, seed=seed)

        return {
            f"baseline_random{tag}": one(random_policy(seed)),
            f"baseline_untrained{tag}": one(sb3_policy(model, deterministic=False)),
        }

    before = run_evals(opponent, "")
    before_random = run_evals("random", "_vs_random") if opponent != "random" else {}
    model.learn(total_timesteps=steps, callback=EpisodeCallback())

    def after(opp: str, tag: str) -> dict[str, EvalResult]:
        return {
            f"trained_sampled{tag}": evaluate(
                sb3_policy(model, False), opp, rules=rules, games=eval_games, seed=seed
            ),
            f"trained_greedy{tag}": evaluate(
                sb3_policy(model, True), opp, rules=rules, games=eval_games, seed=seed
            ),
        }

    results = {**before, **before_random, **after(opponent, "")}
    if opponent != "random":
        results.update(after("random", "_vs_random"))
    result = TrainResult(model=model, log=log, games_played=len(log.episodes), **results)
    if sink is not None:
        sink.finish(result)
    return result
