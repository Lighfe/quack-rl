import copy
import re
import tomllib
from collections.abc import Callable
from importlib import resources
from pathlib import Path
from typing import Any

import pydantic
import pytest

from quack_rl.rules import (
    SUPPORTED_RULES_VERSIONS,
    Ruleset,
    UnsupportedRulesVersion,
    load_ruleset,
)

RULES_DOC = Path(__file__).resolve().parents[1] / "docs" / "rules" / "rules-v2.md"


def doc_money(field: int) -> int:
    # formula from docs/rules/rules-v2.md, section 1 "Track"
    if field <= 14:
        return field
    if field <= 52:
        return 15 + (field - 15) // 2
    return 35


def test_supported_versions():
    assert SUPPORTED_RULES_VERSIONS == ("v2",)


def test_old_version_refused():
    with pytest.raises(UnsupportedRulesVersion):
        load_ruleset("v1.11")  # old-version-ok


def test_load_v2_returns_ruleset():
    rs = load_ruleset("v2")
    assert isinstance(rs, Ruleset)
    assert rs.version == "v2"


def test_unsupported_version_is_value_error():
    assert issubclass(UnsupportedRulesVersion, ValueError)


@pytest.mark.parametrize("version", ["v0", "v1.2", "V1", ""])
def test_unknown_version_is_refused(version: str):
    with pytest.raises(UnsupportedRulesVersion):
        load_ruleset(version)


def test_core_numbers():
    rs = load_ruleset("v2")
    assert rs.version == "v2"
    assert rs.rounds == 9
    assert rs.explosion_limit == 7
    assert rs.max_chip_purchases == 2
    assert rs.track_end == 53


def test_money_track_matches_rules_doc():
    rs = load_ruleset("v2")
    assert len(rs.money) == 54
    assert rs.money == [doc_money(f) for f in range(54)]
    assert rs.money[53] == 35


def test_rubies_match_rules_doc():
    rs = load_ruleset("v2")
    assert rs.rubies == [5, 9, 13, 16, 20, 24, 28, 30, 34, 36, 40, 42, 46, 50, 52]
    line = "Ruby fields: " + ", ".join(str(f) for f in rs.rubies) + "."
    assert line in RULES_DOC.read_text(encoding="utf-8")


def test_start_bag():
    rs = load_ruleset("v2")
    assert rs.start_bag == {"white_1": 4, "white_2": 2, "white_3": 1, "orange_1": 1, "green_1": 1}


def test_chips():
    rs = load_ruleset("v2")
    # v2 names a spellbook: it gives the component of each colour
    assert rs.spellbook == 1
    assert [(c.id, c.colour, c.value) for c in rs.chips] == [
        ("white_1", "white", 1),
        ("white_2", "white", 2),
        ("white_3", "white", 3),
        ("orange_1", "orange", 1),
        ("orange_6", "orange", 6),
        ("green_1", "green", 1),
        ("green_2", "green", 2),
        ("green_4", "green", 4),
        ("blue_1", "blue", 1),
        ("blue_2", "blue", 2),
        ("blue_4", "blue", 4),
        ("red_1", "red", 1),
        ("red_2", "red", 2),
        ("red_4", "red", 4),
        ("black_1", "black", 1),
        ("yellow_1", "yellow", 1),
        ("yellow_2", "yellow", 2),
        ("yellow_4", "yellow", 4),
        ("purple_1", "purple", 1),
    ]
    assert rs.component_name(rs.chip("blue_2")) == "blue@2"


SHOP_LABELS = {
    "orange_1": "Orange 1",
    "orange_6": "Orange 6",
    "green_1": "Green 1",
    "green_2": "Green 2",
    "green_4": "Green 4",
    "blue_1": "Blue 1",
    "blue_2": "Blue 2",
    "blue_4": "Blue 4",
    "red_1": "Red 1",
    "red_2": "Red 2",
    "red_4": "Red 4",
    "black_1": "Black 1",
    "yellow_1": "Yellow 1",
    "yellow_2": "Yellow 2",
    "yellow_4": "Yellow 4",
    "purple_1": "Purple 1",
}


def test_shop_items():
    rs = load_ruleset("v2")
    assert [(i.id, i.price, i.kind) for i in rs.shop] == [
        ("orange_1", 3, "chip"),
        ("orange_6", 22, "chip"),
        ("green_1", 4, "chip"),
        ("green_2", 8, "chip"),
        ("green_4", 14, "chip"),
        ("blue_1", 5, "chip"),
        ("blue_2", 10, "chip"),
        ("blue_4", 19, "chip"),
        ("red_1", 6, "chip"),
        ("red_2", 10, "chip"),
        ("red_4", 16, "chip"),
        ("black_1", 10, "chip"),
        ("yellow_1", 8, "chip"),
        ("yellow_2", 12, "chip"),
        ("yellow_4", 18, "chip"),
        ("purple_1", 9, "chip"),
    ]
    for item in rs.shop:
        assert item.kind == "chip" and item.chip == item.id  # v2 sells chips only


def test_shop_prices_match_rules_doc():
    rs = load_ruleset("v2")
    doc = RULES_DOC.read_text(encoding="utf-8")
    assert [i.id for i in rs.shop] == list(SHOP_LABELS)
    for item in rs.shop:
        pattern = rf"\|[^|\n]*{re.escape(SHOP_LABELS[item.id])}\s*\|\s*{item.price}\s*\|"
        assert re.search(pattern, doc), item.id


def test_die_faces():
    rs = load_ruleset("v2")
    assert [f.id for f in rs.die] == ["orange_1", "droplet_1", "droplet_half", "point_1", "point_2"]
    faces = {f.id: f for f in rs.die}
    assert sum(f.weight for f in rs.die) == 6
    d1 = faces["droplet_1"]
    assert (d1.kind, d1.halves, d1.weight) == ("droplet", 2, 1)
    dh = faces["droplet_half"]
    assert (dh.kind, dh.halves, dh.weight) == ("droplet", 1, 1)
    o1 = faces["orange_1"]
    assert (o1.kind, o1.chip, o1.weight) == ("chip", "orange_1", 1)
    p1 = faces["point_1"]
    assert (p1.kind, p1.points, p1.weight) == ("points", 1, 2)
    p2 = faces["point_2"]
    assert (p2.kind, p2.points, p2.weight) == ("points", 2, 1)  # no money face in v2


def test_lookup_helpers():
    rs = load_ruleset("v2")
    assert rs.chip("blue_2").value == 2
    assert rs.shop_item("orange_6").price == 22
    with pytest.raises(KeyError):
        rs.chip("purple_9")
    with pytest.raises(KeyError):
        rs.shop_item("purple_9")


def _v2_data() -> dict[str, Any]:
    text = resources.files("quack_rl.rules").joinpath("v2.toml").read_text(encoding="utf-8")
    return tomllib.loads(text)


def _by_id(entries: list[dict[str, Any]], entry_id: str) -> dict[str, Any]:
    return next(e for e in entries if e["id"] == entry_id)


def _set_shop_chip(item_id: str) -> Callable[[dict[str, Any]], None]:
    def change(d: dict[str, Any]) -> None:
        _by_id(d["shop"], item_id)["chip"] = "purple_9"

    return change


def _set_die_chip(d: dict[str, Any]) -> None:
    _by_id(d["die"], "orange_1")["chip"] = "purple_9"


def _duplicate_first(key: str) -> Callable[[dict[str, Any]], None]:
    def change(d: dict[str, Any]) -> None:
        d[key].append(copy.deepcopy(d[key][0]))

    return change


REFUSALS: dict[str, Callable[[dict[str, Any]], None]] = {
    "money_53_entries": lambda d: d["money"].pop(),
    "money_55_entries": lambda d: d["money"].append(35),
    "ruby_on_54": lambda d: d["rubies"].append(54),
    "ruby_on_minus_1": lambda d: d["rubies"].insert(0, -1),
    "start_bag_unknown_chip": lambda d: d["start_bag"].update({"purple_9": 1}),
    "shop_chip_item_unknown_chip": _set_shop_chip("blue_1"),
    "die_chip_face_unknown_chip": _set_die_chip,
    "duplicate_chip_id": _duplicate_first("chips"),
    "duplicate_shop_id": _duplicate_first("shop"),
    "duplicate_die_id": _duplicate_first("die"),
    "unknown_top_level_key": lambda d: d.update({"bonus": 1}),
    "unknown_shop_item_key": lambda d: d["shop"][0].update({"discount": 1}),
}


def test_unchanged_v2_data_validates():
    Ruleset.model_validate(_v2_data())


@pytest.mark.parametrize("change", list(REFUSALS.values()), ids=list(REFUSALS))
def test_invalid_ruleset_is_refused(change: Callable[[dict[str, Any]], None]):
    data = _v2_data()
    change(data)
    with pytest.raises(pydantic.ValidationError):
        Ruleset.model_validate(data)


def _set(path: Callable[[dict[str, Any]], dict[str, Any]], key: str, value: Any):
    def change(d: dict[str, Any]) -> None:
        path(d)[key] = value

    return change


def _top(key: str, value: Any) -> Callable[[dict[str, Any]], None]:
    return _set(lambda d: d, key, value)


def _shop(item_id: str, key: str, value: Any) -> Callable[[dict[str, Any]], None]:
    return _set(lambda d: _by_id(d["shop"], item_id), key, value)


def _die(face_id: str, key: str, value: Any) -> Callable[[dict[str, Any]], None]:
    return _set(lambda d: _by_id(d["die"], face_id), key, value)


def _chip(chip_id: str, key: str, value: Any) -> Callable[[dict[str, Any]], None]:
    return _set(lambda d: _by_id(d["chips"], chip_id), key, value)


def _track_end(n: int) -> Callable[[dict[str, Any]], None]:
    def change(d: dict[str, Any]) -> None:
        d["track_end"] = n
        d["money"] = list(range(n + 1))
        d["points"] = [0] * (n + 1)
        d["rubies"] = []

    return change


def _money_at(index: int, value: int) -> Callable[[dict[str, Any]], None]:
    def change(d: dict[str, Any]) -> None:
        d["money"][index] = value

    return change


def _bag(chip_id: str, count: int) -> Callable[[dict[str, Any]], None]:
    def change(d: dict[str, Any]) -> None:
        d["start_bag"][chip_id] = count

    return change


def _append_ruby(value: int) -> Callable[[dict[str, Any]], None]:
    def change(d: dict[str, Any]) -> None:
        d["rubies"].append(value)

    return change


# id -> (change that must be refused, change just inside the range that must validate)
BOUNDARY_CASES: dict[
    str, tuple[Callable[[dict[str, Any]], None], Callable[[dict[str, Any]], None]]
] = {
    "shop_price_minus_1": (_shop("blue_1", "price", -1), _shop("blue_1", "price", 0)),
    "die_weight_0": (_die("point_1", "weight", 0), _die("point_1", "weight", 1)),
    "die_weight_minus_1": (_die("point_1", "weight", -1), _die("point_1", "weight", 1)),
    "rounds_0": (_top("rounds", 0), _top("rounds", 1)),
    "explosion_limit_0": (_top("explosion_limit", 0), _top("explosion_limit", 1)),
    "track_end_0": (_track_end(0), _track_end(1)),
    "start_bag_count_0": (_bag("white_1", 0), _bag("white_1", 1)),
    "chip_value_0": (_chip("white_1", "value", 0), _chip("white_1", "value", 1)),
    "money_entry_minus_1": (_money_at(1, -1), _money_at(1, 0)),
    "die_droplet_halves_0": (_die("droplet_1", "halves", 0), _die("droplet_1", "halves", 1)),
    "die_points_0": (_die("point_1", "points", 0), _die("point_1", "points", 1)),
    "shop_chip_item_chip_missing": (
        _shop("blue_1", "chip", None),
        _shop("blue_1", "chip", "white_1"),
    ),
    "die_chip_face_chip_missing": (
        _die("orange_1", "chip", None),
        _die("orange_1", "chip", "white_1"),
    ),
    "ruby_field_twice": (_append_ruby(5), _append_ruby(6)),
}


@pytest.mark.parametrize("case", list(BOUNDARY_CASES))
def test_out_of_range_value_is_refused(case: str):
    data = _v2_data()
    BOUNDARY_CASES[case][0](data)
    with pytest.raises(pydantic.ValidationError):
        Ruleset.model_validate(data)


@pytest.mark.parametrize("case", list(BOUNDARY_CASES))
def test_boundary_value_validates(case: str):
    data = _v2_data()
    BOUNDARY_CASES[case][1](data)
    Ruleset.model_validate(data)


@pytest.mark.parametrize(
    "field",
    ["points", "spellbook", "point_board", "cards", "explosion_choice", "last_round_money_divisor"],
)
def test_field_without_old_safe_default_is_required(field: str):
    data = _v2_data()
    del data[field]
    with pytest.raises(pydantic.ValidationError, match=field):
        Ruleset.model_validate(data)


def test_v2_values_of_the_required_fields():
    rs = load_ruleset("v2")
    assert rs.explosion_choice is True
    assert rs.last_round_money_divisor == 5
    assert len(rs.points) == rs.track_end + 1
    assert rs.point_board.max_points == 100
    assert len(rs.cards) > 0


def test_v2_meaning_of_a_flag_is_the_only_value():
    data = _v2_data()
    data["explosion_choice"] = False
    with pytest.raises(pydantic.ValidationError):
        Ruleset.model_validate(data)


@pytest.mark.parametrize("kind", ["money", "remove_chip", "droplet", "points"])
def test_kinds_no_v2_entry_uses_are_refused(kind: str):
    shop = _v2_data()
    shop["shop"][0]["kind"] = kind
    with pytest.raises(pydantic.ValidationError):
        Ruleset.model_validate(shop)
    if kind == "money":
        die = _v2_data()
        die["die"][1]["kind"] = kind
        with pytest.raises(pydantic.ValidationError):
            Ruleset.model_validate(die)


def test_chip_component_key_is_refused():
    data = _v2_data()
    data["chips"][0]["component"] = "white@1"
    with pytest.raises(pydantic.ValidationError):
        Ruleset.model_validate(data)
