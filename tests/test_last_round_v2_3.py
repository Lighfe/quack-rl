"""Ruleset v2.3: the last round has no shop, and rubies become points at game end (issue #202)."""

from quack_rl.bots.heuristic import HeuristicBot
from quack_rl.engine import (
    TAKE_MONEY,
    WAIT,
    Phase,
    RngChance,
    ScriptedChance,
    Status,
    new_game,
    step,
)
from quack_rl.engine.shop import end_game
from quack_rl.rules import load_ruleset, with_rounds
from quack_rl.runner import play_game

RS = load_ruleset("v2.3")
SHOP_EVENTS = {"buy", "ruby_drop", "refill_flask", "done"}
NO_RUBY_LANDING = 2  # scoring field 3: no ruby field


def test_v2_3_sets_the_ruby_divisor_to_2():
    assert RS.last_round_ruby_divisor == 2


def last_round_state(
    rs=RS, phase=Phase.RESOLVE, p1_status=Status.STOPPED, p2_status=Status.STOPPED
):
    s = new_game(rs)
    s.round = rs.rounds
    s.phase = phase
    for seat, status in (("p1", p1_status), ("p2", p2_status)):
        p = s.players[seat]
        p.status = status
        p.final_field = p.field = NO_RUBY_LANDING
        p.rubies = 0
    return s


def ruby_point_events(events):
    return [e for e in events if e["kind"] == "ruby_points"]


def test_end_game_turns_rubies_into_points_before_the_winner():
    s = last_round_state()
    s.players["p1"].rubies = 5
    s.players["p1"].points = 10
    s.players["p2"].points = 11
    events = []
    end_game(s, RS, events)
    assert s.phase is Phase.GAME_OVER
    assert (s.players["p1"].points, s.players["p2"].points) == (12, 11)
    assert (s.players["p1"].rubies, s.players["p2"].rubies) == (0, 0)
    assert s.winner == "p1"  # the ruby points count for the winner
    assert events == [
        {"seat": "p1", "kind": "ruby_points", "rubies": 5, "points": 2, "total": 0},
        {"seat": "p2", "kind": "ruby_points", "rubies": 0, "points": 0, "total": 0},
        {
            "seat": None,
            "kind": "game_end",
            "winner": "p1",
            "points": {"p1": 12, "p2": 11},
            "final_fields": {"p1": NO_RUBY_LANDING, "p2": NO_RUBY_LANDING},
        },
    ]


def test_ruby_points_stop_at_max_points():
    cap = RS.point_board.max_points
    s = last_round_state()
    s.players["p1"].points = cap - 1
    s.players["p1"].rubies = 4
    events = []
    end_game(s, RS, events)
    assert s.players["p1"].points == cap
    assert ruby_point_events(events)[0] == {
        "seat": "p1",
        "kind": "ruby_points",
        "rubies": 4,
        "points": 1,
        "total": 0,
    }


def test_one_ruby_gives_no_point_and_is_gone():
    s = last_round_state()
    s.players["p1"].rubies = 1
    events = []
    end_game(s, RS, events)
    assert s.players["p1"].points == 0 and s.players["p1"].rubies == 0
    assert ruby_point_events(events)[0]["points"] == 0


def test_last_round_resolve_without_explosion_ends_the_game():
    s = last_round_state()
    s.players["p1"].rubies = 5
    field = RS.fields[NO_RUBY_LANDING + 1]
    res = step(s, RS, None, ScriptedChance(["point_1", "point_1"]))
    out = res.state
    assert out.phase is Phase.GAME_OVER
    kinds = [e["kind"] for e in res.events]
    assert kinds[-3:] == ["ruby_points", "ruby_points", "game_end"]
    expected = field.points + field.money // RS.last_round_money_divisor + 5 // 2
    assert out.players["p1"].points == expected + 1  # +1 from the die face
    assert out.players["p1"].rubies == 0
    assert res.events[-1]["points"]["p1"] == out.players["p1"].points


def test_last_round_take_money_gives_money_points_then_the_game_ends():
    s = last_round_state(phase=Phase.CHOICE, p1_status=Status.EXPLODED)
    s.players["p1"].rubies = 3
    field = RS.fields[NO_RUBY_LANDING + 1]
    res = step(s, RS, {"p1": TAKE_MONEY, "p2": WAIT}, ScriptedChance([]))
    p1 = res.state.players["p1"]
    assert res.state.phase is Phase.GAME_OVER
    assert p1.money == 0 and p1.rubies == 0
    assert p1.points == field.money // RS.last_round_money_divisor + 3 // 2
    assert [e["kind"] for e in res.events][-3:] == ["ruby_points", "ruby_points", "game_end"]


def test_both_explode_in_the_last_round_then_the_game_ends():
    s = last_round_state(phase=Phase.CHOICE, p1_status=Status.EXPLODED, p2_status=Status.EXPLODED)
    res = step(s, RS, {"p1": TAKE_MONEY, "p2": TAKE_MONEY}, ScriptedChance([]))
    assert res.state.phase is Phase.GAME_OVER


def test_choice_before_the_last_round_still_goes_to_the_shop():
    s = last_round_state(phase=Phase.CHOICE, p1_status=Status.EXPLODED)
    s.round = RS.rounds - 1
    res = step(s, RS, {"p1": TAKE_MONEY, "p2": WAIT}, ScriptedChance([]))
    assert res.state.phase is Phase.SHOP


def test_four_round_game_take_money_in_round_4_ends_the_game():
    rs = with_rounds(RS, 4)
    s = last_round_state(rs, phase=Phase.CHOICE, p1_status=Status.EXPLODED)
    assert s.round == 4
    field = rs.fields[NO_RUBY_LANDING + 1]
    res = step(s, rs, {"p1": TAKE_MONEY, "p2": WAIT}, ScriptedChance([]))
    assert res.state.phase is Phase.GAME_OVER
    assert res.state.players["p1"].points == field.money // rs.last_round_money_divisor


def test_full_bot_game_has_no_shop_in_the_last_round():
    for seed in range(5):
        seen = []

        def on_step(result, _ms, seen=seen):
            if result.round == RS.rounds:
                seen.append(result)

        seats = {
            "p1": HeuristicBot(RS, 30, 1, "points", seed=seed),
            "p2": HeuristicBot(RS, 20, 4, "points", seed=seed + 50),
        }
        final = play_game(RS, seats, RngChance(seed), on_step)
        assert final.phase is Phase.GAME_OVER
        assert seen, "the last round was not played"
        assert all(r.phase is not Phase.SHOP for r in seen)
        assert all(e["kind"] not in SHOP_EVENTS for r in seen for e in r.events)
        assert all(r.state.phase is not Phase.SHOP for r in seen)
        assert [e["kind"] for e in seen[-1].events][-3:] == [
            "ruby_points",
            "ruby_points",
            "game_end",
        ]
