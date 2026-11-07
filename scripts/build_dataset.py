"""Build an offline RL dataset from bot games.

Usage: uv run python scripts/build_dataset.py --out data/datasets/draw20 [--agent B --opponent B
    --games N --seed S]
       uv run python scripts/build_dataset.py --bots SPEC1,SPEC2,... --games-per-pairing N
    --out FOLDER [--seed S]

With only --out: 2000 games of bot:topchip-draw20-pts1 against bot:random plus 2000 games of the
same bot against itself, in one file `dataset.npz`, and `dataset-stats.json` next to it.
Given --agent/--opponent/--games, one such part is built. --out is a folder.

Every mode also writes `manifest.json` next to `dataset.npz` (`write_dataset_manifest`): the bots,
the games per pairing, the seed, the rules, the command line, the layout and the sha256 of the
final `dataset.npz`. In the default mode `bots` is the first part's pair and `games_per_pairing`
is 2000.

With --bots: every ordered pair (a, b) of distinct specs, in the order "for a in list, for b in
list", with a as the recorded agent. Pair k is `build_dataset(a, b, N, S + k*N)`, so with an even
N each spec is recorded at p1 and p2 equally often. Each pair is saved as a part and the parts are
joined with `concat_files`, so the memory stays low.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

from quack_rl.rl.dataset import Dataset, build_dataset, concat_files, write_dataset_manifest
from quack_rl.rl.opponents import make_opponent

BOT = "bot:topchip-draw20-pts1"
RULES = "v2.3"  # every dataset is built with the default ruleset of `build_dataset`


def field_pairs(specs: list[str], games: int, seed: int) -> list[tuple[str, str, int]]:
    """The ordered pairs (agent, opponent, seed) of the field mode, in build order."""
    pairs = [(a, b) for a in specs for b in specs if a != b]
    return [(a, b, seed + k * games) for k, (a, b) in enumerate(pairs)]


def check_field(parser: argparse.ArgumentParser, args: argparse.Namespace) -> list[str]:
    """The specs of --bots, or exit through `parser.error` naming the problem."""
    for flag, value in (("--agent", args.agent), ("--opponent", args.opponent)):
        if value is not None:
            parser.error(f"--bots cannot be combined with {flag}")
    if args.games is not None:
        parser.error("--bots cannot be combined with --games (use --games-per-pairing)")
    if args.games_per_pairing is None:
        parser.error("--bots needs --games-per-pairing")
    if args.games_per_pairing < 1:
        parser.error(f"--games-per-pairing must be positive, not {args.games_per_pairing}")
    if args.games_per_pairing % 2:
        parser.error(
            f"--games-per-pairing must be even (each spec at p1 and p2), "
            f"not {args.games_per_pairing}"
        )
    specs = [item.strip() for item in args.bots.split(",")]
    if len(specs) < 2:
        parser.error(f"--bots needs at least 2 specs, got {len(specs)}")
    for spec in specs:
        if not spec:
            parser.error(f"--bots has an empty item: {args.bots!r}")
        if specs.count(spec) > 1:
            parser.error(f"--bots lists {spec!r} twice")
        try:
            make_opponent(spec)
        except ValueError as err:
            parser.error(f"--bots: {err}")
    return specs


def build_field(specs: list[str], games: int, seed: int, target: Path) -> None:
    """Record every pair of `field_pairs` as a part, then join the parts into `target`."""
    pairs = field_pairs(specs, games, seed)
    parts_dir = target.parent / "parts"
    parts = []
    for k, (agent, opponent, pair_seed) in enumerate(pairs):
        part = parts_dir / f"part{k:04d}.npz"
        build_dataset(agent, opponent, games, pair_seed).save(part)
        parts.append(part)
        print(f"pair {k + 1}/{len(pairs)}: {agent} vs {opponent}", file=sys.stderr, flush=True)
    concat_files(parts, target)
    shutil.rmtree(parts_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--agent", default=None)
    parser.add_argument("--opponent", default=None)
    parser.add_argument("--games", type=int, default=None)
    parser.add_argument("--bots", default=None, help="comma-separated bot specs (field mode)")
    parser.add_argument(
        "--games-per-pairing", type=int, default=None, help="even N per ordered pair (field mode)"
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", required=True, help="output folder")
    args = parser.parse_args()
    if args.bots is None and args.games_per_pairing is not None:
        parser.error("--games-per-pairing needs --bots")
    specs = check_field(parser, args) if args.bots is not None else None
    out = Path(args.out)
    target = out / "dataset.npz"
    if specs is not None:
        build_field(specs, args.games_per_pairing, args.seed, target)
        bots, games = specs, args.games_per_pairing
    elif args.agent is None and args.opponent is None and args.games is None:
        # two parts, saved one by one and joined array by array: the memory stays low
        part1, part2 = out / "part1.npz", out / "part2.npz"
        build_dataset(BOT, "bot:random", 2000, args.seed).save(part1)
        build_dataset(BOT, BOT, 2000, args.seed + 2000).save(part2)
        concat_files([part1, part2], target)
        part1.unlink()
        part2.unlink()
        bots, games = [BOT, "bot:random"], 2000
    else:
        bots, games = [args.agent or BOT, args.opponent or "bot:random"], args.games or 2000
        build_dataset(bots[0], bots[1], games, args.seed).save(target)
    write_dataset_manifest(
        out, bots=bots, games_per_pairing=games, seed=args.seed, rules=RULES, command=sys.argv
    )
    stats = Dataset.load(target).stats()
    (out / "dataset-stats.json").write_text(json.dumps(stats, indent=2) + "\n")
    print(json.dumps(stats))


if __name__ == "__main__":
    main()
