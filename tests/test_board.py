import pytest

from quack_rl.engine import board_position, has_50pts, calculate_rat_tails, tails_between
from quack_rl.rules import load_ruleset

RS = load_ruleset("v2.3")


@pytest.mark.parametrize(
    ("a", "b", "bonus_a", "bonus_b"),
    [
        (0, 2, 1, 0),
        (8, 1, 0, 3),
        (15, 16, 0, 0),
        (48, 51, 1, 0),
        (50, 55, 2, 0),
    ],
)
def test_worked_examples(a, b, bonus_a, bonus_b):
    # (a, b) are the totals; the bonus goes to the lower player. 8/1: the 1 player is lower.
    got = calculate_rat_tails({"a": a, "b": b}, RS)
    if a == 8:
        assert got == {"a": 0, "b": 3}
    else:
        assert got == {"a": bonus_a, "b": bonus_b}


@pytest.mark.parametrize("total", [0, 7, 50, 100])
def test_equal_totals_give_zero(total):
    assert calculate_rat_tails({"a": total, "b": total}, RS) == {"a": 0, "b": 0}


def test_three_seats_tie_for_lead():
    assert calculate_rat_tails({"a": 10, "b": 10, "c": 0}, RS) == {"a": 0, "b": 0, "c": 3}


@pytest.mark.parametrize(
    ("total", "field", "flag"),
    [(0, 0, False), (1, 1, False), (50, 50, False), (51, 1, True), (100, 50, True)],
)
def test_position_and_flag(total, field, flag):
    assert board_position(total, RS) == field
    assert has_50pts(total, RS) is flag


@pytest.mark.parametrize("x", [0, 1, 25, 50, 77])
def test_tails_between_same_is_zero(x):
    assert tails_between(x, x, RS) == 0


