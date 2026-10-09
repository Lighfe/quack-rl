from dataclasses import dataclass


class UnknownStrategy(ValueError):
    """A strategy name that is not in `STRATEGIES`."""


@dataclass(frozen=True)
class Strategy:
    """A strategy is data: the shop items it buys, best first."""

    name: str
    priority: tuple[str, ...] = ()


STRATEGIES: dict[str, Strategy] = {
    "points": Strategy("points"),
}


def load_strategy(name: str) -> Strategy:
    try:
        return STRATEGIES[name]
    except KeyError:
        raise UnknownStrategy(
            f"unknown strategy {name!r} (known: {', '.join(sorted(STRATEGIES))})"
        ) from None
