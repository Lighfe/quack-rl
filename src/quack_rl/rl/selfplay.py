"""Self-play training: MaskablePPO against snapshots of itself.

Spec: docs/specs/2026-10-13-self-play.md.

The opponent of an episode is drawn at the episode reset from a pool: the newest snapshot with
probability `SHARE_NEWEST`, an older one (uniform) with `SHARE_OLDER`, `random` with
`SHARE_RANDOM`. The pool is the list of the files `checkpoints/step_<n>.zip` of the run folder; a
snapshot is loaded only when it is drawn, and at most `MAX_LOADED` stay loaded. Every
`update_every` training steps (decisions of the learner) a snapshot is saved, added to the pool and
the learner is evaluated (`evaluate`, `seed=0`).

Besides the normal run files the loop writes `selfplay.csv`, one row per update:

- `timestep`: training step of the update
- `snapshot`: file name of the snapshot saved at this update (`step_<n>.zip`)
- `games`: games per evaluation
- `vs_random`: win rate of the learner against `RandomBot`
- `vs_heuristics`: JSON object, bot name -> win rate (the bots of `eval_bots` in the config)
- `vs_snapshots`: JSON object, snapshot file name -> win rate, for each snapshot of the pool
  before this update (empty object at the first update)
- `vs_previous_newest`: win rate against the newest snapshot of the previous update (empty at the
  first update)
- `readout`: how the learner was evaluated in this row, `greedy` or `sampled`

The learner is evaluated with the read-out `readout` of `train_selfplay` (default `greedy`, the
most likely action; `sampled` draws from the policy, the way it is trained). SB3 and torch are imported inside the
functions, so this module imports without the `train` group.
"""

import csv
import json
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

from quack_rl.rl.evaluate import EvalResult, Policy, evaluate, random_policy
from quack_rl.rl.opponents import make_opponent
from quack_rl.rl.policy_bot import DEFAULT_READOUT, PolicyBot, check_readout
from quack_rl.rl.single_env import QuackEnv
from quack_rl.rl.train import N_STEPS, TrainingLog, TrainResult, _import_sb3, sb3_policy

SHARE_NEWEST = 0.5
SHARE_OLDER = 0.3
SHARE_RANDOM = 0.2
MAX_LOADED = 3  # snapshots kept loaded at the same time
DEFAULT_UPDATE_EVERY = 50_000
DEFAULT_EVAL_BOTS = ("draw20-pts1-points",)  # the heuristic baseline of the tournament field
EVAL_SEED = 0
SELFPLAY_COLUMNS = (
    "timestep",
    "snapshot",
    "games",
    "vs_random",
    "vs_heuristics",
    "vs_snapshots",
    "vs_previous_newest",
    "readout",
)

Loader = Callable[[Path], Any]  # snapshot file -> bot


def load_snapshot_bot(path: Path, rules: str = "v1.1") -> PolicyBot:
    """A `PolicyBot` (most likely action) from a checkpoint file; needs the `train` group."""
    from sb3_contrib import MaskablePPO

    model = MaskablePPO.load(str(path), device="cpu")

    def policy(obs: np.ndarray, mask: np.ndarray) -> int:
        action, _ = model.predict(obs, action_masks=mask, deterministic=True)
        return int(action)

    return PolicyBot(policy, rules, name=f"snapshot:{path.name}")


class SnapshotCache:
    """Load snapshots through `loader` when they are drawn; keep the last `max_loaded`."""

    def __init__(self, loader: Loader, max_loaded: int = MAX_LOADED):
        self._loader = loader
        self._max = max_loaded
        self._loaded: OrderedDict[Path, Any] = OrderedDict()

    def __call__(self, path: Path) -> Any:
        if path in self._loaded:
            self._loaded.move_to_end(path)
            return self._loaded[path]
        bot = self._loader(path)
        self._loaded[path] = bot
        while len(self._loaded) > self._max:
            self._loaded.popitem(last=False)
        return bot

    @property
    def loaded(self) -> list[Path]:
        return list(self._loaded)


class PoolOpponent:
    """The opponent of the training env: redrawn from the pool at every episode reset.

    The pool is a list of snapshot files, oldest first; `add` appends one. With no snapshot the
    opponent is `random`; with one snapshot "older" falls back to the newest.
    """

    def __init__(self, loader: Loader, rules: str = "v1.1", seed: int = 0):
        self.rules = rules
        self.pool: list[Path] = []
        self.cache = SnapshotCache(loader)
        self._rng = np.random.default_rng(seed)
        self._random_seed = seed
        self._current: Any = make_opponent("random", seed, rules)
        self.last_draw: str = "random"

    kind = "bot"
    name = "pool"
    params: dict = {}

    def add(self, path: Path) -> None:
        self.pool.append(Path(path))

    def draw(self) -> Path | None:
        """The snapshot to play against, or None for `random`."""
        if not self.pool:
            return None
        u = self._rng.random()
        if u < SHARE_NEWEST:
            return self.pool[-1]
        if u < SHARE_NEWEST + SHARE_OLDER:
            older = self.pool[:-1]
            if not older:
                return self.pool[-1]
            return older[int(self._rng.integers(len(older)))]
        return None

    def new_episode(self) -> None:
        snapshot = self.draw()
        if snapshot is None:
            self._current = make_opponent("random", int(self._rng.integers(2**32)), self.rules)
            self.last_draw = "random"
        else:
            self._current = self.cache(snapshot)
            self.last_draw = snapshot.name

    def choose(self, state, seat, legal):
        return self._current.choose(state, seat, legal)


def _selfplay_env(opponent: PoolOpponent, rules: str):
    import gymnasium as gym

    class SelfPlayEnv(gym.Wrapper):
        """Redraw the opponent at each reset; copy info["episode"] to info["quack_episode"]."""

        def reset(self, **kwargs):
            opponent.new_episode()
            return self.env.reset(**kwargs)

        def step(self, action):
            obs, rew, term, trunc, info = self.env.step(action)
            if "episode" in info:
                info["quack_episode"] = info["episode"]
            return obs, rew, term, trunc, info

        def action_masks(self):
            return self.env.action_masks()

    return SelfPlayEnv(QuackEnv(seat="random", rules=rules, opponent=opponent))


def _win_rate(policy: Policy, opponent: Any, rules: str, games: int) -> float:
    return evaluate(policy, opponent, rules=rules, games=games, seed=EVAL_SEED).win_rate


def evaluate_update(
    policy: Policy,
    pool: list[Path],
    previous_newest: Path | None,
    loader: Loader,
    rules: str,
    games: int,
    eval_bots: tuple[str, ...],
    timestep: int,
    snapshot: str,
    readout: str = DEFAULT_READOUT,
) -> dict:
    """One row of `selfplay.csv`: the learner's win rates (see the module docstring).

    `pool` holds the snapshots before the one saved at this update. `readout` is written to the
    row; the caller built `policy` with it.
    """
    # a fresh bot per name: `evaluate` builds it per game from the name
    return {
        "timestep": timestep,
        "snapshot": snapshot,
        "games": games,
        "vs_random": _win_rate(policy, "random", rules, games),
        "vs_heuristics": json.dumps(
            {name: _win_rate(policy, name, rules, games) for name in eval_bots}
        ),
        "vs_snapshots": json.dumps(
            {p.name: _win_rate(policy, loader(p), rules, games) for p in pool}
        ),
        "vs_previous_newest": (
            ""
            if previous_newest is None
            else _win_rate(policy, loader(previous_newest), rules, games)
        ),
        "readout": readout,
    }


def append_selfplay_row(path: Path, row: dict) -> None:
    new = not path.exists()
    with path.open("a", newline="") as f:
        writer = csv.DictWriter(f, SELFPLAY_COLUMNS)
        if new:
            writer.writeheader()
        writer.writerow(row)


def train_selfplay(
    run: str,
    steps: int,
    update_every: int = DEFAULT_UPDATE_EVERY,
    rules: str = "v1.1",
    seed: int = 0,
    eval_games: int = 500,
    eval_bots: tuple[str, ...] = DEFAULT_EVAL_BOTS,
    runs_dir: Path = Path("data/runs"),
    loader: Loader | None = None,
    readout: str = DEFAULT_READOUT,
) -> TrainResult:
    """Train MaskablePPO for `steps` decisions of the learner against its own snapshots.

    Writes the run folder `runs_dir / run` (a name that exists is refused before training): the
    normal run files, `checkpoints/step_<n>.zip` every `update_every` steps and `selfplay.csv`.
    At the end the learner is evaluated against `random` like `train` does.

    `readout` (`greedy` or `sampled`, default `greedy`) selects how the learner is evaluated at each
    update; `selfplay.csv` records it per row. The snapshots of the opponent pool and of the
    evaluation always keep the greedy read-out of `load_snapshot_bot`. Another value raises
    ValueError before any training starts.
    """
    from quack_rl.rl.runs import RunFolder, run_path

    check_readout(readout)
    if steps < 1:
        raise ValueError(f"steps must be at least 1, not {steps}")
    if update_every < 1:
        raise ValueError(f"update_every must be at least 1, not {update_every}")
    if eval_games < 1:
        raise ValueError(f"eval_games must be at least 1, not {eval_games}")
    for name in eval_bots:
        make_opponent(name, seed=seed, rules=rules)  # ValueError on an unknown name
    folder = RunFolder(run_path(runs_dir, run))  # refuses a bad or existing name
    MaskablePPO, BaseCallback, KVWriter, Logger = _import_sb3()

    raw_loader = loader or _default_loader(rules)
    opponent = PoolOpponent(raw_loader, rules=rules, seed=seed)
    cache = opponent.cache  # evaluations share the loaded snapshots
    log = TrainingLog()
    config = {
        "mode": "selfplay",
        "steps": steps,
        "rules": rules,
        "opponent": "selfplay",
        "seed": seed,
        "eval_games": eval_games,
        "update_every": update_every,
        "pool_shares": {
            "newest": SHARE_NEWEST,
            "older": SHARE_OLDER,
            "random": SHARE_RANDOM,
        },
        "max_loaded": MAX_LOADED,
        "eval_bots": list(eval_bots),
        "readout": readout,
    }
    folder.start(config)
    selfplay_csv = folder.path / "selfplay.csv"
    state = {"previous_newest": None}

    class SelfPlayCallback(BaseCallback):
        def _on_training_start(self) -> None:
            self._last = 0

        def _on_step(self) -> bool:
            n = int(self.num_timesteps)
            if n // update_every > self._last // update_every:
                self._last = n
                self._update(n - n % update_every)
            for info in self.locals["infos"]:
                ep = info.get("quack_episode")
                if ep is None:
                    continue
                row = {
                    "episode": len(log.episodes) + 1,
                    "timestep": n,
                    "result": ep["result"],
                    "points_own": ep["points"]["own"],
                    "points_opponent": ep["points"]["opponent"],
                    "explosions_own": ep["explosions"]["own"],
                    "decisions": ep["decisions"],
                }
                log.episodes.append(row)
                folder.episode(row)
            return True

        def _update(self, timestep: int) -> None:
            before = list(opponent.pool)
            folder.checkpoint(self.model, timestep)
            snapshot = folder.path / "checkpoints" / f"step_{timestep}.zip"
            row = evaluate_update(
                sb3_policy(self.model, readout == "greedy"), before, state["previous_newest"],
                cache, rules, eval_games, eval_bots, timestep, snapshot.name, readout,
            )  # fmt: skip
            append_selfplay_row(selfplay_csv, row)
            opponent.add(snapshot)
            state["previous_newest"] = snapshot

    class MetricsWriter(KVWriter):
        def write(self, key_values, key_excluded, step=0):
            from quack_rl.rl.train import _METRIC_KEYS

            row: dict[str, Any] = {"timestep": int(step)}
            for name in _METRIC_KEYS:
                if f"train/{name}" in key_values:
                    row[name] = float(key_values[f"train/{name}"])
            if len(row) == 1:
                return
            log.metrics.append(row)
            folder.metrics(row)

        def close(self) -> None:
            pass

    env = _selfplay_env(opponent, rules)
    env.reset(seed=seed)
    model = MaskablePPO(
        "MlpPolicy", env, n_steps=N_STEPS, batch_size=64, seed=seed, device="cpu", verbose=0
    )
    model.set_logger(Logger(None, [MetricsWriter()]))

    def ev(policy: Policy) -> EvalResult:
        return evaluate(policy, "random", rules=rules, games=eval_games, seed=EVAL_SEED)

    baseline_random = ev(random_policy(seed))
    baseline_untrained = ev(sb3_policy(model, deterministic=False))
    model.learn(total_timesteps=steps, callback=SelfPlayCallback())
    result = TrainResult(
        model=model,
        log=log,
        baseline_random=baseline_random,
        baseline_untrained=baseline_untrained,
        trained_sampled=ev(sb3_policy(model, False)),
        trained_greedy=ev(sb3_policy(model, True)),
        games_played=len(log.episodes),
    )
    folder.finish(result)
    return result


def _default_loader(rules: str) -> Loader:
    def load(path: Path) -> PolicyBot:
        return load_snapshot_bot(Path(path), rules)

    return load
