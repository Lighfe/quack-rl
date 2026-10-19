"""Train a MaskablePPO agent in a dedicated experiment and write its run folder.

Usage: uv run --group train python scripts/train.py --run NAME [--steps N] [--opponent random|<bot>]
       [--rules v1.10] [--seed 0] [--eval-games 500] [--checkpoint-every N] [--runs-dir data/runs]
       uv run --group train python scripts/train.py --resume NAME [--checkpoint-every N]
       [--runs-dir data/runs]

`--resume NAME` continues an interrupted run from its newest checkpoint; the other settings come
from its `config.json`.

The run folder `<runs-dir>/<NAME>` is written as the training goes. At the end the script prints
its path and a table of wins, draws and losses of the baselines and the trained policy.
"""

import argparse
import json
import sys
from pathlib import Path

from quack_rl.rl.train import resume, train

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
    p.add_argument("--run", metavar="NAME", help="run name (folder under --runs-dir)")
    p.add_argument(
        "--resume",
        metavar="NAME",
        help="continue the interrupted run NAME from its newest checkpoint (settings from its "
        "config.json; not with --run, --steps, --opponent, --rules, --seed, --eval-games)",
    )
    p.add_argument(
        "--steps",
        type=int,
        default=None,
        help=f"decisions of the agent, about 42 per game (default: {DEFAULT_STEPS})",
    )
    p.add_argument(
        "--opponent",
        default=None,
        help="'random' or draw<percent>-pts<round>-<strategy> (default: random)",
    )
    p.add_argument("--rules", default=None, help="ruleset version (default: v1.10)")
    p.add_argument("--seed", type=int, default=None, help="seed (default: 0)")
    p.add_argument(
        "--eval-games",
        type=int,
        default=None,
        help="games per evaluation (default: 500)",
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
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.resume is not None:
        taken = ("run", "steps", "opponent", "rules", "seed", "eval_games")
        given = [f"--{k.replace('_', '-')}" for k in taken if getattr(args, k) is not None]
        if given:
            parser.error(f"--resume takes its settings from config.json; remove {', '.join(given)}")
    elif args.run is None:
        parser.error("the following arguments are required: --run")
    try:
        if args.resume is not None:
            result = resume(
                args.resume, runs_dir=args.runs_dir, checkpoint_every=args.checkpoint_every
            )
            name = args.resume
            opponent = json.loads((args.runs_dir / name / "config.json").read_text())["opponent"]
        else:
            name, opponent = args.run, args.opponent or "random"
            result = train(
                args.steps if args.steps is not None else DEFAULT_STEPS,
                rules=args.rules or "v1.10",
                opponent=opponent,
                seed=args.seed if args.seed is not None else 0,
                eval_games=args.eval_games if args.eval_games is not None else 500,
                run=name,
                runs_dir=args.runs_dir,
                checkpoint_every=args.checkpoint_every,
            )
    except (ValueError, FileExistsError, FileNotFoundError, ImportError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 2
    print(format_report(args.runs_dir / name, result, opponent))
    return 0


if __name__ == "__main__":
    sys.exit(main())
