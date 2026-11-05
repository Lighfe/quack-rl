import typer
from rich.console import Console

from quack_rl.bots import RandomBot, RuleBot, parse_bot_name
from quack_rl.cli.human import HumanSeat
from quack_rl.record import SeatInfo
from quack_rl.rl.agents import (
    AGENT_PREFIX,
    AGENTS_ROOT,
    MANIFEST,
    AgentError,
    check_name,
    load_agent,
)
from quack_rl.rules import Ruleset
from quack_rl.runner import Seat

KNOWN_SEATS = ("bot:random", "human")
BOT_FORM = "bot:<strategy>-draw<percent>-pts<round>"
AGENT_FORM = "agent:<name>"


class HumanSeatRequired(typer.BadParameter):
    """A human seat was given where only bots are allowed."""


def check_seat(spec: str, *, allow_human: bool = False) -> None:
    """Raise when `spec` is not a seat this command accepts."""
    if spec == "human" and not allow_human:
        raise HumanSeatRequired("human seats are only allowed in `quack-rl play`")
    if spec in KNOWN_SEATS:
        return
    known = f"known: {', '.join(KNOWN_SEATS)}, {BOT_FORM}, {AGENT_FORM}"
    reason = ""
    if spec.startswith("policy:"):
        raise typer.BadParameter(
            f"unknown seat {spec!r}: policy: seats are not supported ({known})"
        )
    if spec.startswith(AGENT_PREFIX):
        _check_agent(spec.removeprefix(AGENT_PREFIX))
        return
    if spec.startswith("bot:"):
        try:
            parse_bot_name(spec.removeprefix("bot:"))
            return
        except ValueError as e:
            reason = f": {e}"
    raise typer.BadParameter(f"unknown seat {spec!r} ({known}){reason}")


def _check_agent(name: str) -> None:
    """Raise when `name` is not an agent name or its folder has no manifest."""
    try:
        check_name(name)
    except AgentError as e:
        raise typer.BadParameter(f"unknown seat {AGENT_PREFIX + name!r}: {e}") from e
    path = AGENTS_ROOT / name / MANIFEST
    if not path.is_file():
        raise typer.BadParameter(f"unknown agent {name!r}: {path} does not exist")


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
    if spec.startswith(AGENT_PREFIX):
        assert rs is not None, "an agent needs the ruleset"
        try:
            return load_agent(spec.removeprefix(AGENT_PREFIX), rs, seed)
        except AgentError as e:
            raise typer.BadParameter(f"seat {spec!r}: {e}") from e
    assert rs is not None, "a rule bot needs the ruleset"
    strategy, draw_limit, points_round = parse_bot_name(spec.removeprefix("bot:"))
    return RuleBot(rs, strategy, draw_limit, points_round, seed)


def seat_info(seat: Seat) -> SeatInfo:
    kind = "human" if seat.kind == "human" else "bot"
    return SeatInfo(kind=kind, name=seat.name, params=dict(seat.params))
