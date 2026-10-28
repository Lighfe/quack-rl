"""Ruleset v2.3: the black chip rule and the droplet in whole steps.

Black (round end, both pots, an exploded pot too): equal counts of 1 or more give each player
droplet +1; the larger count gives droplet +1 and 1 ruby; otherwise nothing. Every other droplet
move has its v2.2 size, now counted in whole steps.
"""

import dataclasses

import pytest

from quack_rl.components import PotRoundEnd, get_component
from quack_rl.engine import (
    CARD_DROP_2,
    DONE,
    RUBY_DROP,
    WAIT,
    Phase,
    PlayerState,
    ScriptedChance,
    Status,
    new_game,
    start_field,
    step,
)
from quack_rl.rules import load_ruleset

RS = load_ruleset("v2.3")
BLACK = get_component("black@1")
PURPLE = get_component("purple@1")


def chips(n: int, chip_id: str) -> list:
    return [RS.chip(chip_id)] * n


# --- the black component -------------------------------------------------------------


@pytest.mark.parametrize(
    ("mine", "theirs", "want_mine", "want_theirs"),
    [
        (0, 0, PotRoundEnd(), PotRoundEnd()),
        (1, 1, PotRoundEnd(droplet=1), PotRoundEnd(droplet=1)),
        (2, 1, PotRoundEnd(droplet=1, rubies=1), PotRoundEnd()),
        (3, 3, PotRoundEnd(droplet=1), PotRoundEnd(droplet=1)),
        (1, 0, PotRoundEnd(droplet=1, rubies=1), PotRoundEnd()),
    ],
)
def test_black_compares_the_black_chips_of_both_pots(mine, theirs, want_mine, want_theirs):
    a, b = chips(mine, "black_1"), chips(theirs, "black_1")
    assert BLACK.pot_round_end(a, b) == want_mine
    assert BLACK.pot_round_end(b, a) == want_theirs


def test_black_counts_only_black_chips():
    a = [*chips(1, "black_1"), *chips(3, "white_1")]
    b = [*chips(1, "black_1"), *chips(2, "orange_1")]
    assert BLACK.pot_round_end(a, b) == PotRoundEnd(droplet=1)


def test_pot_round_end_counts_whole_steps():
    names = {f.name for f in dataclasses.fields(PotRoundEnd)}
    assert names == {"points", "droplet", "rubies"}


# --- black in the engine: both pots, an exploded pot too ---------------------------------


def resolve_state(p1_placed, p2_placed, exploded=()):
    s = new_game(RS)
    s.card = "card_4"  # no ruby, die or round end effect
    s.phase = Phase.RESOLVE
    for seat, placed in (("p1", p1_placed), ("p2", p2_placed)):
        p = s.players[seat]
        p.placed = list(placed)
        p.field = p.final_field = 0  # scoring field 1: no ruby field
        p.status = Status.EXPLODED if seat in exploded else Status.STOPPED
    return s


def black_events(events):
    return {e["seat"]: e for e in events if e["kind"] == "pot_round_end"}


def resolve(s):
    rolls = [p for p in ("p1", "p2") if s.players[p].status is Status.STOPPED]
    return step(s, RS, None, ScriptedChance(["point_1"] * len(rolls)))


def test_engine_black_0_and_0_gives_nothing():
    r = resolve(resolve_state(["white_1"], ["white_1"]))
    assert black_events(r.events) == {}
    for seat in ("p1", "p2"):
        p = r.state.players[seat]
        assert (p.droplet, p.rubies) == (0, RS.start_rubies)


def test_engine_black_1_and_1_gives_droplet_1_each_and_no_ruby():
    r = resolve(resolve_state(["black_1"], ["black_1"]))
    events = black_events(r.events)
    for seat in ("p1", "p2"):
        p = r.state.players[seat]
        assert (p.droplet, p.rubies) == (1, RS.start_rubies)
        assert events[seat]["drop"] == 1 and events[seat]["rubies"] == 0
        assert "halves" not in events[seat]


def test_engine_black_2_and_1_gives_the_larger_droplet_1_and_1_ruby():
    r = resolve(resolve_state(["black_1", "white_1", "black_1"], ["black_1"]))
    p1, p2 = r.state.players["p1"], r.state.players["p2"]
    assert (p1.droplet, p1.rubies) == (1, RS.start_rubies + 1)
    assert (p2.droplet, p2.rubies) == (0, RS.start_rubies)
    events = black_events(r.events)
    assert events["p1"] == {
        "seat": "p1",
        "kind": "pot_round_end",
        "component": "black@1",
        "points": 0,
        "drop": 1,
        "rubies": 1,
        "total": RS.start_rubies + 1,
    }
    assert "p2" not in events


def test_engine_black_chips_of_an_exploded_pot_count():
    # p1 exploded with 2 black chips, p2 stopped with 1: p1 has the larger count
    r = resolve(resolve_state(["black_1", "black_1"], ["black_1"], exploded=("p1",)))
    p1, p2 = r.state.players["p1"], r.state.players["p2"]
    assert (p1.droplet, p1.rubies) == (1, RS.start_rubies + 1)
    assert p2.droplet == 0
    # the exploded pot's chips also count against the other pot: equal counts
    r = resolve(resolve_state(["black_1"], ["black_1"], exploded=("p2",)))
    assert [r.state.players[s].droplet for s in ("p1", "p2")] == [1, 1]


# --- whole steps: every other move keeps its v2.2 size ---------------------------------------


def test_player_state_counts_the_droplet_in_whole_steps():
    names = {f.name for f in dataclasses.fields(PlayerState)}
    assert "droplet" in names and "droplet_halves" not in names
    p = new_game(RS).players["p1"]
    p.droplet = 4
    assert start_field(p, RS) == 4  # the droplet itself is the start field (no rat tail)


def test_die_face_droplet_moves_the_droplet_by_1():
    face = next(f for f in RS.die if f.kind == "droplet")
    assert face.droplet == 1  # v2.2: 2 halves
    # both stop on the same field: both roll, p1 the droplet face, p2 a point face
    s = resolve_state(["white_1"], ["white_1"])
    r = step(s, RS, None, ScriptedChance(["droplet_1", "point_1"]))
    assert [r.state.players[seat].droplet for seat in ("p1", "p2")] == [1, 0]


def test_card_drops_move_the_droplet_by_1_and_2():
    # card 3: droplet +1 for everyone (v2.2: 2 halves)
    r = step(new_game(RS), RS, None, ScriptedChance(["card_3"]))
    assert [r.state.players[s].droplet for s in ("p1", "p2")] == [1, 1]
    assert {"seat": "p1", "kind": "card_drop", "drop": 1} in r.events
    # card 6: the drop choice is droplet +2 (v2.2: 4 halves)
    s = step(new_game(RS), RS, None, ScriptedChance(["card_6"])).state
    r = step(s, RS, {"p1": CARD_DROP_2, "p2": "card_purple"}, ScriptedChance([]))
    assert r.state.players["p1"].droplet == 2
    assert {"seat": "p1", "kind": "card_drop", "drop": 2} in r.events


@pytest.mark.parametrize(("count", "drop"), [(1, 0), (2, 0), (3, 1), (4, 1)])
def test_purple_three_or_more_moves_the_droplet_by_1(count, drop):
    assert PURPLE.pot_round_end(chips(count, "purple_1"), []).droplet == drop
    r = resolve(resolve_state(["purple_1"] * count, ["white_1"]))
    assert r.state.players["p1"].droplet == drop


def test_ruby_drop_moves_the_droplet_by_1():
    s = new_game(RS)
    s.phase = Phase.RUBY
    for p in s.players.values():
        p.shop_done = True
    s.players["p1"].rubies = 4
    s.players["p2"].rubies = 0
    r = step(s, RS, {"p1": RUBY_DROP, "p2": DONE}, ScriptedChance([]))
    assert r.state.players["p1"].droplet == 1
    assert {"seat": "p1", "kind": "ruby_drop", "rubies": 2, "drop": 1, "total": 2} in r.events
    r = step(r.state, RS, {"p1": RUBY_DROP, "p2": WAIT}, ScriptedChance([]))
    assert r.state.players["p1"].droplet == 2
