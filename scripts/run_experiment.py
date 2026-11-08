"""Run one experiment: for each seed a training process and an evaluator process side by side,
then the final evaluation of each seed and a summary table.

Usage: uv run --group rl python scripts/run_experiment.py --config experiments/<id>.json \
    --out data/experiments [--seeds 0,1,2] [--steps N] [--resume] [--threads N]

The run folder of seed k is <out>/<id>/seed<k>/. Each seed gets one training process
(`run_ppo_seed` or `run_bc_seed`, by the config's `kind`) and one evaluator process
(`python -m quack_rl.rl.live_eval`, the config's `live_eval_games`, modes greedy and sampled).
When all of them have ended, each seed's last checkpoint gets the final evaluation
(`final_eval_games`, `final_eval_seed`, modes greedy and sampled) and one table is printed.

--seeds picks seeds from the config's `seeds`; --steps overrides the step budget of a ppo config
(for trial runs); --resume continues the seed folders that exist; --threads sets
OMP_NUM_THREADS and MKL_NUM_THREADS of each child (default 1). When a child fails, or on Ctrl-C
or SIGTERM, the command stops all children. This command saves no agent.

Exit codes: 0 done, 1 a seed folder is in the way or a child failed, 2 a usage error,
130 Ctrl-C, 143 SIGTERM.
"""

import argparse
import csv
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from quack_rl.rl.experiment import ExperimentConfig, load_config
from quack_rl.rl.live_eval import FINAL_FILE

SCRIPT = Path(__file__).resolve()
TRAIN_COMMAND = "_train"  # the hidden first argument of a training child
MODES = "greedy,sampled"
STOP_SECONDS = 10.0  # how long a child gets after SIGTERM before SIGKILL
WAIT_SECONDS = 0.5


class UsageError(Exception):
    """A wrong argument: exit code 2, no process started."""


class FolderError(Exception):
    """A seed folder in the way: exit code 1, no process started."""


class Stopped(Exception):
    """SIGTERM arrived."""


@dataclass
class Child:
    seed: int
    role: str  # "training", "evaluator" or "final evaluation"
    cmd: list[str]
    env: dict[str, str]
    proc: subprocess.Popen | None = field(default=None, repr=False)


def child_env(threads: int, base: dict[str, str] | None = None) -> dict[str, str]:
    """The environment of a child: `base` (default `os.environ`) with `OMP_NUM_THREADS` and
    `MKL_NUM_THREADS` set to `threads`."""
    env = dict(os.environ if base is None else base)
    env["OMP_NUM_THREADS"] = str(threads)
    env["MKL_NUM_THREADS"] = str(threads)
    return env


def parse_seeds(text: str) -> list[int]:
    try:
        seeds = [int(part) for part in text.split(",") if part.strip()]
    except ValueError as err:
        raise argparse.ArgumentTypeError(
            f"--seeds needs integers like 0,1,2, not {text!r}"
        ) from err
    if not seeds:
        raise argparse.ArgumentTypeError("--seeds names no seed")
    if len(set(seeds)) != len(seeds):
        raise argparse.ArgumentTypeError(f"--seeds has duplicates: {text}")
    return seeds


def positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError as err:
        raise argparse.ArgumentTypeError(f"needs an integer, not {text!r}") from err
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be at least 1, not {value}")
    return value


def seed_dir(out: Path, config: ExperimentConfig, seed: int) -> Path:
    return Path(out) / config.id / f"seed{seed}"


def pick_seeds(config: ExperimentConfig, seeds: list[int] | None) -> list[int]:
    """The seeds to run: `seeds` or the config's. Raise UsageError on a seed the config lacks."""
    if seeds is None:
        return list(config.seeds)
    unknown = [s for s in seeds if s not in config.seeds]
    if unknown:
        raise UsageError(f"seeds {unknown} are not in the config's seeds {config.seeds}")
    return seeds


def check_folders(config: ExperimentConfig, run_dirs: dict[int, Path], resume: bool) -> None:
    """Raise FolderError when a seed folder is in the way of this run."""
    for run_dir in run_dirs.values():
        if not (run_dir / "config.json").is_file():
            continue
        if not resume:
            raise FolderError(f"{run_dir} already has a config.json: pass --resume to continue it")
        if config.kind == "bc" and not (run_dir / "done.json").is_file():
            raise FolderError(
                f"{run_dir} is an unfinished BC run, and BC cannot resume: "
                "delete that folder and run again"
            )


def run_children_for(
    config: ExperimentConfig,
    config_path: Path,
    seed: int,
    run_dir: Path,
    *,
    steps: int | None,
    resume: bool,
    threads: int,
    eval_poll: float,
) -> list[Child]:
    """The training and evaluator children of one seed. A BC seed with `done.json` gets no
    training child (it cannot resume); a PPO seed always gets one, since `run_ppo_seed` returns
    without training on `done.json` after it checked the config, seed and budget."""
    env = child_env(threads)
    children = []
    finished_bc = config.kind == "bc" and (run_dir / "done.json").is_file()
    if not finished_bc:
        cmd = [
            sys.executable,
            str(SCRIPT),
            TRAIN_COMMAND,
            "--config",
            str(config_path),
            "--seed",
            str(seed),
            "--out",
            str(run_dir),
        ]
        if steps is not None:
            cmd += ["--steps", str(steps)]
        if resume:
            cmd.append("--resume")
        children.append(Child(seed, "training", cmd, env))
    evaluator = [
        sys.executable,
        "-m",
        "quack_rl.rl.live_eval",
        str(run_dir),
        "--games",
        str(config.live_eval_games),
        "--modes",
        MODES,
        "--poll",
        str(eval_poll),
    ]
    children.append(Child(seed, "evaluator", evaluator, env))
    return children


def final_child(config: ExperimentConfig, seed: int, run_dir: Path, threads: int) -> Child:
    cmd = [
        sys.executable,
        "-m",
        "quack_rl.rl.live_eval",
        str(run_dir),
        "--final",
        "--games",
        str(config.final_eval_games),
        "--seed",
        str(config.final_eval_seed),
        "--modes",
        MODES,
    ]
    return Child(seed, "final evaluation", cmd, child_env(threads))


def stop_children(children: list[Child]) -> None:
    """Stop every child that still runs (its whole process group): SIGTERM, then SIGKILL after
    `STOP_SECONDS`; return when all have ended."""
    alive = [c for c in children if c.proc is not None and c.proc.poll() is None]
    for child in alive:
        _signal_group(child, signal.SIGTERM)
    deadline = time.monotonic() + STOP_SECONDS
    for child in alive:
        assert child.proc is not None
        try:
            child.proc.wait(max(0.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            _signal_group(child, signal.SIGKILL)
            child.proc.wait()


def _signal_group(child: Child, signum: int) -> None:
    assert child.proc is not None
    try:
        os.killpg(child.proc.pid, signum)
    except ProcessLookupError:
        pass


def run_children(children: list[Child]) -> str | None:
    """Start all `children` and wait until all have ended. When one fails, stop the others and
    return a message naming its seed and role; None when all ended with code 0. Each child runs
    in its own session, so a Ctrl-C reaches only this process, which then stops the children."""
    try:
        for child in children:
            child.proc = subprocess.Popen(child.cmd, env=child.env, start_new_session=True)
        while True:
            running = False
            for child in children:
                assert child.proc is not None
                code = child.proc.poll()
                if code is None:
                    running = True
                elif code != 0:
                    stop_children(children)
                    return f"seed {child.seed}: the {child.role} process failed (exit code {code})"
            if not running:
                return None
            time.sleep(WAIT_SECONDS)
    except BaseException:
        stop_children(children)
        raise


def summary_table(run_dirs: dict[int, Path]) -> str:
    """One line per seed, opponent and mode of the `final_eval.csv` files."""
    lines = [f"{'seed':>4}  {'opponent':<28}  {'mode':<8}  win rate [95% interval]"]
    for seed, run_dir in run_dirs.items():
        with (run_dir / FINAL_FILE).open(newline="") as handle:
            for row in csv.DictReader(handle):
                rate = (
                    f"{float(row['win_rate']):.3f} "
                    f"[{float(row['ci_low']):.3f}, {float(row['ci_high']):.3f}]"
                )
                lines.append(f"{seed:>4}  {row['opponent']:<28}  {row['mode']:<8}  {rate}")
    return "\n".join(lines)


def _raise_stopped(signum, frame) -> None:
    raise Stopped()


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="scripts/run_experiment.py", description=__doc__.splitlines()[0]
    )
    p.add_argument("--config", type=Path, required=True, help="the experiment config (JSON)")
    p.add_argument("--out", type=Path, required=True, help="the folder of the experiment folders")
    p.add_argument(
        "--seeds", type=parse_seeds, default=None, help="comma-separated seeds of the config"
    )
    p.add_argument(
        "--steps", type=positive_int, default=None, help="step budget of a ppo config (trial runs)"
    )
    p.add_argument("--resume", action="store_true", help="continue the seed folders that exist")
    p.add_argument(
        "--threads", type=positive_int, default=1, help="torch threads per child (default 1)"
    )
    p.add_argument(
        "--eval-poll",
        type=float,
        default=30.0,
        metavar="SECONDS",
        help="seconds between two looks of an evaluator at its run folder (default 30)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == [TRAIN_COMMAND]:
        return train_main(argv[1:])
    args = parser().parse_args(argv)
    try:
        config_path = args.config.resolve()
        try:
            config = load_config(config_path)
        except (OSError, ValueError) as err:
            raise UsageError(f"cannot read the config {args.config}: {err}") from err
        seeds = pick_seeds(config, args.seeds)
        if args.steps is not None and config.kind != "ppo":
            raise UsageError(f"--steps needs a ppo config, {config.id} has kind {config.kind}")
        run_dirs = {seed: seed_dir(args.out, config, seed).resolve() for seed in seeds}
        check_folders(config, run_dirs, args.resume)
    except UsageError as err:
        print(f"error: {err}", file=sys.stderr)
        return 2
    except FolderError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1

    previous = signal.signal(signal.SIGTERM, _raise_stopped)
    try:
        children = [
            child
            for seed, run_dir in run_dirs.items()
            for child in run_children_for(
                config,
                config_path,
                seed,
                run_dir,
                steps=args.steps,
                resume=args.resume,
                threads=args.threads,
                eval_poll=args.eval_poll,
            )
        ]
        print(f"{config.id}: training and evaluating seeds {seeds}", flush=True)
        if failure := run_children(children):
            print(f"error: {failure}", file=sys.stderr)
            return 1
        print(f"{config.id}: final evaluation of seeds {seeds}", flush=True)
        finals = [final_child(config, s, d, args.threads) for s, d in run_dirs.items()]
        if failure := run_children(finals):
            print(f"error: {failure}", file=sys.stderr)
            return 1
    except KeyboardInterrupt:
        print("stopped by Ctrl-C: all children are stopped", file=sys.stderr)
        return 130
    except Stopped:
        print("stopped by SIGTERM: all children are stopped", file=sys.stderr)
        return 143
    finally:
        signal.signal(signal.SIGTERM, previous)
    print(summary_table(run_dirs))
    return 0


def train_main(argv: list[str]) -> int:
    """The training child: train one seed of the config into its run folder."""
    p = argparse.ArgumentParser(prog=f"scripts/run_experiment.py {TRAIN_COMMAND}")
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--steps", type=int, default=None)
    p.add_argument("--resume", action="store_true")
    args = p.parse_args(argv)
    config = load_config(args.config)
    if config.kind == "ppo":
        from quack_rl.rl.ppo_run import run_ppo_seed

        run_ppo_seed(config, args.seed, args.out, resume=args.resume, steps_override=args.steps)
    else:
        from quack_rl.rl.bc_run import run_bc_seed

        run_bc_seed(config, args.seed, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
