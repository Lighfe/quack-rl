"""v1.10 is the default: policy entry points called without a version refuse and tell the user to
name an older one; environments and baseline bots work on it; an explicit older version works."""

import pytest

from quack_rl.bots import HeuristicBot, RandomBot
from quack_rl.engine import Phase, RngChance
from quack_rl.rl import PolicyBot, QuackEnv, QuackParallelEnv, evaluate, make_opponent, random_policy
from quack_rl.rl.encode import LayoutRefused
from quack_rl.rl.finetune import finetune_online
from quack_rl.rl.offline import train_offline_run
from quack_rl.rl.selfplay import train_selfplay
from quack_rl.rl.train import train
from quack_rl.rules import load_ruleset
from quack_rl.runner import play_game

HINT = "older rules version"


def test_policy_bot_without_rules_is_refused(tmp_path):
    with pytest.raises(LayoutRefused, match=HINT):
        PolicyBot(lambda o, m: 0)
    with pytest.raises(LayoutRefused, match=HINT):
        PolicyBot.from_run(tmp_path)


def test_train_without_rules_is_refused():
    with pytest.raises(LayoutRefused, match=HINT):
        train(10)


def test_finetune_without_rules_is_refused(tmp_path):
    with pytest.raises(LayoutRefused, match=HINT):
        finetune_online(tmp_path / "src", tmp_path / "out", 10, "random")
    assert not (tmp_path / "out").exists()


def test_selfplay_without_rules_is_refused(tmp_path):
    with pytest.raises(LayoutRefused, match=HINT):
        train_selfplay("x", 100, runs_dir=tmp_path)
    assert not list(tmp_path.iterdir())


def test_offline_without_rules_is_refused(tmp_path):
    with pytest.raises(LayoutRefused, match=HINT):
        train_offline_run(tmp_path / "d.parquet", "x", runs_dir=tmp_path, steps=1)
    assert not list(tmp_path.iterdir())


def test_evaluate_a_policy_without_rules_is_refused():
    with pytest.raises(LayoutRefused, match=HINT):
        evaluate(random_policy(0), "random", games=1)


def test_evaluate_a_policy_with_an_older_version_works():
    result = evaluate(random_policy(0), "random", rules="v1.1", games=2)
    assert result.games == 2


def test_environments_without_rules_run_on_v1_10():
    env = QuackEnv()
    assert env.rs.version == "v1.10"
    obs, info = env.reset(seed=0)
    assert obs is not None and info["action_mask"].any()
    assert QuackParallelEnv().rs.version == "v1.10"


def test_baseline_bots_without_rules_play_v1_10():
    rs = load_ruleset("v1.10")
    opp = make_opponent("draw20-pts4-blue")
    assert isinstance(opp, HeuristicBot)
    final = play_game(rs, {"p1": opp, "p2": RandomBot(1)}, RngChance(2))
    assert final.phase is Phase.GAME_OVER
