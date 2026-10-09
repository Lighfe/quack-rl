import secrets
from collections import Counter
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from rich.console import Console

from quack_rl import __version__
from quack_rl.cli.render import render_board, render_step
from quack_rl.cli.seats import check_seat, parse_seat, seat_info
from quack_rl.engine import RngChance
from quack_rl.record import (
    RECORD_SCHEMA_VERSION,
    GameRecorder,
    HeaderLine,
    LocalRecordStore,
    RecordedGame,
    RecordFormatError,
    berlin_iso,
    new_game_id,
    read_games,
    verify_game,
    verify_seed,
)
from quack_rl.rules import UnsupportedRulesVersion, apply_overrides, load_ruleset, with_rounds
from quack_rl.runner import play_game
from quack_rl.simgame import play_sim_game
from quack_rl.tournament import (
    DEFAULT_SAMPLE_SIZE,
    TournamentConfig,
    TournamentError,
    parse_sweep,
    verify_sample,
    write_run,
)

app = typer.Typer(no_args_is_help=True, help="Quack RL: play, simulate, replay and verify games.")


@app.callback()
def main() -> None:
    """Quack RL command line."""


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo(__version__)


def _fail(message: str, code: int = 1) -> NoReturn:
    """Print an error and exit without a traceback."""
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(code=code)


def _parse_sets(items: list[str] | None) -> dict[str, str]:
    """Turn the --set values into a map, or exit with an error message."""
    overrides: dict[str, str] = {}
    for item in items or []:
        key, sep, value = item.partition("=")
        if not sep or not key:
            _fail(f"--set needs key=value, got {item!r}", code=2)
        if key in overrides:
            _fail(f"--set {key!r} is given twice", code=2)
        overrides[key] = value
    return overrides


def _load_games(path: Path) -> list[RecordedGame]:
    """Read all games of a record file, or exit with an error message."""
    if not path.is_file():
        _fail(f"record file not found: {path}")
    try:
        return list(read_games(path))
    except RecordFormatError as e:
        _fail(f"not a valid record: {e}")


@app.command()
def simulate(
    p1: Annotated[str, typer.Option(help="Seat p1 (bot:random or bot:<name>).")] = "bot:random",
    p2: Annotated[str, typer.Option(help="Seat p2 (bot:random or bot:<name>).")] = "bot:random",
    games: Annotated[int, typer.Option(help="Number of games (at least 1).")] = 100,
    seed: Annotated[int, typer.Option(help="Chance seed of game 0; game i uses seed + i.")] = 0,
    shard_size: Annotated[int, typer.Option(help="Games per shard file (at least 1).")] = 1000,
    rounds: Annotated[int, typer.Option(help="Rounds per game (at least 1).")] = 9,
    rules: Annotated[str, typer.Option(help="Rules version.")] = "v1",
    set_: Annotated[
        list[str] | None,
        typer.Option("--set", help="Override a rule number, key=value (repeatable)."),
    ] = None,
    out: Annotated[Path, typer.Option(help="Record root folder.")] = Path("data/records"),
) -> None:
    """Play bot vs bot games and record them in shards."""
    # Check every input before a run folder or a shard file is created.
    for option, value in (("--games", games), ("--shard-size", shard_size)):
        if value < 1:
            _fail(f"{option} must be at least 1, got {value}", code=2)
    for option, spec in (("--p1", p1), ("--p2", p2)):
        try:
            check_seat(spec)
        except typer.BadParameter as e:
            _fail(f"{option}: {e.message}", code=2)
    if rounds < 1:
        _fail(f"--rounds must be at least 1, got {rounds}")
    try:
        rs = with_rounds(load_ruleset(rules), rounds)
    except UnsupportedRulesVersion as e:
        _fail(str(e), code=2)
    overrides = _parse_sets(set_)
    try:
        rs = apply_overrides(rs, overrides)
    except ValueError as e:
        _fail(str(e), code=2)

    store = LocalRecordStore(out)
    sim_dir = store.new_sim_dir(rules)
    wins: Counter[str] = Counter()
    for shard_index, first in enumerate(range(0, games, shard_size), start=1):
        with store.shard_path(sim_dir, shard_index).open("w", encoding="utf-8") as f:
            for i in range(first, min(first + shard_size, games)):
                final, _ = play_sim_game(
                    rs,
                    rules=rules,
                    rounds=rounds,
                    overrides=overrides,
                    p1=p1,
                    p2=p2,
                    game_seed=seed + i,
                    stream=f,
                )
                wins[final.winner or "?"] += 1
    typer.echo(f"{games} games written to {sim_dir}")
    typer.echo(f"wins: p1 {wins['p1']}, p2 {wins['p2']}, draws {wins['draw']}")


@app.command()
def tournament(
    bots: Annotated[
        list[str],
        typer.Option(
            "--bots", help="Bot seat specs of the field, bot:<name> (comma list or repeat)."
        ),
    ],
    games: Annotated[int, typer.Option(help="Games per pairing (at least 1).")] = 100,
    seed: Annotated[int, typer.Option(help="Chance seed of game 0; game i uses seed + i.")] = 0,
    rules: Annotated[str, typer.Option(help="Base rules version.")] = "v1",
    rounds: Annotated[int, typer.Option(help="Rounds per game (at least 1).")] = 9,
    set_: Annotated[
        list[str] | None,
        typer.Option("--set", help="Override a rule number, key=value (repeatable)."),
    ] = None,
    sweep: Annotated[
        str | None,
        typer.Option(
            help="One parameter with values: draw_limit=15,30 or points_round=3,8 "
            "or a rule key such as shop.droplet_1.price=6,8."
        ),
    ] = None,
    workers: Annotated[
        int, typer.Option(help="Worker processes, one pairing each (1 or more).")
    ] = 1,
    name: Annotated[str, typer.Option(help="Run name, part of the folder name.")] = "run",
    seat_check: Annotated[
        bool,
        typer.Option(
            "--seat-check", help="Seat sanity check: each bot plays itself, no other pairings."
        ),
    ] = False,
    keep_records: Annotated[
        bool, typer.Option("--keep-records", help="Write gzipped game records to records/.")
    ] = False,
    sample_size: Annotated[
        int, typer.Option(help="Games rebuilt from the seed and verified after the run.")
    ] = DEFAULT_SAMPLE_SIZE,
    out: Annotated[Path, typer.Option(help="Tournament root folder.")] = Path("data/tournaments"),
) -> None:
    """Every pair of the field plays; writes config.json and results.csv to its own folder."""
    try:
        config = TournamentConfig(
            bots=tuple(b.strip() for item in bots for b in item.split(",") if b.strip()),
            games=games,
            seed=seed,
            rules=rules,
            rounds=rounds,
            overrides=_parse_sets(set_),
            sweep=parse_sweep(sweep) if sweep is not None else None,
            workers=workers,
            seat_check=seat_check,
            keep_records=keep_records,
            sample_size=sample_size,
            name=name,
        )
        run_dir, rows = write_run(config, out)
    except TournamentError as e:
        _fail(str(e), code=2)
    typer.echo(f"{len(rows)} games written to {run_dir}")
    problems = verify_sample(config, rows)
    if problems:
        for problem in problems:
            typer.echo(f"MISMATCH {problem}", err=True)
        _fail(f"{len(problems)} sampled games do not match their rebuild", code=1)
    typer.echo(f"{min(sample_size, len(rows))} sampled games rebuilt from the seed: ok")


@app.command()
def verify(
    path: Path,
    seed_check: Annotated[
        bool, typer.Option(help="Also check the chance outcomes against the seed.")
    ] = False,
) -> None:
    """Replay every game of a record file and check it."""
    recorded = _load_games(path)
    if not recorded:
        typer.echo(f"{path}: no games in the file")
        raise typer.Exit(code=1)
    failed = 0
    for game in recorded:
        problems = verify_game(game)
        if seed_check and not problems:
            problems = verify_seed(game)
        if problems:
            failed += 1
            typer.echo(f"{game.header.game_id}: " + "; ".join(problems))
    if failed:
        typer.echo(f"{failed} of {len(recorded)} games have problems")
        raise typer.Exit(code=1)
    typer.echo(f"{len(recorded)} games ok")


@app.command()
def replay(
    path: Path,
    game: Annotated[str | None, typer.Option(help="Print only the game with this id.")] = None,
) -> None:
    """Print the steps of a recorded game."""
    recorded = _load_games(path)
    if game is not None:
        recorded = [g for g in recorded if g.header.game_id == game]
        if not recorded:
            _fail(f"no game with id {game!r} in {path}")
    for g in recorded:
        typer.echo(f"game {g.header.game_id} (rules {g.header.rules_version})")
        for line in g.steps:
            actions = ", ".join(f"{s}={a}" for s, a in (line.actions or {}).items()) or "-"
            chance = ", ".join(f"{c['seat']} {c['kind']} {c['value']}" for c in line.chance) or "-"
            typer.echo(
                f"step {line.n} round {line.round} {line.phase}: actions {actions}; chance {chance}"
            )
        if g.footer is not None:
            typer.echo(f"winner {g.footer.winner}, points {g.footer.points}")


@app.command()
def play(
    p1: Annotated[str, typer.Option(help="Seat p1 (human or bot:random).")] = "human",
    p2: Annotated[str, typer.Option(help="Seat p2 (human or bot:random).")] = "bot:random",
    seed: Annotated[int | None, typer.Option(help="Chance seed (random when not given).")] = None,
    bag_assist: Annotated[
        bool, typer.Option("--bag-assist/--no-bag-assist", help="Show the bag contents.")
    ] = True,
    rounds: Annotated[int, typer.Option(help="Rounds per game (at least 1).")] = 9,
    rules: Annotated[str, typer.Option(help="Rules version.")] = "v1",
    set_: Annotated[
        list[str] | None,
        typer.Option("--set", help="Override a rule number, key=value (repeatable)."),
    ] = None,
    out: Annotated[Path, typer.Option(help="Record root folder.")] = Path("data/records"),
) -> None:
    """Play a recorded game in the terminal (human vs bot, or hot seat with two humans)."""
    console = Console()
    # Check every input before the record file is created.
    for option, spec in (("--p1", p1), ("--p2", p2)):
        try:
            check_seat(spec, allow_human=True)
        except typer.BadParameter as e:
            _fail(f"{option}: {e.message}", code=2)
    if rounds < 1:
        _fail(f"--rounds must be at least 1, got {rounds}")
    try:
        rs = with_rounds(load_ruleset(rules), rounds)
    except UnsupportedRulesVersion as e:
        _fail(str(e), code=2)
    overrides = _parse_sets(set_)
    try:
        rs = apply_overrides(rs, overrides)
    except ValueError as e:
        _fail(str(e), code=2)
    game_seed = seed if seed is not None else secrets.randbelow(2**31)
    seats = {
        "p1": parse_seat(
            p1, 2 * game_seed + 1, console=console, rs=rs, bag_assist=bag_assist, label="Player 1"
        ),
        "p2": parse_seat(
            p2, 2 * game_seed + 2, console=console, rs=rs, bag_assist=bag_assist, label="Player 2"
        ),
    }
    path = LocalRecordStore(out).new_play_path(rules)
    header = HeaderLine(
        game_id=new_game_id(),
        schema_version=RECORD_SCHEMA_VERSION,
        rules_version=rules,
        rounds=rounds,
        overrides=overrides,
        seed=game_seed,
        mode="play",
        seats={s: seat_info(x) for s, x in seats.items()},
        ui={"bag_assist": bag_assist},
        engine_version=__version__,
        started_at=berlin_iso(),
    )
    with path.open("w", encoding="utf-8") as f:
        recorder = GameRecorder(f, header)

        def on_step(result, decision_ms):
            recorder.on_step(result, decision_ms)
            console.print(render_step(result, rs), markup=False, highlight=False)

        try:
            final = play_game(rs, seats, RngChance(game_seed), on_step)
        except (KeyboardInterrupt, EOFError):
            console.print(
                f"game aborted, partial record: {path}",
                markup=False,
                highlight=False,
                soft_wrap=True,
            )
            raise typer.Exit(code=130) from None
        recorder.close(final)
    console.print(render_board(final, rs, bag_assist))
    points = ", ".join(f"{s} {final.players[s].points}" for s in ("p1", "p2"))
    console.print(f"winner: {final.winner}  points: {points}", markup=False, highlight=False)
    console.print(f"record: {path}", markup=False, highlight=False, soft_wrap=True)
