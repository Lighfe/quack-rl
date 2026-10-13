from pathlib import Path

import typer
from rich.console import Console

from quack_rl.bots import HeuristicBot, RandomBot, parse_bot_name
from quack_rl.cli.human import HumanSeat
from quack_rl.record import SeatInfo
from quack_rl.rules import Ruleset
from quack_rl.runner import Seat

KNOWN_SEATS = ("bot:random", "human")
BOT_FORM = "bot:draw<percent>-pts<round>-<strategy>"
POLICY_FORM = "policy:<run folder>"


class HumanSeatRequired(typer.BadParameter):
    """A human seat was given where only bots are allowed."""


def check_seat(spec: str, *, allow_human: bool = False) -> None:
    """Raise when `spec` is not a seat this command accepts."""
    if spec == "human" and not allow_human:
        raise HumanSeatRequired("human seats are only allowed in `quack-rl play`")
    if spec in KNOWN_SEATS:
        return
    known = f"known: {', '.join(KNOWN_SEATS)}, {BOT_FORM}, {POLICY_FORM}"
    reason = ""
    if spec.startswith("policy:"):
        folder = spec.removeprefix("policy:")
        if folder and Path(folder).is_dir():
            return
        raise typer.BadParameter(f"policy seat {spec!r}: run folder {folder!r} not found")
    if spec.startswith("bot:"):
        try:
            parse_bot_name(spec.removeprefix("bot:"))
            return
        except ValueError as e:
            reason = f": {e}"
    raise typer.BadParameter(f"unknown seat {spec!r} ({known}){reason}")


def parse_seat(
    spec: str,
    seed: int | None,
    *,
    console: Console | None = None,
    rs: Ruleset | None = None,
    bag_assist: bool = True,
    label: str = "",
) -> Seat:
    """Build a seat. A human seat needs a console and a ruleset (only `play` gives them)."""
    check_seat(spec, allow_human=console is not None and rs is not None)
    if spec == "human":
        assert console is not None and rs is not None
        return HumanSeat(label, console, bag_assist, rs)
    if spec == "bot:random":
        return RandomBot(seed)
    if spec.startswith("policy:"):
        assert rs is not None, "a policy seat needs the ruleset"
        from quack_rl.rl.policy_bot import PolicyBot  # torch stays optional

        return PolicyBot.from_run(spec.removeprefix("policy:"), rs)
    assert rs is not None, "a heuristic bot needs the ruleset"
    draw_limit, points_round, strategy = parse_bot_name(spec.removeprefix("bot:"))
    return HeuristicBot(rs, draw_limit, points_round, strategy, seed)


def seat_info(seat: Seat) -> SeatInfo:
    kind = "human" if seat.kind == "human" else "bot"
    return SeatInfo(kind=kind, name=seat.name, params=dict(seat.params))
