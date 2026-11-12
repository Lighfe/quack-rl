"""Save a finished experiment run folder as an agent folder (seat `agent:<name>`).

Usage: uv run --group rl python scripts/save_run_agent.py RUN_DIR --agent-name NAME \
    --agents-root PATH [--step N]

RUN_DIR is one seed folder written by scripts/run_experiment.py, for example
data/experiments/L/seed0. It must have `done.json`.

- PPO run: the agent gets `checkpoints/step_<N>.zip`; N is the final step (from `done.json`)
  unless --step names another checkpoint.
- BC run: the agent gets `model.pt` (--step is refused).

--agents-root has no default, so an agent goes into data/agents/ only when the owner names it.
The manifest's settings are the run's `config.json`, plus `run_dir`, `checkpoint_step` (PPO) and
`hidden` (the network width the loader needs). Exit code 1 and nothing written when the run is
not finished, the checkpoint is missing or the agent already exists.
"""

import argparse
import json
import sys
from pathlib import Path

from quack_rl.rl.agents import AgentError, ensure_new_agent, write_agent


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_dir", type=Path, help="a finished seed folder of an experiment")
    parser.add_argument("--agent-name", required=True, help="the agent name (seat agent:<name>)")
    parser.add_argument(
        "--agents-root", required=True, type=Path, help="the folder the agent folder goes into"
    )
    parser.add_argument(
        "--step", type=int, default=None, help="PPO only: the checkpoint step (default: final)"
    )
    args = parser.parse_args()

    run: Path = args.run_dir
    if not (run / "done.json").is_file():
        fail(f"{run} has no done.json: the run is not finished")
    stored = json.loads((run / "config.json").read_text(encoding="utf-8"))
    kind = stored["config"]["kind"]
    settings = {**stored, "run_dir": str(run), "hidden": int(stored["config"]["hidden"])}
    if kind == "ppo":
        step = args.step
        if step is None:
            step = int(json.loads((run / "done.json").read_text(encoding="utf-8"))["steps"])
        weights = run / "checkpoints" / f"step_{step}.zip"
        settings["checkpoint_step"] = step
    elif kind == "bc":
        if args.step is not None:
            fail("--step is for PPO runs only; a BC run saves its model.pt")
        weights = run / "model.pt"
    else:
        fail(f"{run}: unknown run kind {kind!r}")
    if not weights.is_file():
        fail(f"{weights} does not exist")
    try:
        ensure_new_agent(args.agent_name, root=args.agents_root)
        folder = write_agent(
            args.agent_name, kind, weights, stored["rules"], settings, root=args.agents_root
        )
    except AgentError as err:
        fail(str(err))
    print(f"agent saved in {folder} (seat agent:{args.agent_name}) from {weights}")


if __name__ == "__main__":
    main()
