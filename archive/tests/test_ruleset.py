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
