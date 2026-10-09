import pytest

from quack_rl.components import Component, UnknownComponent, get_component, register
from quack_rl.components import registry as _registry
from quack_rl.rules import load_ruleset

rs = load_ruleset("v1")


def comp(chip_id):
    return get_component(rs.chip(chip_id).component)


def test_every_ruleset_component_is_registered():
    for chip in rs.chips:
        assert isinstance(get_component(chip.component), Component)


def test_unknown_component():
    assert issubclass(UnknownComponent, KeyError)
    with pytest.raises(UnknownComponent):
        get_component("purple@1")


def test_duplicate_registration_raises():
    @register
    class _First(Component):
        name = "test_duplicate@1"

    try:
        with pytest.raises(ValueError):

            @register
            class _Second(Component):
                name = "test_duplicate@1"

        assert isinstance(get_component("test_duplicate@1"), _First)
    finally:
        _registry._REGISTRY.pop("test_duplicate@1", None)


@pytest.mark.parametrize(
    ("chip_id", "weight"),
    [
        ("white_1", 1),
        ("white_2", 2),
        ("white_3", 3),
        ("orange_1", 0),
        ("blue_2", 0),
        ("green_2", 0),
    ],
)
def test_explosion_weight(chip_id, weight):
    assert comp(chip_id).explosion_weight(rs.chip(chip_id)) == weight


# rules 1 "Chips": blue +1 if the previously placed chip has a value other than 1
@pytest.mark.parametrize(
    ("previous", "bonus"),
    [
        (None, 0),
        ("white_1", 0),
        ("orange_1", 0),
        ("blue_1", 0),
        ("white_2", 1),
        ("green_4", 1),
    ],
)
def test_blue_bonus(previous, bonus):
    prev = rs.chip(previous) if previous else None
    assert comp("blue_2").place_bonus(rs.chip("blue_2"), prev) == bonus


@pytest.mark.parametrize("chip_id", ["white_2", "orange_1", "green_2"])
def test_only_blue_has_a_place_bonus(chip_id):
    assert comp(chip_id).place_bonus(rs.chip(chip_id), rs.chip("white_2")) == 0


# rules 4.3: each green chip among the last two placed chips: droplet +0.5 (one half step)
@pytest.mark.parametrize(("position_from_end", "halves"), [(0, 1), (1, 1), (2, 0)])
def test_green_round_end_bonus(position_from_end, halves):
    assert comp("green_1").round_end_droplet_halves(rs.chip("green_1"), position_from_end) == halves


@pytest.mark.parametrize("chip_id", ["blue_1", "white_1"])
def test_non_green_has_no_round_end_bonus(chip_id):
    assert comp(chip_id).round_end_droplet_halves(rs.chip(chip_id), 0) == 0


@pytest.mark.parametrize(
    ("chip_id", "value", "weight"),
    [("white_2", 2.0, 2.0), ("orange_1", 1.0, 0.0)],
)
def test_features_describe_the_chip(chip_id, value, weight):
    features = comp(chip_id).features(rs.chip(chip_id))
    assert features["value"] == value
    assert features["explosion_weight"] == weight
