from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar

from quack_rl.rules import ChipSpec


@dataclass(frozen=True)
class PotRoundEnd:
    """What a component gives at round end for a whole pot: points and droplet half steps."""

    points: int = 0
    droplet_halves: int = 0


class Component:
    """Behavior of one chip type. Subclasses override only the hooks they use."""

    name: ClassVar[str]

    def place_bonus(
        self, chip: ChipSpec, previous: ChipSpec | None, pot: Sequence[ChipSpec] = ()
    ) -> int:
        """Extra fields to advance when this chip is placed after `previous` (None: first chip).

        `pot` holds all chips the player placed this round, in order (without `chip`)."""
        return 0

    def explosion_weight(self, chip: ChipSpec) -> int:
        """Amount added to the white total when this chip is placed."""
        return 0

    def hand_size(self, chip: ChipSpec) -> int:
        """Chips the player draws into a hand when this chip is placed (0: none)."""
        return 0

    def round_end_droplet_halves(self, chip: ChipSpec, position_from_end: int) -> int:
        """Droplet half steps at round end; position_from_end 0 = last placed chip."""
        return 0

    def pot_round_end(self, pot: Sequence[ChipSpec], other_pot: Sequence[ChipSpec]) -> PotRoundEnd:
        """Round-end effect that sees the whole pot of the player and the pot of the other player.

        The engine calls it once per player and component that has a chip in the pot. Pots hold all
        chips placed this round, in order, an exploded pot included."""
        return PotRoundEnd()

    def puts_back_previous(self, chip: ChipSpec, previous: ChipSpec | None) -> bool:
        """True if the chip just placed sends `previous` (the chip placed before it, None: first
        chip) back into the bag."""
        return False

    def features(self, chip: ChipSpec) -> dict[str, float]:
        """Descriptive features for entity encodings (spec 7.4)."""
        return {
            "value": float(chip.value),
            "explosion_weight": float(self.explosion_weight(chip)),
        }
