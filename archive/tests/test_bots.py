"""Moved from tests/test_bots.py (#170): the bot tests that need the v1 shop.

They check bot rules for items ruleset v2 does not have (points items, `remove_white_1`,
`droplet_1`) or the v1.1 chip rule. They run on the old rulesets (`load_ruleset("v1")` ...).
Helpers (`shop_state`, `shop_legal`, `shop_state11`, `play_shop` ...) are in tests/test_bots.py
as of the commit before this move.
"""

def test_points_round_buys_biggest_points_item_first():
    bot = HeuristicBot(RS, 30, 1, "points", seed=1)
    state = shop_state(22)
    assert bot.choose(state, "p1", shop_legal(state)) == "buy:points_10"


def test_buys_next_biggest_affordable():
    bot = HeuristicBot(RS, 30, 1, "points", seed=1)
    state = shop_state(12)
    assert bot.choose(state, "p1", shop_legal(state)) == "buy:points_2"
    state = shop_state(13)
    assert bot.choose(state, "p1", shop_legal(state)) == "buy:points_5"


def test_no_points_item_before_the_points_round():
    bot = HeuristicBot(RS, 30, 3, "points", seed=1)
    state = shop_state(6, rnd=2)
    assert "buy:points_2" in shop_legal(state)
    assert bot.choose(state, "p1", shop_legal(state)) == DONE


def test_done_when_purchases_used_up():
    bot = HeuristicBot(RS, 30, 1, "points", seed=1)
    state = shop_state(22, purchases=RS.max_purchases)
    assert bot.choose(state, "p1", shop_legal(state)) == DONE


def test_spends_remaining_money_by_strategy_after_points():
    from quack_rl.bots import Strategy

    bot = HeuristicBot(RS, 30, 1, Strategy("t", ("orange_1",)), seed=1)
    state = shop_state(25)
    assert bot.choose(state, "p1", shop_legal(state)) == "buy:points_10"
    state.players["p1"].money = 3
    state.players["p1"].purchases = 1
    assert bot.choose(state, "p1", shop_legal(state)) == "buy:orange_1"


def test_equal_points_items_tie_is_seeded():
    from quack_rl.engine import legal_actions
    from quack_rl.rules.model import ShopItem

    twin = ShopItem(id="points_10b", price=22, kind="points", points=10)
    rs2 = RS.model_copy(update={"shop": [*RS.shop, twin]})
    state = new_game(rs2)
    state.phase = Phase.SHOP
    state.round = 1
    state.players["p1"].money = 22

    def picks(seed):
        bot = HeuristicBot(rs2, 30, 1, "points", seed=seed)
        return [bot.choose(state, "p1", legal_actions(state, rs2, "p1")) for _ in range(12)]

    assert picks(1) == picks(1)
    assert set(picks(1) + picks(2) + picks(3)) == {"buy:points_10", "buy:points_10b"}


def test_blue_buys_blue_only(batches):
    bought = set(flat(batches["blue"]))
    assert bought & BLUE
    assert not bought & (GREEN | {"droplet_1", "remove_white_1"})


def test_green_buys_green_and_droplets(batches):
    bought = set(flat(batches["green"]))
    assert bought & GREEN
    assert "droplet_1" in bought
    assert not bought & BLUE


def test_cleaner_removes_white_most_and_no_droplet(batches):
    count = {s: flat(g).count("remove_white_1") for s, g in batches.items()}
    assert count["cleaner"] >= 1
    assert "droplet_1" not in flat(batches["cleaner"])
    for other in ("blue", "green", "balanced"):
        assert count["cleaner"] > count[other]


def test_balanced_buys_a_bit_of_everything(batches):
    bought = set(flat(batches["balanced"]))
    assert {"orange_1", "remove_white_1", "droplet_1"} <= bought
    assert bought & BLUE
    assert bought & GREEN


def test_v1_1_points_round_buys_points_then_done():
    bot = HeuristicBot(RS11, 20, 1, "points", seed=1)
    state = shop_state11(30, rnd=1)
    assert play_shop(bot, state) == ["buy:points_10", "buy:points_2", DONE]
    assert state.players["p1"].money == 2


def test_v1_1_points_round_buys_no_chips_after_points():
    bot = HeuristicBot(RS11, 20, 1, "cleaner", seed=1)
    state = shop_state11(12, rnd=1)
    assert "buy:orange_1" in legal11(state)
    assert bot.choose(state, "p1", legal11(state)) == "buy:points_2"
    apply11(state, "buy:points_2")
    assert state.players["p1"].money == 5
    assert "buy:orange_1" in legal11(state)
    assert bot.choose(state, "p1", legal11(state)) == DONE


def test_v1_1_points_round_has_no_cap_of_three():
    bot = HeuristicBot(RS11, 20, 1, "points", seed=1)
    state = shop_state11(70, rnd=1)
    assert play_shop(bot, state) == ["buy:points_10"] * 3 + ["buy:points_2", DONE]
    assert state.players["p1"].money == 0


def test_v1_1_before_points_round_fallback_most_expensive_non_points():
    bot = HeuristicBot(RS11, 20, 4, "blue", seed=1)
    state = shop_state11(20, rnd=2)
    apply11(state, "buy:blue_4")
    assert state.players["p1"].money == 5
    legal = legal11(state)
    assert "buy:blue_1" not in legal
    assert bot.choose(state, "p1", legal) == "buy:green_1"
    apply11(state, "buy:green_1")
    assert bot.choose(state, "p1", legal11(state)) == DONE


def test_v1_1_fallback_includes_remove_white_and_repeats():
    bot = HeuristicBot(RS11, 20, 4, "blue", seed=1)
    state = shop_state11(40, rnd=2)
    assert play_shop(bot, state) == [
        "buy:blue_4",
        "buy:remove_white_1",
        "buy:green_2",
        DONE,
    ]
    assert state.players["p1"].money == 2


@pytest.mark.parametrize("money", range(7, 14))
def test_v1_1_fallback_never_buys_points(money):
    bot = HeuristicBot(RS11, 20, 4, "blue", seed=1)
    state = shop_state11(100, rnd=2)
    apply11(state, "buy:blue_4")
    apply11(state, "buy:green_4")
    state.players["p1"].money = money
    legal = legal11(state)
    assert "buy:points_2" in legal
    assert bot.choose(state, "p1", legal) == DONE


@pytest.mark.parametrize(
    "changes,money,expected",
    [
        # remove_white_1 at 13 ties green_4 (13): green_4 comes first in the shop
        ({"remove_white_1": 13}, 13, "buy:green_4"),
        # blue_2 at 9 ties green_2 (9): blue_2 comes first in the shop
        ({"blue_2": 9}, 9, "buy:blue_2"),
    ],
)
def test_v1_1_fallback_tie_takes_the_first_in_shop_order(changes, money, expected):
    from quack_rl.bots import Strategy

    shop = [i.model_copy(update={"price": changes.get(i.id, i.price)}) for i in RS11.shop]
    rs = RS11.model_copy(update={"shop": shop})
    state = shop_state11(money, rnd=2, rs=rs)
    legal = legal11(state, rs)
    tied = [i for i in rs.shop if i.kind != "points" and i.price == money]
    assert len(tied) == 2 and all(f"buy:{i.id}" in legal for i in tied)
    bot = HeuristicBot(rs, 20, 4, Strategy("t"), seed=1)
    assert bot.choose(state, "p1", legal) == expected
