from dataclasses import dataclass


class UnknownStrategy(ValueError):
    """A strategy name that is not in `STRATEGIES`."""


@dataclass(frozen=True)
class Strategy:
    """A strategy is data: the shop items it buys, best first, and optional weights.

    `priority` lists the items in order. `weights` maps an item id to a weight
    (default 0): a higher weight ranks first, equal weights keep the priority order.
    """

    name: str
    priority: tuple[str, ...] = ()
    weights: tuple[tuple[str, float], ...] = ()

    def ranked(self) -> list[str]:
        """The priority items, best first (weight descending, then priority order)."""
        weight = dict(self.weights)
        order = {item: i for i, item in enumerate(self.priority)}
        return sorted(self.priority, key=lambda item: (-weight.get(item, 0.0), order[item]))


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
