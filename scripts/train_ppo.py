"""Train MaskablePPO against a bot and evaluate it.

Usage: uv run --group rl python scripts/train_ppo.py --opponent bot:random --steps 200000 \
    --seed 0 --eval-games 500 --out data/runs/ppo-vs-random

--opponent also takes a comma-separated list of bot specs, for example
bot:topchip-draw20-pts6,bot:spendmost-draw20-pts6: each game is then played against one spec,
sampled with --seed (a repeated spec counts twice), and the model is evaluated against each
distinct spec and bot:random.

Writes config.json, metrics.csv, result.json and model.zip to the out folder. With
--agent-name <name> the model is also saved as the agent folder data/agents/<name>/.
"""

import argparse
import json
from pathlib import Path

from quack_rl.rl.agents import AgentError, ensure_new_agent, write_agent
from quack_rl.rl.opponents import parse_opponents
from quack_rl.rl.train import CurvePoint, run_ppo_experiment


def progress(point: CurvePoint) -> None:
    print(f"steps {point.steps:>8}  mean reward {point.mean_reward:+.3f}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--opponent",
        default="bot:random",
        help="bot:random or a rule bot, bot:<strategy>-draw<percent>-pts<round>; or a "
        "comma-separated list of them, one sampled per game",
    )
    parser.add_argument("--steps", type=int, default=200_000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--eval-games", type=int, default=500)
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--agent-name",
        default=None,
        help="also save the model as the agent folder data/agents/<name>/ (seat agent:<name>)",
    )
    args = parser.parse_args()
    try:
        specs = parse_opponents(args.opponent)
    except ValueError as err:
        parser.error(str(err))
    opponent = specs[0] if len(specs) == 1 else specs
    if args.agent_name is not None:
        try:
            ensure_new_agent(args.agent_name)
        except AgentError as err:
            parser.error(str(err))
    result = run_ppo_experiment(
        opponent, args.steps, args.seed, args.eval_games, args.out, on_progress=progress
    )
    for label, ev in result.evaluations.items():
        print(
            f"vs {label}: win rate {ev.win_rate:.3f} [{ev.ci_low:.3f}, {ev.ci_high:.3f}] "
            f"({ev.wins}W {ev.draws}D {ev.losses}L)"
        )
    print(f"train seconds {result.train_seconds:.0f}; files in {result.out}")
    if args.agent_name is not None:
        out = Path(args.out)
        settings = json.loads((out / "config.json").read_text())
        folder = write_agent(args.agent_name, "ppo", out / "model.zip", settings["rules"], settings)
        print(f"agent saved in {folder}")


if __name__ == "__main__":
    main()
