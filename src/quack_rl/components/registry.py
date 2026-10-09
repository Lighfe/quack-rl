from quack_rl.components.base import Component

_REGISTRY: dict[str, Component] = {}


class UnknownComponent(KeyError):
    """No component is registered under this name."""


def register[C: Component](cls: type[C]) -> type[C]:
    if cls.name in _REGISTRY:
        raise ValueError(f"component {cls.name} is already registered")
    _REGISTRY[cls.name] = cls()
    return cls


def get_component(name: str) -> Component:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise UnknownComponent(name) from None
