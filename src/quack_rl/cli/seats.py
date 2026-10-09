import typer

from quack_rl.bots import RandomBot
from quack_rl.record import SeatInfo
from quack_rl.runner import Seat

KNOWN_SEATS = ("bot:random", "human")


class HumanSeatRequired(typer.BadParameter):
    """A human seat was given where only bots are allowed."""


def check_seat(spec: str, *, allow_human: bool = False) -> None:
    """Raise when `spec` is not a seat this command accepts."""
    if spec == "human" and not allow_human:
        raise HumanSeatRequired("human seats are only allowed in `quack-rl play`")
    if spec not in KNOWN_SEATS:
        raise typer.BadParameter(f"unknown seat {spec!r} (known: {', '.join(KNOWN_SEATS)})")


def parse_seat(spec: str, seed: int | None) -> Seat:
    check_seat(spec)
    return RandomBot(seed)


def seat_info(seat: Seat) -> SeatInfo:
    kind = "human" if seat.kind == "human" else "bot"
    return SeatInfo(kind=kind, name=seat.name, params=dict(seat.params))
