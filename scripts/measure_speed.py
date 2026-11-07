"""Speed of the bots: milliseconds and record size per game, one core.

Usage: uv run python scripts/measure_speed.py [--games 1000] [--seed 0]
       uv run python scripts/measure_speed.py --env-steps N [--seed 0]
       uv run python scripts/measure_speed.py --rollout-games N

With no mode flag, each bot plays both seats against itself, ruleset v2.3, 9 rounds, with the game
recorded in memory (as `simulate` does). Prints one row per bot: ms per game, KB per game raw, KB
per game gzipped.

`--env-steps N` prints one line with the `QuackEnv` steps per second: agent seat p1, opponent
`bot:topchip-draw20-pts6`, uniformly random legal agent actions from the action mask, `N` env steps
from the fixed seed `--seed`.

`--rollout-games N` prints one line with the mean ms per rollout game: `runner.play_game` with
`bot:topchip-draw20-pts6` in both seats (`planner.make_rollout_bot`), `RngChance(seed)`, no
`on_step` and no record, seeds `0..N-1` (the loop the planner runs per simulation).
"""

import argparse
import gzip
import io
import time

import numpy as np

from quack_rl.engine.chance import RngChance
from quack_rl.rl.planner import make_rollout_bot
from quack_rl.rl.single_env import QuackEnv
from quack_rl.rules import load_ruleset, with_rounds
from quack_rl.runner import play_game
from quack_rl.simgame import play_sim_game

BOTS = (
    "bot:random",
    "bot:topchip-draw30-pts3",
    "bot:spendmost-draw30-pts3",
    "bot:blackpurple-draw30-pts3",
)


def format_row(bot: str, games: int, seconds: float, raw_bytes: int, gz_bytes: int) -> str:
    """One output row: per-game values from the totals of `games` games."""
    return (
        f"{bot:<26}{seconds * 1000 / games:>12.2f}{raw_bytes / games / 1000:>12.2f}"
        f"{gz_bytes / games / 1000:>12.2f}"
    )


def measure(bot: str, games: int, seed: int, rules: str = "v2.3", rounds: int = 9) -> str:
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


SPEED_BOT = "bot:topchip-draw20-pts6"
SPEED_RULES = "v2.3"


def env_steps_per_second(steps: int, seed: int = 0) -> float:
    """`QuackEnv` steps per second over `steps` env steps (random legal agent actions)."""
    rs = load_ruleset(SPEED_RULES)
    env = QuackEnv(seat="p1", opponent=make_rollout_bot(rs, SPEED_BOT, seed), rules=rs)
    rng = np.random.default_rng(seed)
    started = time.perf_counter()
    env.reset(seed=seed)
    for _ in range(steps):
        action = int(rng.choice(np.flatnonzero(env.action_masks())))
        _, _, done, _, _ = env.step(action)
        if done:
            env.reset()
    return steps / (time.perf_counter() - started)


def rollout_ms_per_game(games: int) -> float:
    """Mean ms per rollout game over the seeds `0..games-1`."""
    rs = load_ruleset(SPEED_RULES)
    elapsed = 0.0
    for seed in range(games):
        seats = {
            "p1": make_rollout_bot(rs, SPEED_BOT, seed),
            "p2": make_rollout_bot(rs, SPEED_BOT, seed),
        }
        started = time.perf_counter()
        play_game(rs, seats, RngChance(seed))
        elapsed += time.perf_counter() - started
    return elapsed * 1000 / games


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=1000, help="games per bot (default 1000)")
    parser.add_argument("--seed", type=int, default=0)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--env-steps", type=int, metavar="N", help="QuackEnv steps per second")
    mode.add_argument("--rollout-games", type=int, metavar="N", help="mean ms per rollout game")
    args = parser.parse_args()
    if args.env_steps is not None:
        rate = env_steps_per_second(args.env_steps, args.seed)
        print(f"QuackEnv steps/s ({args.env_steps} steps, seed {args.seed}): {rate:.1f}")
        return
    if args.rollout_games is not None:
        ms = rollout_ms_per_game(args.rollout_games)
        n = args.rollout_games
        print(f"rollout ms/game ({n} games, seeds 0..{n - 1}): {ms:.2f}")
        return
    print(f"{'bot':<26}{'ms/game':>12}{'KB raw':>12}{'KB gzip':>12}")
    for bot in BOTS:
        print(measure(bot, args.games, args.seed), flush=True)


if __name__ == "__main__":
    main()
