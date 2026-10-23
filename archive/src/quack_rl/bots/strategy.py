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
    # First guesses, not tuned. Points are bought by the points rule of the bot core.
    "blue": Strategy(
        "blue",
        priority=("blue_4", "blue_2", "blue_1"),
        weights=(("blue_4", 3.0), ("blue_2", 2.0), ("blue_1", 1.0)),
    ),
    "green": Strategy(
        "green",
        priority=("green_4", "droplet_1", "green_2", "green_1"),
        weights=(("green_4", 3.0), ("droplet_1", 2.5), ("green_2", 2.0), ("green_1", 1.0)),
    ),
    # No droplet: removing white makes the bag better, so each added chip is drawn more often.
    "cleaner": Strategy(
        "cleaner",
        priority=("remove_white_1", "orange_1"),
        weights=(("remove_white_1", 3.0), ("orange_1", 1.0)),
    ),
    "balanced": Strategy(
        "balanced",
        priority=(
            "droplet_1",
            "blue_2",
            "green_2",
            "orange_1",
            "remove_white_1",
            "blue_1",
            "green_1",
        ),
        weights=(
            ("remove_white_1", 3.0),
            ("droplet_1", 2.5),
            ("blue_2", 2.0),
            ("green_2", 1.5),
            ("orange_1", 1.0),
        ),
    ),
}


def load_strategy(name: str) -> Strategy:
    try:
        return STRATEGIES[name]
    except KeyError:
        raise UnknownStrategy(
            f"unknown strategy {name!r} (known: {', '.join(sorted(STRATEGIES))})"
        ) from None
