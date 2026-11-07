"""Tests for the point-margin reward (`quack_rl.rl.reward`)."""

from types import SimpleNamespace

from quack_rl.rl.reward import MARGIN_SCALE, REWARDS, margin_reward, reward


def state(p1: int, p2: int) -> SimpleNamespace:
    """A stand-in final state: only `players[seat].points` is read."""
    return SimpleNamespace(
        players={"p1": SimpleNamespace(points=p1), "p2": SimpleNamespace(points=p2)}
    )


def test_equal_points_give_zero():
    assert margin_reward(state(40, 40), "p1") == 0.0
    assert margin_reward(state(40, 40), "p2") == 0.0


def test_ahead_is_positive_and_behind_is_negative():
    assert margin_reward(state(50, 40), "p1") > 0
    assert margin_reward(state(50, 40), "p2") < 0
    assert margin_reward(state(50, 40), "p1") == -margin_reward(state(50, 40), "p2")


def test_margin_is_scaled():
    assert margin_reward(state(45, 40), "p1") == min(1.0, 5 / MARGIN_SCALE)


def test_huge_margins_are_clipped():
    assert margin_reward(state(1000, 0), "p1") == 1.0
    assert margin_reward(state(0, 1000), "p1") == -1.0
    for p1, p2 in ((1000, 0), (0, 1000)):
        assert -1.0 <= margin_reward(state(p1, p2), "p1") <= 1.0


def test_rewards_table():
    assert REWARDS == {"win_loss": reward, "margin": margin_reward}
