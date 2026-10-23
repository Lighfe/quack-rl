"""Round-start card effects (v1.11): a registry of the effect names a ruleset `cards` entry may use.

This registers names only. The engine does not play the cards yet (issues #143 and #144).
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


register_card_effect("ruby_extra", "a ruby field gives 1 ruby more")
register_card_effect("restart_after_5", "restart option after 5 chips")
register_card_effect("drop_all_1", "every drop +1")
register_card_effect("explosion_limit_plus_2", "explosion limit +2 this round")
register_card_effect(
    "choice_black_or_value2_or_drop", "choice: black 1 chip, or any value-2 chip, or drop +1.5 at round end"
)
register_card_effect("choice_drop2_or_purple", "choice: drop +2, or purple 1 chip")
register_card_effect("fewest_points_green", "fewest points get a green 1 chip")
register_card_effect("no_effect", "no effect")
