"""Ruleset v1.11: the deck of round-start cards (the ruleset field only; the engine does not play them)."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from quack_rl.rules import (
    SUPPORTED_RULES_VERSIONS,
    CardSpec,
    UnknownCardEffect,
    apply_overrides,
    get_card_effect,
    load_ruleset,
    registered_card_effects,
)

RS = load_ruleset("v1.11")
RS110 = load_ruleset("v1.10")
RULES_DOC = Path(__file__).resolve().parents[1] / "docs" / "rules" / "rules-v1.11.md"
RULES_DIR = Path(__file__).resolve().parents[1] / "src" / "quack_rl" / "rules"


def test_v1_11_is_supported_and_loads():
    assert "v1.11" in SUPPORTED_RULES_VERSIONS
    assert RS.version == "v1.11"


def test_everything_else_is_as_v1_10():
    a = RS.model_dump(exclude={"cards", "version"})
    b = RS110.model_dump(exclude={"cards", "version"})
    assert a == b


@pytest.mark.parametrize("version", ["v1", "v1.1", "v1.8", "v1.9", "v1.10"])
def test_older_versions_have_an_empty_deck(version):
    assert load_ruleset(version).cards == []


def test_deck_has_12_cards_and_5_without_effect():
    assert sum(c.count for c in RS.cards) == 12
    assert sum(c.count for c in RS.cards if c.effect == "no_effect") == 5
    assert len([c for c in RS.cards if c.effect != "no_effect"]) == 7
    assert len({c.id for c in RS.cards}) == len(RS.cards)


def test_every_effect_is_registered():
    for card in RS.cards:
        assert get_card_effect(card.effect).name == card.effect
    assert {c.effect for c in RS.cards} <= set(registered_card_effects())


def test_unknown_effect_name_is_refused():
    with pytest.raises(UnknownCardEffect):
        get_card_effect("nope")
    with pytest.raises(ValueError, match="not registered"):
        RS.model_validate({**RS.model_dump(), "cards": [{"id": "x", "effect": "nope", "count": 1}]})


def test_count_below_one_is_refused():
    for count in (0, -1):
        with pytest.raises(ValidationError):
            CardSpec.model_validate({"id": "x", "effect": "no_effect", "count": count})
    with pytest.raises(ValidationError):
        CardSpec.model_validate({"id": "x", "effect": "no_effect", "count": "1"})  # a TOML string


def test_repeated_id_is_refused():
    cards = [{"id": "x", "effect": "no_effect", "count": 1}] * 2
    with pytest.raises(ValueError, match="duplicate ids"):
        RS.model_validate({**RS.model_dump(), "cards": cards})


def test_card_count_can_be_overridden_and_a_bad_value_fails():
    assert apply_overrides(RS, {"cards.card_8_to_12.count": "3"}).cards[-1].count == 3
    with pytest.raises(ValueError):
        apply_overrides(RS, {"cards.card_8_to_12.count": "0"})


def test_older_ruleset_files_have_no_cards_table():
    for version in ("v1", "v1.1", "v1.8", "v1.9", "v1.10"):
        assert "cards" not in (RULES_DIR / f"{version}.toml").read_text(encoding="utf-8"), version


def test_rules_doc_agrees_with_the_file():
    text = RULES_DOC.read_text(encoding="utf-8")
    assert "Rules version: `v1.11`" in text
    assert "Changes from v1.10" in text
    for card in RS.cards:
        row = f"| {card.id} | {card.effect} | {get_card_effect(card.effect).description} | {card.count} |"
        assert row in text, row
    assert "The deck has 12 cards, 5 of them without an effect." in text
