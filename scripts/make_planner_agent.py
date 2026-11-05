"""Write the agent folder of a planner (flat Monte Carlo search, no weights).

Usage: uv run python scripts/make_planner_agent.py --name planner \
    [--simulations 40] [--rollout bot:topchip-draw20-pts6]

Writes data/agents/<name>/agent.json (kind `planner`); the seat `agent:<name>` then plays with it
in the CLI, the tournament and the web service. The defaults keep a decision under 2 s.
"""

import argparse
from datetime import UTC, datetime
from pathlib import Path

from quack_rl.rl.agents import AGENTS_ROOT, AgentError, AgentManifest, ensure_new_agent, save_agent
from quack_rl.rl.encode import BOARD_LAYOUT
from quack_rl.rl.planner import (
    DEFAULT_MAX_SECONDS,
    DEFAULT_ROLLOUT,
    DEFAULT_SIMULATIONS,
    check_rollout,
)
from quack_rl.rules import load_ruleset


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name", required=True)
    parser.add_argument(
        "--simulations",
        type=int,
        default=DEFAULT_SIMULATIONS,
        help="simulations per decision, split evenly over the legal actions",
    )
    parser.add_argument(
        "--rollout",
        default=DEFAULT_ROLLOUT,
        help="the bot of both seats in a simulation: bot:random or bot:<rule bot>",
    )
    parser.add_argument("--rules", default="v2.3")
    parser.add_argument("--root", default=str(AGENTS_ROOT), help="the agents folder")
    args = parser.parse_args()
    if args.simulations < 1:
        parser.error("--simulations must be at least 1")
    try:
        check_rollout(args.rollout)
    except ValueError as err:
        parser.error(str(err))
    rs = load_ruleset(args.rules)
    try:
        folder = ensure_new_agent(args.name, Path(args.root))
        save_agent(
            folder,
            AgentManifest(
                name=args.name,
                kind="planner",
                rules=rs.version,
                layout=BOARD_LAYOUT,
                settings={
                    "simulations": args.simulations,
                    "rollout": args.rollout,
                    "max_seconds": DEFAULT_MAX_SECONDS,
                },
                created_at=datetime.now(UTC).isoformat(timespec="seconds"),
            ),
        )
    except AgentError as err:
        parser.error(str(err))
    print(f"wrote {folder / 'agent.json'} (seat agent:{args.name})")


if __name__ == "__main__":
    main()
