from helpers import RS, play

from quack_rl.engine import DONE, DRAW, Phase, ScriptedChance, Status, buy, new_game, step
from quack_rl.rules import load_ruleset


def test_placed_fields_follow_every_draw():
    s = new_game(RS)
    for chip in ("white_1", "white_2", "orange_1"):
        r = play(s, DRAW, DRAW, chip, "white_1")
        s = r.state
        place = next(e for e in r.events if e["kind"] == "place" and e["seat"] == "p1")
        p = s.players["p1"]
        assert p.placed_fields[-1] == place["to"]
        assert len(p.placed_fields) == len(p.placed)


def test_placed_fields_follow_every_draw_v1_1():
    rs = load_ruleset("v2")
    s = new_game(rs)
    for chip in ("white_1", "white_2", "orange_1"):
        r = step(s, rs, {"p1": DRAW, "p2": DRAW}, ScriptedChance((chip, "white_1")))
        s = r.state
        place = next(e for e in r.events if e["kind"] == "place" and e["seat"] == "p1")
        p = s.players["p1"]
        assert p.placed_fields[-1] == place["to"]
        assert len(p.placed_fields) == len(p.placed)


def test_two_chips_on_track_end_both_store_track_end():
    s = new_game(RS)
    s.players["p1"].field = 52
    s = play(s, DRAW, DRAW, "white_2", "white_1").state
    s = play(s, DRAW, DRAW, "white_1", "white_1").state
    p = s.players["p1"]
    assert p.placed_fields == [RS.track_end, RS.track_end]


def _shop_state(placed):
    s = new_game(RS)
    s.phase = Phase.SHOP
    for p in s.players.values():
        p.money, p.status = 20, Status.STOPPED
        p.placed = list(placed)
        p.placed_fields = list(range(1, len(placed) + 1))
        for c in placed:
            p.bag[c] -= 1
        p.field = p.final_field = len(placed)
    return s


def test_remove_chip_drops_the_entry_of_the_removed_chip():
    s = _shop_state(["white_1", "white_2", "orange_1"])
    s.players["p1"].placed_fields = [1, 2, 3]
    r = play(s, buy("remove_white_1"), DONE)
    p = r.state.players["p1"]
    assert p.placed == ["white_2", "orange_1"]
    assert p.placed_fields == [2, 3]


def test_duplicate_chip_id_drops_the_first_occurrence_entry():
    s = _shop_state(["white_1", "white_2", "white_1"])
    s.players["p1"].placed_fields = [1, 3, 4]
    r = play(s, buy("remove_white_1"), DONE)
    p = r.state.players["p1"]
    assert p.placed == ["white_2", "white_1"]
    assert p.placed_fields == [3, 4]
    assert len(p.placed_fields) == len(p.placed)


def test_placed_fields_empty_after_round_reset():
    s = _shop_state(["white_1", "white_2"])
    r = play(s, DONE, DONE)
    assert r.state.round == 2
    for p in r.state.players.values():
        assert p.placed == [] and p.placed_fields == []
