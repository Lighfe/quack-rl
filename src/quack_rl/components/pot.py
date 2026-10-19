from collections.abc import Sequence

from quack_rl.components.base import Component, PotRoundEnd
from quack_rl.components.registry import get_component
from quack_rl.rules import Ruleset


def pot_effects(
    rs: Ruleset, pot: Sequence[str], other_pot: Sequence[str]
) -> list[tuple[Component, PotRoundEnd]]:
    """The round-end effects that see a whole pot, in the order the engine applies them.

    `pot` and `other_pot` are chip ids placed this round. One entry per component that has a chip
    in `pot`, ordered by `round_end_order` and name; entries without an effect are included.
    The engine (`apply_resolve`) and the report (odds) both call this, so they use one order and
    the same hook inputs."""
    chips = [rs.chip(c) for c in pot]
    other_chips = [rs.chip(c) for c in other_pot]
    names = {rs.component_name(c) for c in chips}
    components = sorted(
        (get_component(n) for n in names), key=lambda c: (c.round_end_order, c.name)
    )
    return [(c, c.pot_round_end(chips, other_chips)) for c in components]
