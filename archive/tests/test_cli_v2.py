"""Moved from tests/test_cli_v2.py (#170): the board of a ruleset without a point board."""

from quack_rl.engine import new_game
from quack_rl.rules import load_ruleset

RS11 = load_ruleset("v1.11")
# board: as in tests/test_cli_v2.py


def test_board_without_bonus_renders_as_before_v1_11():
    s11 = new_game(RS11)
    assert "rat tail" not in board(s11, RS11)
    assert "start 0" in board(s11, RS11)

