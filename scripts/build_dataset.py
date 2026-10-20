"""Play bot games and write them as an offline RL dataset (Parquet) with its config.

Usage: uv run python scripts/build_dataset.py --out data/datasets/NAME.parquet [--games N]
       [--seed 0] [--rules v1.11] [--bots bot:a,bot:b,...] [--overwrite]

Each row is one decision of the recorded seat (see `quack_rl.rl.dataset`). For every game a
seeded RNG draws the recorded bot and the opponent from the list (mirror matches allowed) and
the recorded seat (p1 or p2). Default bots: draw20-pts4-blue, draw20-pts4-green,
draw20-pts4-balanced, draw20-pts4-cleaner, draw10-pts4-balanced, random (a given list replaces
them; `bot:` prefix optional). The config (bots, games, seed, rules, command line) is written
next to the data with the suffix .json. An existing output is kept unless --overwrite is given.
"""

import argparse
import sys
import time
from pathlib import Path

from quack_rl.rl.dataset import DEFAULT_BOTS, command_line, write_dataset


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="build_dataset.py", description=__doc__.split("\n\n")[0])
    p.add_argument("--out", type=Path, required=True, help="output Parquet file")
    p.add_argument("--games", type=int, default=5000, help="games to play (default: 5000)")
    p.add_argument("--seed", type=int, default=0, help="seed (default: 0)")
    p.add_argument("--rules", default="v1.11", help="ruleset version (default: v1.11)")
    p.add_argument(
        "--bots",
        default=",".join(DEFAULT_BOTS),
        help="comma list of bot names or bot:<name> (default: %(default)s)",
    )
    p.add_argument("--overwrite", action="store_true", help="replace an existing output")
    return p


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    args = build_parser().parse_args(argv)
    bots = [b for b in args.bots.split(",") if b.strip()]
    start = time.perf_counter()
    try:
        config = write_dataset(
            args.out,
            bots,
            args.games,
            args.seed,
            args.rules,
            args.overwrite,
            command_line(argv),
        )
    except (ValueError, FileExistsError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 2
    secs = time.perf_counter() - start
    mb = args.out.stat().st_size / 1e6
    print(f"wrote {args.out}: {config['games']} games, {config['rows']} rows, "
          f"{mb:.2f} MB, {secs:.1f} s")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
