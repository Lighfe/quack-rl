"""`LayoutRefused` and `check_policy_layout`, taken out of `encode.py` when the policy code was archived."""

from quack_rl.rl.encode import HAND_LAYOUT, observation_layout
from quack_rl.rules import Ruleset


class LayoutRefused(ValueError):
    """A trained policy was asked to act on a layout it was not built for (layout 4, 5, 6 or 7)."""


def check_policy_layout(rs: Ruleset) -> None:
    """Raise `LayoutRefused` for a ruleset on layout 4, 5, 6 or 7: no policy is trained for it yet."""
    layout = observation_layout(rs)
    if layout >= HAND_LAYOUT:
        raise LayoutRefused(
            f"rules {rs.version!r} use observation layout {layout}; no trained policy, "
            f"self-play, finetune, offline or evaluate run exists for layout {layout} yet "
            "(name an older rules version to run a policy, for example --rules v1.1)"
        )
