"""Human CLI under ruleset v1.11: card of the round, card choice, restart question."""

import io

import pytest
from rich.console import Console
from test_cli_play import text_of

from quack_rl.cli.human import HumanSeat, key_map
from quack_rl.cli.render import render_board
from quack_rl.engine import (
    CONTINUE,
    DRAW,
    RESTART,
    SEATS,
    WAIT,
    Phase,
    ScriptedChance,
    Status,
    legal_actions,
    new_game,
    step,
)
from quack_rl.rules import load_ruleset
from quack_rl.runner import play_game

RS = load_ruleset("v1.11")
RS10 = load_ruleset("v1.10")
VALUE_TWO = [c.id for c in RS.chips if c.value == 2]


def seat_with(keys, label="Player 1", rs=RS):
    stream = io.StringIO()
    it = iter(keys)
    seat = HumanSeat(label, Console(file=stream, width=2000), True, rs, read_key=lambda: next(it))
    return seat, stream


def after_draw(card):
    return step(new_game(RS), RS, None, ScriptedChance([card])).state


def both(a, b=None):
    return {"p1": a, "p2": a if b is None else b}


def deck_line(state, rs=RS):
    lines = text_of(render_board(state, rs, False), 2000).splitlines()
    return [line for line in lines if "deck:" in line]


# --- board -------------------------------------------------------------------------------


def test_board_shows_the_card_and_the_deck_count():
    s = new_game(RS)
    (line,) = deck_line(s)
    assert "card: -" in line and "deck: 12 left" in line
    s = after_draw("card_3")
    (line,) = deck_line(s)
    assert "card_3" in line and RS.card("card_3").effect and "every drop +1" in line
    assert "deck: 11 left" in line


def test_board_shows_neither_in_v1_10():
    s = new_game(RS10)
    text = text_of(render_board(s, RS10, False), 2000)
    assert "card" not in text.replace("card_", "") and "deck" not in text


# --- card choice -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("card", "expected"),
    [
        (
            "card_5",
            ["card_black", *(f"card_chip:{c}" for c in VALUE_TWO), "card_drop_end"],
        ),
        ("card_6", ["card_drop_2", "card_purple"]),
    ],
)
def test_every_card_option_has_a_key_that_reaches_the_engine(card, expected):
    s = after_draw(card)
    assert s.phase is Phase.CARD_CHOICE
    legal = legal_actions(s, RS, "p1")
    assert legal == expected
    keys = key_map(legal)
    assert sorted(keys.values()) == sorted(expected)
    for key, action in keys.items():
        seat, _ = seat_with([key])
        picked = seat.choose(s, "p1", legal)
        assert picked == action
        result = step(s, RS, both(picked), ScriptedChance([]))
        assert [e["action"] for e in result.events if e["kind"] == "card_choice"] == [action] * 2


def test_card_5_lists_the_value_two_chips_from_the_ruleset():
    s = after_draw("card_5")
    seat, stream = seat_with(["1"])
    seat.choose(s, "p1", legal_actions(s, RS, "p1"))
    menu = stream.getvalue()
    assert VALUE_TWO  # the ruleset has value-2 chips
    assert len([c for c in VALUE_TWO if f"a {RS_label(c)} chip" in menu]) == len(VALUE_TWO)
    assert "a K1 chip" in menu and "drop +1.5" in menu
    s6 = after_draw("card_6")
    seat, stream = seat_with(["1"])
    seat.choose(s6, "p1", legal_actions(s6, RS, "p1"))
    assert "drop +2" in stream.getvalue() and "a P1 chip" in stream.getvalue()


def RS_label(chip_id):
    from quack_rl.cli.render import chip_text

    return chip_text(chip_id, RS).plain


def test_the_other_seat_does_not_see_the_pick_before_both_have_chosen():
    s = after_draw("card_5")
    legal = legal_actions(s, RS, "p1")
    outputs = []
    for first_key in ("1", "2", str(len(legal))):
        first, first_stream = seat_with([first_key], "Player 1")
        second, second_stream = seat_with(["1"], "Player 2")
        first.choose(s, "p1", legal)
        before = first_stream.getvalue()
        # Nothing is printed between the two choices: the pick is not echoed or announced.
        second.choose(s, "p2", legal_actions(s, RS, "p2"))
        assert first_stream.getvalue() == before
        outputs.append(second_stream.getvalue())
    # The output of the second seat is the same whatever the first seat picked.
    assert outputs[0] == outputs[1] == outputs[2]


# --- restart -----------------------------------------------------------------------------


def brew_state():
    s = after_draw("card_2")
    for p in s.players.values():
        p.bag = {"white_1": 30}
    return s


def draw_n(s, n, actions=None):
    for _ in range(n):
        s = step(s, RS, actions or both(DRAW), ScriptedChance(["white_1", "white_1"])).state
    return s


def test_restart_question_goes_to_the_deciding_seat_only():
    s = brew_state()
    s = draw_n(s, 4)
    s.players["p2"].status = Status.STOPPED
    s = step(s, RS, {"p1": DRAW, "p2": WAIT}, ScriptedChance(["white_1"])).state
    assert s.phase is Phase.RESTART
    assert legal_actions(s, RS, "p2") == [WAIT]
    legal = legal_actions(s, RS, "p1")
    assert legal == [CONTINUE, RESTART]
    keys = key_map(legal)
    assert keys == {"c": CONTINUE, "r": RESTART}
    for key, action in keys.items():
        seat, stream = seat_with([key])
        assert seat.choose(s, "p1", legal) == action
        assert "continue" in stream.getvalue() and "restart" in stream.getvalue()


def test_other_seat_is_not_asked_and_goes_on_brewing():
    s = brew_state()
    s = draw_n(s, 4)
    s.players["p2"].placed = s.players["p2"].placed[:2]
    s.players["p2"].white_total = 2
    s = step(s, RS, both(DRAW), ScriptedChance(["white_1", "white_1"])).state
    seats = {"p1": seat_with(["r"])[0], "p2": seat_with([])[0]}  # p2 has no key to give
    result = play_until_brew(s, seats)
    assert result.phase is Phase.BREW and len(result.players["p2"].placed) == 3
    assert result.players["p1"].placed == []  # p1 restarted


def play_until_brew(s, seats):
    actions = {}
    for seat in SEATS:
        legal = legal_actions(s, RS, seat)
        actions[seat] = WAIT if legal == [WAIT] else seats[seat].choose(s, seat, legal)
    return step(s, RS, actions, ScriptedChance([])).state


def test_no_question_after_explosion_on_the_5th_chip():
    s = draw_n(brew_state(), 4)
    s.players["p1"].white_total = 6
    s.players["p2"].status = Status.STOPPED
    s.players["p1"].bag["white_2"] = 1
    s = step(s, RS, {"p1": DRAW, "p2": WAIT}, ScriptedChance(["white_2"])).state
    assert s.players["p1"].status is Status.EXPLODED
    assert s.phase is not Phase.RESTART
    assert legal_actions(s, RS, "p1") != [CONTINUE, RESTART]


def test_no_second_question_in_the_same_round():
    s = draw_n(brew_state(), 5)
    assert s.phase is Phase.RESTART
    s = step(s, RS, both(RESTART), ScriptedChance([])).state
    s = draw_n(s, 5)
    assert s.phase is Phase.BREW  # five chips again, but no question this time
    assert all(len(p.placed) == 5 for p in s.players.values())
    assert legal_actions(s, RS, "p1") == [DRAW, "stop"]


# --- a full game -------------------------------------------------------------------------


class Scripted(ScriptedChance):
    """Scripted chance: the cards in a fixed order, the lowest white chip, the first die face."""

    ORDER = ["card_2", "card_5", "card_6", "card_7", "card_1", "card_3", "card_4"] + [
        "card_8_to_12"
    ] * 2

    def __init__(self):
        super().__init__([])
        self._next_card = 0

    def draw_card(self, deck):
        card = self.ORDER[self._next_card]
        self._next_card += 1
        assert card in deck
        return card

    def draw_chip(self, bag, seat):
        ids = sorted(c for c, n in bag.items() if n > 0)
        return "white_1" if "white_1" in ids else ids[0]

    def roll_die(self, faces, seat):
        return faces[0].id


class KeySeat(HumanSeat):
    """A human seat whose keys are picked from the state it was asked about."""

    def choose(self, state, seat, legal):
        self.asked = (state, legal)
        return super().choose(state, seat, legal)


def pick_key(seat):
    state, legal = seat.asked
    keys = key_map(legal)
    if CONTINUE in legal:
        return "r" if seat.label == "Player 1" else "c"
    if state.phase is Phase.CARD_CHOICE:
        return "1" if seat.label == "Player 1" else str(len(keys))
    if state.phase is Phase.SHOP:
        return "0"
    p = state.players[seat.seat_name]
    return "s" if len(p.placed) >= 5 else "d"


def test_a_scripted_game_shows_cards_choices_and_a_restart():
    stream = io.StringIO()
    console = Console(file=stream, width=2000)
    seats = {}
    for name, label in (("p1", "Player 1"), ("p2", "Player 2")):
        seat = KeySeat(label, console, True, RS, read_key=lambda n=name: pick_key(seats[n]))
        seat.seat_name = name
        seats[name] = seat
    final = play_game(RS, seats, Scripted())
    out = stream.getvalue()
    assert final.phase is Phase.GAME_OVER and final.round == RS.rounds
    assert "card_2 (restart option after 5 chips)" in out
    assert "card_5 (choice: black 1 chip" in out and "card_6 (choice: drop +2" in out
    assert "a K1 chip into the bag" in out  # card 5 choice
    assert "a P1 chip into the bag" in out and "drop +2 now" in out  # card 6 choice
    assert "[c] continue brewing" in out and "[r] restart" in out  # restart question
    assert "deck: 11 left" in out and "deck: 3 left" in out
