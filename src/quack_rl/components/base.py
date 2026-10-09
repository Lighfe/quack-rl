from typing import ClassVar

from quack_rl.rules import ChipSpec


class Component:
    """Behavior of one chip type. Subclasses override only the hooks they use."""

    name: ClassVar[str]

    def place_bonus(self, chip: ChipSpec, previous: ChipSpec | None) -> int:
        """Extra fields to advance when this chip is placed after `previous` (None: first chip)."""
        return 0

    def explosion_weight(self, chip: ChipSpec) -> int:
        """Amount added to the white total when this chip is placed."""
        return 0

    def round_end_droplet_halves(self, chip: ChipSpec, position_from_end: int) -> int:
        """Droplet half steps at round end; position_from_end 0 = last placed chip."""
        return 0

    def features(self, chip: ChipSpec) -> dict[str, float]:
        """Descriptive features for entity encodings (spec 7.4)."""
        return {
            "value": float(chip.value),
            "explosion_weight": float(self.explosion_weight(chip)),
        }
