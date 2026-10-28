"""Round chips (v2.3): a chip every player gets into the bag at the card step of a round."""

import pytest
from pydantic import ValidationError

from quack_rl.bots import RandomBot
from quack_rl.engine import SEATS, RngChance, ScriptedChance, new_game, step
from quack_rl.engine.cards import apply_card
from quack_rl.engine.chance import ChanceLog
from quack_rl.rules import Ruleset, load_ruleset, with_rounds
from quack_rl.runner import play_game

RS = load_ruleset("v2.3")


def card_step(round_no, card="card_16", rs=RS, state=None):
    s = state if state is not None else new_game(rs)
    s.round = round_no
    out = step(s, rs, None, ScriptedChance([card]))
    return out


def white_1(state, seat):
    return state.players[seat].bag.get("white_1", 0)


def test_the_ruleset_has_the_round_6_chip():
    assert [(rc.round, rc.chip) for rc in RS.round_chips] == [(6, "white_1")]


@pytest.mark.parametrize(
    "entry",
    [{"round": 10, "chip": "white_1"}, {"round": 0, "chip": "white_1"},
     {"round": 6, "chip": "no_such_chip"}],
)  # fmt: skip
def test_a_bad_round_chip_is_refused(entry):
    with pytest.raises(ValidationError):
        Ruleset.model_validate({**RS.model_dump(), "round_chips": [entry]})


def test_no_round_chip_in_rounds_1_to_5():
    for n in range(1, 6):
        s = new_game(RS)
        before = {seat: white_1(s, seat) for seat in SEATS}
        out = card_step(n, state=s)
        assert not any(e["kind"] == "round_chip" for e in out.events)
        assert {seat: white_1(out.state, seat) for seat in SEATS} == before


def test_round_6_gives_both_seats_one_chip_before_the_card():
    s = new_game(RS)
    before = {seat: white_1(s, seat) for seat in SEATS}
    out = card_step(6, card="card_7", state=s)
    kinds = [(e["seat"], e["kind"]) for e in out.events]
    assert kinds[:3] == [("p1", "round_chip"), ("p2", "round_chip"), (None, "card_draw")]
    assert out.events[0]["chip"] == "white_1"
    for seat in SEATS:
        assert white_1(out.state, seat) == before[seat] + 1


def test_a_choice_card_still_gets_the_chips_first():
    out = card_step(6, card="card_6")
    assert [e["kind"] for e in out.events[:3]] == ["round_chip", "round_chip", "card_draw"]


def test_the_chip_stays_in_rounds_7_to_9():
    s = new_game(RS)
    s.round = 5
    base = white_1(s, "p1")
    for n in (6, 7, 8, 9):
        s.round = n
        events = []
        apply_card(s, RS, ChanceLog(ScriptedChance([s.deck[0]]), RS), events)
        assert white_1(s, "p1") == base + 1
        assert sum(e["kind"] == "round_chip" for e in events) == (2 if n == 6 else 0)


def test_a_game_gives_the_chip_once_in_round_6_only():
    results = []
    play_game(
        RS,
        {"p1": RandomBot(1), "p2": RandomBot(2)},
        RngChance(3),
        on_step=lambda r, ms: results.append(r),
    )
    chips = [(r.round, e) for r in results for e in r.events if e["kind"] == "round_chip"]
    assert [(n, e["seat"]) for n, e in chips] == [(6, "p1"), (6, "p2")]


def test_a_four_round_game_has_no_round_chip():
    rs = with_rounds(RS, 4)
    results = []
    play_game(
        rs,
        {"p1": RandomBot(1), "p2": RandomBot(2)},
        RngChance(3),
        on_step=lambda r, ms: results.append(r),
    )
    assert not any(e["kind"] == "round_chip" for r in results for e in r.events)
