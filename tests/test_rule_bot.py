"""RuleBot: three shop strategies with a seeded pseudo-policy (ruleset v2.3)."""

from collections import Counter

import pytest
from helpers import RS

from quack_rl.bots import HeuristicBot
from quack_rl.bots import rule_bot as rule_bot_module
from quack_rl.bots.rule_bot import (
    DEFAULT_TEMPERATURE,
    RuleBot,
    bot_name,
    parse_bot_name,
    shop_probabilities,
)
from quack_rl.bots.strategy import STRATEGIES
from quack_rl.engine import BUY_PREFIX, DONE, Phase, RngChance, legal_actions, new_game
from quack_rl.runner import play_game

NAMES = ("topchip", "spendmost", "blackpurple")
PRICE = {i.id: i.price for i in RS.shop}
COLOUR = {i.id: RS.chip(i.chip).colour for i in RS.shop}


def shop_state(rnd=1, money=20, black=0):
    state = new_game(RS)
    state.phase, state.round = Phase.SHOP, rnd
    p = state.players["p1"]
    p.money = money
    p.bag = {k: v for k, v in p.bag.items() if k != "black_1"}
    if black:
        p.bag["black_1"] = black
    return state


def choose(strategy, state, temperature=0.0, seed=0):
    bot = RuleBot(RS, strategy, 20, 4, seed=seed, temperature=temperature)
    legal = legal_actions(state, RS, "p1")
    action = bot.choose(state, "p1", legal)
    assert action in legal
    return action


def bought(state, action):
    """The state after p1 buys the item of `action` (as the engine books it)."""
    item = action.removeprefix(BUY_PREFIX)
    p = state.players["p1"]
    p.money -= PRICE[item]
    p.chip_purchases += 1
    p.chip_colours.append(COLOUR[item])
    p.bag[item] = p.bag.get(item, 0) + 1
    return state


# --- the strategies at temperature 0 ---------------------------------------------------------


def test_names_colours_and_interface():
    assert set(STRATEGIES) == set(NAMES)
    assert {n: s.colour for n, s in STRATEGIES.items()} == {
        "topchip": "blue",
        "spendmost": "blue",
        "blackpurple": "red",
    }
    bot = RuleBot(RS, "spendmost", 30, 5, seed=3, temperature=0.4)
    assert bot.kind == "bot"
    assert bot.name == "spendmost-draw30-pts5"
    assert bot.params == {
        "strategy": "spendmost",
        "draw_limit": 30,
        "points_round": 5,
        "seed": 3,
        "temperature": 0.4,
    }


def test_topchip_buys_the_most_expensive_then_done():
    state = shop_state(rnd=1, money=20)
    action = choose("topchip", state)
    assert action == "buy:blue_4"
    state = bought(state, action)
    assert state.players["p1"].money == 1
    assert choose("topchip", state) == DONE


def test_spendmost_starts_the_best_pair():
    state = shop_state(rnd=2, money=20)
    action = choose("spendmost", state)
    item = action.removeprefix(BUY_PREFIX)
    legal = legal_actions(state, RS, "p1")
    partners = [
        a.removeprefix(BUY_PREFIX)
        for a in legal
        if a.startswith(BUY_PREFIX)
        and COLOUR[a.removeprefix(BUY_PREFIX)] != COLOUR[item]
        and PRICE[item] + PRICE[a.removeprefix(BUY_PREFIX)] == 20
    ]
    assert partners, action
    # The partner is still legal after the first buy.
    after = legal_actions(bought(state, action), RS, "p1")
    assert any(f"{BUY_PREFIX}{p}" in after for p in partners)


def test_spendmost_takes_the_only_affordable_buy():
    state = shop_state(rnd=2, money=3)
    assert legal_actions(state, RS, "p1") == [DONE, "buy:orange_1"]
    assert choose("spendmost", state) == "buy:orange_1"


def test_blackpurple_rounds():
    for rnd in (1, 2, 3):
        for black in (0, 1):
            assert choose("blackpurple", shop_state(rnd, 20, black)) == "buy:black_1", (rnd, black)
    assert choose("blackpurple", shop_state(2, 20, 2)) != "buy:black_1"
    for rnd in (5, 6, 7):
        assert choose("blackpurple", shop_state(rnd, 20)) == "buy:purple_1", rnd
    assert choose("blackpurple", shop_state(4, 6)) == "buy:red_1"


@pytest.mark.parametrize("strategy", NAMES)
def test_only_done_legal_gives_done(strategy):
    state = shop_state(rnd=1, money=0)
    assert legal_actions(state, RS, "p1") == [DONE]
    for t in (0.0, DEFAULT_TEMPERATURE):
        assert choose(strategy, state, temperature=t) == DONE


# --- the pseudo-policy -----------------------------------------------------------------------


@pytest.mark.parametrize("strategy", NAMES)
@pytest.mark.parametrize("temperature", [0.0, DEFAULT_TEMPERATURE])
def test_probabilities_sum_to_one_over_legal(strategy, temperature):
    for rnd, money in ((1, 20), (2, 20), (4, 6), (6, 30), (1, 0)):
        state = shop_state(rnd, money)
        legal = legal_actions(state, RS, "p1")
        bot = RuleBot(RS, strategy, 20, 4, temperature=temperature)
        probs = shop_probabilities(bot, state, "p1", legal)
        assert set(probs) <= set(legal)
        assert abs(sum(probs.values()) - 1) <= 1e-9


def test_negative_temperature_is_rejected():
    with pytest.raises(ValueError):
        RuleBot(RS, "topchip", 20, 4, temperature=-1)


def test_same_seed_same_shop_actions():
    for strategy in NAMES:
        a = RuleBot(RS, strategy, 20, 4, seed=5)
        b = RuleBot(RS, strategy, 20, 4, seed=5)
        for rnd, money in ((1, 20), (2, 20), (3, 15), (5, 25), (6, 12)) * 10:
            state = shop_state(rnd, money)
            legal = legal_actions(state, RS, "p1")
            assert a.choose(state, "p1", legal) == b.choose(state, "p1", legal)


def test_default_temperature_band_and_docstring():
    doc = rule_bot_module.__doc__
    assert "DEFAULT_TEMPERATURE" in doc
    assert f"{DEFAULT_TEMPERATURE}" in doc
    state = shop_state(rnd=1, money=20)
    legal = legal_actions(state, RS, "p1")
    for strategy in NAMES:
        probs = shop_probabilities(RuleBot(RS, strategy, 20, 4), state, "p1", legal)
        top = max(probs, key=probs.get)
        assert top == choose(strategy, state)  # the temperature 0 choice
        assert 0.6 <= probs[top] <= 0.9, (strategy, probs[top])
        assert f"`{top}`" in doc and f"{probs[top]:.2f}" in doc, (strategy, top)


def test_topchip_samples_the_top_buy_most_often():
    state = shop_state(rnd=1, money=20)
    legal = legal_actions(state, RS, "p1")
    counts = Counter(
        RuleBot(RS, "topchip", 20, 4, seed=s).choose(state, "p1", legal) for s in range(200)
    )
    assert counts["buy:blue_4"] > 100
    assert sum(n for a, n in counts.items() if a != "buy:blue_4") >= 1


# --- whole games -----------------------------------------------------------------------------


class Recorder:
    """Wraps a bot and records the chip colours it buys in each round."""

    def __init__(self, bot):
        self.bot = bot
        self.kind, self.name, self.params = bot.kind, bot.name, bot.params
        self.colours: dict[int, list[str]] = {}

    def choose(self, state, seat, legal):
        action = self.bot.choose(state, seat, legal)
        assert action in legal
        if state.phase is Phase.SHOP and action.startswith(BUY_PREFIX):
            item = action.removeprefix(BUY_PREFIX)
            self.colours.setdefault(state.round, []).append(COLOUR[item])
        return action


@pytest.mark.slow
def test_no_two_chips_of_one_colour_in_a_round():
    pairs = [(a, b) for a in NAMES for b in NAMES]
    buys = 0
    for seed in range(200):
        s1, s2 = pairs[seed % len(pairs)]
        seats = {
            "p1": Recorder(RuleBot(RS, s1, 20, 4, seed=seed)),
            "p2": Recorder(RuleBot(RS, s2, 25, 3, seed=seed + 1000)),
        }
        play_game(RS, seats, RngChance(seed))
        for rec in seats.values():
            for rnd, colours in rec.colours.items():
                buys += len(colours)
                assert len(colours) == len(set(colours)), (seed, rnd, colours)
                assert len(colours) <= 2
    assert buys > 0


class Compare:
    """Wraps a RuleBot; at every non-shop decision a HeuristicBot must choose the same."""

    def __init__(self, bot, reference):
        self.bot, self.reference = bot, reference
        self.kind, self.name, self.params = bot.kind, bot.name, bot.params
        self.checked = 0

    def choose(self, state, seat, legal):
        action = self.bot.choose(state, seat, legal)
        if state.phase is not Phase.SHOP:
            assert self.reference.choose(state, seat, list(legal)) == action, (
                state.phase,
                state.card,
                legal,
            )
            self.checked += 1
        return action


@pytest.mark.parametrize(("draw", "pts"), [(20, 4), (0, 6)])
def test_non_shop_decisions_match_the_heuristic_bot(draw, pts):
    checked = 0
    for seed in range(50):
        names = (("topchip", "spendmost"), ("spendmost", "blackpurple"), ("blackpurple", "topchip"))
        s1, s2 = names[seed % 3]
        seats = {}
        for seat, strategy, offset in (("p1", s1, 0), ("p2", s2, 500)):
            bot = RuleBot(RS, strategy, draw, pts, seed=seed + offset)
            if strategy in ("topchip", "spendmost"):
                seats[seat] = Compare(bot, HeuristicBot(RS, draw, pts, "points"))
            else:
                seats[seat] = bot
        play_game(RS, seats, RngChance(seed))
        checked += sum(s.checked for s in seats.values() if isinstance(s, Compare))
    assert checked > 0


def test_blackpurple_card_12_swaps_for_red_1():
    assert STRATEGIES["blackpurple"].colour == "red"
    state = new_game(RS)
    state.phase, state.card = Phase.CARD_CHOICE, "card_12"
    legal = legal_actions(state, RS, "p1")
    assert "card_swap:red_1" in legal
    assert RuleBot(RS, "blackpurple", 20, 4).choose(state, "p1", legal) == "card_swap:red_1"


# --- names -----------------------------------------------------------------------------------


@pytest.mark.parametrize("strategy", NAMES)
def test_bot_name_round_trip(strategy):
    for d, p in ((0, 1), (20, 4), (100, 9)):
        assert parse_bot_name(bot_name(strategy, d, p)) == (strategy, d, p)


def test_parse_bot_name_prefix_and_errors():
    assert parse_bot_name("bot:topchip-draw20-pts4") == ("topchip", 20, 4)
    with pytest.raises(ValueError, match="<strategy>-draw<limit>-pts<round>"):
        parse_bot_name("draw20-pts1-points")
    for bad in ("topchip-draw101-pts4", "topchip-draw20-pts0", "nosuch-draw20-pts4"):
        with pytest.raises(ValueError):
            parse_bot_name(bad)
