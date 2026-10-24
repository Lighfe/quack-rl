"""Heuristic bots answer every action of v2.1 (issue #190). Balance is not tested."""

import random

import pytest
from helpers import RS

from quack_rl.bots import HeuristicBot, RandomBot
from quack_rl.bots.strategy import STRATEGIES, STRATEGY_COLOUR, strategy_colour
from quack_rl.engine import (
    DONE,
    DRAW,
    SEATS,
    STOP,
    WAIT,
    Phase,
    RngChance,
    legal_actions,
    needs_actions,
    new_game,
    step,
)

CARDS = [c.id for c in RS.cards]


class ForcedCard(RngChance):
    """Seeded chance that draws `card` whenever it is in the deck."""

    def __init__(self, seed, card):
        super().__init__(seed)
        self.card = card

    def draw_card(self, deck):
        return self.card if self.card in deck else super().draw_card(deck)


class Checked:
    """Wraps a bot: fails when it returns an action that is not in `legal`."""

    def __init__(self, bot):
        self.bot = bot
        self.kind, self.name, self.params = bot.kind, bot.name, bot.params
        self.seen: set[str] = set()

    def choose(self, state, seat, legal):
        action = self.bot.choose(state, seat, legal)
        assert action in legal, (state.phase, state.card, action, legal)
        self.seen.add(action)
        return action


def play_forced(card, bots, seed):
    """A whole game where `card` is drawn when it can be, from a state where the cards matter
    (p2 leads by points, both have rubies)."""
    state = new_game(RS)
    state.players["p1"].points = 4
    state.players["p2"].points = 20
    for p in state.players.values():
        p.rubies = 6
    chance = ForcedCard(seed, card)
    steps = 0
    while state.phase is not Phase.GAME_OVER:
        actions = None
        if needs_actions(state):
            actions = {}
            for seat in SEATS:
                legal = legal_actions(state, RS, seat)
                actions[seat] = WAIT if legal == [WAIT] else bots[seat].choose(state, seat, legal)
        state = step(state, RS, actions, chance).state
        steps += 1
        assert steps < 5000
    return state


@pytest.mark.parametrize("card", CARDS)
def test_every_card_heuristic_vs_heuristic(card):
    bots = {
        "p1": Checked(HeuristicBot(RS, 30, 2, "green", seed=1)),
        "p2": Checked(HeuristicBot(RS, 20, 1, "balanced", seed=2)),
    }
    play_forced(card, bots, seed=7)


@pytest.mark.parametrize("card", CARDS)
def test_every_card_heuristic_vs_random(card):
    bots = {
        "p1": Checked(HeuristicBot(RS, 25, 3, "blue", seed=3)),
        "p2": Checked(RandomBot(seed=4)),
    }
    play_forced(card, bots, seed=11)
    bots = {"p1": bots["p2"], "p2": bots["p1"]}
    play_forced(card, bots, seed=12)


def test_games_use_the_new_actions():
    seen: set[str] = set()
    for seed in range(12):
        bots = {
            "p1": Checked(HeuristicBot(RS, 10, 1, "cleaner", seed=seed)),
            "p2": Checked(HeuristicBot(RS, 10, 1, "points", seed=seed)),
        }
        play_forced("card_17", bots, seed)
        seen |= bots["p1"].seen | bots["p2"].seen
    assert "ruby_drop" in seen


# --- strategy colour ----------------------------------------------------------


def test_strategy_colour_table():
    assert STRATEGY_COLOUR == {
        "points": "blue", "blue": "blue", "balanced": "blue", "green": "green", "cleaner": "green",
    }
    assert set(STRATEGY_COLOUR) == set(STRATEGIES)
    assert strategy_colour("unknown") == "blue"


# --- hand-built states --------------------------------------------------------


def bot(strategy="points", draw=20, pts=1):
    return HeuristicBot(RS, draw, pts, strategy)


def brew_state(bag, placed, white_total, **kw):
    state = new_game(RS)
    state.phase = Phase.BREW
    p = state.players["p1"]
    p.bag, p.placed, p.white_total = dict(bag), list(placed), white_total
    p.placed_fields = list(range(1, len(placed) + 1))
    for k, v in kw.items():
        setattr(p, k, v)
    return state


def test_use_flask_when_the_white_chip_makes_the_draw_too_risky():
    # limit 7: total 5 with white_2 in the pot; white_3 explodes (8); without the chip (3) none does
    state = brew_state({"white_3": 4, "green_1": 1}, ["white_2"], 5)
    legal = [DRAW, STOP, "use_flask"]
    assert bot().choose(state, "p1", legal) == "use_flask"


def test_flask_is_not_used_when_the_draw_is_fine():
    state = brew_state({"green_1": 4}, ["white_1"], 1)
    assert bot().choose(state, "p1", [DRAW, STOP, "use_flask"]) == DRAW


def test_flask_is_not_used_when_taking_the_chip_back_does_not_help():
    # the pot holds 4 white_3 (total 12) and the bag only white_3: still too risky without one
    state = brew_state({"white_3": 4}, ["white_3"] * 4, 12)
    assert bot().choose(state, "p1", [DRAW, STOP, "use_flask"]) == STOP


def test_use_card_17_before_the_flask():
    state = brew_state({"white_3": 4, "green_1": 1}, ["white_2"], 5)
    legal = [DRAW, STOP, "use_flask", "use_card_17"]
    assert bot().choose(state, "p1", legal) == "use_card_17"
    assert bot().choose(state, "p1", [DRAW, STOP, "use_card_17"]) == "use_card_17"


def test_stop_when_risky_and_nothing_to_take_back():
    state = brew_state({"white_3": 4, "green_1": 1}, ["white_2"], 5)
    assert bot().choose(state, "p1", [DRAW, STOP]) == STOP


def shop_state(rubies, flask_full=True, rnd=1, money=0):
    state = new_game(RS)
    state.phase, state.round = Phase.SHOP, rnd
    p = state.players["p1"]
    p.rubies, p.flask_full, p.money = rubies, flask_full, money
    return state


def shop_choice(state, strategy="points"):
    return bot(strategy).choose(state, "p1", legal_actions(state, RS, "p1"))


def test_ruby_drop_while_it_can_pay():
    assert RS.ruby_cost == 2
    assert shop_choice(shop_state(3)) == "ruby_drop"
    assert shop_choice(shop_state(1)) == DONE


def test_ruby_drop_with_a_full_flask_never_refills():
    assert shop_choice(shop_state(9)) == "ruby_drop"


def test_refill_only_with_an_empty_flask_and_two_rubies_left_over():
    assert shop_choice(shop_state(4, flask_full=False)) == "refill_flask"
    assert shop_choice(shop_state(3, flask_full=False)) == "ruby_drop"


def test_rubies_are_spent_in_the_last_round_too():
    assert shop_choice(shop_state(2, rnd=RS.rounds)) == "ruby_drop"


def card_state(card, **points):
    state = new_game(RS)
    state.phase, state.card = Phase.CARD_CHOICE, card
    for seat, v in points.items():
        state.players[seat].points = v
    return state


def card_choice(state, strategy="points", seat="p1"):
    b = bot(strategy)
    legal = legal_actions(state, RS, seat)
    action = b.choose(state, seat, legal)
    assert action in legal
    return action


def test_card_5_takes_3_rubies_and_card_6_the_drop():
    assert card_choice(card_state("card_5")) == "card_rubies"
    assert card_choice(card_state("card_6")) == "card_drop_2"


def test_card_8_gives_up_the_full_allowed_amount():
    state = card_state("card_8", p1=0, p2=5)
    assert card_choice(state) == "card_tails:2"
    state = card_state("card_8", p1=0, p2=40)
    assert card_choice(state) == "card_tails:3"


def test_card_10_places_the_lowest_value_chip():
    state = card_state("card_10")
    state.players["p1"].card_draw = ["green_2", "white_3", "blue_1", "white_1"]
    assert card_choice(state) == "card_place:blue_1"  # blue_1 and white_1 tie: the first
    state.players["p1"].card_draw = ["green_2", "white_3"]
    assert card_choice(state) == "card_place:green_2"


def test_card_11_upgrades_the_strategy_colour_else_the_first():
    state = card_state("card_11")
    state.players["p1"].card_draw = ["green_1", "blue_1", "white_1"]
    assert card_choice(state, "blue") == "card_upgrade:blue_1"
    assert card_choice(state, "cleaner") == "card_upgrade:green_1"
    state.players["p1"].card_draw = ["red_1", "green_1"]
    assert card_choice(state, "blue") == "card_upgrade:red_1"


def test_card_12_swaps_for_the_strategy_colour_value_1_chip():
    assert card_choice(card_state("card_12"), "balanced") == "card_swap:blue_1"
    assert card_choice(card_state("card_12"), "green") == "card_swap:green_1"


def test_card_12_declines_without_the_colour_in_the_options():
    b = bot("green")
    state = card_state("card_12")
    assert b.choose(state, "p1", ["card_swap:red_1", "card_swap_no"]) == "card_swap_no"


def test_card_14_takes_the_points():
    assert card_choice(card_state("card_14")) == "card_points"


def test_card_19_points_from_entitlement_3_else_a_chip_of_the_colour():
    from quack_rl.engine import calculate_rat_tails

    near, far = 5, 40
    assert calculate_rat_tails({"p1": 0, "p2": near}, RS)["p1"] < 3
    assert calculate_rat_tails({"p1": 0, "p2": far}, RS)["p1"] >= 3
    assert card_choice(card_state("card_19", p1=0, p2=near), "blue") == "card_chip4:blue_4"
    assert card_choice(card_state("card_19", p1=0, p2=near), "green") == "card_chip4:green_4"
    assert card_choice(card_state("card_19", p1=0, p2=far)) == "card_tail_points"
    assert card_choice(card_state("card_19", p1=7, p2=7), "cleaner") == "card_chip4:green_4"


def test_names_and_strategies_are_unchanged():
    from quack_rl.bots import parse_bot_name

    assert sorted(STRATEGIES) == ["balanced", "blue", "cleaner", "green", "points"]
    assert parse_bot_name("bot:draw30-pts3-blue") == (30, 3, "blue")
    assert HeuristicBot(RS, 30, 3, "blue").name == "draw30-pts3-blue"


def test_random_seeds_play_to_the_end():
    rng = random.Random(0)
    for _ in range(5):
        card = rng.choice(CARDS)
        bots = {
            "p1": Checked(
                HeuristicBot(RS, rng.choice([0, 20, 60]), 1, rng.choice(list(STRATEGIES)))
            ),
            "p2": Checked(HeuristicBot(RS, 20, 2, "balanced")),
        }
        assert play_forced(card, bots, rng.randrange(1000)).phase is Phase.GAME_OVER
