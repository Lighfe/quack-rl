"""Moved from tests/test_board.py (#170): a ruleset without a point board."""

import pytest

from quack_rl.engine.board import board_position
from quack_rl.rules import load_ruleset


def test_no_board_raises():
    with pytest.raises(ValueError):
        board_position(3, load_ruleset("v1.11"))
