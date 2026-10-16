"""Offline RL dataset: bot games written as one Parquet file of decisions.

One row is one decision of the recorded seat, seen as `QuackEnv` shows it (same observation,
action index and reward; Wait-only steps are skipped and their reward is summed into the
decision before them). The terminal observation (all-zero mask) is not stored.

Columns: `episode` int32, `step` int32, `obs` list<float32> (848), `action_mask` list<int8>
(15, the mask of the state the action was taken in), `action` int16, `reward` float32,
`terminal` bool (true on the last row of each episode only), `bot` (the bot of the recorded
seat), `opponent` (the bot of the other seat), `seat` (`p1` or `p2`).

How a game gets its bots: a seeded RNG draws, per game, the recorded bot and the opponent from
the list (independently, so mirror matches happen) and the recorded seat (`p1` or `p2`), and
seeds the bots and the game. Same arguments give the same content.
"""

import json
import shlex
from pathlib import Path
from typing import Any

import numpy as np

from quack_rl.engine import legal_actions
from quack_rl.rl.opponents import make_opponent
from quack_rl.rl.single_env import QuackEnv

DEFAULT_BOTS = (
    "draw20-pts4-blue",
    "draw20-pts4-green",
    "draw20-pts4-balanced",
    "draw20-pts4-cleaner",
    "draw10-pts4-balanced",
    "random",
)


def parse_bot_specs(specs: list[str]) -> list[str]:
    """Return bot names (without `bot:`). Raise ValueError on an empty list, a `human` or
    `policy:` spec, or an unknown bot name."""
    if not specs:
        raise ValueError("the bot list is empty: give at least one bot")
    names = []
    for spec in specs:
        spec = spec.strip()
        if spec == "human" or spec.startswith("policy:"):
            raise ValueError(f"seat spec {spec!r} is not allowed: only bot:<name> specs")
        name = spec.removeprefix("bot:")
        make_opponent(name)  # raises ValueError on an unknown name
        names.append(name)
    return names


def _play_game(
    bot_name: str, opp_name: str, seat: str, rules: str, rng: np.random.Generator
) -> list[dict[str, Any]]:
    bot = make_opponent(bot_name, int(rng.integers(2**32)), rules)
    opp = make_opponent(opp_name, int(rng.integers(2**32)), rules)
    env = QuackEnv(seat=seat, opponent=opp, rules=rules)
    obs, _ = env.reset(seed=int(rng.integers(2**32)))
    names = env._env._names
    rows = []
    done = False
    while not done:
        mask = env.action_masks()
        legal = legal_actions(env.state, env.rs, seat)
        action = names.index(bot.choose(env.state, seat, legal))
        new_obs, rew, done, _, _ = env.step(action)
        rows.append({"obs": obs, "action_mask": mask, "action": action, "reward": rew})
        obs = new_obs
    rows[-1]["terminal"] = True
    return rows


def build_dataset(
    bots: list[str], games: int, seed: int = 0, rules: str = "v1.1"
) -> dict[str, list]:
    """Play `games` games and return the columns (see module docstring)."""
    if games < 1:
        raise ValueError(f"games must be at least 1, not {games}")
    bots = parse_bot_specs(bots)
    rng = np.random.default_rng(seed)
    cols: dict[str, list] = {
        k: []
        for k in ("episode", "step", "obs", "action_mask", "action", "reward", "terminal")
        + ("bot", "opponent", "seat")
    }
    for ep in range(games):
        bot = bots[int(rng.integers(len(bots)))]
        opp = bots[int(rng.integers(len(bots)))]
        seat = ("p1", "p2")[int(rng.integers(2))]
        for step, r in enumerate(_play_game(bot, opp, seat, rules, rng)):
            cols["episode"].append(ep)
            cols["step"].append(step)
            cols["obs"].append(r["obs"])
            cols["action_mask"].append(r["action_mask"])
            cols["action"].append(r["action"])
            cols["reward"].append(r["reward"])
            cols["terminal"].append(r.get("terminal", False))
            cols["bot"].append(bot)
            cols["opponent"].append(opp)
            cols["seat"].append(seat)
    return cols


def to_table(cols: dict[str, list]):
    import pyarrow as pa

    return pa.table(
        {
            "episode": pa.array(cols["episode"], pa.int32()),
            "step": pa.array(cols["step"], pa.int32()),
            "obs": pa.array([o.tolist() for o in cols["obs"]], pa.list_(pa.float32())),
            "action_mask": pa.array(
                [m.tolist() for m in cols["action_mask"]], pa.list_(pa.int8())
            ),
            "action": pa.array(cols["action"], pa.int16()),
            "reward": pa.array(cols["reward"], pa.float32()),
            "terminal": pa.array(cols["terminal"], pa.bool_()),
            "bot": pa.array(cols["bot"], pa.string()),
            "opponent": pa.array(cols["opponent"], pa.string()),
            "seat": pa.array(cols["seat"], pa.string()),
        }
    )


def config_path(out: Path) -> Path:
    return out.with_suffix(".json")


def write_dataset(
    out: Path,
    bots: list[str],
    games: int,
    seed: int = 0,
    rules: str = "v1.1",
    overwrite: bool = False,
    command: str | None = None,
) -> dict[str, Any]:
    """Build the dataset and write `out` (Parquet) and the config next to it (same name, `.json`).

    Raise ValueError on bad arguments and FileExistsError when `out` exists and `overwrite` is
    false; in both cases nothing is written. Return the config."""
    import pyarrow.parquet as pq

    out = Path(out)
    cfg_file = config_path(out)
    if not overwrite and (out.exists() or cfg_file.exists()):
        raise FileExistsError(f"{out} exists: pass --overwrite to replace it")
    cols = build_dataset(bots, games, seed, rules)
    table = to_table(cols)
    config = {
        "bots": parse_bot_specs(bots),
        "games": games,
        "seed": seed,
        "rules": rules,
        "rows": table.num_rows,
        "command": command,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, out, compression="zstd")
    cfg_file.write_text(json.dumps(config, indent=2) + "\n")
    return config


def command_line(argv: list[str]) -> str:
    return "uv run python scripts/build_dataset.py " + " ".join(shlex.quote(a) for a in argv)
