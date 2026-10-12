import numpy as np
import pytest
from gymnasium import spaces
from gymnasium.utils.env_checker import check_env

from quack_rl.bots.heuristic import HeuristicBot
from quack_rl.bots.random_bot import RandomBot
from quack_rl.engine import WAIT, action_names, legal_actions
from quack_rl.engine.state import Phase
from quack_rl.rl import QuackEnv, observe, reward, vector_names, vectorize
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
