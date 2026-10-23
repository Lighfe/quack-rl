import copy
import random

import numpy as np
import pytest

from quack_rl.bots.heuristic import explosion_chance
from quack_rl.engine import (
    TAKE_MONEY,
    RngChance,
    Status,
    legal_actions,
    needs_actions,
    new_game,
    step,
)
from quack_rl.engine.state import Phase, scoring_field
from quack_rl.rl import observation_bounds, observe, vector_names, vectorize
from quack_rl.rl.derive import derived, derived_names
from quack_rl.rules import load_ruleset

VERSIONS = ["v2"]


def _states(rs, seed):
    rng = random.Random(seed)
    chance = RngChance(seed)
    state = new_game(rs)
    yield state
    while state.phase is not Phase.GAME_OVER:
        actions = (
            {s: rng.choice(legal_actions(state, rs, s)) for s in ("p1", "p2")}
            if needs_actions(state)
            else None
        )
        state = step(state, rs, actions, chance).state
        yield state


def _state(rs, f1, f2, s1=Status.BREWING, s2=Status.BREWING):
    state = new_game(rs)
    state.players["p1"].field = f1
    state.players["p2"].field = f2
    state.players["p1"].status = s1
    state.players["p2"].status = s2
    return state


def test_money_if_stop_normal_exploded_and_last_round():
    rs = load_ruleset("v2")
    state = _state(rs, 9, 9)
    f = scoring_field(9, rs)
    assert derived(state, rs, "p1")["own.money_if_stop"] == rs.money[f]
    assert derived(state, rs, "p1")["opponent.money_if_stop"] == rs.money[f]

    state = _state(rs, 9, 9, s1=Status.EXPLODED)
    d = derived(state, rs, "p1")
    # v2 has the explosion choice: an exploded seat takes the full table money, not half of it
    assert d["own.money_if_stop"] == rs.money[f]
    assert d["opponent.money_if_stop"] == rs.money[f]

    state = _state(rs, 9, 9, s1=Status.EXPLODED)
    state.round = rs.rounds
    d = derived(state, rs, "p1")
    # the last-round money becomes points at once: no money is left to take
    assert rs.last_round_money_divisor is not None
    assert d["own.money_if_stop"] == 0
    assert d["opponent.money_if_stop"] == 0


def test_money_if_stop_equals_engine_money_without_die():
    """The explosion choice gives the table money to an exploded seat that takes money."""
    rs = load_ruleset("v2")
    state = _state(rs, 20, 20, s1=Status.EXPLODED, s2=Status.EXPLODED)
    for p in state.players.values():
        p.final_field = p.field
    d = derived(state, rs, "p1")
    state.phase = Phase.CHOICE
    result = step(state, rs, {"p1": TAKE_MONEY, "p2": TAKE_MONEY}, RngChance(0))
    amounts = {e["seat"]: e["amount"] for e in result.events if e["kind"] == "take_money"}
    assert amounts["p1"] == d["own.money_if_stop"]
    assert amounts["p2"] == d["opponent.money_if_stop"]


def test_rolls_die_lead_tie_lag_and_exploded():
    rs = load_ruleset("v2")
    d = derived(_state(rs, 10, 5), rs, "p1")
    assert (d["own.rolls_die"], d["opponent.rolls_die"]) == (1, 0)
    d = derived(_state(rs, 5, 10), rs, "p1")
    assert (d["own.rolls_die"], d["opponent.rolls_die"]) == (0, 1)
    d = derived(_state(rs, 7, 7), rs, "p1")
    assert (d["own.rolls_die"], d["opponent.rolls_die"]) == (1, 1)
    # Exploded seat on the better field: own flag 0, the opponent rolls although it lags.
    d = derived(_state(rs, 20, 5, s1=Status.EXPLODED), rs, "p1")
    assert (d["own.rolls_die"], d["opponent.rolls_die"]) == (0, 1)
    d = derived(_state(rs, 20, 5, s1=Status.EXPLODED), rs, "p2")
    assert (d["own.rolls_die"], d["opponent.rolls_die"]) == (1, 0)
    d = derived(_state(rs, 5, 5, Status.EXPLODED, Status.EXPLODED), rs, "p1")
    assert (d["own.rolls_die"], d["opponent.rolls_die"]) == (0, 0)


@pytest.mark.parametrize("version", VERSIONS)
def test_explosion_chance_equals_the_bot_helper_and_is_finite(version):
    rs = load_ruleset(version)
    for state in _states(rs, 3):
        for seat, who in (("p1", "own"), ("p2", "opponent")):
            p = state.players[seat]
            d = derived(state, rs, "p1")
            assert d[f"{who}.explosion_chance"] == explosion_chance(p.bag, p.white_total, rs)
    state = new_game(rs)
    state.players["p1"].bag = {}
    d = derived(state, rs, "p1")
    assert d["own.explosion_chance"] == 0.0
    assert np.isfinite(vectorize(observe(state, rs, "p1"), rs)).all()


def test_other_features():
    rs = load_ruleset("v2")
    state = _state(rs, 12, 3)
    state.players["p1"].points = 7
    state.players["p2"].points = 10
    state.players["p1"].white_total = 4
    state.players["p1"].placed = ["white_1", "white_1"]
    d = derived(state, rs, "p1")
    assert d["point_delta"] == -3
    assert derived(state, rs, "p2")["point_delta"] == 3
    assert d["own.limit_distance"] == rs.explosion_limit - 4
    assert d["own.chips_placed"] == 2 and d["opponent.chips_placed"] == 0
    assert d["own.scoring_field"] == 13
    assert d["own.ruby_at_scoring_field"] == float(13 in rs.rubies)


def test_names_are_generic():
    names = derived_names()
    assert len(set(names)) == len(names) == 17
    rs = load_ruleset("v2")
    colours = {c.colour for c in rs.chips} | {c.id for c in rs.chips}
    for n in names:
        assert not any(c in n for c in colours)
        assert "droplet" not in n and "buy" not in n


@pytest.mark.parametrize("version", VERSIONS)
def test_derived_entries_in_vector_and_inside_bounds(version):
    rs = load_ruleset(version)
    names = vector_names(rs)
    low, high = observation_bounds(rs)
    for seed in range(5):
        for state in _states(rs, seed):
            for seat in ("p1", "p2"):
                vec = vectorize(observe(state, rs, seat), rs)
                d = derived(state, rs, seat)
                for n, v in d.items():
                    i = names.index(n)
                    assert vec[i] == np.float32(v)
                    assert low[i] <= vec[i] <= high[i], n


@pytest.mark.parametrize("version", VERSIONS)
def test_derived_ignores_bag_order(version):
    rs = load_ruleset(version)
    for state in _states(rs, 2):
        other = copy.deepcopy(state)
        for p in other.players.values():
            p.bag = dict(reversed(list(p.bag.items())))
        assert derived(state, rs, "p1") == derived(other, rs, "p1")
