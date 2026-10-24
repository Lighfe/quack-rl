import pytest

from quack_rl.bots import RandomBot
from quack_rl.rl import make_opponent
from quack_rl.rl.evaluate import evaluate, wilson_interval


def test_wilson_interval_known_values():
    low, high = wilson_interval(50, 100)
    assert low == pytest.approx(0.4038, abs=1e-3) and high == pytest.approx(0.5962, abs=1e-3)
    assert wilson_interval(0, 10)[0] == 0.0 and wilson_interval(10, 10)[1] == pytest.approx(1.0)
    with pytest.raises(ValueError):
        wilson_interval(0, 0)


def test_evaluate_is_reproducible_and_counts():
    a = evaluate(RandomBot(5), "bot:random", games=6, seed=2)
    b = evaluate(RandomBot(5), "bot:random", games=6, seed=2)
    assert a == b
    assert a.wins + a.draws + a.losses == 6
    assert a.win_rate == (a.wins + a.draws / 2) / 6
    assert a.ci_low <= a.win_rate <= a.ci_high


def test_evaluate_refuses_an_illegal_choice():
    class Bad:
        def choose(self, state, seat, legal):
            return "no-such-action"

    with pytest.raises(ValueError, match="not legal"):
        evaluate(Bad(), "bot:random", games=1)


def test_make_opponent_accepts_bot_random():
    assert make_opponent("bot:random", 1).name == "random"
    assert make_opponent("bot:draw20-pts1-points").name.startswith("draw20")
