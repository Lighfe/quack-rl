"""Train a policy offline (BC or CQL) on a dataset and evaluate it.

Usage: uv run --group rl python scripts/train_offline.py \
    --dataset data/datasets/draw20/dataset.npz --method bc --epochs 5 --seed 0 \
    --eval-games 500 --out data/runs/bc

Writes config.json, metrics.csv (loss curve) and result.json to the out folder.
"""

import argparse

from quack_rl.rl.offline import run_offline_experiment


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--method", choices=("bc", "cql"), required=True)
    parser.add_argument("--epochs", type=int, default=5, help="bc")
    parser.add_argument("--steps", type=int, default=20_000, help="cql")
    parser.add_argument("--alpha", type=float, default=1.0, help="cql")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--eval-games", type=int, default=500)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = run_offline_experiment(
        args.dataset,
        args.method,
        args.seed,
        args.eval_games,
        args.out,
        epochs=args.epochs,
        steps=args.steps,
        alpha=args.alpha,
    )
    for label, ev in (
        ("bot:random", result.against_random),
        ("heuristic", result.against_heuristic),
    ):
        print(
            f"vs {label}: win rate {ev.win_rate:.3f} [{ev.ci_low:.3f}, {ev.ci_high:.3f}] "
            f"({ev.wins}W {ev.draws}D {ev.losses}L)"
        )
    print(f"train seconds {result.train_seconds:.0f}; final loss {result.curve[-1]:.4f}")


if __name__ == "__main__":
    main()
