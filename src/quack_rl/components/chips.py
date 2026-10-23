from collections.abc import Sequence

from quack_rl.components.base import Component, PotRoundEnd
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
class Green(Component):
    name = "green@1"

    def round_end_droplet_halves(self, chip: ChipSpec, position_from_end: int) -> int:
        return 1 if position_from_end in (0, 1) else 0


@register
class BlueSpellbook1(Component):
    """Blue of spellbook 1: draws a hand of as many chips as its value (the pick step)."""

    name = "blue@2"

    def hand_size(self, chip: ChipSpec) -> int:
        return chip.value


@register
class Red(Component):
    """Red of spellbook 1: moves +1 with 1 or 2 orange chips in the pot, +2 with 3 or more."""

    name = "red@1"

    def place_bonus(
        self, chip: ChipSpec, previous: ChipSpec | None, pot: Sequence[ChipSpec] = ()
    ) -> int:
        oranges = sum(1 for c in pot if c.colour == "orange")
        return 0 if oranges == 0 else 1 if oranges <= 2 else 2


def _count(pot: Sequence[ChipSpec], colour: str) -> int:
    return sum(1 for c in pot if c.colour == colour)


@register
class Black(Component):
    """Black: at round end, drop +1 each on equal counts (1 or more), +1.5 for the larger."""

    name = "black@1"
    round_end_order = 1

    def pot_round_end(self, pot: Sequence[ChipSpec], other_pot: Sequence[ChipSpec]) -> PotRoundEnd:
        mine, theirs = _count(pot, "black"), _count(other_pot, "black")
        if mine >= 1 and mine == theirs:
            return PotRoundEnd(droplet_halves=2)
        if mine > theirs:
            return PotRoundEnd(droplet_halves=3)
        return PotRoundEnd()


@register
class Yellow(Component):
    """Yellow: sends a white chip placed just before it back into the bag."""

    name = "yellow@1"

    def puts_back_previous(self, chip: ChipSpec, previous: ChipSpec | None) -> bool:
        return previous is not None and previous.colour == "white"


@register
class Purple(Component):
    """Purple: at round end, 1 chip: 1 point; 2: 1 point, drop +0.5; 3 or more: 2 points, drop +1."""

    name = "purple@1"
    round_end_order = 2

    def pot_round_end(self, pot: Sequence[ChipSpec], other_pot: Sequence[ChipSpec]) -> PotRoundEnd:
        count = _count(pot, "purple")
        if count == 0:
            return PotRoundEnd()
        if count == 1:
            return PotRoundEnd(points=1)
        if count == 2:
            return PotRoundEnd(points=1, droplet_halves=1)
        return PotRoundEnd(points=2, droplet_halves=2)
