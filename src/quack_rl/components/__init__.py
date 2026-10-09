from quack_rl.components import chips as _chips  # noqa: F401  (registers the v1 components)
from quack_rl.components.base import Component
from quack_rl.components.registry import UnknownComponent, get_component, register

__all__ = ["Component", "UnknownComponent", "get_component", "register"]
