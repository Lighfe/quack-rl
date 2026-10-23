"""Engine under v1.11: the joint card choice (cards 5, 6) and the restart (card 2), issue #144."""

import copy
import io
import json

import pytest
from typer.testing import CliRunner

from quack_rl.cli.main import app
from quack_rl.engine import (
    DONE,
    DRAW,
    SEATS,
    STOP,
    WAIT,
    IllegalAction,
    Phase,
    RngChance,
    ScriptedChance,
    Status,
    action_names,
    legal_actions,
    new_game,
    state_from_dict,
    state_to_dict,
    step,
)
from quack_rl.record import GameRecorder, HeaderLine, SeatInfo, read_games, verify_game, verify_seed
from quack_rl.rl.encode import observe
from quack_rl.rules import load_ruleset
from quack_rl.runner import play_game

RS = load_ruleset("v1.11")
CONTINUE, RESTART = "continue", "restart"
VALUE_TWO = [c.id for c in RS.chips if c.value == 2]


def after_draw(card):
    s = new_game(RS)
    return step(s, RS, None, ScriptedChance([card])).state


def both(a, b=None):
    return {"p1": a, "p2": a if b is None else b}


def choose(card, a, b):
    s = after_draw(card)
    assert s.phase is Phase.CARD_CHOICE
    return step(s, RS, both(a, b), ScriptedChance([]))


# --- cards 5 and 6: the joint choice ----------------------------------------------------


def test_card_6_offers_drop_or_purple_to_both_seats():
    s = after_draw("card_6")
    assert s.phase is Phase.CARD_CHOICE
    for seat in SEATS:
        assert legal_actions(s, RS, seat) == ["card_drop_2", "card_purple"]


def test_card_5_offers_black_every_value_2_chip_and_the_late_drop():
    s = after_draw("card_5")
    assert VALUE_TWO  # the list comes from the ruleset
    expected = ["card_black", *(f"card_chip:{c}" for c in VALUE_TWO), "card_drop_end"]
    for seat in SEATS:
        assert legal_actions(s, RS, seat) == expected


def test_the_minimum_buy_round_does_not_limit_the_value_2_choice():
    s = after_draw("card_5")
    assert s.round == 1
    assert any(i.min_round > 1 and i.kind == "chip" for i in RS.shop)
    assert "card_chip:yellow_2" in legal_actions(s, RS, "p1")


def test_new_card_actions_are_appended_at_the_end_of_the_action_list():
    names = action_names(RS)
    tail = ["continue", "restart", "card_drop_2", "card_purple", "card_black"]
    assert names[-(len(tail) + len(VALUE_TWO) + 1) :][: len(tail)] == tail
    assert names[-1] == "card_drop_end"
    old = action_names(load_ruleset("v1.10"))
    assert old == [n for n in names if n in old]
    assert names[: len(old)] == old or set(old) <= set(names)
    assert len(names) == len(set(names))


def test_card_6_drop_two_moves_the_drop_at_once_and_the_field():
    r = choose("card_6", "card_drop_2", "card_drop_2")
    assert [p.droplet_halves for p in r.state.players.values()] == [4, 4]
    assert [p.field for p in r.state.players.values()] == [2, 2]
    assert r.state.phase is Phase.BREW


def test_card_6_purple_chip_goes_into_the_bag_and_can_be_drawn_at_once():
    r = choose("card_6", "card_purple", "card_purple")
    assert [p.bag["purple_1"] for p in r.state.players.values()] == [1, 1]
    s = r.state
    for p in s.players.values():
        p.bag = {"purple_1": 1}
    out = step(s, RS, both(DRAW), ScriptedChance(["purple_1", "purple_1"]))
    assert [p.placed for p in out.state.players.values()] == [["purple_1"], ["purple_1"]]


def test_card_5_black_chip_and_value_2_chip_go_into_the_bag():
    r = choose("card_5", "card_black", "card_chip:yellow_2")
    p1, p2 = r.state.players["p1"], r.state.players["p2"]
    assert p1.bag["black_1"] == 1 and p2.bag["yellow_2"] == 1
    assert "yellow_2" not in p1.bag and "black_1" not in p2.bag
    kinds = [(e["seat"], e["kind"]) for e in r.events]
    assert ("p1", "card_chip") in kinds and ("p2", "card_chip") in kinds


def test_card_5_value_2_chip_can_be_drawn_in_the_same_round():
    s = choose("card_5", "card_chip:white_2", "card_chip:white_2").state
    for p in s.players.values():
        p.bag = {"white_2": 1}
    out = step(s, RS, both(DRAW), ScriptedChance(["white_2", "white_2"]))
    assert all(p.placed == ["white_2"] for p in out.state.players.values())


def test_card_5_late_drop_changes_nothing_now_and_fires_at_round_end():
    r = choose("card_5", "card_drop_end", "card_drop_end")
    s = r.state
    assert [p.droplet_halves for p in s.players.values()] == [0, 0]
    assert [p.round_end_halves for p in s.players.values()] == [3, 3]
    s.phase = Phase.RESOLVE
    for p in s.players.values():
        p.status, p.final_field, p.field = Status.STOPPED, 1, 1
    money = [f.id for f in RS.die if f.kind == "money"][:1] * 2
    out = step(s, RS, None, ScriptedChance(money))
    assert [p.droplet_halves for p in out.state.players.values()] == [3, 3]
    assert [p.round_end_halves for p in out.state.players.values()] == [0, 0]
    assert [e["seat"] for e in out.events if e["kind"] == "card_round_end_drop"] == ["p1", "p2"]


def test_card_5_late_drop_fires_also_when_the_pot_exploded():
    s = choose("card_5", "card_drop_end", "card_black").state
    s.phase = Phase.RESOLVE
    for p in s.players.values():
        p.status, p.final_field, p.field = Status.EXPLODED, 0, 0
    out = step(s, RS, None, ScriptedChance([]))
    assert out.state.players["p1"].droplet_halves == 3
    assert out.state.players["p2"].droplet_halves == 0


def test_the_late_drop_does_not_carry_into_the_next_round():
    s = choose("card_5", "card_drop_end", "card_drop_end").state
    s.phase = Phase.SHOP
    for p in s.players.values():
        p.status, p.final_field = Status.STOPPED, 1
        p.round_end_halves = 3
    out = step(s, RS, both(DONE), ScriptedChance([])).state
    assert [p.round_end_halves for p in out.players.values()] == [0, 0]


@pytest.mark.parametrize(
    ("card", "a", "b"),
    [
        ("card_5", "card_black", "card_drop_end"),
        ("card_5", "card_chip:red_2", "card_black"),
        ("card_6", "card_drop_2", "card_purple"),
    ],
)
def test_the_two_players_can_choose_different_options(card, a, b):
    r = choose(card, a, b)
    assert [e["action"] for e in r.events if e["kind"] == "card_choice"] == [a, b]
    assert r.state.players["p1"] != r.state.players["p2"]
    if card == "card_6":
        assert r.state.players["p1"].droplet_halves == 4
        assert r.state.players["p2"].droplet_halves == 0
        assert r.state.players["p2"].bag["purple_1"] == 1


def test_a_joint_choice_needs_one_legal_action_per_seat():
    s = after_draw("card_6")
    with pytest.raises(IllegalAction):
        step(s, RS, {"p1": "card_drop_2"}, ScriptedChance([]))
    with pytest.raises(IllegalAction):
        step(s, RS, both("card_drop_2", "card_black"), ScriptedChance([]))
    with pytest.raises(IllegalAction):
        step(s, RS, both(DRAW), ScriptedChance([]))


def test_the_opponent_view_does_not_show_a_choice_before_it_resolves():
    s = after_draw("card_5")
    before = copy.deepcopy(s)
    view = observe(s, RS, "p2")
    # nothing of the state records a pending choice, so the view cannot depend on it
    assert state_to_dict(s) == state_to_dict(before)
    assert observe(before, RS, "p2") == view
    assert view["opponent"]["bag_owned"] == view["own"]["bag_owned"]
    # the same state viewed after p1 picks one option or another differs only after the step
    a = choose("card_5", "card_black", "card_drop_end").state
    b = choose("card_5", "card_chip:red_2", "card_drop_end").state
    assert observe(a, RS, "p2")["own"] == observe(b, RS, "p2")["own"]
    assert not any("card_" in str(v) for v in view["opponent"].values())


# --- card 2: restart --------------------------------------------------------------------


def brew_state():
    s = after_draw("card_2")
    assert s.phase is Phase.BREW
    for p in s.players.values():
        p.bag = {"white_1": 30}
    return s


def draw_n(s, n, actions=None):
    for _ in range(n):
        s = step(s, RS, actions or both(DRAW), ScriptedChance(["white_1", "white_1"])).state
    return s


def test_both_players_reach_5_chips_in_the_same_step():
    s = draw_n(brew_state(), 5)
    assert s.phase is Phase.RESTART
    assert [len(p.placed) for p in s.players.values()] == [5, 5]
    for seat in SEATS:
        assert legal_actions(s, RS, seat) == [CONTINUE, RESTART]


def test_one_restarts_and_one_continues():
    s = draw_n(brew_state(), 5)
    r = step(s, RS, {"p1": RESTART, "p2": CONTINUE}, ScriptedChance([]))
    p1, p2 = r.state.players["p1"], r.state.players["p2"]
    assert r.state.phase is Phase.BREW
    assert p1.placed == [] and p1.placed_fields == [] and p1.white_total == 0
    assert p1.field == 0 and p1.hand == []
    assert p1.bag["white_1"] == 30  # 25 left plus the 5 placed chips
    assert p2.placed == ["white_1"] * 5 and p2.white_total == 5 and p2.field == 5
    assert [e["kind"] for e in r.events] == ["restart", "restart_continue"]
    assert legal_actions(r.state, RS, "p1") == [DRAW]  # empty pot: no stop yet


def test_restart_resets_to_the_start_field_of_the_player():
    s = brew_state()
    s.players["p1"].droplet_halves = 6
    s.players["p1"].field = 3
    s = draw_n(s, 5)
    r = step(s, RS, {"p1": RESTART, "p2": CONTINUE}, ScriptedChance([]))
    assert r.state.players["p1"].field == 3  # start field, not 3 + chips


def test_restart_puts_the_blue_hand_back_into_the_bag():
    s = draw_n(brew_state(), 5)
    p1 = s.players["p1"]
    p1.hand = ["blue_2", "blue_1"]
    before = sum(p1.bag.values())
    r = step(s, RS, {"p1": RESTART, "p2": CONTINUE}, ScriptedChance([]))
    q = r.state.players["p1"]
    assert q.hand == [] and sum(q.bag.values()) == before + 5 + 2
    assert q.bag["blue_2"] == 1 and q.bag["blue_1"] == 1


def test_no_second_choice_after_a_restart_or_after_continue():
    s = draw_n(brew_state(), 5)
    s = step(s, RS, {"p1": RESTART, "p2": CONTINUE}, ScriptedChance([])).state
    s.players["p2"].status = Status.STOPPED
    s = draw_n(s, 5, {"p1": DRAW, "p2": WAIT})  # p1 reaches 5 chips again
    assert len(s.players["p1"].placed) == 5
    assert s.phase is Phase.BREW


def test_the_other_seat_waits_while_a_player_decides():
    s = brew_state()
    s = draw_n(s, 4)
    s.players["p2"].status = Status.STOPPED  # p2 stopped earlier with 4 chips
    s = step(s, RS, {"p1": DRAW, "p2": WAIT}, ScriptedChance(["white_1"])).state
    assert s.phase is Phase.RESTART
    assert legal_actions(s, RS, "p1") == [CONTINUE, RESTART]
    assert legal_actions(s, RS, "p2") == [WAIT]


def test_a_player_still_below_5_chips_waits_and_plays_on_afterwards():
    s = brew_state()
    s = draw_n(s, 4)
    s.players["p2"].placed = s.players["p2"].placed[:2]  # p2 is at 2 chips
    s.players["p2"].white_total = 2
    s = step(s, RS, both(DRAW), ScriptedChance(["white_1", "white_1"])).state
    assert s.phase is Phase.RESTART
    assert legal_actions(s, RS, "p2") == [WAIT]
    s = step(s, RS, {"p1": CONTINUE, "p2": WAIT}, ScriptedChance([])).state
    assert s.phase is Phase.BREW and len(s.players["p2"].placed) == 3


def test_exploding_on_the_5th_chip_gives_no_choice():
    s = brew_state()
    s = draw_n(s, 4)
    s.players["p1"].white_total = 6
    s.players["p2"].status = Status.STOPPED
    s.players["p1"].bag["white_2"] = 1
    r = step(s, RS, {"p1": DRAW, "p2": WAIT}, ScriptedChance(["white_2"]))
    assert r.state.players["p1"].status is Status.EXPLODED
    assert r.state.phase is not Phase.RESTART


def test_stopping_before_5_chips_gives_no_choice():
    s = draw_n(brew_state(), 3)
    s = step(s, RS, {"p1": STOP, "p2": DRAW}, ScriptedChance(["white_1"])).state
    assert s.players["p1"].status is Status.STOPPED
    s = step(s, RS, {"p1": WAIT, "p2": DRAW}, ScriptedChance(["white_1"])).state
    assert len(s.players["p2"].placed) == 5 and s.phase is Phase.RESTART
    assert legal_actions(s, RS, "p1") == [WAIT]
    assert not s.players["p1"].restart_pending


def test_a_player_who_stops_on_the_5th_chip_bag_empty_gets_no_choice():
    s = brew_state()
    for p in s.players.values():
        p.bag = {"white_1": 5}
    s = draw_n(s, 5)
    assert s.phase is Phase.RESOLVE


def test_no_restart_in_other_cards():
    s = after_draw("card_8_to_12")
    for p in s.players.values():
        p.bag = {"white_1": 30}
    s = draw_n(s, 5)
    assert s.phase is Phase.BREW


def test_round_end_effects_see_only_the_chips_placed_after_the_restart():
    s = brew_state()
    for p in s.players.values():
        p.bag = {"white_1": 30}
        p.placed = ["green_1"] * 4
        p.placed_fields = [1, 2, 3, 4]
        p.field = 4
    s = draw_n(s, 1)  # the 5th chip, a white_1
    assert s.phase is Phase.RESTART
    s = step(s, RS, {"p1": RESTART, "p2": CONTINUE}, ScriptedChance([])).state
    s = step(s, RS, {"p1": DRAW, "p2": STOP}, ScriptedChance(["white_1"])).state
    s = step(s, RS, {"p1": STOP, "p2": WAIT}, ScriptedChance([])).state
    assert s.phase is Phase.RESOLVE
    out = step(s, RS, None, ScriptedChance([f.id for f in RS.die] * 2))
    bonus = {e["seat"] for e in out.events if e["kind"] == "round_end_bonus"}
    assert bonus == {"p2"}  # p2 kept its green chips; p1's pot holds one white chip only
    assert out.state.players["p1"].placed == ["white_1"]


def test_the_restart_flags_are_reset_in_the_next_round():
    s = draw_n(brew_state(), 5)
    s = step(s, RS, both(RESTART), ScriptedChance([])).state
    assert all(p.restart_offered for p in s.players.values())
    s.phase = Phase.SHOP
    for p in s.players.values():
        p.status, p.final_field = Status.STOPPED, 1
    s = step(s, RS, both(DONE), ScriptedChance([])).state
    assert not any(p.restart_offered or p.restart_pending for p in s.players.values())


def test_state_with_the_new_fields_round_trips():
    s = draw_n(brew_state(), 5)
    assert state_from_dict(copy.deepcopy(state_to_dict(s))) == s
    s2 = choose("card_5", "card_drop_end", "card_black").state
    assert state_from_dict(copy.deepcopy(state_to_dict(s2))) == s2


# --- record, replay, seed check ---------------------------------------------------------


class CardBot:
    """Draws to 5 chips and restarts once offered; takes the last option of a card choice."""

    kind = "bot"
    name = "card-bot"
    params: dict = {}

    def choose(self, state, seat, legal):
        if state.phase is Phase.CARD_CHOICE:
            return legal[-1]
        if state.phase is Phase.RESTART:
            return RESTART
        if state.phase is Phase.SHOP:
            return DONE
        if state.phase is not Phase.BREW:
            return legal[0]
        p = state.players[seat]
        return STOP if len(p.placed) >= 5 and STOP in legal else DRAW


def record(seed):
    header = HeaderLine(
        game_id=f"g-v1.11-b-{seed}",
        schema_version=1,
        rules_version="v1.11",
        rounds=RS.rounds,
        seed=seed,
        mode="sim",
        seats={s: SeatInfo(kind="bot", name="card-bot") for s in SEATS},
        ui={},
        engine_version="0.1.0",
        started_at="2026-10-20T12:00:00+02:00",
    )
    stream = io.StringIO()
    rec = GameRecorder(stream, header)
    final = play_game(RS, {s: CardBot() for s in SEATS}, RngChance(seed), rec.on_step)
    rec.close(final)
    return stream.getvalue(), final


def find_game():
    for seed in range(400):
        text, final = record(seed)
        path = io.StringIO(text)
        lines = [json.loads(x) for x in path.read().splitlines()]
        events = [e for line in lines for e in line.get("events", [])]
        kinds = {e["kind"] for e in events}
        cards = {e["card"] for e in events if e["kind"] == "card_draw"}
        if "restart" in kinds and {"card_2", "card_5", "card_6"} <= cards:
            return seed, text, final
    raise AssertionError("no seed in range uses cards 2, 5 and 6 with a restart")


def test_a_game_with_cards_2_5_and_6_records_replays_and_passes_the_seed_check(tmp_path):
    seed, text, final = find_game()
    path = tmp_path / "game.jsonl"
    path.write_text(text, encoding="utf-8")
    (game,) = read_games(path)
    assert verify_game(game) == [] and verify_seed(game) == []
    kinds = {e["kind"] for s in game.steps for e in s.events}
    assert {"restart", "card_choice"} <= kinds
    result = CliRunner().invoke(app, ["verify", str(path), "--seed-check"])
    assert result.exit_code == 0, result.output
    assert "1 games ok" in result.output
    assert final.phase is Phase.GAME_OVER
