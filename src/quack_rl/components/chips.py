from collections.abc import Sequence

from quack_rl.components.base import Component
from quack_rl.components.registry import register
from quack_rl.rules import ChipSpec


@register
class White(Component):
    name = "white@1"

    def explosion_weight(self, chip: ChipSpec) -> int:
        return chip.value


@register
class Orange(Component):
    name = "orange@1"


@register
class Blue(Component):
    name = "blue@1"

    def place_bonus(
        self, chip: ChipSpec, previous: ChipSpec | None, pot: Sequence[ChipSpec] = ()
    ) -> int:
        return 1 if previous is not None and previous.value != 1 else 0


@register
class Green(Component):
    name = "green@1"

    def round_end_droplet_halves(self, chip: ChipSpec, position_from_end: int) -> int:
        return 1 if position_from_end in (0, 1) else 0


@register
class BlueSpellbook1(Component):
    """Blue of spellbook 1: no effect yet (the pick step is built later)."""

    name = "blue@2"


@register
class Red(Component):
    """Red of spellbook 1: moves +1 with 1 or 2 orange chips in the pot, +2 with 3 or more."""

    name = "red@1"

    def place_bonus(
        self, chip: ChipSpec, previous: ChipSpec | None, pot: Sequence[ChipSpec] = ()
    ) -> int:
        oranges = sum(1 for c in pot if c.colour == "orange")
        return 0 if oranges == 0 else 1 if oranges <= 2 else 2
