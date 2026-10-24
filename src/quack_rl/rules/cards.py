"""Round-start card effects (v1.11): a registry of the effect names a ruleset `cards` entry may use.

The engine plays them in `engine/cards.py`, `engine/resolve.py` and `engine/shop.py`.
"""

from dataclasses import dataclass


class UnknownCardEffect(ValueError):
    """No card effect is registered under this name."""


@dataclass(frozen=True)
class CardEffect:
    name: str
    description: str


_EFFECTS: dict[str, CardEffect] = {}


def register_card_effect(name: str, description: str) -> CardEffect:
    if name in _EFFECTS:
        raise ValueError(f"card effect {name!r} is already registered")
    _EFFECTS[name] = effect = CardEffect(name, description)
    return effect


def get_card_effect(name: str) -> CardEffect:
    try:
        return _EFFECTS[name]
    except KeyError:
        raise UnknownCardEffect(
            f"card effect {name!r} is not registered (registered: {sorted(_EFFECTS)})"
        ) from None


def registered_card_effects() -> dict[str, CardEffect]:
    return dict(_EFFECTS)


register_card_effect("ruby_extra", "a ruby field gives 1 ruby more this round")
register_card_effect("restart_after_5", "restart option after 5 chips")
register_card_effect("drop_all_1", "every drop +1")
register_card_effect("explosion_limit_plus_2", "explosion limit +2 this round")
register_card_effect(
    "choice_black_or_value2_or_rubies",
    "choice: black 1 chip, or any value-2 chip, or 3 rubies",
)
register_card_effect("choice_drop2_or_purple", "choice: drop +2, or purple 1 chip")
register_card_effect("fewest_points_green", "fewest points get a green 1 chip")
register_card_effect("die_twice", "a player who rolls the bonus die in Resolve rolls it twice")
register_card_effect("fewest_rubies_ruby", "the player(s) with the fewest rubies get 1 ruby")
register_card_effect("ruby_field_points", "a scoring ruby field gives +2 points on top of the ruby")
register_card_effect("refill_flasks", "at the end of the round all flasks are refilled")
register_card_effect("everyone_rolls", "at the card step every player rolls the bonus die once")
register_card_effect(
    "rat_tails_for_rubies", "a player may give up 1 to 3 rat tails of the bonus for the same number of rubies"
)
register_card_effect("ruby_for_chip", "a player may swap one ruby for a value-1 chip")
register_card_effect(
    "points_or_remove_white", "choice: 4 points, or a white 1 chip leaves the bag for the rest of the game"
)
register_card_effect(
    "chip4_or_tail_points", "choice: a value-4 chip, or points equal to the rat tail entitlement"
)
