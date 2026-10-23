"""Ruleset v1.10: black, yellow and purple, and a minimum buy round per shop item."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from quack_rl.components import PotRoundEnd, get_component
from quack_rl.rules import SUPPORTED_RULES_VERSIONS, ShopItem, apply_overrides, get_spellbook, load_ruleset

RS = load_ruleset("v1.10")
RS19 = load_ruleset("v1.9")
RULES_DOC = Path(__file__).resolve().parents[1] / "docs" / "rules" / "rules-v1.10.md"

NEW_ITEMS = {  # id: (price, min_round)
    "black_1": (10, 1),
    "yellow_1": (8, 2), "yellow_2": (12, 2), "yellow_4": (18, 2),
    "purple_1": (9, 3),
}  # fmt: skip


def comp(colour: str):
    chip = next(c for c in RS.chips if c.colour == colour)
    return get_component(RS.component_name(chip))


def pot(colour: str, n: int):
    chip = next(c for c in RS.chips if c.colour == colour)
    return [chip] * n


def test_v1_10_is_supported_and_loads():
    assert "v1.10" in SUPPORTED_RULES_VERSIONS
    assert RS.version == "v1.10"
    assert RS.spellbook == 1


def test_everything_else_is_as_v1_9():
    for field in (
        "rounds", "explosion_limit", "max_chip_purchases", "distinct_chip_colours", "track_end",
        "last_round_money_percent", "explosion_choice", "last_round_money_divisor", "money",
        "points", "rubies", "start_bag", "die", "spellbook",
    ):  # fmt: skip
        assert getattr(RS, field) == getattr(RS19, field), field
    old_chips = [c.model_dump() for c in RS19.chips]
    assert [c.model_dump() for c in RS.chips if c.colour not in ("black", "yellow", "purple")] == old_chips


def test_shop_is_v1_9_plus_the_new_items():
    old = {i.id: i.price for i in RS19.shop}
    now = {i.id: i.price for i in RS.shop}
    assert {k: v for k, v in now.items() if k in old} == old
    assert {k: (RS.shop_item(k).price, RS.shop_item(k).min_round) for k in now if k not in old} == NEW_ITEMS
    assert all(RS.shop_item(k).min_round == 1 for k in old)


def test_new_chip_values_and_no_component_field():
    found: dict[str, list[int]] = {}
    for c in RS.chips:
        found.setdefault(c.colour, []).append(c.value)
        assert c.component is None
    assert found["black"] == [1] and found["yellow"] == [1, 2, 4] and found["purple"] == [1]


def test_min_round_default_is_one_in_every_older_version():
    for version in ("v1", "v1.1", "v1.8", "v1.9"):
        assert all(i.min_round == 1 for i in load_ruleset(version).shop), version


def test_min_round_validation():
    base = {"id": "x", "price": 1, "kind": "droplet", "halves": 1}
    assert ShopItem.model_validate(base).min_round == 1
    assert ShopItem.model_validate({**base, "min_round": 4}).min_round == 4
    with pytest.raises(ValidationError):
        ShopItem.model_validate({**base, "min_round": 0})
    with pytest.raises(ValidationError):
        ShopItem.model_validate({**base, "min_round": "2"})  # a TOML string against an integer


def test_min_round_can_be_overridden_and_a_bad_value_fails():
    assert apply_overrides(RS, {"shop.purple_1.min_round": "5"}).shop_item("purple_1").min_round == 5
    with pytest.raises(ValueError):
        apply_overrides(RS, {"shop.purple_1.min_round": "0"})


def test_spellbook_1_has_black_yellow_purple():
    book = get_spellbook(1)
    assert set(book) == {"white", "orange", "green", "blue", "red", "black", "yellow", "purple"}
    assert {c.colour for c in RS.chips} == set(book)
    for chip in RS.chips:
        get_component(RS.component_name(chip))


def test_v1_9_has_no_chip_of_the_new_colours():
    assert {c.colour for c in RS19.chips} == {"white", "orange", "green", "blue", "red"}


def test_black_equal_counts_both_drop_one():
    black = comp("black")
    assert black.pot_round_end(pot("black", 1), pot("black", 1)) == PotRoundEnd(droplet_halves=2)
    assert black.pot_round_end(pot("black", 3), pot("black", 3)) == PotRoundEnd(droplet_halves=2)


def test_black_larger_count_drops_one_and_a_half_smaller_gets_nothing():
    black = comp("black")
    assert black.pot_round_end(pot("black", 2), pot("black", 1)) == PotRoundEnd(droplet_halves=3)
    assert black.pot_round_end(pot("black", 1), []) == PotRoundEnd(droplet_halves=3)
    assert black.pot_round_end(pot("black", 1), pot("black", 2)) == PotRoundEnd()


def test_black_zero_counts_and_other_colours_do_nothing():
    black = comp("black")
    assert black.pot_round_end([], []) == PotRoundEnd()
    assert black.pot_round_end(pot("white", 2), pot("black", 1)) == PotRoundEnd()
    assert black.pot_round_end(pot("black", 1) + pot("white", 2), pot("black", 1)) == PotRoundEnd(droplet_halves=2)


@pytest.mark.parametrize(
    ("count", "expected"),
    [(0, PotRoundEnd()), (1, PotRoundEnd(points=1)), (2, PotRoundEnd(1, 1)), (3, PotRoundEnd(2, 2)), (5, PotRoundEnd(2, 2))],
)
def test_purple_by_chips_in_the_pot(count, expected):
    assert comp("purple").pot_round_end(pot("purple", count) + pot("white", 2), pot("purple", 4)) == expected


def test_yellow_puts_back_a_white_chip_before_it():
    yellow = comp("yellow")
    white, orange, green = RS.chip("white_2"), RS.chip("orange_1"), RS.chip("green_1")
    assert yellow.puts_back_previous(RS.chip("yellow_1"), white) is True
    assert yellow.puts_back_previous(RS.chip("yellow_4"), white) is True
    assert yellow.puts_back_previous(RS.chip("yellow_2"), orange) is False
    assert yellow.puts_back_previous(RS.chip("yellow_2"), green) is False
    assert yellow.puts_back_previous(RS.chip("yellow_2"), None) is False


def test_new_hooks_default_to_nothing_for_older_components():
    for colour in ("white", "orange", "green", "blue", "red"):
        c = comp(colour)
        assert c.pot_round_end(pot(colour, 2), pot("black", 2)) == PotRoundEnd()
        assert c.puts_back_previous(RS.chip("white_1"), RS.chip("white_1")) is False
    green = RS.chip("green_1")
    assert comp("green").round_end_droplet_halves(green, 0) == 1
    assert comp("green").round_end_droplet_halves(green, 2) == 0


def test_rules_doc_agrees_with_the_file():
    text = RULES_DOC.read_text(encoding="utf-8")
    assert "Rules version: `v1.10`" in text
    assert "Changes from v1.9" in text
    for item in RS.shop:
        name = item.id.replace("_", " ").title()
        assert f"{name} | {item.price} | {item.min_round} |" in text
    for f in range(54):
        assert f"| {f} | {RS.money[f]} | {RS.points[f]} |" in text
