"""Moved from tests/test_ruleset.py (#170): boundary cases of v1 shop and die entries.

Ruleset v2 has no `remove_chip`, `droplet` or `points` shop items and no money die face. The
entries below were cases of `BOUNDARY_CASES` / `REFUSALS` (tests/test_ruleset.py before the move);
they ran on `_v1_data()`, the data of v1.toml.
"""

    "shop_droplet_halves_0": (_shop("droplet_1", "halves", 0), _shop("droplet_1", "halves", 1)),
    "shop_points_0": (_shop("points_2", "points", 0), _shop("points_2", "points", 1)),
    "die_money_amount_0": (_die("money_1", "amount", 0), _die("money_1", "amount", 1)),
    "shop_remove_item_chip_missing": (
        _shop("remove_white_1", "chip", None),
        _shop("remove_white_1", "chip", "white_2"),
    ),

# REFUSALS: "shop_remove_item_unknown_chip": _set_shop_chip("remove_white_1"),


# ---- Moved from tests/test_ruleset.py (#170), original text ----

def test_supported_versions_is_v1_only():
    assert SUPPORTED_RULES_VERSIONS == ("v1", "v1.1", "v1.8", "v1.9", "v1.10", "v1.11", "v2")


def test_load_v1_returns_ruleset():
    rs = load_ruleset("v1")
    assert isinstance(rs, Ruleset)
    assert rs.version == "v1"


def test_unchanged_v1_data_validates():
    Ruleset.model_validate(_v1_data())


def test_v1_last_round_money_percent_is_150():
    assert load_ruleset("v1").last_round_money_percent == 150
