"""Ruleset v1.8: points per field, no shop points, explosion choice, last round conversion."""

import tomllib
from importlib import resources
from pathlib import Path

import pytest
from pydantic import ValidationError

from quack_rl.rules import SUPPORTED_RULES_VERSIONS, load_ruleset

RS18 = load_ruleset("v1.8")
RULES_DOC = Path(__file__).resolve().parents[1] / "docs" / "rules" / "rules-v1.8.md"


def _toml(version: str) -> dict:
    text = resources.files("quack_rl.rules").joinpath(f"{version}.toml").read_text(encoding="utf-8")
    return tomllib.loads(text)


def test_v1_8_is_supported_and_loads():
    assert SUPPORTED_RULES_VERSIONS[:2] == ("v1", "v1.1")
    assert "v1.8" in SUPPORTED_RULES_VERSIONS
    assert RS18.version == "v1.8"


def test_v1_8_scalar_settings():
    assert RS18.last_round_money_percent == 100
    assert RS18.explosion_choice is True
    assert RS18.last_round_money_divisor == 5


def test_points_follow_the_formula():
    expected = [max(0, round(0.6 * m - 6.2)) for m in RS18.money]
    assert RS18.points == expected
    assert len(RS18.points) == 54


@pytest.mark.parametrize(
    ("fields", "points"), [((53,), 15), ((39, 40), 10), ((29, 30), 7), ((19, 20), 4)]
)
def test_points_known_values(fields, points):
    for f in fields:
        assert RS18.points[f] == points


def test_shop_has_no_points_items_and_the_rest_is_as_v1_1():
    rs11 = load_ruleset("v1.1")
    removed = {"points_2", "points_5", "points_10"}
    assert {i.id for i in rs11.shop} - {i.id for i in RS18.shop} == removed
    assert all(i.kind != "points" for i in RS18.shop)
    assert RS18.shop == [i for i in rs11.shop if i.id not in removed]
    assert RS18.die == rs11.die
    assert RS18.money == rs11.money
    assert RS18.chips == rs11.chips


@pytest.mark.parametrize("version", ["v1", "v1.1"])
def test_old_versions_have_the_new_fields_unset(version):
    rs = load_ruleset(version)
    assert rs.points is None
    assert rs.explosion_choice is False
    assert rs.last_round_money_divisor is None


@pytest.mark.parametrize("bad", [[0] * 53, [0] * 55, [0] * 53 + [-1]])
def test_bad_points_are_rejected(bad):
    data = _toml("v1.8")
    data["points"] = bad
    with pytest.raises(ValidationError):
        type(RS18).model_validate(data)


def test_rules_doc_exists_with_changes_section_and_table():
    text = RULES_DOC.read_text(encoding="utf-8")
    assert "Rules version: `v1.8`" in text
    assert "Changes from v1.1" in text
    for word in ("explosion choice", "money // 5", "No shop points"):
        assert word.lower() in text.lower()
    for f in range(54):
        assert f"| {f} | {RS18.money[f]} | {RS18.points[f]} |" in text
