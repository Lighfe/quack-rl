"""Train a policy from the Parquet dataset by masked behaviour cloning and write a run folder.

Usage: uv run --group train python scripts/train_offline.py --dataset data/datasets/full.parquet
       --run NAME [--steps 20000] [--seed 0] [--runs-dir data/runs] [--rules v1.10]
       [--batch-size 256] [--lr 0.001] [--hidden 256] [--log-every 100]

Writes `<runs-dir>/<NAME>/` with `config.json`, `model.zip` and `metrics.csv` (step, loss,
accuracy). No game is played. A bad argument prints one error line and exits with code 2, and
leaves no run folder.
"""

import argparse
import sys
from pathlib import Path

from quack_rl.rl.offline import train_offline_run


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="train_offline.py", description=__doc__.split("\n")[0])
    p.add_argument("--dataset", type=Path, required=True, help="Parquet file of #89")
    p.add_argument("--run", required=True, metavar="NAME", help="run folder name under --runs-dir")
    p.add_argument("--steps", type=int, default=20_000, help="gradient steps (default: 20000)")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--rules", default="v1.10")
    p.add_argument("--runs-dir", type=Path, default=Path("data/runs"))
    p.add_argument("--batch-size", type=int, default=256)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--hidden", type=int, default=256, help="units of each of the two layers")
    p.add_argument("--log-every", type=int, default=100)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = train_offline_run(
            args.dataset, args.run, args.runs_dir, args.seed, args.steps, args.rules,
            args.batch_size, args.lr, args.hidden, args.log_every,
        )  # fmt: skip
    except (FileNotFoundError, FileExistsError, ValueError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 2
    print(f"run folder: {Path(args.runs_dir) / args.run}")
    print(f"rows {config['dataset_rows']}, steps {config['steps']}, "
          f"train {config['seconds_train']} s")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
