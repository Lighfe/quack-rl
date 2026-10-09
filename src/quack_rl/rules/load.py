import tomllib
from collections.abc import Mapping
from importlib import resources
from typing import Any

from quack_rl.rules.model import Ruleset

SUPPORTED_RULES_VERSIONS: tuple[str, ...] = ("v1",)


class UnsupportedRulesVersion(ValueError):
    """The rules version is not supported by this engine."""


def load_ruleset(version: str) -> Ruleset:
    if version not in SUPPORTED_RULES_VERSIONS:
        raise UnsupportedRulesVersion(
            f"rules version {version!r} is not supported (supported: {SUPPORTED_RULES_VERSIONS})"
        )
    text = resources.files("quack_rl.rules").joinpath(f"{version}.toml").read_text(encoding="utf-8")
    return Ruleset.model_validate(tomllib.loads(text))


def with_rounds(rs: Ruleset, rounds: int) -> Ruleset:
    """A copy of the ruleset with another number of rounds (the last round gets the multiplier)."""
    if rounds < 1:
        raise ValueError(f"rounds must be at least 1, got {rounds}")
    return rs.model_copy(update={"rounds": rounds})


_REFUSED_KEYS = {
    "rounds": "use --rounds",
    "version": "the base version is chosen with --rules",
}


def _parse_value(key: str, raw: Any, current: Any) -> Any:
    """Parse an override value by the type of the field it replaces."""
    if isinstance(current, bool):
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str) and raw.strip().lower() in ("true", "false"):
            return raw.strip().lower() == "true"
        raise ValueError(f"override {key!r}: {raw!r} is not a bool (true or false)")
    if isinstance(current, int):
        if isinstance(raw, int) and not isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            try:
                return int(raw.strip())
            except ValueError:
                pass
        raise ValueError(f"override {key!r}: {raw!r} is not an int")
    if isinstance(current, str):
        if isinstance(raw, str):
            return raw
        raise ValueError(f"override {key!r}: {raw!r} is not a str")
    raise ValueError(f"override {key!r}: the target is not a single int, bool or str value")


def _apply_one(data: dict[str, Any], key: str, raw: Any) -> None:
    segments = key.split(".")
    if segments[0] in _REFUSED_KEYS and len(segments) == 1:
        raise ValueError(f"override {key!r} is not allowed: {_REFUSED_KEYS[segments[0]]}")
    node: Any = data
    for i, seg in enumerate(segments):
        last = i == len(segments) - 1
        if isinstance(node, dict):
            if seg not in node:
                raise ValueError(f"override {key!r}: unknown key {seg!r}")
            container, slot = node, seg
        elif isinstance(node, list):
            matches = [e for e in node if isinstance(e, dict) and e.get("id") == seg]
            if not matches:
                raise ValueError(f"override {key!r}: unknown entry id {seg!r}")
            if last:
                raise ValueError(f"override {key!r}: the target is not a single value")
            node = matches[0]
            continue
        else:
            raise ValueError(f"override {key!r}: {seg!r} is below a single value")
        if last:
            container[slot] = _parse_value(key, raw, container[slot])
        else:
            node = container[slot]


def apply_overrides(rs: Ruleset, overrides: Mapping[str, Any]) -> Ruleset:
    """A validated copy of the ruleset with overrides applied; the input stays unchanged.

    A key is a dotted path. A segment is a field name; for a list (shop, chips, die) it is the
    `id` of an entry, for example `shop.orange_1.price`. A string value is parsed by the type
    of the target field.
    """
    if not overrides:
        return rs
    data = rs.model_dump()
    for key, raw in overrides.items():
        _apply_one(data, key, raw)
    try:
        return Ruleset.model_validate(data)
    except ValueError as e:
        keys = ", ".join(repr(k) for k in overrides)
        raise ValueError(f"overrides {keys} break the ruleset: {e}") from e
