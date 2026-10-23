"""RL environments, evaluation, self-play and datasets on rules v1.8 (CHOICE phase, layout 3)."""

import random

import numpy as np

import pytest

from gymnasium.utils.env_checker import check_env

from pettingzoo.test import parallel_api_test

from quack_rl.bots import RandomBot

from quack_rl.engine import TAKE_MONEY, TAKE_POINTS, action_names, legal_actions

from quack_rl.engine.state import Phase

from quack_rl.rl import QuackEnv, QuackParallelEnv, evaluate, random_policy, reward

from quack_rl.rl.dataset import iter_games

from quack_rl.rl.opponents import make_opponent

from quack_rl.rl.selfplay import PoolOpponent, _selfplay_env

OPPONENTS = ["random", "draw20-pts4-blue"]

SEATS = ("p1", "p2")

def _to_agent_choice(seed):
    """A QuackEnv (random opponent) stopped at the first CHOICE decision of the agent."""
    env = QuackEnv(rules="v1.8")
    rng = np.random.default_rng(seed)
    _, info = env.reset(seed=seed)
    log = []
    while env.state.phase is not Phase.CHOICE:
        a = int(rng.choice(np.flatnonzero(info["action_mask"])))
        log.append(a)
        _, _, done, _, info = env.step(a)
        if done:
            return None, log
    return env, log

class Spy:
    """Wraps a bot and records the legal list of each choice it is asked."""

    def __init__(self, bot):
        self.bot, self.choices = bot, []

    def choose(self, state, seat, legal):
        action = self.bot.choose(state, seat, legal)
        if TAKE_MONEY in legal:
            self.choices.append((state.round, action, state.phase))
        return action

    def __getattr__(self, item):
        return getattr(self.bot, item)


@pytest.mark.parametrize("name", OPPONENTS)
def test_evaluate_counts_add_up(name):
    res = evaluate(random_policy(0), name, rules="v1.8", games=6, seed=1)
    assert res.wins + res.losses + res.draws == res.games == 6


@pytest.mark.slow
def test_selfplay_run_folder_v1_8(tmp_path):
    import csv
    import json

    pytest.importorskip("sb3_contrib", reason="needs the train group: uv sync --group train")
    from quack_rl.rl.selfplay import SELFPLAY_COLUMNS, train_selfplay

    train_selfplay("sp8", 100, update_every=128, rules="v1.8", seed=1, eval_games=2,
                   runs_dir=tmp_path)
    run = tmp_path / "sp8"
    with (run / "selfplay.csv").open(newline="") as f:
        rows = list(csv.DictReader(f))
    assert tuple(rows[0]) == SELFPLAY_COLUMNS and rows
    assert json.loads((run / "config.json").read_text())["rules"] == "v1.8"
    assert (run / "model.zip").exists()



def test_selfplay_env_and_pool_opponent_games_end():
    env = _selfplay_env(PoolOpponent(lambda p: None, rules="v1.8"), "v1.8")
    rng = np.random.default_rng(0)
    for seed in range(3):
        _, info = env.reset(seed=seed)
        done = False
        while not done:
            _, _, done, _, info = env.step(int(rng.choice(np.flatnonzero(info["action_mask"]))))
        assert info["episode"]["result"] in ("win", "loss", "draw")


def test_make_opponent_and_iter_games_play_full_v1_8_games():
    for name in OPPONENTS:
        assert make_opponent(name, 1, "v1.8") is not None
    games = list(iter_games(OPPONENTS, 4, seed=3, rules="v1.8"))
    assert len(games) == 4 and all(len(g["episode"]) > 0 for g in games)


# ---- Moved from tests/test_rl_v1_8.py (#170), original text ----

"""RL environments, evaluation, self-play and datasets on rules v1.8 (CHOICE phase, layout 3)."""

import random

import numpy as np
import pytest
from gymnasium.utils.env_checker import check_env
from pettingzoo.test import parallel_api_test

from quack_rl.bots import RandomBot
from quack_rl.engine import TAKE_MONEY, TAKE_POINTS, action_names, legal_actions
from quack_rl.engine.state import Phase
from quack_rl.rl import QuackEnv, QuackParallelEnv, reward
from quack_rl.rl.opponents import make_opponent

OPPONENTS = ["random", "draw20-pts4-blue"]
SEATS = ("p1", "p2")


def test_check_env():
    check_env(QuackEnv(rules="v1.8"), skip_render_check=True)


@pytest.mark.parametrize("name", OPPONENTS)
@pytest.mark.parametrize("seat", SEATS)
def test_random_policy_games_follow_the_mask_and_reach_choice(name, seat):
    reached = 0
    for seed in range(25):
        env = QuackEnv(seat=seat, opponent=make_opponent(name, seed, "v1.8"), rules="v1.8")
        names = action_names(env.rs)
        rng = np.random.default_rng(seed)
        _, info = env.reset(seed=seed)
        done = False
        while not done:
            mask = info["action_mask"]
            legal = set(legal_actions(env.state, env.rs, env.agent_seat))
            assert {names[i] for i in np.flatnonzero(mask)} == legal
            if env.state.phase is Phase.CHOICE:
                reached += 1
            _, _, done, _, info = env.step(int(rng.choice(np.flatnonzero(mask))))
            assert not info["illegal_action"]
        assert env.state.phase is Phase.GAME_OVER
    assert reached > 0


def test_parallel_api():
    parallel_api_test(QuackParallelEnv(rules="v1.8"), num_cycles=1000)


def test_parallel_full_game_with_random_legal_actions():
    env = QuackParallelEnv(rules="v1.8")
    rng = random.Random(2)
    obs, _ = env.reset(seed=2)
    choice = False
    while env.agents:
        choice |= env.state.phase is Phase.CHOICE
        acts = {a: rng.choice(np.flatnonzero(obs[a]["action_mask"]).tolist()) for a in env.agents}
        obs, rew, term, _, _ = env.step(acts)
    assert env.state.phase is Phase.GAME_OVER and term == {"p1": True, "p2": True}
    assert {s: rew[s] for s in SEATS} == {s: reward(env.state, s) for s in SEATS}


def _to_agent_choice(seed):
    """A QuackEnv (random opponent) stopped at the first CHOICE decision of the agent."""
    env = QuackEnv(rules="v1.8")
    rng = np.random.default_rng(seed)
    _, info = env.reset(seed=seed)
    log = []
    while env.state.phase is not Phase.CHOICE:
        a = int(rng.choice(np.flatnonzero(info["action_mask"])))
        log.append(a)
        _, _, done, _, info = env.step(a)
        if done:
            return None, log
    return env, log


def test_choice_for_the_agent_both_actions():
    names = action_names(QuackEnv(rules="v1.8").rs)
    for seed in range(200):
        env, log = _to_agent_choice(seed)
        if env is None:
            continue
        mask = env.action_masks()
        if {names[i] for i in np.flatnonzero(mask)} == {TAKE_MONEY, TAKE_POINTS}:
            break
    else:
        pytest.fail("no seed gave the agent a CHOICE decision")
    assert np.flatnonzero(mask).size == 2
    outcome = {}
    for action in (TAKE_MONEY, TAKE_POINTS):
        e = QuackEnv(rules="v1.8")
        _, info = e.reset(seed=seed)
        for a in log:
            _, _, _, _, info = e.step(a)
        before = e.state.players[e.agent_seat]
        money0, points0 = before.money, before.points
        e.step(names.index(action))
        after = e.state.players[e.agent_seat]
        outcome[action] = (after.money - money0, after.points - points0)
    assert outcome[TAKE_MONEY] != outcome[TAKE_POINTS]
    assert outcome[TAKE_MONEY][0] > 0 and outcome[TAKE_MONEY][1] == 0
    assert outcome[TAKE_POINTS][0] <= 0 and outcome[TAKE_POINTS][1] > 0


class Spy:
    """Wraps a bot and records the legal list of each choice it is asked."""

    def __init__(self, bot):
        self.bot, self.choices = bot, []

    def choose(self, state, seat, legal):
        action = self.bot.choose(state, seat, legal)
        if TAKE_MONEY in legal:
            self.choices.append((state.round, action, state.phase))
        return action

    def __getattr__(self, item):
        return getattr(self.bot, item)


@pytest.mark.parametrize("name", OPPONENTS)
def test_opponent_choice_is_made_by_the_bot_not_asked_of_the_agent(name):
    names = None
    asked = 0
    for seed in range(15):
        bot = Spy(make_opponent(name, seed, "v1.8"))
        env = QuackEnv(opponent=bot, rules="v1.8")
        names = action_names(env.rs)
        rng = np.random.default_rng(seed)
        _, info = env.reset(seed=seed)
        done = False
        while not done:
            seats_exploded = env.state.players[env.agent_seat].status.name == "EXPLODED"
            if env.state.phase is Phase.CHOICE:
                assert seats_exploded  # the agent is only asked when it exploded itself
            _, _, done, _, info = env.step(int(rng.choice(np.flatnonzero(info["action_mask"]))))
        asked += len(bot.choices)
        assert all(action in (TAKE_MONEY, TAKE_POINTS) for _, action, _ in bot.choices)
    assert asked > 0


def test_reward_win_loss_at_the_end_only():
    env = QuackEnv(opponent=RandomBot(0), rules="v1.8")
    rng = np.random.default_rng(4)
    _, info = env.reset(seed=4)
    done = False
    rewards = []
    while not done:
        _, rew, done, _, info = env.step(int(rng.choice(np.flatnonzero(info["action_mask"]))))
        rewards.append(rew)
    assert all(r == 0.0 for r in rewards[:-1])
    own = env.state.players[env.agent_seat].points
    opp = env.state.players["p2" if env.agent_seat == "p1" else "p1"].points
    assert rewards[-1] == (1.0 if own > opp else -1.0 if own < opp else 0.0)
    assert rewards[-1] == reward(env.state, env.agent_seat)
