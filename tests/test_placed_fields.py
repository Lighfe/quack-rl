from helpers import RS, play

from quack_rl.engine import DONE, DRAW, Phase, ScriptedChance, Status, new_game, step
from quack_rl.rules import load_ruleset


def brew_game(rs=RS):
    """A new game after the first card (no effect), at the first brew step."""
    return step(new_game(rs), rs, None, ScriptedChance(["card_8_to_12"])).state


def test_placed_fields_follow_every_draw():
    s = brew_game()
    for chip in ("white_1", "white_2", "orange_1"):
        r = play(s, DRAW, DRAW, chip, "white_1")
        s = r.state
        place = next(e for e in r.events if e["kind"] == "place" and e["seat"] == "p1")
        p = s.players["p1"]
        assert p.placed_fields[-1] == place["to"]
        assert len(p.placed_fields) == len(p.placed)


def test_placed_fields_follow_every_draw_with_step_called_directly():
    rs = load_ruleset("v2.1")
    s = brew_game(rs)
    for chip in ("white_1", "white_2", "orange_1"):
        r = step(s, rs, {"p1": DRAW, "p2": DRAW}, ScriptedChance((chip, "white_1")))
        s = r.state
        place = next(e for e in r.events if e["kind"] == "place" and e["seat"] == "p1")
        p = s.players["p1"]
        assert p.placed_fields[-1] == place["to"]
        assert len(p.placed_fields) == len(p.placed)


def test_two_chips_on_track_end_both_store_track_end():
    s = brew_game()
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


def test_placed_fields_empty_after_round_reset():
    s = _shop_state(["white_1", "white_2"])
    r = play(s, DONE, DONE)
    assert r.state.round == 2
    for p in r.state.players.values():
        assert p.placed == [] and p.placed_fields == []
