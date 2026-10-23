"""Observation layout 7 (rules v2): layout choice, points in the map, refusals."""

import random

import numpy as np

from quack_rl.engine import RngChance, legal_actions, needs_actions, new_game, step
from quack_rl.engine.state import Phase
from quack_rl.rl import (
    map_channels,
    map_slice,
    observation_bounds,
    observation_layout,
    observe,
    vector_names,
    vectorize,
)
from quack_rl.rl.encode import BOARD_LAYOUT, map_colours
from quack_rl.rules import load_ruleset

RS2 = load_ruleset("v2")
RS11 = load_ruleset("v1.11")
SEATS = ("p1", "p2")


def states(seed, rs=RS2):
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


def test_layout_numbers():
    assert BOARD_LAYOUT == 7
    assert observation_layout(RS2) == 7
    assert observation_layout(RS11) == 6
    # the board is checked before the cards
    assert RS2.cards
    assert observation_layout(RS2.model_copy(update={"point_board": None})) == 6


def test_layout_7_uses_what_layout_6_uses():
    assert map_colours(RS2) == map_colours(RS11) == 8
    assert map_channels(RS2) == map_channels(RS11) + 1
    names2, names11 = vector_names(RS2), vector_names(RS11)
    assert "phase.card" in names2 and "card.ruby_double" in names2
    assert len(set(names2)) == len(names2)


def test_map_points_names_and_values_equal_the_table():
    names = vector_names(RS2)
    sl = map_slice(RS2)
    assert sl.stop == len(names)
    assert sl.stop - sl.start == (RS2.track_end + 1) * map_channels(RS2)
    state = new_game(RS2)
    v = dict(zip(names, vectorize(observe(state, RS2, "p1"), RS2), strict=True))
    for f in range(RS2.track_end + 1):
        i = names.index(f"map.{f}.money")
        assert names[i + 1] == f"map.{f}.points"
        assert names[i + 2] == f"map.{f}.ruby"
        assert v[f"map.{f}.points"] == RS2.points[f]


def test_map_points_are_zero_without_a_points_table():
    rs = RS2.model_copy(update={"points": None})
    names = vector_names(rs)
    v = dict(zip(names, vectorize(observe(new_game(rs), rs, "p1"), rs), strict=True))
    assert all(v[f"map.{f}.points"] == 0 for f in range(rs.track_end + 1))
    lo, hi = observation_bounds(rs)
    assert len(lo) == len(hi) == len(names)


def test_bounds_cover_masked_games():
    names = vector_names(RS2)
    lo, hi = observation_bounds(RS2)
    assert len(lo) == len(hi) == len(names)
    i = names.index("map.3.points")
    assert hi[i] == max(RS2.points)
    for seed in range(4):
        for state in states(seed):
            for seat in SEATS:
                vec = vectorize(observe(state, RS2, seat), RS2)
                assert len(vec) == len(names)
                assert np.all(vec >= lo) and np.all(vec <= hi)


def test_older_layouts_are_unchanged():
    for version in ("v1", "v1.1", "v1.8", "v1.9", "v1.10", "v1.11"):
        rs = load_ruleset(version)
        assert not any(n.endswith(".points") and n.startswith("map.") for n in vector_names(rs))
        assert map_channels(rs) == 2 + 2 * (map_colours(rs) + 2)


def _named(state, seat):
    names = vector_names(RS2)
    return dict(zip(names, vectorize(observe(state, RS2, seat), RS2), strict=True))


def test_board_block_names_and_position():
    names = vector_names(RS2)
    fields = RS2.point_board.fields
    i = names.index("own.board.marker.0")
    expected = [
        *(f"own.board.marker.{k}" for k in range(fields + 1)),
        "own.board.has_50pts",
        "own.rat_tail",
        *(f"opponent.board.marker.{k}" for k in range(fields + 1)),
        "opponent.board.has_50pts",
        "opponent.rat_tail",
        *(f"board.tail.{f}" for f in range(fields)),
    ]
    assert names[i : i + len(expected)] == expected
    # between the card block and the map block
    assert names.index("opponent.round_end_halves") < i
    assert i + len(expected) == names.index("map.0.money")
    assert len(set(names)) == len(names)
    # the older layouts have no board block
    assert not [n for n in vector_names(RS11) if "board.marker" in n or n.startswith("board.tail")]
    assert "board" not in observe(new_game(RS11), RS11, "p1")


def test_totals_50_and_51():
    state = new_game(RS2)
    state.players["p1"].points = 50
    state.players["p2"].points = 51
    v = _named(state, "p1")
    assert v["own.board.marker.50"] == 1 and v["own.board.has_50pts"] == 0
    assert sum(v[f"own.board.marker.{k}"] for k in range(51)) == 1
    assert v["opponent.board.marker.1"] == 1 and v["opponent.board.has_50pts"] == 1
    assert sum(v[f"opponent.board.marker.{k}"] for k in range(51)) == 1
    w = _named(state, "p2")
    assert w["own.board.marker.1"] == 1 and w["own.board.has_50pts"] == 1
    assert w["opponent.board.marker.50"] == 1 and w["opponent.board.has_50pts"] == 0


def test_rat_tail_and_tail_entries_equal_the_state_and_toml():
    state = new_game(RS2)
    state.players["p1"].rat_tail = 7
    state.players["p2"].rat_tail = 3
    v = _named(state, "p1")
    assert (v["own.rat_tail"], v["opponent.rat_tail"]) == (7, 3)
    assert (_named(state, "p2")["own.rat_tail"], _named(state, "p2")["opponent.rat_tail"]) == (3, 7)
    for seat in SEATS:
        w = _named(state, seat)
        tails = [f for f in range(RS2.point_board.fields) if w[f"board.tail.{f}"] == 1]
        assert tails == RS2.point_board.rat_tails == [
            1, 4, 7, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32, 34, 36, 38, 40, 42, 44, 46, 48,
        ]


def test_board_bounds():
    names = vector_names(RS2)
    lo, hi = observation_bounds(RS2)
    for who in ("own", "opponent"):
        assert hi[names.index(f"{who}.rat_tail")] == 46
        assert hi[names.index(f"{who}.points")] == 100
        assert hi[names.index(f"{who}.board.has_50pts")] == 1
        assert hi[names.index(f"{who}.board.marker.50")] == 1
    assert hi[names.index("board.tail.48")] == 1
    assert np.all(lo[names.index("own.board.marker.0") : names.index("map.0.money")] == 0)
    # older layouts keep inf points
    assert observation_bounds(RS11)[1][vector_names(RS11).index("own.points")] == np.inf


def test_rat_tail_stays_inside_bounds_in_masked_games():
    lo, hi = observation_bounds(RS2)
    names = vector_names(RS2)
    ia, ib = names.index("own.rat_tail"), names.index("opponent.rat_tail")
    seen = 0
    for seed in range(6):
        for state in states(seed):
            for seat in SEATS:
                vec = vectorize(observe(state, RS2, seat), RS2)
                assert np.all(vec >= lo) and np.all(vec <= hi)
                seen = max(seen, vec[ia], vec[ib])
    assert seen > 0


def test_view_of_the_other_seat_has_no_hand_and_no_pending_choice():
    names = vector_names(RS2)
    assert not [n for n in names if n.startswith("opponent.") and ("hand" in n or "choice" in n or "pending" in n)]
    for state in states(1):
        for seat in SEATS:
            view = observe(state, RS2, seat)
            assert set(view["opponent"]).isdisjoint({"hand"})
            assert not [k for k in view["opponent"] if "choice" in k or "pending" in k]
            assert set(view["board"]["opponent"]) == {"position", "has_50pts", "rat_tail"}
    # changing the hand or a pending flag of p1 does not change the view of p2
    state = new_game(RS2)
    before = vectorize(observe(state, RS2, "p2"), RS2)
    state.players["p1"].hand = []
    state.players["p1"].restart_pending = not state.players["p1"].restart_pending
    assert np.array_equal(before, vectorize(observe(state, RS2, "p2"), RS2))
