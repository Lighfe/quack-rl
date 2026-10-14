"""Train a MaskablePPO agent against snapshots of itself and write its run folder.

Usage: uv run --group train python scripts/train_selfplay.py --run NAME [--steps N]
       [--update-every N] [--rules v1.1] [--seed 0] [--eval-games 500]
       [--eval-bot NAME ...] [--runs-dir data/runs]

The run folder `<runs-dir>/<NAME>` has the normal run files, `checkpoints/step_<n>.zip` (the
snapshots) and `selfplay.csv` (the evaluation at each update).
Spec: docs/specs/2026-10-13-self-play.md.
"""

import argparse
import sys
from pathlib import Path

from quack_rl.rl.selfplay import DEFAULT_EVAL_BOTS, DEFAULT_UPDATE_EVERY, train_selfplay

DEFAULT_STEPS = 200_000


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="train_selfplay.py", description="Self-play training of MaskablePPO."
    )
    p.add_argument(
        "--run", required=True, metavar="NAME", help="run name (folder under --runs-dir)"
    )
    p.add_argument(
        "--steps",
        type=int,
        default=DEFAULT_STEPS,
        help="decisions of the learner, about 42 per game (default: %(default)s)",
    )
    p.add_argument(
        "--update-every",
        type=int,
        default=DEFAULT_UPDATE_EVERY,
        metavar="N",
        help="save a snapshot and evaluate every N steps (default: %(default)s)",
    )
    p.add_argument("--rules", default="v1.1", help="ruleset version (default: %(default)s)")
    p.add_argument("--seed", type=int, default=0, help="seed (default: %(default)s)")
    p.add_argument(
        "--eval-games", type=int, default=500, help="games per evaluation (default: %(default)s)"
    )
    p.add_argument(
        "--eval-bot",
        action="append",
        metavar="NAME",
        help="heuristic bot to evaluate against at each update, repeatable "
        f"(default: {', '.join(DEFAULT_EVAL_BOTS)})",
    )
    p.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("data/runs"),
        help="folder for run folders (default: %(default)s)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = train_selfplay(
            args.run,
            args.steps,
            update_every=args.update_every,
            rules=args.rules,
            seed=args.seed,
            eval_games=args.eval_games,
            eval_bots=tuple(args.eval_bot or DEFAULT_EVAL_BOTS),
            runs_dir=args.runs_dir,
        )
    except (ValueError, FileExistsError, ImportError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 2
    g = result.trained_greedy
    print(f"run folder: {args.runs_dir / args.run}")
    print(f"games_played: {result.games_played}")
    print(f"trained (greedy) vs random: {g.wins} wins, {g.draws} draws, {g.losses} losses")
    return 0


if __name__ == "__main__":
    sys.exit(main())
