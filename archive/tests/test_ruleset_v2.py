"""Moved from tests/test_ruleset_v2.py (#170): v2 against the rulesets before it."""

import pytest

from quack_rl.rules import load_ruleset

RS = load_ruleset("v2")
RS111 = load_ruleset("v1.11")


def test_v2_equals_v1_11_elsewhere():
    for name in ("money", "points", "rubies", "shop", "chips", "cards", "rounds"):
        assert getattr(RS, name) == getattr(RS111, name), name


@pytest.mark.parametrize("version", ["v1", "v1.1", "v1.8", "v1.9", "v1.10", "v1.11"])
def test_old_versions_have_no_point_board(version):
    assert load_ruleset(version).point_board is None
