"""v1.11 is the default: policy entry points called without a version refuse and tell the user to
name an older one; environments and baseline bots work on it; an explicit older version works."""


from quack_rl.bots import HeuristicBot, RandomBot
from quack_rl.engine import Phase, RngChance
from quack_rl.rl import QuackEnv, QuackParallelEnv, make_opponent
from quack_rl.rules import load_ruleset
from quack_rl.runner import play_game

HINT = "older rules version"


def test_environments_without_rules_run_on_v1_11():
    env = QuackEnv()
    assert env.rs.version == "v1.11"
    obs, info = env.reset(seed=0)
    assert obs is not None and info["action_mask"].any()
    assert QuackParallelEnv().rs.version == "v1.11"


def test_baseline_bots_without_rules_play_v1_11():
    rs = load_ruleset("v1.11")
    opp = make_opponent("draw20-pts4-blue")
    assert isinstance(opp, HeuristicBot)
    final = play_game(rs, {"p1": opp, "p2": RandomBot(1)}, RngChance(2))
    assert final.phase is Phase.GAME_OVER
