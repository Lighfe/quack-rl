"""Observation layout 6 (rules v1.11): layout choice, vector, card block, actions, envs, refusals."""

import random

import numpy as np
import pytest
from gymnasium.utils.env_checker import check_env
from pettingzoo.test import parallel_api_test

from quack_rl.engine import (
    RngChance,
    action_names,
    legal_actions,
    needs_actions,
    new_game,
    step,
)
from quack_rl.engine.state import Phase
from quack_rl.rl import (
    QuackEnv,
    QuackParallelEnv,
    action_mask,
    map_channels,
    map_slice,
    observation_bounds,
    observation_layout,
    observe,
    vector_names,
    vectorize,
)
from quack_rl.rl.encode import CARD_COLOURS, LAYOUT_COLOURS, map_colours
from quack_rl.rl.opponents import make_opponent
from quack_rl.rules import load_ruleset

RS11 = load_ruleset("v1.11")
RS10 = load_ruleset("v1.10")
SEATS = ("p1", "p2")
KINDS = [
    "ruby_double",
    "restart_after_5",
    "drop_all_1",
    "explosion_limit_plus_2",
    "choice_black_or_value2_or_drop",
    "choice_drop2_or_purple",
    "fewest_points_green",
    "no_effect",
]
CARD_ACTIONS = [
    "continue",
    "restart",
    "card_drop_2",
    "card_purple",
    "card_black",
    "card_chip:white_2",
    "card_chip:green_2",
    "card_chip:blue_2",
    "card_chip:red_2",
    "card_chip:yellow_2",
    "card_drop_end",
]


def states(seed, rs=RS11):
    rng = random.Random(seed)
    chance = RngChance(seed)
    state = new_game(rs)
    yield state
    while state.phase is not Phase.GAME_OVER:
        actions = (
            {s: rng.choice(legal_actions(state, rs, s)) for s in SEATS}
            if needs_actions(state)
            else None
        )
        state = step(state, rs, actions, chance).state
        yield state


def test_layout_comes_from_the_cards_not_the_version_name():
    assert observation_layout(RS11) == 6
    assert observation_layout(RS10) == 5
    # the same ruleset with the version renamed and without cards is layout 5 again
    no_cards = RS11.model_copy(update={"cards": []})
    assert observation_layout(no_cards) == 5
    # a ruleset with cards and another name is layout 6
    renamed = RS10.model_copy(update={"version": "x", "cards": RS11.cards})
    assert observation_layout(renamed) == 6


def test_colour_count_comes_from_the_layout():
    assert LAYOUT_COLOURS == {2: 4, 3: 4, 4: 5, 5: 8}
    assert CARD_COLOURS == 8
    assert map_colours(RS11) == 8
    assert map_channels(RS11) == 2 + 2 * (8 + 2)


def test_vector_names_card_block_and_sizes():
    names = vector_names(RS11)
    assert len(set(names)) == len(names)
    lo, hi = observation_bounds(RS11)
    assert len(lo) == len(hi) == len(names)
    # the card phases have a slot
    for phase in ("card", "card_choice", "restart"):
        assert f"phase.{phase}" in names
    sl = map_slice(RS11)
    assert sl.stop == len(names)
    block = [n for n in names[: sl.start] if n.startswith(("card.", "deck.", "restart.")) or "round_end" in n]
    assert block == [
        *(f"card.{k}" for k in KINDS),
        *(f"deck.{k}" for k in KINDS),
        "restart.available",
        "own.round_end_halves",
        "opponent.round_end_halves",
    ]
    assert len(block) == 2 * len(KINDS) + 3 == 19
    start = names.index("card.ruby_double")
    assert names[start - 1] == f"shop.{RS11.shop[-1].id}.open"
    assert names[start + 19] == "map.0.money"
    # layout 5 is the same vector without the card block and the card phases
    assert len(vector_names(RS11)) == len(vector_names(RS10)) + 19 + 3


def test_card_block_follows_the_state():
    names = vector_names(RS11)
    saw_card = saw_restart = False
    lo, hi = observation_bounds(RS11)
    for seed in range(12):
        for state in states(seed):
            for seat in SEATS:
                vec = vectorize(observe(state, RS11, seat), RS11)
                assert np.all(vec >= lo) and np.all(vec <= hi)
                v = dict(zip(names, vec, strict=True))
                kinds = [RS11.card(state.card).effect] if state.card else []
                for k in KINDS:
                    assert v[f"card.{k}"] == float(k in kinds)
                    left = sum(RS11.card(c).effect == k for c in state.deck)
                    assert v[f"deck.{k}"] == left
                assert sum(v[f"card.{k}"] for k in KINDS) == (1 if state.card else 0)
                assert sum(v[f"deck.{k}"] for k in KINDS) == len(state.deck)
                if v["card.restart_after_5"]:
                    saw_restart |= v["restart.available"] == 1.0
                else:
                    assert v["restart.available"] == 0.0
                saw_card |= bool(state.card)
                limit = 9 if (state.card and RS11.card(state.card).effect == "explosion_limit_plus_2") else 7
                assert v["explosion_limit"] == limit
    assert saw_card and saw_restart


def test_restart_is_available_until_offered():
    for seed in range(40):
        for state in states(seed):
            if not state.card or RS11.card(state.card).effect != "restart_after_5":
                continue
            for seat in SEATS:
                p = state.players[seat]
                obs = observe(state, RS11, seat)
                assert obs["restart_available"] == (
                    p.restart_pending or (not p.restart_offered and p.status.value == "brewing")
                )
                if state.phase is Phase.RESTART and not p.restart_pending:
                    assert not obs["restart_available"] or p.status.value == "brewing"
            return
    pytest.fail("no restart card drawn")


def _first_state(phase, effect=None):
    for seed in range(200):
        for state in states(seed):
            if state.phase is phase and (effect is None or RS11.card(state.card).effect == effect):
                return state
    pytest.fail(f"no state in phase {phase}")


def test_pending_choice_of_the_opponent_is_not_in_the_view():
    names = vector_names(RS11)
    assert not [n for n in names if n.startswith("opponent.") and ("restart" in n or "choice" in n)]
    # a restart that only p1 is asked for: the view of p2 does not change with p1's pending flag
    state = _first_state(Phase.RESTART)
    pending = [s for s in SEATS if state.players[s].restart_pending]
    assert pending
    other = "p2" if pending[0] == "p1" else "p1"
    before = vectorize(observe(state, RS11, other), RS11)
    state.players[pending[0]].restart_pending = not state.players[pending[0]].restart_pending
    after = vectorize(observe(state, RS11, other), RS11)
    own_other = state.players[other].restart_pending
    if not own_other:
        assert np.array_equal(before, after)
    obs = observe(state, RS11, other)
    assert "restart_available" in obs and "restart_pending" not in obs["opponent"]
    # card choice: the choices are not in the state, so both views are equal up to the seat
    state = _first_state(Phase.CARD_CHOICE)
    for seat in SEATS:
        view = observe(state, RS11, seat)
        assert view["opponent"]["round_end_halves"] == 0
        assert set(view["opponent"]) >= {"round_end_halves"}
        assert not [k for k in view["opponent"] if "choice" in k or "pending" in k]


def test_resolved_card_5_drop_is_open_after_the_choice():
    names = vector_names(RS11)
    for seed in range(200):
        prev = None
        for state in states(seed):
            if prev is not None and prev.phase is Phase.CARD_CHOICE and state.phase is Phase.BREW:
                for seat in SEATS:
                    other = "p2" if seat == "p1" else "p1"
                    v = dict(zip(names, vectorize(observe(state, RS11, seat), RS11), strict=True))
                    assert v["own.round_end_halves"] == state.players[seat].round_end_halves
                    assert v["opponent.round_end_halves"] == state.players[other].round_end_halves
                    if state.players[seat].round_end_halves:
                        return
            prev = state
    pytest.fail("no resolved card 5 drop")


def test_action_list_appends_the_card_actions_at_the_end():
    names10 = action_names(RS10)
    names11 = action_names(RS11)
    assert names11[: len(names10)] == names10
    assert names11[len(names10) :] == CARD_ACTIONS
    assert len(names11) == len(names10) + len(CARD_ACTIONS)
    assert len(set(names11)) == len(names11)


def test_mask_equals_legal_actions_and_bounds_cover_card_phases():
    names = action_names(RS11)
    seen = set()
    for seed in range(12):
        for state in states(seed):
            for seat in SEATS:
                legal = set(legal_actions(state, RS11, seat))
                mask = action_mask(state, RS11, seat)
                assert mask.shape == (len(names),)
                assert {n for n, m in zip(names, mask, strict=True) if m} == legal
                seen |= legal & set(CARD_ACTIONS)
    assert seen == set(CARD_ACTIONS)


def test_parallel_api():
    parallel_api_test(QuackParallelEnv(rules="v1.11"), num_cycles=1000)


def test_check_env():
    check_env(QuackEnv(rules="v1.11"), skip_render_check=True)


def test_parallel_env_masked_games_stay_in_the_space():
    env = QuackParallelEnv(rules="v1.11")
    rng = random.Random(0)
    for seed in range(15):
        obs, _ = env.reset(seed=seed)
        while env.agents:
            acts = {a: rng.choice(np.flatnonzero(obs[a]["action_mask"]).tolist()) for a in env.agents}
            obs, *_ = env.step(acts)
            for a in obs:
                assert env.observation_space(a)["observation"].contains(obs[a]["observation"])
        assert env.state.phase is Phase.GAME_OVER


@pytest.mark.parametrize("seat", SEATS)
def test_single_env_masked_games_run_to_the_end(seat):
    for seed in range(10):
        env = QuackEnv(seat=seat, opponent=make_opponent("draw20-pts4-blue", seed, "v1.11"), rules="v1.11")
        names = action_names(env.rs)
        rng = np.random.default_rng(seed)
        _, info = env.reset(seed=seed)
        done = False
        while not done:
            legal = set(legal_actions(env.state, env.rs, env.agent_seat))
            assert {names[i] for i in np.flatnonzero(info["action_mask"])} == legal
            _, _, done, _, info = env.step(int(rng.choice(np.flatnonzero(info["action_mask"]))))
            assert not info["illegal_action"]
        assert env.state.phase is Phase.GAME_OVER
