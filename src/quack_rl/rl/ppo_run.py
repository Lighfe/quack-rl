"""One PPO run of one seed of an experiment config, written into a run folder while it runs.

The run folder gets `config.json` at the start, one `ppo.csv` row per rollout (after its update),
`checkpoints/step_<n>.zip` every `checkpoint_every` steps and at the end, and `done.json` when the
run has finished. With `save_games` it also gets `games.jsonl`, one line per finished game (chance
seed and joint actions, see `quack_rl.rl.game_log`). An interrupted run continues from its
newest complete checkpoint with `resume=True`; the opponent mix and the env generators restart
then, only the model state continues.

SB3 and torch are imported inside the functions, so this module imports without the `rl`
dependency group (`uv run --group rl ...`).
"""

import csv
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from quack_rl.rl.experiment import ExperimentConfig, config_diff
from quack_rl.rl.opponents import OpponentMix
from quack_rl.rl.reward import REWARDS
from quack_rl.rl.selfplay import ResumeError
from quack_rl.rl.single_env import QuackEnv
from quack_rl.rl.train import BATCH_SIZE, N_STEPS, library_versions

RULES = "v2.3"
PPO_COLUMNS = (
    "steps",
    "mean_reward",
    "games",
    "policy_loss",
    "value_loss",
    "entropy",
    "approx_kl",
    "clip_fraction",
    "explained_variance",
    "wall_seconds",
)
# ppo.csv column -> SB3 logger key (entropy is handled apart: it is minus train/entropy_loss)
_LOGGER_KEYS = {
    "policy_loss": "train/policy_gradient_loss",
    "value_loss": "train/value_loss",
    "approx_kl": "train/approx_kl",
    "clip_fraction": "train/clip_fraction",
    "explained_variance": "train/explained_variance",
}
CHECKPOINT_RE = re.compile(r"step_(\d+)\.zip")
GAMES_FILE = "games.jsonl"
GAME_INFO = "game_record"  # info key of the terminal step; Monitor overwrites "episode"


class _RecordingEnv(QuackEnv):
    """`QuackEnv` whose terminal step info has the game record under `GAME_INFO`: chance seed,
    agent seat, the opponent spec of the game (`OpponentMix.current`) and the joint actions. It
    is made in `step`, before the vec env resets the env."""

    def step(self, action: int):
        obs, total, done, truncated, info = super().step(action)
        if done:
            info[GAME_INFO] = {
                "chance_seed": self.chance_seed,
                "agent_seat": self.agent_seat,
                "opponent": self.opponent.current,
                "actions": self.joint_actions,
            }
        return obs, total, done, truncated, info


def policy_kwargs(hidden: int) -> dict[str, Any]:
    """The shared network shape: two `hidden`-unit ReLU layers in the actor and in the critic."""
    import torch

    return {
        "net_arch": dict(pi=[hidden, hidden], vf=[hidden, hidden]),
        "activation_fn": torch.nn.ReLU,
    }


def newest_complete_checkpoint(out: Path) -> Path | None:
    """The `checkpoints/step_<n>.zip` of `out` with the highest n (by number), None if none.

    A temporary file of an interrupted save (`step_<n>.tmp.zip`) does not match and is ignored.
    """
    folder = Path(out) / "checkpoints"
    if not folder.is_dir():
        return None
    found = [
        (int(m.group(1)), p)
        for p in folder.iterdir()
        if p.is_file() and (m := CHECKPOINT_RE.fullmatch(p.name))
    ]
    return max(found)[1] if found else None


def git_commit() -> str:
    """The commit of the repo this module is in, or `"unknown"`."""
    try:
        done = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return done.stdout.strip() or "unknown"


def _opponent_specs(config: ExperimentConfig) -> list[str]:
    return [share.spec for share in config.opponents for _ in range(share.weight)]


def _check(config: ExperimentConfig, steps: int) -> None:
    """Raise ValueError on a config this function cannot run; writes nothing."""
    if config.kind != "ppo":
        raise ValueError(f"run_ppo_seed needs a ppo experiment, not kind {config.kind!r}")
    if steps < 1:
        raise ValueError(f"steps must be at least 1, not {steps}")
    every = config.checkpoint_every
    if every is not None and (every < 1 or every % N_STEPS):
        raise ValueError(f"checkpoint_every must be a multiple of {N_STEPS}, not {every}")
    OpponentMix(_opponent_specs(config), 0, RULES)  # raises ValueError naming an unknown spec


def _read_rows(path: Path) -> list[list[str]]:
    if not path.is_file():
        return []
    with path.open(newline="") as handle:
        return [row for row in csv.reader(handle)][1:]


def _write_rows(path: Path, rows: list[list[str]]) -> None:
    """Write `ppo.csv` (header and `rows`) through a temporary file, then rename it."""
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(PPO_COLUMNS)
        writer.writerows(rows)
    os.replace(tmp, path)


def _trim_games(path: Path, start: int) -> None:
    """Keep the lines of `games.jsonl` with `step` at most `start` (rewritten through a temporary
    file); a last line that is not complete JSON is dropped. No file: an empty file is written.
    Raise ValueError naming the line (counted from 1) for a broken line before the last."""
    texts = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    kept = []
    for number, text in enumerate(texts, start=1):
        try:
            line = json.loads(text)
        except json.JSONDecodeError as err:
            if number == len(texts):
                break
            raise ValueError(f"{path} line {number} is not JSON: {err}") from err
        if int(line["step"]) <= start:
            kept.append(text + "\n")
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("".join(kept), encoding="utf-8")
    os.replace(tmp, path)


def _save_checkpoint(model: Any, out: Path, steps: int) -> Path:
    folder = out / "checkpoints"
    folder.mkdir(exist_ok=True)
    path = folder / f"step_{steps}.zip"
    tmp = folder / f"step_{steps}.tmp.zip"  # does not match step_<int>.zip
    model.save(str(tmp))
    os.replace(tmp, path)
    return path


def _resume_problems(stored: dict[str, Any], config: ExperimentConfig, seed: int, steps: int):
    names = config_diff(ExperimentConfig.model_validate(stored["config"]), config)
    if stored.get("seed") != seed:
        names.append("seed")
    if stored.get("steps") != steps:
        names.append("steps")
    return names


def run_ppo_seed(
    config: ExperimentConfig,
    seed: int,
    out: Path,
    *,
    resume: bool = False,
    steps_override: int | None = None,
) -> Path:
    """Train MaskablePPO for one seed of `config` into the run folder `out`; return `out`.

    The opponents are an `OpponentMix` of the config's specs, each repeated `weight` times; the
    reward is `REWARDS[config.reward]`; the network is `policy_kwargs(config.hidden)`. The step
    budget is `steps_override` or `config.steps`; the run ends at the first rollout end at or past
    it. `checkpoint_every=None` means only the final checkpoint.

    `resume=False` raises FileExistsError when `out` already has a `config.json`. `resume=True`
    raises `ResumeError` naming each differing setting when the config, the seed or the budget
    differs from `config.json`; with `done.json` present it returns without training; otherwise it
    loads the newest complete checkpoint (none: from step 0), drops the `ppo.csv` rows past its
    step (and with `save_games` the `games.jsonl` lines past it and a broken last line) and trains
    up to the budget. Raises ValueError before any file is written on an unknown
    opponent spec or a `checkpoint_every` that is not a multiple of `N_STEPS`.
    """
    out = Path(out)
    steps = config.steps if steps_override is None else steps_override
    assert steps is not None  # a ppo config always has steps
    _check(config, steps)
    config_path = out / "config.json"
    if config_path.is_file():
        if not resume:
            raise FileExistsError(f"{out} already has a config.json: pass resume=True")
        stored = json.loads(config_path.read_text())
        problems = _resume_problems(stored, config, seed, steps)
        if problems:
            raise ResumeError(f"cannot resume {out}: differs from config.json in {problems}")
        if (out / "done.json").is_file():
            return out
    else:
        out.mkdir(parents=True, exist_ok=True)
        stored = {
            "config": config.model_dump(mode="json"),
            "seed": seed,
            "steps": steps,
            "rules": RULES,
            "n_steps": N_STEPS,
            "batch_size": BATCH_SIZE,
            "git_commit": git_commit(),
            "versions": library_versions(),
        }
        config_path.write_text(json.dumps(stored, indent=2) + "\n")

    from sb3_contrib import MaskablePPO

    env = _RecordingEnv(
        seat="random",
        opponent=OpponentMix(_opponent_specs(config), seed, RULES),
        rules=RULES,
        reward_fn=REWARDS[config.reward],
    )
    csv_path = out / "ppo.csv"
    checkpoint = newest_complete_checkpoint(out)
    if checkpoint is None:
        start = 0
        model = MaskablePPO(
            "MlpPolicy",
            env,
            n_steps=N_STEPS,
            batch_size=BATCH_SIZE,
            seed=seed,
            device="cpu",
            policy_kwargs=policy_kwargs(config.hidden),
        )
    else:
        start = int(CHECKPOINT_RE.fullmatch(checkpoint.name).group(1))
        model = MaskablePPO.load(str(checkpoint), env=env, device="cpu")
        model.set_random_seed(seed)
        model._last_obs = None  # the saved observation belongs to the old env: reset on learn
    kept = [row for row in _read_rows(csv_path) if row and int(row[0]) <= start]
    _write_rows(csv_path, kept)
    wall_offset = float(kept[-1][-1]) if kept else 0.0
    games = None
    if config.save_games:
        _trim_games(out / GAMES_FILE, start)
        games = (out / GAMES_FILE).open("a", encoding="utf-8")

    callback = _make_callback(out, csv_path, config.checkpoint_every, wall_offset, games)
    try:
        model.learn(
            total_timesteps=max(0, steps - int(model.num_timesteps)),
            callback=callback,
            reset_num_timesteps=False,
        )
    finally:
        if games is not None:
            games.close()
    final = int(model.num_timesteps)
    if not (out / "checkpoints" / f"step_{final}.zip").is_file():
        _save_checkpoint(model, out, final)
    rows = _read_rows(csv_path)
    train_seconds = float(rows[-1][-1]) if rows else wall_offset
    done = {"steps": final, "train_seconds": train_seconds}
    (out / "done.json").write_text(json.dumps(done, indent=2) + "\n")
    return out


def _make_callback(
    out: Path, csv_path: Path, every: int | None, wall_offset: float, games: Any = None
) -> Any:
    """The callback that writes one `ppo.csv` row per rollout and the periodic checkpoints, and
    with an open `games` file one `games.jsonl` line per finished game (`step` is the run step at
    the end of the game).

    SB3 records the `train/*` values of rollout k in `train()`, after the rollout callbacks of
    rollout k, so the row of rollout k is made at the start of the next rollout or at the end of
    training. The row is written before the checkpoint, so a checkpoint always has its row.
    """
    from stable_baselines3.common.callbacks import BaseCallback

    started = time.monotonic()

    class PPORun(BaseCallback):
        def __init__(self) -> None:
            super().__init__()
            self.finished: list[float] = []
            self.pending: list[float] | None = None  # rewards of a rollout that has no row yet

        def _on_step(self) -> bool:
            infos = self.locals["infos"]
            for reward, done, info in zip(
                self.locals["rewards"], self.locals["dones"], infos, strict=True
            ):
                if done:  # the reward is paid once, at the end of the game
                    self.finished.append(float(reward))
                    if games is not None:
                        line = {"step": int(self.num_timesteps), **info[GAME_INFO]}
                        games.write(json.dumps(line) + "\n")
                        games.flush()
            return True

        def _on_rollout_end(self) -> None:
            self.pending, self.finished = self.finished, []

        def _on_rollout_start(self) -> None:
            self._flush()

        def _on_training_end(self) -> None:
            self._flush()

        def _flush(self) -> None:
            if self.pending is None:
                return
            finished, self.pending = self.pending, None
            values = self.model.logger.name_to_value
            steps = int(self.num_timesteps)
            row: dict[str, Any] = {
                "steps": steps,
                "mean_reward": sum(finished) / len(finished) if finished else "",
                "games": len(finished),
                "entropy": -float(values["train/entropy_loss"]),
                "wall_seconds": round(wall_offset + time.monotonic() - started, 3),
            }
            row.update({column: float(values[key]) for column, key in _LOGGER_KEYS.items()})
            with csv_path.open("a", newline="") as handle:
                csv.writer(handle).writerow([row[c] for c in PPO_COLUMNS])
                handle.flush()
                os.fsync(handle.fileno())
            if every is not None and steps % every == 0:
                if games is not None:  # the games of a checkpoint are on disk before it
                    os.fsync(games.fileno())
                _save_checkpoint(self.model, out, steps)

    return PPORun()
