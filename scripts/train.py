"""Train a MaskablePPO agent in a dedicated experiment and write its run folder.

Usage: uv run --group train python scripts/train.py --run NAME [--steps N] [--opponent random|<bot>]
       [--rules v1.1] [--seed 0] [--eval-games 500] [--checkpoint-every N] [--runs-dir data/runs]

The run folder `<runs-dir>/<NAME>` is written as the training goes. At the end the script prints
its path and a table of wins, draws and losses of the baselines and the trained policy.
"""

import argparse
import sys
from pathlib import Path

from quack_rl.rl.train import train

DEFAULT_STEPS = 20_000

_ROWS = (
    ("random agent", "baseline_random"),
    ("untrained network", "baseline_untrained"),
    ("trained (sampled)", "trained_sampled"),
    ("trained (greedy)", "trained_greedy"),
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="train.py", description="Train MaskablePPO and write a run folder."
    )
    p.add_argument(
        "--run", required=True, metavar="NAME", help="run name (folder under --runs-dir)"
    )
    p.add_argument(
        "--steps",
        type=int,
        default=DEFAULT_STEPS,
        help="decisions of the agent, about 42 per game (default: %(default)s)",
    )
    p.add_argument(
        "--opponent",
        default="random",
        help="'random' or draw<percent>-pts<round>-<strategy> (default: %(default)s)",
    )
    p.add_argument("--rules", default="v1.1", help="ruleset version (default: %(default)s)")
    p.add_argument("--seed", type=int, default=0, help="seed (default: %(default)s)")
    p.add_argument(
        "--eval-games",
        type=int,
        default=500,
        help="games per evaluation (default: %(default)s)",
    )
    p.add_argument(
        "--checkpoint-every",
        type=int,
        default=None,
        metavar="N",
        help="save a checkpoint every N steps (default: none)",
    )
    p.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("data/runs"),
        help="folder for run folders (default: %(default)s)",
    )
    return p


def _table(title: str, result, suffix: str) -> list[str]:
    lines = [title, f"{'':<20}{'wins':>8}{'draws':>8}{'losses':>8}"]
    for label, field in _ROWS:
        r = getattr(result, field + suffix)
        lines.append(f"{label:<20}{r.wins:>8}{r.draws:>8}{r.losses:>8}")
    return lines


def format_report(path: Path, result, opponent: str) -> str:
    lines = [f"run folder: {path}", f"games_played: {result.games_played}", ""]
    lines += _table(f"vs {opponent}", result, "")
    if result.trained_greedy_vs_random is not None:
        lines += ["", *_table("vs RandomBot", result, "_vs_random")]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = train(
            args.steps,
            rules=args.rules,
            opponent=args.opponent,
            seed=args.seed,
            eval_games=args.eval_games,
            run=args.run,
            runs_dir=args.runs_dir,
            checkpoint_every=args.checkpoint_every,
        )
    except (ValueError, FileExistsError, ImportError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 2
    print(format_report(args.runs_dir / args.run, result, args.opponent))
    return 0


if __name__ == "__main__":
    sys.exit(main())
