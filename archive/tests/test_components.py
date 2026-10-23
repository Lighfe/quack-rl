"""Moved from tests/test_components.py (#170): the blue@1 place bonus.

Ruleset v2 uses spellbook 1, where blue is `blue@2` (a hand drawn and picked, no place bonus).
"""

import pytest

from quack_rl.components import get_component
from quack_rl.rules import load_ruleset

rs = load_ruleset("v1")


def comp(chip_id):
    return get_component(rs.chip(chip_id).component)


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
