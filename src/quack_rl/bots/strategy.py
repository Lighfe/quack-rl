"""The shop strategies of `RuleBot`: each is data (name, colour) plus a scoring function.

A scoring function gets a `ShopView` and gives every legal shop action a score; a higher score
is a better action. The scores are ranks: the best action scores 0, the next distinct level -1,
and so on, so one temperature fits every strategy (see `bots/rule_bot.py`). Equal scores tie;
the bot breaks a tie at temperature 0 by `legal` order.
"""

from collections.abc import Callable, Hashable
from dataclasses import dataclass

from quack_rl.engine import BUY_PREFIX, DONE

# Ruleset v2.3: chip buys per player per round (`max_chip_purchases`), of distinct colours.
MAX_CHIP_BUYS = 2

BLACK = "black_1"
PURPLE = "purple_1"
BLACK_ROUNDS = range(1, 4)  # blackpurple buys black in rounds 1 to 3 ...
BLACK_TARGET = 2  # ... while the player owns fewer than this many black chips
PURPLE_ROUNDS = range(5, 8)  # blackpurple buys purple in rounds 5 to 7
PREFERRED_COLOURS = frozenset({"red", "orange"})  # blackpurple's colours otherwise


@dataclass(frozen=True)
class ShopView:
    """What a strategy sees of one shop decision.

    `prices` and `colours` are keyed by shop item id. `bought_colours` are the chip colours
    bought this round; `black_bought` counts the black chips the player owns.
    """

    round: int
    money: int
    legal: tuple[str, ...]
    bought_colours: frozenset[str]
    black_bought: int
    prices: dict[str, int]
    colours: dict[str, str]

    def buys(self) -> list[str]:
        """The legal shop item ids, in `legal` order."""
        return [a.removeprefix(BUY_PREFIX) for a in self.legal if a.startswith(BUY_PREFIX)]


@dataclass(frozen=True)
class Strategy:
    name: str
    colour: str  # the chip colour for cards 11, 12 and 19
    score: Callable[[ShopView], dict[str, float]]


def _ranks(view: ShopView, key: Callable[[str], Hashable]) -> dict[str, float]:
    """Score each legal action by the dense rank of `key(item)`, best (smallest key) 0.

    `done` gets the rank below every buy, so it wins only when no buy is legal."""
    keys = {BUY_PREFIX + item: key(item) for item in view.buys()}
    levels = sorted(set(keys.values()))
    rank = {k: i for i, k in enumerate(levels)}
    scores: dict[str, float] = {a: -float(rank[k]) for a, k in keys.items()}
    if DONE in view.legal:
        scores[DONE] = -float(len(levels))
    return scores


def score_topchip(view: ShopView) -> dict[str, float]:
    """The most expensive chip the money pays for; the next shop step spends the rest alike."""
    return _ranks(view, lambda item: -view.prices[item])


def score_spendmost(view: ShopView) -> dict[str, float]:
    """The buy that starts the one- or two-buy set with the highest total price.

    A second buy is of another colour and paid from the money left after the first. Among
    equal totals the more expensive first buy ranks first."""
    buys = view.buys()
    second_allowed = len(view.bought_colours) + 1 < MAX_CHIP_BUYS

    def total(item: str) -> int:
        price = view.prices[item]
        rest = view.money - price
        seconds = [
            view.prices[other]
            for other in buys
            if second_allowed
            and view.colours[other] != view.colours[item]
            and view.prices[other] <= rest
        ]
        return price + max(seconds, default=0)

    return _ranks(view, lambda item: (-total(item), -view.prices[item]))


def score_blackpurple(view: ShopView) -> dict[str, float]:
    """Black in rounds 1 to 3 (fewer than two owned), purple in rounds 5 to 7, else red and
    orange; within a tier the most expensive first, as `topchip`."""

    def tier(item: str) -> int:
        if item == BLACK and view.round in BLACK_ROUNDS and view.black_bought < BLACK_TARGET:
            return 0
        if item == PURPLE and view.round in PURPLE_ROUNDS:
            return 0
        if view.colours[item] in PREFERRED_COLOURS:
            return 1
        return 2

    return _ranks(view, lambda item: (tier(item), -view.prices[item]))


STRATEGIES: dict[str, Strategy] = {
    "topchip": Strategy("topchip", "blue", score_topchip),
    "spendmost": Strategy("spendmost", "blue", score_spendmost),
    "blackpurple": Strategy("blackpurple", "red", score_blackpurple),
}
