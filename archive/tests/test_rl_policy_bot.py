import json

import numpy as np
import pytest
import typer

from quack_rl.bots import HeuristicBot, RandomBot
from quack_rl.cli.seats import check_seat, parse_seat
from quack_rl.engine import Phase, RngChance, legal_actions, new_game
from quack_rl.rl import PolicyBot, QuackEnv, evaluate, random_policy
from quack_rl.rl.encode import OBSERVATION_LAYOUT, vector_names
from quack_rl.rl.runs import LayoutMismatch
from quack_rl.rules import load_ruleset
from quack_rl.runner import play_game

RS = load_ruleset("v1.1")


def make_bot(seed=1):
    return PolicyBot(random_policy(seed), RS)


def test_attributes():
    bot = make_bot()
    assert bot.kind == "bot" and bot.name and isinstance(bot.params, dict)


@pytest.mark.parametrize("own", ["p1", "p2"])
@pytest.mark.parametrize("other", ["random", "heuristic"])
def test_play_game_ends_without_illegal_action(own, other):
    opp = RandomBot(2) if other == "random" else HeuristicBot(RS, 30, 3, "points", 2)
    seats = {own: make_bot(3), ("p2" if own == "p1" else "p1"): opp}
    final = play_game(RS, seats, RngChance(5))
    assert final.phase is Phase.GAME_OVER


def test_policy_bot_as_opponent_of_env_and_evaluate():
    env = QuackEnv(opponent=make_bot(4), rules="v1.1")
    obs, info = env.reset(seed=0)
    done = False
    while not done:
        obs, _, done, _, info = env.step(int(np.flatnonzero(info["action_mask"])[0]))
    assert info["episode"]["result"] in ("win", "draw", "loss")
    result = evaluate(random_policy(0), make_bot(5), rules="v1.1", games=4, seed=0)
    assert result.wins + result.draws + result.losses == 4


def test_illegal_index_raises_with_the_action_name():
    def bad(obs, mask):
        return int(np.flatnonzero(mask == 0)[0])

    state = new_game(RS)
    legal = legal_actions(state, RS, "p1")
    with pytest.raises(ValueError, match="illegal action"):
        PolicyBot(bad, RS).choose(state, "p1", legal)


def moves(seed):
    log = []
    seats = {"p1": make_bot(seed), "p2": make_bot(seed + 1)}
    for s in seats.values():
        orig = s.choose

        def rec(state, seat, legal, orig=orig):
            a = orig(state, seat, legal)
            log.append((seat, a))
            return a

        s.choose = rec
    final = play_game(RS, seats, RngChance(9))
    return log, {s: final.players[s].points for s in final.players}


def test_same_seed_same_game():
    assert moves(7) == moves(7)


def fake_run(path, **config):
    path.mkdir()
    (path / "config.json").write_text(json.dumps(config))
    return path


def test_from_run_refuses_old_layout(tmp_path):
    run = fake_run(tmp_path / "r", layout=1, vector_names=vector_names(RS))
    with pytest.raises(LayoutMismatch):
        PolicyBot.from_run(run, "v1.1")


def test_from_run_refuses_wrong_vector_names(tmp_path):
    run = fake_run(tmp_path / "r", layout=OBSERVATION_LAYOUT, vector_names=["x"])
    with pytest.raises(LayoutMismatch):
        PolicyBot.from_run(run, "v1.1")


@pytest.mark.slow
def test_from_run_with_a_real_model(tmp_path):
    pytest.importorskip("sb3_contrib")
    from quack_rl.rl.runs import save_run
    from quack_rl.rl.train import train

    result = train(steps=256, rules="v1.1", opponent="random", seed=1, eval_games=4)
    save_run(tmp_path / "run", result, {"steps": 256, "rules": "v1.1", "opponent": "random"})
    bot = PolicyBot.from_run(tmp_path / "run", "v1.1")
    assert play_game(RS, {"p1": bot, "p2": RandomBot(1)}, RngChance(1)).phase is Phase.GAME_OVER


# --- seat spec ---


def test_check_seat_policy_rejects_empty_and_missing(tmp_path):
    for spec in ("policy:", f"policy:{tmp_path / 'missing'}"):
        with pytest.raises(typer.BadParameter):
            check_seat(spec)


def test_policy_spec_builds_a_policy_bot(tmp_path):
    run = fake_run(tmp_path / "r", layout=OBSERVATION_LAYOUT, vector_names=vector_names(RS))
    check_seat(f"policy:{run}")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("quack_rl.rl.runs.load_model", lambda p, r: object())
        mp.setattr("quack_rl.rl.policy_bot.load_model", lambda p, r: object())
        seat = parse_seat(f"policy:{run}", 1, rs=RS)
    assert isinstance(seat, PolicyBot)


def test_old_seat_specs_still_pass():
    check_seat("bot:random")
    check_seat("bot:draw30-pts3-points")
    with pytest.raises(typer.BadParameter):
        check_seat("nonsense")


# --- read-out: greedy and sampled ---


def stub_bot(readout, seed=0, rs=RS):
    """A bot with a non-degenerate distribution: greedy takes the first legal action, sampled
    draws uniformly over the legal ones."""

    def greedy(obs, mask):
        return int(np.flatnonzero(mask)[0])

    def dist(obs, mask):
        return np.ones(len(mask))  # mass on illegal actions too: the bot must mask it

    return PolicyBot(greedy, rs, readout=readout, seed=seed, distribution=dist)


def branching_states(n=30):
    """(state, seat, legal) of a random game, where the seat has more than one legal action."""
    found = []

    class Recorder(RandomBot):
        def choose(self, state, seat, legal):
            if len(legal) > 1:
                found.append((state, seat, legal))
            return super().choose(state, seat, legal)

    play_game(RS, {"p1": Recorder(1), "p2": Recorder(2)}, RngChance(3))
    assert len(found) >= n
    return found[:n]


def play_moves(bot):
    return [bot.choose(state, seat, legal) for state, seat, legal in branching_states()]


def test_default_readout_is_greedy():
    assert PolicyBot(random_policy(1), RS).params["readout"] == "greedy"
    assert "greedy" in PolicyBot.__doc__


def test_sampled_same_seed_same_moves_other_seed_differs():
    assert play_moves(stub_bot("sampled", 3)) == play_moves(stub_bot("sampled", 3))
    assert play_moves(stub_bot("sampled", 3)) != play_moves(stub_bot("sampled", 4))


def test_greedy_and_sampled_differ_on_a_fixed_state():
    state, seat, legal = branching_states()[0]
    greedy = stub_bot("greedy").choose(state, seat, legal)
    sampled = {stub_bot("sampled", s).choose(state, seat, legal) for s in range(20)}
    assert sampled - {greedy}


def test_sampled_never_returns_an_illegal_action():
    bot = stub_bot("sampled", 1)
    for _ in range(5):
        for state, seat, legal in branching_states():
            assert bot.choose(state, seat, legal) in legal


def test_sampled_needs_a_distribution_and_unknown_readout_is_refused():
    with pytest.raises(ValueError, match="distribution"):
        PolicyBot(random_policy(1), RS, readout="sampled")
    with pytest.raises(ValueError, match="greedy, sampled"):
        PolicyBot(random_policy(1), RS, readout="random")


def test_check_seat_readout_suffix(tmp_path):
    run = fake_run(tmp_path / "r", layout=OBSERVATION_LAYOUT, vector_names=vector_names(RS))
    check_seat(f"policy:{run}")
    check_seat(f"policy:{run}#greedy")
    check_seat(f"policy:{run}#sampled")
    with pytest.raises(typer.BadParameter, match="greedy.*sampled"):
        check_seat(f"policy:{run}#random")
    odd = fake_run(tmp_path / "a#b", layout=OBSERVATION_LAYOUT, vector_names=vector_names(RS))
    check_seat(f"policy:{odd}")  # a '#' in a folder name is not a suffix
