"""Ruleset v1.9: spellbook 1, new chips and prices, no remove item."""

from pathlib import Path

import pytest

from quack_rl.components import get_component
from quack_rl.rules import SUPPORTED_RULES_VERSIONS, get_spellbook, load_ruleset

RS = load_ruleset("v1.9")
RS18 = load_ruleset("v1.8")
RULES_DOC = Path(__file__).resolve().parents[1] / "docs" / "rules" / "rules-v1.9.md"

CHIPS = {
    "white": [1, 2, 3],
    "orange": [1, 6],
    "green": [1, 2, 4],
    "blue": [1, 2, 4],
    "red": [1, 2, 4],
}
PRICES = {
    "orange_1": 3, "orange_6": 22,
    "green_1": 4, "green_2": 8, "green_4": 14,
    "blue_1": 5, "blue_2": 10, "blue_4": 19,
    "red_1": 6, "red_2": 10, "red_4": 16,
}  # fmt: skip


def test_v1_9_is_supported_and_loads_with_spellbook_1():
    assert "v1.9" in SUPPORTED_RULES_VERSIONS
    assert RS.version == "v1.9"
    assert RS.spellbook == 1


def test_everything_else_is_as_v1_8():
    for field in (
        "rounds", "explosion_limit", "max_chip_purchases", "distinct_chip_colours", "track_end",
        "last_round_money_percent", "explosion_choice", "last_round_money_divisor", "money",
        "points", "rubies", "start_bag", "die",
    ):  # fmt: skip
        assert getattr(RS, field) == getattr(RS18, field), field


def test_chips_and_no_component_field():
    found: dict[str, list[int]] = {}
    for c in RS.chips:
        found.setdefault(c.colour, []).append(c.value)
        assert c.component is None
    assert found == CHIPS


def test_shop_prices_and_no_remove_item():
    assert {i.id: i.price for i in RS.shop} == PRICES
    assert all(i.kind == "chip" for i in RS.shop)
    assert all(i.kind != "remove_chip" for i in RS.shop)


def test_spellbook_1_has_the_five_colours_of_v1_9_and_the_three_of_v1_10():
    # Spellbook 1 also knows black, yellow and purple since v1.10; v1.9 has no chip of them.
    book = get_spellbook(1)
    assert set(book) == {"white", "orange", "green", "blue", "red", "black", "yellow", "purple"}
    assert {c.colour for c in RS.chips} == {"white", "orange", "green", "blue", "red"}
    for chip in RS.chips:
        get_component(RS.component_name(chip))  # every component is registered


def test_green_and_white_behave_as_in_v1_8():
    by_id = {c.id: c for c in RS.chips}
    old = {c.id: c for c in RS18.chips}
    for chip_id in ("white_1", "white_3", "green_1", "green_4"):
        new_comp = get_component(RS.component_name(by_id[chip_id]))
        old_comp = get_component(RS18.component_name(old[chip_id]))
        assert new_comp is old_comp


@pytest.mark.parametrize("chip_id", ["blue_1", "blue_4", "red_1", "red_4"])
def test_blue_and_red_do_nothing_yet(chip_id):
    # Until the engine issues for red (#114) and blue (#115) are done, blue and red only move by
    # their value: no bonus, no explosion weight, no round-end droplet.
    chip = RS.chip(chip_id)
    comp = get_component(RS.component_name(chip))
    other = RS.chip("white_1")
    assert comp.place_bonus(chip, None) == 0
    assert comp.place_bonus(chip, RS.chip("white_2")) == 0
    assert comp.place_bonus(chip, other) == 0
    assert comp.explosion_weight(chip) == 0
    assert comp.round_end_droplet_halves(chip, 0) == 0


def test_rules_doc_agrees_with_the_file():
    text = RULES_DOC.read_text(encoding="utf-8")
    assert "Rules version: `v1.9`" in text
    assert "Changes from v1.8" in text
    for item in RS.shop:
        assert f"{item.id.replace('_', ' ').title()} | {item.price} |" in text
    for f in range(54):
        assert f"| {f} | {RS.money[f]} | {RS.points[f]} |" in text
