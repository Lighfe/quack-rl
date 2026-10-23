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
