"""Bots on ruleset v2.3: the ruby step after the shop."""

import pytest

from quack_rl.bots import HeuristicBot, RandomBot
from quack_rl.bots.heuristic import REFILL_RESERVE
from quack_rl.engine import (
    DONE,
    REFILL_FLASK,
    RUBY_DROP,
    SEATS,
    Phase,
    RngChance,
    legal_actions,
    needs_actions,
    new_game,
    step,
)
from quack_rl.rules import load_ruleset

RS = load_ruleset("v2.3")


def phase_state(rs, phase, rubies, flask_full):
    state = new_game(rs)
    state.phase = phase
    p = state.players["p1"]
    p.rubies, p.flask_full, p.money = rubies, flask_full, 0
    return state


@pytest.mark.parametrize("rubies", range(0, 7))
@pytest.mark.parametrize("flask_full", [True, False])
def test_heuristic_ruby_step_rule(rubies, flask_full):
    bot = HeuristicBot(RS, 20, 1, "points", seed=0)
    ruby = phase_state(RS, Phase.RUBY, rubies, flask_full)
    got = bot.choose(ruby, "p1", legal_actions(ruby, RS, "p1"))
    if not flask_full and rubies >= RS.ruby_cost and rubies - RS.ruby_cost >= REFILL_RESERVE:
        assert got == REFILL_FLASK
    elif rubies >= RS.ruby_cost:
        assert got == RUBY_DROP
    else:
        assert got == DONE


def test_heuristic_v2_3_shop_buys_chips_without_ruby_spends():
    bot = HeuristicBot(RS, 20, 1, "points", seed=0)
    state = phase_state(RS, Phase.SHOP, 6, False)
    state.players["p1"].money = 20
    legal = legal_actions(state, RS, "p1")
    assert bot.choose(state, "p1", legal).startswith("buy:")


def _play(bots, seed):
    state = new_game(RS)
    chance = RngChance(seed)
    phases = set()
    while state.phase is not Phase.GAME_OVER:
        actions = None
        if needs_actions(state):
            phases.add(state.phase)
            actions = {}
            for seat in SEATS:
                legal = legal_actions(state, RS, seat)
                action = bots[seat].choose(state, seat, legal)
                assert action in legal, (state.phase, action, legal)
                actions[seat] = action
        state = step(state, RS, actions, chance).state
    return phases


def test_heuristic_and_random_play_full_v2_3_games():
    phases = set()
    for seed in range(4):
        bots = {
            "p1": HeuristicBot(RS, 20, 1, "points", seed=seed),
            "p2": RandomBot(seed=seed) if seed % 2 else HeuristicBot(RS, 30, 2, "green", seed=seed),
        }
        phases |= _play(bots, seed)
    assert Phase.RUBY in phases
