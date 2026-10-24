"""Build an offline RL dataset from bot games.

Usage: uv run python scripts/build_dataset.py --out data/datasets/draw20 [--agent B --opponent B
    --games N --seed S]

With only --out: 2000 games of bot:draw20-pts1-points against bot:random plus 2000 games of the
same bot against itself, in one file `dataset.npz`, and `dataset-stats.json` next to it.
Given --agent/--opponent/--games, one such part is built. --out is a folder.
"""

import argparse
import json
from pathlib import Path

from quack_rl.rl.dataset import Dataset, build_dataset, concat_files

BOT = "bot:draw20-pts1-points"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--agent", default=None)
    parser.add_argument("--opponent", default=None)
    parser.add_argument("--games", type=int, default=None)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", required=True, help="output folder")
    args = parser.parse_args()
    out = Path(args.out)
    target = out / "dataset.npz"
    if args.agent is None and args.opponent is None and args.games is None:
        # two parts, saved one by one and joined array by array: the memory stays low
        part1, part2 = out / "part1.npz", out / "part2.npz"
        build_dataset(BOT, "bot:random", 2000, args.seed).save(part1)
        build_dataset(BOT, BOT, 2000, args.seed + 2000).save(part2)
        concat_files([part1, part2], target)
        part1.unlink()
        part2.unlink()
    else:
        build_dataset(
            args.agent or BOT, args.opponent or "bot:random", args.games or 2000, args.seed
        ).save(target)
    stats = Dataset.load(target).stats()
    (out / "dataset-stats.json").write_text(json.dumps(stats, indent=2) + "\n")
    print(json.dumps(stats))


if __name__ == "__main__":
    main()
