"""Live and final evaluation of the checkpoints of a run folder (PPO or BC).

`watch_run` runs in its own process next to a training: it polls the run folder and measures
every new complete checkpoint (`checkpoints/step_<n>.zip` of a PPO run, `checkpoints/epoch_<n>.pt`
of a BC run) against each of `EVAL_OPPONENTS` in each play mode, and appends the rows to
`eval.csv`. `final_eval` measures the checkpoint with the highest n with the fixed protocol and
writes `final_eval.csv`. Both use `evaluate` with the rules of the run's `config.json`.

torch and SB3 are imported inside the functions, so this module imports without the `rl`
dependency group.

CLI: `python -m quack_rl.rl.live_eval RUN_DIR [--games N] [--seed S] [--modes greedy,sampled]
[--final]`.
"""

import argparse
import csv
import json
import os
import re
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from quack_rl.rl.evaluate import evaluate
from quack_rl.rl.experiment import EVAL_OPPONENTS
from quack_rl.rl.policy_bot import mode_params

EVAL_COLUMNS = (
    "step",
    "opponent",
    "mode",
    "games",
    "wins",
    "draws",
    "losses",
    "win_rate",
    "ci_low",
    "ci_high",
)
EVAL_FILE = "eval.csv"
FINAL_FILE = "final_eval.csv"
# a temporary file (`step_<n>.tmp.zip`, `epoch_<n>.tmp.pt`) does not match
CHECKPOINT_RES = (re.compile(r"step_(\d+)\.zip"), re.compile(r"epoch_(\d+)\.pt"))
WATCH_GAMES, WATCH_SEED = 50, 0
FINAL_GAMES, FINAL_SEED = 200, 2026
DEFAULT_MODES: tuple[str, ...] = ("greedy", "sampled")


def complete_checkpoints(run_dir: Path) -> list[tuple[int, Path]]:
    """The complete checkpoints of `run_dir` as (n, path), ascending by n; [] if none."""
    folder = Path(run_dir) / "checkpoints"
    if not folder.is_dir():
        return []
    found = []
    for path in folder.iterdir():
        for pattern in CHECKPOINT_RES:
            if path.is_file() and (m := pattern.fullmatch(path.name)):
                found.append((int(m.group(1)), path))
    return sorted(found)


def _check_modes(modes: Sequence[str]) -> None:
    if not modes:
        raise ValueError("modes must name at least one mode")
    for mode in modes:
        mode_params(mode, None)  # raises ValueError on an unknown mode


def _load_policy(path: Path, config: dict[str, Any]) -> Any:
    """A factory `make(mode, seed) -> bot` for the checkpoint `path`; loads the weights once."""
    rules = config["rules"]
    if path.suffix == ".zip":
        from sb3_contrib import MaskablePPO

        from quack_rl.rl.policy_bot import PolicyBot

        model = MaskablePPO.load(str(path), device="cpu")
        return lambda mode, seed: PolicyBot(model, rules, path.stem, mode, seed)
    import torch

    from quack_rl.rl.offline import OfflinePolicy, make_mlp

    net = make_mlp(
        int(config["obs_dim"]), int(config["n_actions"]), int(config["config"]["hidden"])
    )
    net.load_state_dict(torch.load(path, map_location="cpu", weights_only=True))
    return lambda mode, seed: OfflinePolicy(net, rules, path.stem, mode=mode, seed=seed)


def _evaluate_checkpoint(
    step: int, path: Path, config: dict[str, Any], games: int, seed: int, modes: Sequence[str]
) -> list[list[Any]]:
    """The `EVAL_COLUMNS` rows of one checkpoint: one per opponent and mode, each with a fresh bot
    seeded with `seed`."""
    make = _load_policy(path, config)
    rows = []
    for opponent in EVAL_OPPONENTS:
        for mode in modes:
            result = evaluate(make(mode, seed), opponent, games, seed, config["rules"])
            rows.append(
                [
                    step,
                    opponent,
                    mode,
                    result.games,
                    result.wins,
                    result.draws,
                    result.losses,
                    result.win_rate,
                    result.ci_low,
                    result.ci_high,
                ]
            )
    return rows


def _read_config(run_dir: Path) -> dict[str, Any] | None:
    path = run_dir / "config.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:  # written but not complete yet: read it on the next poll
        return None


def evaluated_steps(csv_path: Path) -> set[int]:
    """The steps that have rows in `csv_path` (a broken row is ignored); empty if no file."""
    if not csv_path.is_file():
        return set()
    steps = set()
    with csv_path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                steps.add(int(row["step"]))
            except (TypeError, ValueError, KeyError):
                continue
    return steps


def _append_rows(csv_path: Path, rows: list[list[Any]]) -> None:
    """Append `rows` in one write (with the header when the file is new) and sync it."""
    new = not csv_path.is_file() or csv_path.stat().st_size == 0
    with csv_path.open("a", newline="") as handle:
        writer = csv.writer(handle)
        if new:
            writer.writerow(EVAL_COLUMNS)
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())


def watch_run(
    run_dir: Path,
    *,
    games: int,
    seed: int,
    modes: tuple[str, ...],
    poll_seconds: float = 30.0,
) -> None:
    """Evaluate every complete checkpoint of `run_dir` once against each of `EVAL_OPPONENTS` in
    each of `modes`, appending the rows of one checkpoint together to `run_dir/eval.csv` in
    ascending n. A checkpoint whose step already has rows in `eval.csv` is skipped, so a restart
    writes no duplicates. While the folder, `checkpoints/`, `config.json` or a new checkpoint is
    missing it polls every `poll_seconds`; it returns once `done.json` exists and every checkpoint
    has rows (with `done.json` and no checkpoint: without rows). Raise ValueError on an unknown
    mode."""
    _check_modes(modes)
    run_dir = Path(run_dir)
    csv_path = run_dir / EVAL_FILE
    while True:
        # done.json is written after the last checkpoint: read it first, so a checkpoint listed
        # below is never newer than the done flag
        done = (run_dir / "done.json").is_file()
        evaluated = evaluated_steps(csv_path)
        pending = [(n, p) for n, p in complete_checkpoints(run_dir) if n not in evaluated]
        if not pending:
            if done:
                return
            time.sleep(poll_seconds)
            continue
        config = _read_config(run_dir)
        if config is None:
            time.sleep(poll_seconds)
            continue
        for step, path in pending:
            _append_rows(csv_path, _evaluate_checkpoint(step, path, config, games, seed, modes))


def final_eval(
    run_dir: Path,
    *,
    games: int = FINAL_GAMES,
    seed: int = FINAL_SEED,
    modes: tuple[str, ...] = DEFAULT_MODES,
) -> Path:
    """Evaluate the checkpoint of `run_dir` with the highest n like `watch_run` and write
    (overwrite) `run_dir/final_eval.csv`; return its path. Raise FileNotFoundError when the run
    has no complete checkpoint or no `config.json`, ValueError on an unknown mode."""
    _check_modes(modes)
    run_dir = Path(run_dir)
    checkpoints = complete_checkpoints(run_dir)
    if not checkpoints:
        raise FileNotFoundError(f"{run_dir} has no complete checkpoint")
    config = _read_config(run_dir)
    if config is None:
        raise FileNotFoundError(f"{run_dir} has no readable config.json")
    step, path = checkpoints[-1]
    rows = _evaluate_checkpoint(step, path, config, games, seed, modes)
    out = run_dir / FINAL_FILE
    tmp = out.with_name(out.name + ".tmp")
    with tmp.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(EVAL_COLUMNS)
        writer.writerows(rows)
    os.replace(tmp, out)
    return out


def _parse_modes(text: str) -> tuple[str, ...]:
    modes = tuple(part.strip() for part in text.split(",") if part.strip())
    try:
        _check_modes(modes)
    except ValueError as err:
        raise argparse.ArgumentTypeError(str(err)) from err
    return modes


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m quack_rl.rl.live_eval",
        description="Evaluate the checkpoints of a run folder while it trains, or the last one.",
    )
    parser.add_argument("run_dir", metavar="RUN_DIR", type=Path, help="the run folder")
    parser.add_argument(
        "--games",
        type=int,
        default=None,
        help=f"games per opponent and mode (default {WATCH_GAMES}, with --final {FINAL_GAMES})",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help=f"chance seed of the first game (default {WATCH_SEED}, with --final {FINAL_SEED})",
    )
    parser.add_argument(
        "--modes",
        type=_parse_modes,
        default=DEFAULT_MODES,
        help="comma-separated play modes (default greedy,sampled)",
    )
    parser.add_argument(
        "--final",
        action="store_true",
        help="run only the final evaluation of the last checkpoint into final_eval.csv",
    )
    args = parser.parse_args(argv)
    if args.final:
        games = FINAL_GAMES if args.games is None else args.games
        seed = FINAL_SEED if args.seed is None else args.seed
        print(final_eval(args.run_dir, games=games, seed=seed, modes=args.modes))
    else:
        games = WATCH_GAMES if args.games is None else args.games
        seed = WATCH_SEED if args.seed is None else args.seed
        watch_run(args.run_dir, games=games, seed=seed, modes=args.modes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
