import copy
import random

import numpy as np
import pytest

from quack_rl.engine import (
    RngChance,
    ScriptedChance,
    action_names,
    legal_actions,
    needs_actions,
    new_game,
    step,
)
from quack_rl.engine.state import Phase
from quack_rl.rl import (
    action_mask,
    map_channels,
    map_slice,
    observation_bounds,
    observation_layout,
    observe,
    reward,
    vector_names,
    vectorize,
)
from quack_rl.rules import apply_overrides, load_ruleset, with_rounds

VERSIONS = ["v2.1"]


def brew_game(rs):
    """A new game after the first card (a card without effect), at the first brew step."""
    return step(new_game(rs), rs, None, ScriptedChance(["card_8_to_12"])).state


def random_game(rs, seed):
    """Yield every state of a random game, the last one included."""
    rng = random.Random(seed)
    chance = RngChance(seed)
    state = new_game(rs)
    yield state
    while state.phase is not Phase.GAME_OVER:
        if needs_actions(state):
            actions = {s: rng.choice(legal_actions(state, rs, s)) for s in ("p1", "p2")}
        else:
            actions = None
        state = step(state, rs, actions, chance).state
        yield state


@pytest.mark.parametrize("version", VERSIONS)
def test_action_mask_equals_legal_actions_at_every_step(version):
    rs = load_ruleset(version)
    names = action_names(rs)
    for seed in range(5):
        for state in random_game(rs, seed):
            for seat in ("p1", "p2"):
                mask = action_mask(state, rs, seat)
                assert mask.dtype == np.int8
                assert len(mask) == len(names)
                got = [n for n, m in zip(names, mask, strict=True) if m]
                assert got == [n for n in names if n in legal_actions(state, rs, seat)]


@pytest.mark.parametrize("version", VERSIONS)
def test_vector_layout_depends_only_on_ruleset(version):
    rs = load_ruleset(version)
    names = vector_names(rs)
    assert len(set(names)) == len(names)
    for state in random_game(rs, 1):
        for seat in ("p1", "p2"):
            vec = vectorize(observe(state, rs, seat), rs)
            assert vec.dtype == np.float32
            assert vec.shape == (len(names),)


def test_layout_differs_between_rulesets_only_by_ruleset():
    assert vector_names(load_ruleset("v2.1")) == vector_names(load_ruleset("v2.1"))


@pytest.mark.parametrize("version", VERSIONS)
def test_observation_is_mirrored_between_seats(version):
    rs = load_ruleset(version)
    for state in random_game(rs, 3):
        swapped = copy.deepcopy(state)
        swapped.players = {"p1": state.players["p2"], "p2": state.players["p1"]}
        assert observe(state, rs, "p1") == observe(swapped, rs, "p2")
        o1 = observe(state, rs, "p1")
        o2 = observe(state, rs, "p2")
        # the hand is private: only the own view has it
        assert {k: v for k, v in o1["own"].items() if k != "hand"} == o2["opponent"]
        assert o1["opponent"] == {k: v for k, v in o2["own"].items() if k != "hand"}


def test_observation_content():
    rs = load_ruleset("v2.1")
    state = new_game(rs)
    obs = observe(state, rs, "p1")
    assert obs["round"] == 1
    assert obs["phase"] == "card"  # v2.1 opens with the card step
    state = brew_game(rs)
    obs = observe(state, rs, "p1")
    assert obs["phase"] == "brew"
    assert obs["own"]["bag_remaining"]["white_1"] == 4
    assert set(obs["own"]) >= {
        "board",
        "money",
        "white_total",
        "ruby_fields_ahead",
        "points",
        "status",
        "droplet_halves",
        "purchases",
        "chip_colours",
    }
    assert "bag" not in obs["opponent"] and "placed" not in obs["own"] and "field" not in obs["own"]
    assert obs["own"]["ruby_fields_ahead"] == sum(f.ruby for f in rs.fields)
    state.players["p1"].field = 12  # scoring field 13: rubies 13.. are ahead
    assert observe(state, rs, "p1")["own"]["ruby_fields_ahead"] == sum(f.ruby for f in rs.fields) - 2


@pytest.mark.parametrize("version", VERSIONS)
def test_no_hidden_information(version):
    rs = load_ruleset(version)
    for state in random_game(rs, 2):
        shuffled = copy.deepcopy(state)
        for p in shuffled.players.values():
            items = list(p.bag.items())
            random.Random(7).shuffle(items)
            p.bag = dict(reversed(items))
        for seat in ("p1", "p2"):
            a = observe(state, rs, seat)
            b = observe(shuffled, rs, seat)
            assert a == b
            assert np.array_equal(vectorize(a, rs), vectorize(b, rs))


def test_reward_win_loss_draw():
    rs = load_ruleset("v2.1")
    state = new_game(rs)
    state.players["p1"].points = 10
    state.players["p2"].points = 4
    assert reward(state, "p1") == 1.0
    assert reward(state, "p2") == -1.0
    state.players["p2"].points = 10
    assert reward(state, "p1") == 0.0
    assert reward(state, "p2") == 0.0


def _place_events(rs, seed):
    """Yield (state, place events of the round so far per seat) for every state of a game."""
    rng = random.Random(seed)
    chance = RngChance(seed)
    state = new_game(rs)
    events = {"p1": [], "p2": []}
    yield state, events
    while state.phase is not Phase.GAME_OVER:
        actions = (
            {s: rng.choice(legal_actions(state, rs, s)) for s in ("p1", "p2")}
            if needs_actions(state)
            else None
        )
        result = step(state, rs, actions, chance)
        if result.state.round != state.round:
            events = {"p1": [], "p2": []}
        for e in result.events:
            if e["kind"] == "place":
                events[e["seat"]].append(e)
        state = result.state
        yield state, events


@pytest.mark.parametrize("version", VERSIONS)
def test_names_unique_and_layout_version(version):
    rs = load_ruleset(version)
    names = vector_names(rs)
    assert observation_layout(rs) == 7
    assert len(set(names)) == len(names)
    assert names == vector_names(load_ruleset(version))
    sl = map_slice(rs)
    assert sl.stop == len(names)
    assert (sl.stop - sl.start) == (rs.track_end + 1) * map_channels(rs)
    assert names[sl.start] == "map.0.money"


@pytest.mark.parametrize("version", VERSIONS)
def test_map_matches_place_events(version):
    rs = load_ruleset(version)
    colours = list(dict.fromkeys(c.colour for c in rs.chips))
    for seed in range(4):
        for state, events in _place_events(rs, seed):
            if state.phase not in (Phase.BREW, Phase.RESOLVE):
                continue
            for seat in ("p1", "p2"):
                vec = vectorize(observe(state, rs, seat), rs)
                grid = vec[map_slice(rs)].reshape(rs.track_end + 1, map_channels(rs))
                expected = {
                    "own": {},
                    "opponent": {},
                }
                for who, s in (("own", seat), ("opponent", "p2" if seat == "p1" else "p1")):
                    for order, e in enumerate(events[s], start=1):
                        expected[who][e["to"]] = (rs.chip(e["chip"]), order)
                for f in range(rs.track_end + 1):
                    # layout 7: money, points and ruby, then the cells of both seats
                    assert grid[f, 0] == rs.fields[f].money
                    assert grid[f, 1] == rs.fields[f].points
                    assert grid[f, 2] == rs.fields[f].ruby
                    for k, who in enumerate(("own", "opponent")):
                        cell = grid[f, 3 + k * (len(colours) + 2) :][: len(colours) + 2]
                        if f in expected[who]:
                            chip, order = expected[who][f]
                            flags = [float(chip.colour == c) for c in colours]
                            assert list(cell) == [*flags, chip.value, order]
                        else:
                            assert not cell.any()


def test_two_chips_on_track_end_later_chip_fills_the_slot():
    rs = load_ruleset("v2.1")
    state = brew_game(rs)
    state.players["p1"].field = 52
    for chip in ("white_2", "white_1"):
        state = step(
            state, rs, {"p1": "draw", "p2": "draw"}, ScriptedChance([chip, "white_1"])
        ).state
    assert state.players["p1"].placed_fields == [rs.track_end, rs.track_end]
    vec = vectorize(observe(state, rs, "p1"), rs)
    grid = vec[map_slice(rs)].reshape(rs.track_end + 1, map_channels(rs))
    colours = list(dict.fromkeys(c.colour for c in rs.chips))
    cell = grid[rs.track_end, 3 : 3 + len(colours) + 2]
    assert list(cell) == [1.0, *[0.0] * (len(colours) - 1), rs.chip("white_1").value, 2.0]


@pytest.mark.parametrize("version", VERSIONS)
def test_bags_of_both_seats(version):
    rs = load_ruleset(version)
    names = vector_names(rs)
    for state in random_game(rs, 4):
        vec = vectorize(observe(state, rs, "p1"), rs)
        for who, seat in (("own", "p1"), ("opponent", "p2")):
            p = state.players[seat]
            for c in rs.chips:
                assert vec[names.index(f"{who}.bag.remaining.{c.id}")] == p.bag.get(c.id, 0)
                assert vec[names.index(f"{who}.bag.owned.{c.id}")] == p.owned(c.id)


def test_rule_scalars_follow_the_ruleset():
    base = load_ruleset("v2.1")
    variants = [
        base,
        apply_overrides(base, {"explosion_limit": 5}),
        with_rounds(base, 4),
        with_rounds(apply_overrides(base, {"explosion_limit": 9}), 3),
    ]
    for rs in variants:
        names = vector_names(rs)
        vec = vectorize(observe(new_game(rs), rs, "p1"), rs)
        assert vec[names.index("explosion_limit")] == rs.explosion_limit
        assert vec[names.index("rounds")] == rs.rounds


@pytest.mark.parametrize("version", VERSIONS)
def test_removed_entries_and_kept_entries(version):
    names = vector_names(load_ruleset(version))
    for who in ("own", "opponent"):
        assert not [n for n in names if n.startswith(f"{who}.placed.")]
        assert f"{who}.field" not in names
        for k in ("points", "droplet_halves", "white_total", "ruby_fields_ahead", "money"):
            assert f"{who}.{k}" in names
        assert f"{who}.status.exploded" in names
    assert "round" in names and "phase.brew" in names


@pytest.mark.parametrize("version", VERSIONS)
def test_vector_lies_inside_the_bounds(version):
    rs = load_ruleset(version)
    low, high = observation_bounds(rs)
    assert low.dtype == high.dtype == np.float32
    assert low.shape == high.shape == (len(vector_names(rs)),)
    names = vector_names(rs)
    assert high[names.index("own.points")] == 100  # v2.1 caps the points at 100
    assert high[names.index("own.status.exploded")] == 1
    assert np.isfinite(high[names.index("own.ruby_fields_ahead")])
    for seed in range(5):
        for state in random_game(rs, seed):
            for seat in ("p1", "p2"):
                vec = vectorize(observe(state, rs, seat), rs)
                assert (vec >= low).all() and (vec <= high).all()


@pytest.mark.parametrize("version", VERSIONS)
def test_bag_insertion_order_does_not_change_the_vector(version):
    rs = load_ruleset(version)
    for state in random_game(rs, 5):
        reordered = copy.deepcopy(state)
        for p in reordered.players.values():
            p.bag = dict(reversed(list(p.bag.items())))
        for seat in ("p1", "p2"):
            assert np.array_equal(
                vectorize(observe(state, rs, seat), rs),
                vectorize(observe(reordered, rs, seat), rs),
            )


@pytest.mark.parametrize("version", VERSIONS)
def test_pending_choice_of_the_opponent_does_not_change_the_vector(version):
    """The seat sees the state before the joint step; the choice of the opponent is not in the
    state, and both choices lead from the same observation."""
    rs = load_ruleset(version)
    state = step(
        brew_game(rs), rs, {"p1": "draw", "p2": "draw"}, ScriptedChance(["white_1"] * 2)
    ).state
    before = vectorize(observe(state, rs, "p1"), rs)
    outcomes = []
    for p2_choice in legal_actions(state, rs, "p2"):
        copy_state = copy.deepcopy(state)
        step(copy_state, rs, {"p1": "draw", "p2": p2_choice}, ScriptedChance(["white_1"] * 2))
        assert np.array_equal(vectorize(observe(state, rs, "p1"), rs), before)
        outcomes.append(p2_choice)
    assert len(outcomes) > 1


@pytest.mark.parametrize("version", VERSIONS)
def test_derived_entries_come_before_the_map_block(version):
    from quack_rl.rl.derive import derived_names

    rs = load_ruleset(version)
    names = vector_names(rs)
    first = names.index(derived_names()[0])
    assert names[first : first + len(derived_names())] == derived_names()
    # v2.1: the card, shop and board blocks follow the derived entries, then the map block
    assert first + len(derived_names()) <= map_slice(rs).start
