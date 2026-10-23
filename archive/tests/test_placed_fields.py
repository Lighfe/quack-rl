"""Moved from tests/test_placed_fields.py (#170): ruleset v2 has no `remove_white_1` shop item."""

from quack_rl.engine import DONE, Phase, ScriptedChance, Status, buy, new_game, step
from quack_rl.rules import load_ruleset

RS = load_ruleset("v1")


def play(state, p1, p2, *chance):
    return step(state, RS, {"p1": p1, "p2": p2}, ScriptedChance(chance))


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


# ---- Moved from tests/test_placed_fields.py (#170), original text ----

def test_placed_fields_follow_every_draw_v1_1():
    rs = load_ruleset("v1.1")
    s = new_game(rs)
    for chip in ("white_1", "white_2", "orange_1"):
        r = step(s, rs, {"p1": DRAW, "p2": DRAW}, ScriptedChance((chip, "white_1")))
        s = r.state
        place = next(e for e in r.events if e["kind"] == "place" and e["seat"] == "p1")
        p = s.players["p1"]
        assert p.placed_fields[-1] == place["to"]
        assert len(p.placed_fields) == len(p.placed)
