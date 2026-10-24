"""Self-play: train MaskablePPO against a pool of its own earlier checkpoints.

Usage: uv run --group rl python scripts/train_selfplay.py --rounds 5 --steps-per-round 20000 \
    --seed 0 --eval-games 500 --out data/runs/selfplay

Writes config.json, selfplay.csv, result.json and checkpoint_<i>.zip to the out folder.
"""

import argparse

from quack_rl.rl.selfplay import RoundPoint, run_selfplay


def progress(point: RoundPoint) -> None:
    reward = "none" if point.mean_reward is None else f"{point.mean_reward:+.3f}"
    print(
        f"round {point.round}  steps {point.steps:>8}  mean reward {reward}  "
        f"pool {point.pool_size}",
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--steps-per-round", type=int, default=20_000)
    parser.add_argument("--pool-size", type=int, default=4)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--eval-games", type=int, default=500)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = run_selfplay(
        args.out,
        args.rounds,
        args.steps_per_round,
        args.pool_size,
        args.seed,
        args.eval_games,
        on_progress=progress,
    )
    for label, ev in (
        ("bot:random", result.against_random),
        ("bot:draw20-pts1-points", result.against_heuristic),
        ("first checkpoint", result.against_first),
    ):
        if ev is not None:
            print(
                f"vs {label}: win rate {ev.win_rate:.3f} [{ev.ci_low:.3f}, {ev.ci_high:.3f}] "
                f"({ev.wins}W {ev.draws}D {ev.losses}L)"
            )
    print(f"train seconds {result.train_seconds:.0f}; files in {result.out}")


if __name__ == "__main__":
    main()
