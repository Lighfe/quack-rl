"""Train MaskablePPO against a bot and evaluate it.

Usage: uv run --group rl python scripts/train_ppo.py --opponent bot:random --steps 200000 \
    --seed 0 --eval-games 500 --out data/runs/ppo-vs-random

Writes config.json, metrics.csv, result.json and model.zip to the out folder.
"""

import argparse

from quack_rl.rl.train import CurvePoint, run_ppo_experiment


def progress(point: CurvePoint) -> None:
    print(f"steps {point.steps:>8}  mean reward {point.mean_reward:+.3f}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--opponent", default="bot:random", help="bot:random or a heuristic bot")
    parser.add_argument("--steps", type=int, default=200_000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--eval-games", type=int, default=500)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = run_ppo_experiment(
        args.opponent, args.steps, args.seed, args.eval_games, args.out, on_progress=progress
    )
    for label, ev in (("opponent", result.against_opponent), ("bot:random", result.against_random)):
        print(
            f"vs {label}: win rate {ev.win_rate:.3f} [{ev.ci_low:.3f}, {ev.ci_high:.3f}] "
            f"({ev.wins}W {ev.draws}D {ev.losses}L)"
        )
    print(f"train seconds {result.train_seconds:.0f}; files in {result.out}")


if __name__ == "__main__":
    main()
