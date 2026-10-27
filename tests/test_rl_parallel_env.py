import random

import numpy as np
import pytest
from pettingzoo.test import parallel_api_test

from quack_rl.engine import (
    RngChance,
    ScriptedChance,
    action_names,
    legal_actions,
    needs_actions,
    new_game,
    state_to_dict,
    step,
)
from quack_rl.engine.state import Phase
from quack_rl.rl import QuackParallelEnv, reward
from quack_rl.rules import load_ruleset

VERSIONS = ["v2.1", "v2.2"]
SEATS = ("p1", "p2")


def play_env(env, seed, action_seed=0):
    """Random legal joint actions through the env; returns the trace and the last result."""
    rng = random.Random(action_seed)
    obs, _ = env.reset(seed=seed)
    trace = []
    while env.agents:
        acts = {a: rng.choice(np.flatnonzero(obs[a]["action_mask"]).tolist()) for a in env.agents}
        obs, rew, term, _, _ = env.step(acts)
        trace.append((obs, rew, term, state_to_dict(env.state)))
    return trace


@pytest.mark.parametrize("version", VERSIONS)
def test_parallel_api(version):
    parallel_api_test(QuackParallelEnv(rules=version), num_cycles=1000)


def test_accepts_ruleset_object():
    rs = load_ruleset("v2.1")
    env = QuackParallelEnv(rules=rs)
    obs, _ = env.reset(seed=1)
    assert set(obs) == set(SEATS)
    assert set(obs["p1"]) == {"observation", "action_mask"}


@pytest.mark.parametrize("version", VERSIONS)
def test_waiting_seat_has_only_wait(version):
    env = QuackParallelEnv(rules=version)
    names = action_names(env.rs)
    rng = random.Random(3)
    obs, _ = env.reset(seed=3)
    saw_wait_only = False
    while env.agents:
        for a in env.agents:
            legal = legal_actions(env.state, env.rs, a)
            got = [n for n, m in zip(names, obs[a]["action_mask"], strict=True) if m]
            assert got == [n for n in names if n in legal]
            if legal == ["wait"]:
                saw_wait_only = True
        obs, *_ = env.step(
            {a: rng.choice(np.flatnonzero(obs[a]["action_mask"]).tolist()) for a in env.agents}
        )
    assert saw_wait_only


@pytest.mark.parametrize("version", VERSIONS)
def test_steps_land_on_decision_points_and_end_after_round_9(version):
    env = QuackParallelEnv(rules=version)
    rng = random.Random(0)
    obs, _ = env.reset(seed=0)
    assert needs_actions(env.state)
    while True:
        obs, rew, term, trunc, _ = env.step(
            {a: rng.choice(np.flatnonzero(obs[a]["action_mask"]).tolist()) for a in env.agents}
        )
        if not env.agents:
            break
        assert needs_actions(env.state)
        assert set(rew.values()) == {0.0}
        assert not any(term.values())
    assert env.state.phase is Phase.GAME_OVER
    assert term == {"p1": True, "p2": True}
    assert set(obs) == set(SEATS)
    for seat in SEATS:
        assert rew[seat] == reward(env.state, seat)
        assert not obs[seat]["action_mask"].any()  # game over: all zero


def test_custom_reward_fn():
    env = QuackParallelEnv(rules="v2.1", reward_fn=lambda state, seat: 7.0)
    trace = play_env(env, 0)
    assert trace[-1][1] == {"p1": 7.0, "p2": 7.0}


@pytest.mark.parametrize("version", VERSIONS)
def test_same_seed_same_game_different_seed_differs(version):
    env = QuackParallelEnv(rules=version)
    a = play_env(env, 5)
    b = play_env(env, 5)
    assert len(a) == len(b)
    for (o1, r1, t1, s1), (o2, r2, t2, s2) in zip(a, b, strict=True):
        assert r1 == r2 and t1 == t2 and s1 == s2
        for seat in SEATS:
            assert np.array_equal(o1[seat]["observation"], o2[seat]["observation"])
            assert np.array_equal(o1[seat]["action_mask"], o2[seat]["action_mask"])

    # same actions (always draw, else wait/done), different seed
    def fixed(seed):
        obs, _ = env.reset(seed=seed)
        first = (obs,)
        while env.agents:
            obs = first[0]
            acts = {a: int(np.flatnonzero(obs[a]["action_mask"])[0]) for a in env.agents}
            first = env.step(acts)
        return first[0], state_to_dict(env.state)

    differs = False
    for seed in range(1, 6):
        o0, s0 = fixed(0)
        o1, s1 = fixed(seed)
        if s0 != s1 or any(
            not np.array_equal(o0[s]["observation"], o1[s]["observation"]) for s in SEATS
        ):
            differs = True
    assert differs


def test_step_after_end_raises_runtime_error():
    env = QuackParallelEnv(rules="v2.1")
    play_env(env, 0)
    with pytest.raises(RuntimeError, match="reset"):
        env.step({s: 0 for s in SEATS})
    obs, _ = env.reset(seed=0)
    # works again after reset (the first legal action: the first card may open a choice)
    env.step({s: int(np.flatnonzero(obs[s]["action_mask"])[0]) for s in SEATS})


def test_step_before_reset_raises_runtime_error():
    with pytest.raises(RuntimeError, match="reset"):
        QuackParallelEnv(rules="v2.1").step({s: 0 for s in SEATS})


@pytest.mark.parametrize("version", VERSIONS)
def test_env_matches_engine_with_same_actions_and_chance(version):
    rs = load_ruleset(version)
    seed = 11
    env = QuackParallelEnv(rules=rs)
    rng = random.Random(4)
    obs, _ = env.reset(seed=seed)
    state, chance = new_game(rs), RngChance(seed)
    while not needs_actions(state):
        state = step(state, rs, None, chance).state
    names = action_names(rs)
    while env.agents:
        idx = {a: rng.choice(np.flatnonzero(obs[a]["action_mask"]).tolist()) for a in env.agents}
        obs, *_ = env.step(idx)
        state = step(state, rs, {a: names[i] for a, i in idx.items()}, chance).state
        while state.phase is not Phase.GAME_OVER and not needs_actions(state):
            state = step(state, rs, None, chance).state
    assert state_to_dict(env.state) == state_to_dict(state)
    assert state.phase is Phase.GAME_OVER


@pytest.mark.parametrize("version", VERSIONS)
def test_scripted_actions_and_scripted_chance_match_engine(version):
    rs = load_ruleset(version)
    rng = random.Random(8)
    names = action_names(rs)
    # engine game with recorded joint actions and chance outcomes
    state, chance = new_game(rs), RngChance(8)
    joint_actions, outcomes = [], []
    while state.phase is not Phase.GAME_OVER:
        acts = None
        if needs_actions(state):
            acts = {s: rng.choice(legal_actions(state, rs, s)) for s in SEATS}
            joint_actions.append(acts)
        result = step(state, rs, acts, chance)
        outcomes += [c["value"] for c in result.chance]
        state = result.state
    # the env replays the same actions and the same outcomes
    env = QuackParallelEnv(rules=rs, chance=ScriptedChance(outcomes))
    env.reset()
    for acts in joint_actions:
        assert env.agents
        env.step({s: names.index(a) for s, a in acts.items()})
    assert not env.agents
    assert state_to_dict(env.state) == state_to_dict(state)


@pytest.mark.parametrize("version", VERSIONS)
def test_trace_events_equal_direct_engine_events(version):
    rs = load_ruleset(version)
    seed = 21
    rng = random.Random(5)
    env = QuackParallelEnv(rules=rs)
    obs, _ = env.reset(seed=seed)
    state, chance = new_game(rs), RngChance(seed)
    direct = []
    while not needs_actions(state):
        result = step(state, rs, None, chance)
        direct += result.events
        state = result.state
    names = action_names(rs)
    while env.agents:
        idx = {a: rng.choice(np.flatnonzero(obs[a]["action_mask"]).tolist()) for a in env.agents}
        obs, *_ = env.step(idx)
        result = step(state, rs, {a: names[i] for a, i in idx.items()}, chance)
        direct += result.events
        state = result.state
        while state.phase is not Phase.GAME_OVER and not needs_actions(state):
            result = step(state, rs, None, chance)
            direct += result.events
            state = result.state
    assert [e for r in env.trace for e in r.events] == direct
    assert len(env.trace) > 1


def test_trace_is_cleared_on_reset_and_readable_after_the_end():
    env = QuackParallelEnv(rules="v2.1")
    play_env(env, seed=2)
    assert not env.agents
    ended = len(env.trace)
    assert ended > 0 and env.trace[-1].state is env.state
    env.reset(seed=3)
    assert len(env.trace) < ended  # only the steps folded inside reset
    assert all(r.state.phase is not Phase.GAME_OVER for r in env.trace)
