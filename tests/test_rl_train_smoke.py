import csv
import json

import numpy as np
import pytest

pytest.importorskip("sb3_contrib")

from quack_rl.bots import RandomBot  # noqa: E402
from quack_rl.engine import action_names, legal_actions  # noqa: E402
from quack_rl.rl import QuackEnv  # noqa: E402
from quack_rl.rl.evaluate import evaluate  # noqa: E402
from quack_rl.rl.policy_bot import PolicyBot  # noqa: E402
from quack_rl.rl.train import run_ppo_experiment  # noqa: E402


def test_train_save_load_evaluate(tmp_path):
    from sb3_contrib import MaskablePPO

    progress = []
    result = run_ppo_experiment("bot:random", 2000, 0, 4, tmp_path, on_progress=progress.append)
    for name in ("config.json", "metrics.csv", "result.json", "model.zip"):
        assert (tmp_path / name).is_file(), name
    config = json.loads((tmp_path / "config.json").read_text())
    assert config["steps"] == 2000 and config["versions"]["sb3-contrib"] != "not installed"
    rows = list(csv.reader((tmp_path / "metrics.csv").open()))
    assert rows[0] == ["steps", "mean_reward"] and len(rows) > 1 and len(rows) - 1 == len(progress)
    data = json.loads((tmp_path / "result.json").read_text())
    assert data["against_opponent"]["games"] == 4 and data["against_random"]["games"] == 4
    assert result.against_opponent.games == 4

    bot = PolicyBot(MaskablePPO.load(str(tmp_path / "model.zip")), "v2.3")
    names = action_names(QuackEnv().rs)
    for i in range(4):  # the bot as the agent: no illegal action
        env = QuackEnv(seat="p1" if i % 2 == 0 else "p2", opponent=RandomBot(i))
        env.reset(seed=i)
        done = False
        while not done:
            legal = legal_actions(env.state, env.rs, env.agent_seat)
            choice = bot.choose(env.state, env.agent_seat, legal)
            assert choice in legal
            _, _, done, _, info = env.step(names.index(choice))
            assert not info["illegal_action"]
    # the bot also works as the opponent of an env
    env = QuackEnv(opponent=bot)
    obs, info = env.reset(seed=1)
    done = False
    rng = np.random.default_rng(0)
    while not done:
        _, _, done, _, info = env.step(int(rng.choice(np.flatnonzero(info["action_mask"]))))
    assert evaluate(bot, "bot:random", 4, 3) == evaluate(bot, "bot:random", 4, 3)


def test_check_env_sb3():
    from stable_baselines3.common.env_checker import check_env

    check_env(QuackEnv(), warn=False, skip_render_check=True)


def test_policy_bot_plays_a_seat_of_the_runner():
    from sb3_contrib import MaskablePPO

    from quack_rl.engine import GameState, Phase, RngChance
    from quack_rl.rules import load_ruleset
    from quack_rl.runner import play_game

    rs = load_ruleset("v2.3")
    env = QuackEnv(rules=rs)
    bot = PolicyBot(MaskablePPO("MlpPolicy", env, device="cpu", seed=0), rs)
    final = play_game(rs, {"p1": bot, "p2": RandomBot(1)}, RngChance(2))
    assert isinstance(final, GameState) and final.phase is Phase.GAME_OVER
