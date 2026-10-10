"""Speed of the bots: milliseconds and record size per game, one core.

Usage: uv run python scripts/measure_speed.py [--games 1000] [--seed 0]

Each bot plays both seats against itself, ruleset v1, 9 rounds, with the game recorded in memory
(as `simulate` does). Prints one row per bot: ms per game, KB per game raw, KB per game gzipped.
"""

import argparse
import gzip
import io
import time

from quack_rl.rules import load_ruleset, with_rounds
from quack_rl.simgame import play_sim_game

BOTS = (
    "bot:random",
    "bot:draw30-pts3-blue",
    "bot:draw30-pts3-green",
    "bot:draw30-pts3-cleaner",
    "bot:draw30-pts3-balanced",
)


def format_row(bot: str, games: int, seconds: float, raw_bytes: int, gz_bytes: int) -> str:
    """One output row: per-game values from the totals of `games` games."""
    return (
        f"{bot:<26}{seconds * 1000 / games:>12.2f}{raw_bytes / games / 1000:>12.2f}"
        f"{gz_bytes / games / 1000:>12.2f}"
    )


def measure(bot: str, games: int, seed: int, rules: str = "v1", rounds: int = 9) -> str:
    rs = with_rounds(load_ruleset(rules), rounds)
    raw = 0
    gz = 0
    elapsed = 0.0
    for i in range(games):
        stream = io.StringIO()
        started = time.perf_counter()
        play_sim_game(
            rs,
            rules=rules,
            rounds=rounds,
            overrides={},
            p1=bot,
            p2=bot,
            game_seed=seed + i,
            stream=stream,
        )
        elapsed += time.perf_counter() - started
        data = stream.getvalue().encode("utf-8")
        raw += len(data)
        gz += len(gzip.compress(data))
    return format_row(bot, games, elapsed, raw, gz)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=1000, help="games per bot (default 1000)")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    print(f"{'bot':<26}{'ms/game':>12}{'KB raw':>12}{'KB gzip':>12}")
    for bot in BOTS:
        print(measure(bot, args.games, args.seed), flush=True)


if __name__ == "__main__":
    main()
