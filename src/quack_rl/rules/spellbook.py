"""Spellbooks: a named set that gives each chip colour its component name."""

from collections.abc import Mapping
from types import MappingProxyType

# White and orange work the same in every spellbook.
FIXED_COLOURS: Mapping[str, str] = MappingProxyType({"white": "white@1", "orange": "orange@1"})

_SPELLBOOKS: dict[int | str, Mapping[str, str]] = {}


class UnknownSpellbook(ValueError):
    """No spellbook is registered under this name."""


def register_spellbook(name: int | str, components: Mapping[str, str]) -> None:
    if name in _SPELLBOOKS:
        raise ValueError(f"spellbook {name!r} is already registered")
    for colour, component in FIXED_COLOURS.items():
        if components.get(colour) != component:
            raise ValueError(f"spellbook {name!r}: {colour} must be {component!r}")
    _SPELLBOOKS[name] = MappingProxyType(dict(components))


def unregister_spellbook(name: int | str) -> None:
    _SPELLBOOKS.pop(name, None)


def registered_spellbooks() -> dict[int | str, Mapping[str, str]]:
    return dict(_SPELLBOOKS)


def get_spellbook(name: int | str) -> Mapping[str, str]:
    try:
        return _SPELLBOOKS[name]
    except KeyError:
        raise UnknownSpellbook(
            f"spellbook {name!r} is not registered (registered: {sorted(_SPELLBOOKS)})"
        ) from None


# Spellbook 1 (ruleset v1.9). Blue and red have no effect yet: blue@2 and red@1 are placeholders
# until the effects of blue (pick step) and red (orange chips in the pot) are built.
register_spellbook(
    1,
    {
        "white": "white@1",
        "orange": "orange@1",
        "green": "green@1",
        "blue": "blue@2",
        "red": "red@1",
    },
)
