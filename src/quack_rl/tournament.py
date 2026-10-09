"""Tournament: every pair of a bot field plays, optionally for each value of one sweep."""

import csv
import gzip
import io
import json
import multiprocessing
import random
import re
import tempfile
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from quack_rl import __version__
from quack_rl.bots import bot_name, parse_bot_name
from quack_rl.cli.seats import check_seat
from quack_rl.record import berlin_iso, berlin_stamp, read_games, verify_game, verify_seed
from quack_rl.rules import Ruleset, apply_overrides, load_ruleset, with_rounds
from quack_rl.simgame import GameStats, play_sim_game

BOT_SWEEPS = ("draw_limit", "points_round")
BASE_COLUMNS: list[str] = [
    "pairing",
    "p1",
    "p2",
    "game",
    "seed",
    "sweep_value",
    "winner",
    "p1_points",
    "p2_points",
    "p1_explosions",
    "p2_explosions",
]


def csv_columns(rs: Ruleset) -> list[str]:
    """Columns of results.csv: the base ones, then purchases per shop item, then draws."""
    buys = [f"{seat}_buy_{item.id}" for seat in ("p1", "p2") for item in rs.shop]
    return [*BASE_COLUMNS, *buys, "p1_draws", "p2_draws"]


CSV_COLUMNS: list[str] = csv_columns(load_ruleset("v1"))
SEAT_CHECK_PREFIX = "seatcheck:"
DEFAULT_SAMPLE_SIZE = 20
_NAME_OK = re.compile(r"[A-Za-z0-9._-]+")


class TournamentError(ValueError):
    """The inputs of a tournament are not valid."""


@dataclass(frozen=True)
class Sweep:
    param: str
    values: tuple[str, ...]


@dataclass(frozen=True)
class TournamentConfig:
    bots: tuple[str, ...]  # seat specs, `bot:<name>`
    games: int  # games per pairing
    seed: int
    rules: str = "v1"
    rounds: int = 9
    overrides: dict[str, str] = field(default_factory=dict)
    sweep: Sweep | None = None
    workers: int = 1
    seat_check: bool = False
    keep_records: bool = False
    sample_size: int = DEFAULT_SAMPLE_SIZE
    name: str = "run"


@dataclass(frozen=True)
class _Task:
    index: int
    pairing: str
    p1: str
    p2: str
    sweep_value: str  # "" without a sweep


def parse_sweep(text: str) -> Sweep:
    """`param=v1,v2,...` into a Sweep."""
    param, sep, raw = text.partition("=")
    values = tuple(v.strip() for v in raw.split(",")) if sep else ()
    if not param or not values or any(not v for v in values):
        raise TournamentError(f"--sweep needs param=value1,value2,..., got {text!r}")
    if len(set(values)) != len(values):
        raise TournamentError(f"--sweep {param!r} lists a value twice")
    return Sweep(param, values)


def _spec_for(spec: str, sweep: Sweep | None, value: str) -> str:
    """The seat spec a bot plays with at one sweep value."""
    if sweep is None or sweep.param not in BOT_SWEEPS or spec == "bot:random":
        return spec
    draw_limit, points_round, strategy = parse_bot_name(spec)
    if sweep.param == "draw_limit":
        draw_limit = int(value)
    else:
        points_round = int(value)
    new = bot_name(draw_limit, points_round, strategy)
    parse_bot_name(new)  # a value out of range is an error before any run
    return "bot:" + new


def _rules_for(config: TournamentConfig, value: str):
    """The ruleset of one sweep value."""
    rs = with_rounds(load_ruleset(config.rules), config.rounds)
    return apply_overrides(rs, _overrides_for(config, value))


def _overrides_for(config: TournamentConfig, value: str) -> dict[str, str]:
    sweep = config.sweep
    if sweep is None or sweep.param in BOT_SWEEPS:
        return dict(config.overrides)
    return {**config.overrides, sweep.param: value}


def validate(config: TournamentConfig) -> None:
    """Check every input. Raises TournamentError; nothing is written."""
    if config.games < 1:
        raise TournamentError(f"games per pairing must be at least 1, got {config.games}")
    if config.workers < 1:
        raise TournamentError(f"workers must be at least 1, got {config.workers}")
    if config.rounds < 1:
        raise TournamentError(f"rounds must be at least 1, got {config.rounds}")
    if config.sample_size < 0:
        raise TournamentError(f"sample size must not be negative, got {config.sample_size}")
    if not _NAME_OK.fullmatch(config.name):
        raise TournamentError(f"run name {config.name!r} may only use letters, digits, . _ -")
    for spec in config.bots:
        if not spec.startswith("bot:"):
            raise TournamentError(f"bot {spec!r} must be a bot seat spec (bot:random, bot:<name>)")
        try:
            check_seat(spec)
        except ValueError as e:
            raise TournamentError(str(e)) from e
    if len(set(config.bots)) != len(config.bots):
        raise TournamentError("the field lists a bot twice")
    if len(config.bots) < (1 if config.seat_check else 2):
        raise TournamentError(
            "a tournament needs at least 2 different bots (one bot is only the seat check)"
        )
    sweep = config.sweep
    if sweep is not None:
        if sweep.param in config.overrides:
            raise TournamentError(f"{sweep.param!r} is both swept and given with --set")
        if sweep.param in BOT_SWEEPS:
            for value in sweep.values:
                if not value.isdigit():
                    raise TournamentError(f"sweep {sweep.param}: {value!r} is not a whole number")
    try:
        load_ruleset(config.rules)
        for value in sweep.values if sweep else ("",):
            _rules_for(config, value)
            for spec in config.bots:
                _spec_for(spec, sweep, value)
    except ValueError as e:
        raise TournamentError(str(e)) from e


def _tasks(config: TournamentConfig) -> list[_Task]:
    sweep = config.sweep
    values = sweep.values if sweep else ("",)
    tasks: list[_Task] = []
    for value in values:
        specs = [_spec_for(s, sweep, value) for s in config.bots]
        if config.seat_check:
            pairs = [(s, s) for s in specs]
        else:
            pairs = [
                (specs[i], specs[j]) for i in range(len(specs)) for j in range(i + 1, len(specs))
            ]
        for p1, p2 in pairs:
            a, b = p1.removeprefix("bot:"), p2.removeprefix("bot:")
            label = f"{SEAT_CHECK_PREFIX}{a}" if config.seat_check else f"{a} vs {b}"
            tasks.append(_Task(len(tasks), label, p1, p2, value))
    return tasks


def _row(
    task: _Task,
    game: int,
    seed: int,
    final,
    explosions: dict[str, int],
    stats: GameStats,
    rs: Ruleset,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "pairing": task.pairing,
        "p1": task.p1.removeprefix("bot:"),
        "p2": task.p2.removeprefix("bot:"),
        "game": game,
        "seed": seed,
        "sweep_value": task.sweep_value,
        "winner": final.winner or "?",
        "p1_points": final.players["p1"].points,
        "p2_points": final.players["p2"].points,
        "p1_explosions": explosions["p1"],
        "p2_explosions": explosions["p2"],
    }
    for seat in ("p1", "p2"):
        for item in rs.shop:
            row[f"{seat}_buy_{item.id}"] = stats.buys[seat][item.id]
    row["p1_draws"] = stats.draws["p1"]
    row["p2_draws"] = stats.draws["p2"]
    return row


def _play_task(args: tuple[TournamentConfig, _Task, str | None]) -> list[dict[str, Any]]:
    """Play all games of one pairing (runs in a worker). Optionally write a gzipped shard."""
    config, task, records_dir = args
    rs = _rules_for(config, task.sweep_value)
    overrides = _overrides_for(config, task.sweep_value)
    rows: list[dict[str, Any]] = []
    shard = (
        gzip.open(
            Path(records_dir) / f"shard-{task.index + 1:04d}.jsonl.gz", "wt", encoding="utf-8"
        )
        if records_dir
        else None
    )
    try:
        for i in range(config.games):
            seed = config.seed + i
            final, explosions, stats = play_sim_game(
                rs,
                rules=config.rules,
                rounds=config.rounds,
                overrides=overrides,
                p1=task.p1,
                p2=task.p2,
                game_seed=seed,
                stream=shard,
            )
            rows.append(_row(task, i, seed, final, explosions, stats, rs))
    finally:
        if shard is not None:
            shard.close()
    return rows


def run_games(config: TournamentConfig, records_dir: Path | None = None) -> list[dict[str, Any]]:
    """Play every pairing and return the rows in a fixed order (sweep value, pairing, game)."""
    tasks = _tasks(config)
    jobs = [(config, t, str(records_dir) if records_dir else None) for t in tasks]
    if config.workers == 1 or len(jobs) == 1:
        per_task = [_play_task(j) for j in jobs]
    else:
        ctx = multiprocessing.get_context("spawn")
        with ProcessPoolExecutor(max_workers=config.workers, mp_context=ctx) as pool:
            per_task = list(pool.map(_play_task, jobs))
    return [row for rows in per_task for row in rows]


def results_csv(rows: Sequence[dict[str, Any]]) -> str:
    out = io.StringIO()
    fieldnames = list(rows[0]) if rows else CSV_COLUMNS
    writer = csv.DictWriter(out, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def _config_json(config: TournamentConfig, created_at: str) -> str:
    data = asdict(config)
    data["bots"] = list(config.bots)
    data["engine_version"] = __version__
    data["created_at"] = created_at
    return json.dumps(data, indent=2) + "\n"


def new_run_dir(root: Path, name: str, now: datetime | None = None) -> Path:
    base = f"{berlin_stamp(now)}-{name}"
    folder = root / base
    n = 1
    while True:
        try:
            folder.mkdir(parents=True, exist_ok=False)
            return folder
        except FileExistsError:
            n += 1
            folder = root / f"{base}-{n}"


def sample_rows(config: TournamentConfig, total: int) -> list[int]:
    """Indexes of the rows to rebuild and verify, drawn from the run seed."""
    k = min(config.sample_size, total)
    return sorted(random.Random(config.seed).sample(range(total), k))


def verify_sample(config: TournamentConfig, rows: Sequence[dict[str, Any]]) -> list[str]:
    """Rebuild a random sample of games from the seed. Returns one problem text per bad game."""
    problems: list[str] = []
    for index in sample_rows(config, len(rows)):
        row = rows[index]
        where = f"game {row['game']} (seed {row['seed']}) of pairing {row['pairing']!r}"
        if row["sweep_value"]:
            where += f" at sweep value {row['sweep_value']}"
        value = row["sweep_value"]
        rs = _rules_for(config, value)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "game.jsonl"
            with path.open("w", encoding="utf-8") as f:
                final, explosions, stats = play_sim_game(
                    rs,
                    rules=config.rules,
                    rounds=config.rounds,
                    overrides=_overrides_for(config, value),
                    p1="bot:" + row["p1"],
                    p2="bot:" + row["p2"],
                    game_seed=row["seed"],
                    stream=f,
                )
            (game,) = read_games(path)
        task = _Task(0, row["pairing"], "bot:" + row["p1"], "bot:" + row["p2"], value)
        if _row(task, row["game"], row["seed"], final, explosions, stats, rs) != row:
            problems.append(f"{where}: the stored result differs from the rebuilt game")
            continue
        found = verify_game(game) or verify_seed(game)
        if found:
            problems.append(f"{where}: {'; '.join(found)}")
    return problems


def write_run(config: TournamentConfig, out: Path) -> tuple[Path, list[dict[str, Any]]]:
    """Validate, play and write config.json and results.csv. Returns the folder and the rows."""
    validate(config)
    run_dir = new_run_dir(out, config.name)
    (run_dir / "config.json").write_text(_config_json(config, berlin_iso()), encoding="utf-8")
    records_dir: Path | None = None
    if config.keep_records:
        records_dir = run_dir / "records"
        records_dir.mkdir()
    rows = run_games(config, records_dir)
    (run_dir / "results.csv").write_text(results_csv(rows), encoding="utf-8", newline="")
    return run_dir, rows
