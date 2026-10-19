from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from quack_rl.bots import HeuristicBot, RandomBot
from quack_rl.rl import EvalResult, Policy, evaluate, make_opponent, random_policy
from quack_rl.rl import evaluate as evaluate_from_pkg
from quack_rl.rl.evaluate import QuackEnv


def test_make_opponent_names():
    assert make_opponent("draw20-pts4-blue").name == "draw20-pts4-blue"
    assert isinstance(make_opponent("draw20-pts4-blue"), HeuristicBot)
    assert make_opponent("bot:draw20-pts4-blue").name == "draw20-pts4-blue"
    assert make_opponent("random").name == "random"
    assert isinstance(make_opponent("random", seed=1), RandomBot)
    assert make_opponent("draw20-pts4-blue", rules="v1").name == "draw20-pts4-blue"


@pytest.mark.parametrize("name", ["draw200-pts4-blue", "foo"])
def test_make_opponent_bad_name(name):
    with pytest.raises(ValueError, match=r"random.*draw<percent>-pts<round>-<strategy>"):
        make_opponent(name)


def test_random_policy_respects_mask_and_seed():
    mask = np.zeros(10, dtype=np.int8)
    mask[[2, 5, 7]] = 1
    obs = np.zeros(3)
    a, b = random_policy(3), random_policy(3)
    acts = [a(obs, mask) for _ in range(200)]
    assert set(acts) <= {2, 5, 7}
    assert len(set(acts)) > 1
    assert acts == [b(obs, mask) for _ in range(200)]
    assert Policy is not None


def test_evaluate_counts_and_frozen():
    res = evaluate(random_policy(0), "random", rules="v1.1", games=10, seed=1)
    assert isinstance(res, EvalResult)
    assert res.games == 10
    assert res.wins + res.draws + res.losses == 10
    assert res.win_rate == res.wins / 10
    assert res.draw_rate == res.draws / 10
    assert res.loss_rate == res.losses / 10
    with pytest.raises(FrozenInstanceError):
        res.wins = 3  # type: ignore[misc]
    assert evaluate_from_pkg is evaluate


@pytest.mark.slow
def test_evaluate_reproducible():
    for opp in ("draw20-pts4-blue", "random"):
        a = evaluate(random_policy(5), opp, rules="v1.1", games=8, seed=2)
        b = evaluate(random_policy(5), opp, rules="v1.1", games=8, seed=2)
        assert a == b


def test_evaluate_games_zero():
    with pytest.raises(ValueError):
        evaluate(random_policy(0), "random", rules="v1.1", games=0)


def test_evaluate_uses_both_seats_and_seeds():
    class Recorder:
        def choose(self, state, seat, legal):
            seats.add(seat)
            return legal[0]

    seats: set[str] = set()
    per_game = []
    orig = QuackEnv.reset

    def spy(self, *, seed=None, options=None):
        per_game.append((self.agent_seat, seed))
        return orig(self, seed=seed, options=options)

    QuackEnv.reset = spy
    try:
        evaluate(random_policy(0), Recorder(), rules="v1.1", games=4, seed=10)
    finally:
        QuackEnv.reset = orig
    assert per_game == [("p1", 10), ("p2", 11), ("p1", 12), ("p2", 13)]
    assert seats == {"p1", "p2"}


def test_evaluate_counts_a_draw_only_as_draw():
    # an agent that always Stops/Waits against an opponent that does the same: scripted draws
    class Passive:
        def choose(self, state, seat, legal):
            return legal[-1]

    def passive(obs, mask):
        return int(np.flatnonzero(mask)[-1])

    res = evaluate(passive, Passive(), rules="v1.1", games=6, seed=0)
    env_results = []
    for i in range(6):
        env = QuackEnv(seat="p1" if i % 2 == 0 else "p2", opponent=Passive(), rules="v1.1")
        obs, info = env.reset(seed=i)
        done = False
        while not done:
            obs, _, done, _, info = env.step(passive(obs, info["action_mask"]))
        env_results.append(info["episode"]["result"])
    assert res.draws == env_results.count("draw")
    assert res.wins == env_results.count("win")
    assert res.losses == env_results.count("loss")
    assert res.wins + res.draws + res.losses == 6


def test_draw_is_not_win_or_loss(monkeypatch):
    def fake_summary(self):
        return {
            "result": "draw",
            "points": {"own": 3, "opponent": 3},
            "explosions": {"own": 1, "opponent": 0},
            "decisions": 0,
            "seat": self.agent_seat,
        }

    monkeypatch.setattr(QuackEnv, "_episode_summary", fake_summary)
    res = evaluate(random_policy(0), "random", rules="v1.1", games=4)
    assert (res.wins, res.draws, res.losses) == (0, 4, 0)
    assert res.draw_rate == 1.0
    assert res.points_own == 3 and res.points_opponent == 3 and res.explosions_own == 1
