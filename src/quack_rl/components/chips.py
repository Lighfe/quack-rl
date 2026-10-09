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

    def place_bonus(self, chip: ChipSpec, previous: ChipSpec | None) -> int:
        return 1 if previous is not None and previous.value != 1 else 0


@register
class Green(Component):
    name = "green@1"

    def round_end_droplet_halves(self, chip: ChipSpec, position_from_end: int) -> int:
        return 1 if position_from_end in (0, 1) else 0
