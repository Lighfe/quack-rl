"""Self-play: train MaskablePPO against a pool of its own earlier checkpoints.

Usage: uv run --group rl python scripts/train_selfplay.py --rounds 5 --steps-per-round 20000 \
    --seed 0 --eval-games 500 --out data/runs/selfplay

Writes config.json, selfplay.csv, result.json and checkpoint_<i>.zip to the out folder. With
--agent-name <name> the final checkpoint is also saved as the agent folder data/agents/<name>/.

An interrupted run is continued from its newest checkpoint, with the settings of its config.json:
    uv run --group rl python scripts/train_selfplay.py --resume data/runs/selfplay
"""

import argparse
import json
import sys
from pathlib import Path

from quack_rl.rl.agents import AgentError, ensure_new_agent, write_agent
from quack_rl.rl.selfplay import ResumeError, RoundPoint, resume_selfplay, run_selfplay

# the settings flags and their defaults; with --resume they come from config.json
SETTINGS = {
    "rounds": 5,
    "steps_per_round": 20_000,
    "pool_size": 4,
    "seed": 0,
    "eval_games": 500,
}


def progress(point: RoundPoint) -> None:
    reward = "none" if point.mean_reward is None else f"{point.mean_reward:+.3f}"
    print(
        f"round {point.round}  steps {point.steps:>8}  mean reward {reward}  "
        f"pool {point.pool_size}",
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for name, default in SETTINGS.items():
        flag = "--" + name.replace("_", "-")
        parser.add_argument(
            flag, type=int, default=None, help=f"default {default}; not with --resume"
        )
    where = parser.add_mutually_exclusive_group(required=True)
    where.add_argument("--out", help="the folder of a new run")
    where.add_argument(
        "--resume", metavar="OUT", help="continue the run in OUT from its newest checkpoint"
    )
    parser.add_argument(
        "--agent-name",
        default=None,
        help="also save the model as the agent folder data/agents/<name>/ (seat agent:<name>)",
    )
    args = parser.parse_args()
    given = [name for name in SETTINGS if getattr(args, name) is not None]
    if args.resume is not None and given:
        flags = ", ".join("--" + name.replace("_", "-") for name in given)
        parser.error(f"{flags} cannot be given with --resume (the settings come from config.json)")
    for name, default in SETTINGS.items():
        if getattr(args, name) is None:
            setattr(args, name, default)
    if args.agent_name is not None:
        try:
            ensure_new_agent(args.agent_name)
        except AgentError as err:
            parser.error(str(err))
    if args.resume is not None:
        try:
            result = resume_selfplay(args.resume, on_progress=progress)
        except ResumeError as err:
            print(f"train_selfplay: {err}", file=sys.stderr)
            sys.exit(1)
    else:
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
        ("bot:topchip-draw20-pts1", result.against_heuristic),
        ("first checkpoint", result.against_first),
    ):
        if ev is not None:
            print(
                f"vs {label}: win rate {ev.win_rate:.3f} [{ev.ci_low:.3f}, {ev.ci_high:.3f}] "
                f"({ev.wins}W {ev.draws}D {ev.losses}L)"
            )
    print(f"train seconds {result.train_seconds:.0f}; files in {result.out}")
    if args.agent_name is not None:
        out = Path(args.out if args.resume is None else args.resume)
        settings = json.loads((out / "config.json").read_text())
        final = out / f"checkpoint_{settings['rounds']}.zip"
        folder = write_agent(args.agent_name, "ppo", final, settings["rules"], settings)
        print(f"agent saved in {folder}")


if __name__ == "__main__":
    main()
