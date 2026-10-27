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


# Spellbook 1 (rulesets v1.9, v1.10). Blue draws a hand and the player picks (blue@2). Black,
# yellow and purple are used only from v1.10; v1.9 has no chip of these colours.
register_spellbook(
    1,
    {
        "white": "white@1",
        "orange": "orange@1",
        "green": "green@1",
        "blue": "blue@2",
        "red": "red@1",
        "black": "black@1",
        "yellow": "yellow@1",
        "purple": "purple@1",
    },
)


# One-line effect text of each component (at most 60 characters, no newline), shown with the
# shop catalogue. It agrees with the "Effect when placed" column of the Chips table in the
# rules document. A colour's text is the text of the component its spellbook gives it.
_COMPONENT_EFFECTS: Mapping[str, str] = MappingProxyType(
    {
        "white@1": "Advance by its value; adds it to the explosion total.",
        "orange@1": "Advance by its value. No other effect.",
        "green@1": "Advance; 1 ruby at round end if among the last two placed.",
        "blue@2": "Advance by its value, then draw hand chips and pick one.",
        "red@1": "Advance by its value, plus extra for orange chips placed.",
        "black@1": "Advance; round end: droplet effect comparing black chips.",
        "yellow@1": "Advance; a white chip placed just before goes back to bag.",
        "purple@1": "Advance; round end: points and droplet by purple count.",
    }
)


def colour_effect(spellbook: int | str, colour: str) -> str:
    """The one-line effect text of a colour in a spellbook."""
    return _COMPONENT_EFFECTS[get_spellbook(spellbook)[colour]]
