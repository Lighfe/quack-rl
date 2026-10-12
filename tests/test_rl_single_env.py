import warnings

import numpy as np
import pytest
from gymnasium import spaces
from gymnasium.utils.env_checker import check_env

from quack_rl.bots.heuristic import HeuristicBot
from quack_rl.bots.random_bot import RandomBot
from quack_rl.engine import WAIT, action_names, legal_actions
from quack_rl.engine.state import Phase
from quack_rl.rl import QuackEnv, observation_bounds, observe, reward, vector_names, vectorize
from quack_rl.rules import load_ruleset

VERSIONS = ["v1", "v1.1"]


def play(env, seed=0, action_seed=0):
    """Random legal agent actions; returns the list of (obs, reward, terminated, info)."""
    rng = np.random.default_rng(action_seed)
    obs, info = env.reset(seed=seed)
    out = []
    done = False
    while not done:
        action = int(rng.choice(np.flatnonzero(info["action_mask"])))
        obs, rew, term, trunc, info = env.step(action)
        assert not trunc
        out.append((obs, rew, term, info))
        done = term
    return out


@pytest.mark.parametrize("version", VERSIONS)
def test_check_env(version):
    check_env(QuackEnv(rules=version), skip_render_check=True)


@pytest.mark.parametrize("version", VERSIONS)
def test_check_env_without_warnings_and_bounded_entries(version):
    env = QuackEnv(rules=version)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        # points and bag counts have no real upper bound: that warning stays
        warnings.filterwarnings("ignore", message=".*maximum value is infinity.*")
        check_env(env, skip_render_check=True)
    box = env.observation_space
    names = vector_names(env.rs)
    low, high = observation_bounds(env.rs)
    assert np.array_equal(box.low, low) and np.array_equal(box.high, high)
    assert np.isfinite(box.high[names.index("own.status.exploded")])
    assert np.isfinite(box.high[names.index("explosion_limit")])
    assert np.isinf(box.high[names.index("own.points")])


@pytest.mark.parametrize("seat", ["p1", "p2"])
def test_heuristic_opponent_full_game(seat):
    rs = load_ruleset("v1.1")
    env = QuackEnv(seat=seat, opponent=HeuristicBot(rs), rules=rs)
    steps = play(env, seed=3)
    assert steps[-1][2] is True


@pytest.mark.parametrize("version", VERSIONS)
def test_spaces(version):
    rs = load_ruleset(version)
    env = QuackEnv(rules=version)
    assert isinstance(env.observation_space, spaces.Box)
    assert env.observation_space.dtype == np.float32
    assert env.observation_space.shape == (len(vector_names(rs)),)
    assert env.action_space == spaces.Discrete(len(action_names(rs)))


def test_mask_in_info_and_action_masks():
    env = QuackEnv()
    _, info = env.reset(seed=1)
    assert np.array_equal(info["action_mask"], env.action_masks())
    _, _, _, _, info = env.step(int(np.flatnonzero(info["action_mask"])[0]))
    assert np.array_equal(info["action_mask"], env.action_masks())


@pytest.mark.parametrize("seat", ["p1", "p2", "random"])
@pytest.mark.parametrize("version", VERSIONS)
def test_no_wait_only_mask_and_mask_is_legal(seat, version):
    env = QuackEnv(seat=seat, rules=version)
    wait = action_names(env.rs).index(WAIT)
    for seed in range(5):
        obs, info = env.reset(seed=seed)
        done = False
        rng = np.random.default_rng(seed)
        while not done:
            mask = info["action_mask"]
            legal = set(legal_actions(env.state, env.rs, env.agent_seat))
            names = action_names(env.rs)
            assert {names[i] for i in np.flatnonzero(mask)} == legal
            assert not (mask.sum() == 1 and mask[wait] == 1)
            obs, rew, done, _, info = env.step(int(rng.choice(np.flatnonzero(mask))))
            if done:
                assert not info["action_mask"].any()
                assert not env.action_masks().any()
                assert legal_actions(env.state, env.rs, env.agent_seat) == []
                assert env.state.phase is Phase.GAME_OVER
                assert env.rs.rounds == 9 and env.state.round >= env.rs.rounds
                assert rew == reward(env.state, env.agent_seat)


@pytest.mark.parametrize("seat", ["p1", "p2"])
def test_observation_is_agent_view(seat):
    env = QuackEnv(seat=seat)
    obs, _ = env.reset(seed=2)
    expected = vectorize(observe(env.state, env.rs, seat), env.rs)
    assert np.array_equal(obs, expected)
    obs, *_ = env.step(int(np.flatnonzero(env.action_masks())[0]))
    assert np.array_equal(obs, vectorize(observe(env.state, env.rs, seat), env.rs))


def test_random_seat_varies_per_episode():
    env = QuackEnv(seat="random")
    seats = set()
    for seed in range(20):
        env.reset(seed=seed)
        seats.add(env.agent_seat)
    assert seats == {"p1", "p2"}


def test_same_seed_same_game():
    a = play(QuackEnv(seat="random"), seed=5, action_seed=1)
    b = play(QuackEnv(seat="random"), seed=5, action_seed=1)
    assert len(a) == len(b)
    assert all(np.array_equal(x[0], y[0]) and x[1] == y[1] for x, y in zip(a, b, strict=True))


def test_default_opponent_is_random_bot_and_custom_bot_is_used():
    assert isinstance(QuackEnv().opponent, RandomBot)
    calls = []

    class Spy(RandomBot):
        def choose(self, state, seat, legal):
            calls.append(seat)
            return super().choose(state, seat, legal)

    play(QuackEnv(seat="p1", opponent=Spy(1)), seed=0)
    assert set(calls) == {"p2"}


def test_custom_reward_fn():
    env = QuackEnv(reward_fn=lambda state, seat: 42.0)
    steps = play(env)
    assert steps[-1][1] == 42.0
    assert all(s[1] == 0.0 for s in steps[:-1])


def test_step_after_end_raises():
    env = QuackEnv()
    play(env)
    with pytest.raises(RuntimeError):
        env.step(0)


def test_illegal_action_is_replaced_and_flagged():
    env = QuackEnv()
    _, info = env.reset(seed=0)
    illegal = int(np.flatnonzero(info["action_mask"] == 0)[0])
    _, _, _, _, info = env.step(illegal)
    assert info["illegal_action"] is True


def _explosions(env):
    out = {"p1": 0, "p2": 0}
    for result in env.trace:
        for e in result.events:
            if e["kind"] == "explode":
                out[e["seat"]] += 1
    return out


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("seat", ["p1", "p2"])
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_episode_summary_on_random_games(version, seat, seed):
    env = QuackEnv(seat=seat, rules=version)
    rng = np.random.default_rng(seed)
    obs, info = env.reset(seed=seed)
    assert "episode" not in info
    assert env.trace is env._env.trace
    calls = 0
    while True:
        action = int(rng.choice(np.flatnonzero(info["action_mask"])))
        obs, rew, term, trunc, info = env.step(action)
        calls += 1
        if term:
            break
        assert "episode" not in info
    ep = info["episode"]
    assert set(ep) == {"result", "points", "explosions", "decisions", "seat"}
    assert ep["seat"] == seat
    other = "p2" if seat == "p1" else "p1"
    assert ep["points"] == {
        "own": env.state.players[seat].points,
        "opponent": env.state.players[other].points,
    }
    boom = _explosions(env)
    assert ep["explosions"] == {"own": boom[seat], "opponent": boom[other]}
    assert ep["decisions"] == calls
    assert ep["result"] == ("win" if rew > 0 else "loss" if rew < 0 else "draw")


def test_episode_seat_follows_random_seat():
    env = QuackEnv(seat="random")
    seats = set()
    for seed in range(8):
        _, info = env.reset(seed=seed)
        agent = env.agent_seat
        done = False
        while not done:
            _, _, done, _, info = env.step(int(np.flatnonzero(info["action_mask"])[0]))
        assert info["episode"]["seat"] == agent
        seats.add(agent)
    assert seats == {"p1", "p2"}
