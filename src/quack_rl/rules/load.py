import tomllib
from importlib import resources

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
