import io

import pytest
from helpers import RS, brew_start
from rich.console import Console

from quack_rl.cli import human
from quack_rl.cli.human import HumanSeat
from quack_rl.engine import DONE, RUBY_DROP, Phase, buy
from quack_rl.labels import action_label

RUBY_DROP_LABEL = "ruby drop: 2 rubies, droplet +1"
BUY_ORANGE_LABEL = "buy orange_1 (3)"


def shop_state():
    """p1 in the shop with money for an orange 1 and rubies for a ruby drop."""
    state = brew_start()
    state.phase = Phase.SHOP
    p1 = state.players["p1"]
    p1.money = 3
    p1.rubies = 2
    return state


def test_labels_of_ruby_drop_and_buy():
    assert action_label(RUBY_DROP, RS) == RUBY_DROP_LABEL
    assert action_label(buy("orange_1"), RS) == BUY_ORANGE_LABEL


def test_cli_menu_uses_action_label():
    state = shop_state()
    stream = io.StringIO()
    seat = HumanSeat("Player 1", Console(file=stream, width=2000), True, RS, read_key=lambda: "0")
    legal = [DONE, buy("orange_1"), RUBY_DROP]
    assert seat.choose(state, "p1", legal) == DONE
    out = stream.getvalue()
    assert RUBY_DROP_LABEL in out
    assert BUY_ORANGE_LABEL in out


def test_describe_is_removed_from_the_human_seat():
    assert not hasattr(HumanSeat, "_describe")
    assert human.action_label is action_label


def test_service_view_labels_equal_the_cli_labels():
    pytest.importorskip("fastapi")
    from quack_rl.web.session import GameSession
    from quack_rl.web.view import seat_view

    session = GameSession.create(RS, {"p1": "human", "p2": "human"}, seed=1)
    session.state = shop_state()
    labels = {a["id"]: a["label"] for a in seat_view(session, "p1")["legal"]}
    assert labels[buy("orange_1")] == BUY_ORANGE_LABEL
    assert list(labels) == [DONE, *(buy(i.id) for i in RS.shop if i.price <= 3)]
    # the ruby drop is offered in the ruby step after the shop
    session.state.phase = Phase.RUBY
    session.state.players["p1"].shop_done = True
    labels = {a["id"]: a["label"] for a in seat_view(session, "p1")["legal"]}
    assert labels == {DONE: action_label(DONE, RS), RUBY_DROP: RUBY_DROP_LABEL}


@pytest.mark.parametrize(
    "action",
    [
        "use_flask", "use_card_17", "ruby_drop", "refill_flask", "card_tails:2", "card_tails:0",
        "card_place:blue_2", "card_upgrade:green_1", "card_swap:green_1", "card_swap_no",
        "card_points", "card_remove_white", "card_chip4:red_4", "card_tail_points",
    ],
)
def test_label_of_new_actions_is_short_text(action):
    text = action_label(action, RS)
    assert text != action and 0 < len(text) <= 45
