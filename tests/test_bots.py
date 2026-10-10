import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from quack_rl.bots import (
    BASELINE_NAME,
    HeuristicBot,
    UnknownStrategy,
    explosion_chance,
    load_strategy,
    parse_bot_name,
)
from quack_rl.cli.main import app
from quack_rl.engine import DONE, DRAW, STOP, GameState, Phase, new_game
from quack_rl.rules import load_ruleset

RS = load_ruleset("v1")
runner = CliRunner()


def brew_state(bag, white_total, placed=("white_1",)):
    state = new_game(RS)
    p = state.players["p1"]
    p.bag = dict(bag)
    p.white_total = white_total
    p.placed = list(placed)
    return state


def shop_state(money, rnd=1, purchases=0):
    state = new_game(RS)
    state.phase = Phase.SHOP
    state.round = rnd
    state.players["p1"].money = money
    state.players["p1"].purchases = purchases
    return state


def shop_legal(state):
    from quack_rl.engine import legal_actions

    return legal_actions(state, RS, "p1")


# --- explosion chance ---------------------------------------------------------


def test_chance_zero_when_nothing_explodes():
    assert explosion_chance({"white_1": 3, "blue_1": 2}, 0, RS) == 0


def test_chance_one_when_every_chip_explodes():
    assert explosion_chance({"white_1": 2, "white_3": 3}, 7, RS) == 1


def test_chance_mixed_bag_is_a_fraction():
    # white total 5, limit 7: white_3 explodes (8), white_2 does not (7)
    assert explosion_chance({"white_3": 2, "white_2": 1, "blue_4": 2}, 5, RS) == pytest.approx(0.4)


def test_chance_empty_bag_is_zero():
    assert explosion_chance({}, 3, RS) == 0


# --- draw rule ----------------------------------------------------------------

# bag of 5 chips, white total 5: two white_3 explode, so the chance is 0.4
BAG = {"white_3": 2, "white_1": 3}


@pytest.mark.parametrize(
    "limit,expected", [(50, DRAW), (40, DRAW), (39, STOP), (30, STOP), (0, STOP), (100, DRAW)]
)
def test_draw_rule_below_equal_above_limit(limit, expected):
    bot = HeuristicBot(RS, limit, 1, "points", seed=1)
    assert bot.choose(brew_state(BAG, 5), "p1", [DRAW, STOP]) == expected


def test_draw_when_stop_not_legal():
    bot = HeuristicBot(RS, 0, 1, "points", seed=1)
    state = brew_state(BAG, 5, placed=())
    assert bot.choose(state, "p1", [DRAW]) == DRAW


# --- shop rule ----------------------------------------------------------------


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


def test_strategy_priority_before_points_round():
    from quack_rl.bots import Strategy

    bot = HeuristicBot(RS, 30, 5, Strategy("t", ("blue_1", "green_1")), seed=1)
    state = shop_state(10, rnd=1)
    assert bot.choose(state, "p1", shop_legal(state)) == "buy:blue_1"


def test_done_when_nothing_affordable():
    bot = HeuristicBot(RS, 30, 1, "points", seed=1)
    state = shop_state(2)
    assert bot.choose(state, "p1", shop_legal(state)) == DONE


def test_done_when_purchases_used_up():
    bot = HeuristicBot(RS, 30, 1, "points", seed=1)
    state = shop_state(22, purchases=RS.max_purchases)
    assert bot.choose(state, "p1", shop_legal(state)) == DONE


def test_bot_returns_only_legal_actions():
    bot = HeuristicBot(RS, 30, 1, "points", seed=1)
    for money in range(0, 40):
        state = shop_state(money)
        legal = shop_legal(state)
        assert bot.choose(state, "p1", legal) in legal


# --- strategies and names -----------------------------------------------------


def test_load_strategy_points():
    assert load_strategy("points").priority == ()


def test_unknown_strategy_names_it():
    with pytest.raises(UnknownStrategy, match="nosuch"):
        load_strategy("nosuch")


def test_baseline_name_and_params():
    bot = HeuristicBot(RS)
    assert bot.name == BASELINE_NAME == "draw30-pts1-points"
    assert bot.params["draw_limit"] == 30
    assert bot.params["points_round"] == 1
    assert bot.params["strategy"] == "points"


def test_parse_bot_name():
    assert parse_bot_name("draw30-pts1-points") == (30, 1, "points")
    for bad in ("draw30", "draw30-pts3-nosuch", "drawx-pts3-points", "draw30-pts0-points"):
        with pytest.raises(ValueError):
            parse_bot_name(bad)


# --- CLI ----------------------------------------------------------------------


def sim(out, p1, p2, seed="4", games="4"):
    return runner.invoke(
        app,
        ["simulate", "--p1", p1, "--p2", p2, "--games", games, "--seed", seed, "--out", str(out)],
    )


def records(out: Path):
    lines = []
    for shard in sorted(out.glob("**/shard-*.jsonl")):
        lines += [json.loads(x) for x in shard.read_text().splitlines()]
    return lines


@pytest.mark.parametrize("spec", ["bot:draw30", "bot:draw30-pts3-nosuch", "bot:drawx-pts3-points"])
def test_bad_bot_spec_fails_clean(tmp_path, spec):
    result = sim(tmp_path, spec, "bot:random")
    assert result.exit_code != 0
    assert "Traceback" not in result.output
    assert spec in result.output
    assert result.exception is None or isinstance(result.exception, SystemExit)


def test_bad_bot_spec_in_play(tmp_path):
    result = runner.invoke(
        app, ["play", "--p1", "bot:draw30", "--p2", "bot:random", "--out", str(tmp_path)]
    )
    assert result.exit_code != 0
    assert "bot:draw30" in result.output
    assert "Traceback" not in result.output


def test_simulate_same_seed_same_records(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    for out in (a, b):
        r = sim(out, "bot:draw30-pts1-points", "bot:draw50-pts3-points")
        assert r.exit_code == 0, r.output

    def strip(lines):
        return [
            {k: v for k, v in line.items() if k not in ("game_id", "started_at", "finished_at")}
            for line in lines
        ]

    assert strip(records(a)) == strip(records(b))


def test_header_has_bot_params(tmp_path):
    r = sim(tmp_path, "bot:draw30-pts1-points", "bot:draw50-pts3-points", games="1")
    assert r.exit_code == 0, r.output
    header = records(tmp_path)[0]
    p1 = header["seats"]["p1"]
    assert p1["name"] == "draw30-pts1-points"
    assert p1["params"]["draw_limit"] == 30
    assert p1["params"]["points_round"] == 1
    assert p1["params"]["strategy"] == "points"
    assert header["seats"]["p2"]["params"]["draw_limit"] == 50


def test_verify_passes_on_bot_game(tmp_path):
    r = sim(tmp_path, "bot:draw30-pts1-points", "bot:draw50-pts1-points", games="3")
    assert r.exit_code == 0, r.output
    (shard,) = tmp_path.glob("**/shard-0001.jsonl")
    v = runner.invoke(app, ["verify", str(shard)])
    assert v.exit_code == 0, v.output
    assert "3 games ok" in v.output


# --- strategy weights, seeded ties, spending after points -------------------------


def test_strategy_weights_rank_before_priority_order():
    from quack_rl.bots import Strategy

    s = Strategy("t", ("orange_1", "blue_1", "green_1"), (("green_1", 2.0), ("blue_1", 1.0)))
    assert s.ranked() == ["green_1", "blue_1", "orange_1"]
    assert Strategy("u", ("orange_1", "blue_1")).ranked() == ["orange_1", "blue_1"]


def test_weights_change_what_the_bot_buys():
    from quack_rl.bots import Strategy

    s = Strategy("t", ("orange_1", "green_1"), (("green_1", 1.0),))
    bot = HeuristicBot(RS, 30, 5, s, seed=1)
    state = shop_state(10, rnd=1)
    assert bot.choose(state, "p1", shop_legal(state)) == "buy:green_1"


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


def test_simulate_same_seed_only_ids_and_times_differ(tmp_path):
    # game_id is random and the times are clock values, by design (verify --game selects
    # by id). Everything else must be identical, including the full step lines.
    a, b = tmp_path / "a", tmp_path / "b"
    for out in (a, b):
        r = sim(out, "bot:draw30-pts1-points", "bot:draw50-pts3-points")
        assert r.exit_code == 0, r.output
    ra, rb = records(a), records(b)
    assert len(ra) == len(rb) > 1
    assert ra[0]["game_id"] != rb[0]["game_id"]
    for x, y in zip(ra, rb):
        for key in ("game_id", "started_at", "finished_at"):
            x.pop(key, None)
            y.pop(key, None)
        assert x == y


# --- the four shop strategies -----------------------------------------------------

from quack_rl.bots import STRATEGIES  # noqa: E402

BLUE = {"blue_1", "blue_2", "blue_4"}
GREEN = {"green_1", "green_2", "green_4"}


def test_strategies_registry_keys_and_names():
    assert set(STRATEGIES) == {"points", "blue", "green", "cleaner", "balanced"}
    for key, s in STRATEGIES.items():
        assert s.name == key
        assert load_strategy(key) is s


def test_blue_strategy_data():
    s = load_strategy("blue")
    assert set(s.priority) == BLUE
    assert s.ranked()[0] == "blue_4"


def test_green_strategy_data():
    s = load_strategy("green")
    assert set(s.priority) == GREEN | {"droplet_1"}
    assert set(s.ranked()) == GREEN | {"droplet_1"}


def test_cleaner_strategy_data():
    s = load_strategy("cleaner")
    assert s.ranked()[0] == "remove_white_1"
    assert len(set(s.priority) - {"remove_white_1"}) >= 1
    assert "droplet_1" not in s.priority


def test_balanced_strategy_data():
    p = set(load_strategy("balanced").priority)
    assert "orange_1" in p and "remove_white_1" in p and "droplet_1" in p
    assert p & BLUE and p & GREEN


def test_only_points_strategy_lists_points_items():
    for key, s in STRATEGIES.items():
        if key != "points":
            assert not any(i.startswith("points_") for i in s.priority)


@pytest.mark.parametrize("draw", [15, 30, 50])
@pytest.mark.parametrize("pts", [3, 8])
@pytest.mark.parametrize("strategy", ["points", "blue", "green", "cleaner", "balanced"])
def test_all_bot_specs_are_accepted(draw, pts, strategy):
    name = f"draw{draw}-pts{pts}-{strategy}"
    assert parse_bot_name(name) == (draw, pts, strategy)
    assert HeuristicBot(RS, draw, pts, strategy).name == name
    assert parse_bot_name(f"bot:{name}") == (draw, pts, strategy)


def test_unknown_strategy_lists_known_ones():
    with pytest.raises(UnknownStrategy) as e:
        parse_bot_name("draw30-pts3-nosuch")
    for key in STRATEGIES:
        assert key in str(e.value)
    with pytest.raises(UnknownStrategy) as e:
        parse_bot_name("bot:draw30-pts3-nosuch")
    for key in STRATEGIES:
        assert key in str(e.value)


def test_all_24_specs_run_as_seats(tmp_path):
    for draw in (15, 30, 50):
        for pts in (3, 8):
            for strategy in ("blue", "green", "cleaner", "balanced"):
                spec = f"bot:draw{draw}-pts{pts}-{strategy}"
                r = sim(tmp_path / spec.replace(":", "_"), spec, "bot:random", games="1")
                assert r.exit_code == 0, r.output
                header = records(tmp_path / spec.replace(":", "_"))[0]
                assert f"bot:{header['seats']['p1']['name']}" == spec


def purchases(out: Path) -> list[list[str]]:
    """Per game, the bought item ids of both seats."""
    games: dict[str, list[str]] = {}
    for line in records(out):
        if line.get("type") != "step":
            continue
        bought = [e["item"] for e in line["events"] if e["kind"] == "buy"]
        games.setdefault(line["game_id"], []).extend(bought)
    return list(games.values())


@pytest.fixture(scope="module")
def batches(tmp_path_factory):
    out = {}
    for strategy in ("blue", "green", "cleaner", "balanced"):
        d = tmp_path_factory.mktemp(strategy)
        spec = f"bot:draw30-pts8-{strategy}"
        r = sim(d, spec, spec, seed="7", games="30")
        assert r.exit_code == 0, r.output
        out[strategy] = purchases(d)
        assert len(out[strategy]) == 30
    return out


def flat(games):
    return [i for g in games for i in g]


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


@pytest.mark.parametrize("strategy", ["blue", "green", "cleaner", "balanced"])
def test_strategy_games_verify(tmp_path, strategy):
    r = sim(tmp_path, f"bot:draw30-pts3-{strategy}", "bot:random", games="3")
    assert r.exit_code == 0, r.output
    (shard,) = tmp_path.glob("**/shard-0001.jsonl")
    v = runner.invoke(app, ["verify", str(shard)])
    assert v.exit_code == 0, v.output
    assert "3 games ok" in v.output


# --- v1.1 chip rule (max_chip_purchases) --------------------------------------

RS11 = load_ruleset("v1.1")


def shop_state11(money, rnd, rs=RS11):
    state = new_game(rs)
    state.phase = Phase.SHOP
    state.round = rnd
    state.players["p1"].money = money
    return state


def legal11(state, rs=RS11):
    from quack_rl.engine import legal_actions

    return legal_actions(state, rs, "p1")


def apply11(state, action, rs=RS11):
    """Apply one shop action of p1 with the engine (p2 waits, so the round does not end)."""
    from quack_rl.engine.shop import apply_shop

    apply_shop(state, rs, {"p1": action, "p2": "wait"}, [])


def play_shop(bot, state, rs=RS11, limit=20):
    """The bot's actions until `done`, each checked against the legal list of its step."""
    actions = []
    for _ in range(limit):
        legal = legal11(state, rs)
        action = bot.choose(state, "p1", legal)
        assert action in legal, (action, legal)
        actions.append(action)
        if action == DONE:
            return actions
        apply11(state, action, rs)
    raise AssertionError(f"no done after {limit} actions: {actions}")


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


def test_v1_1_before_points_round_strategy_list_first():
    bot = HeuristicBot(RS11, 20, 4, "blue", seed=1)
    state = shop_state11(20, rnd=2)
    assert bot.choose(state, "p1", legal11(state)) == "buy:blue_4"


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


@pytest.mark.parametrize("strategy", ["green", "balanced"])
@pytest.mark.parametrize("rnd", [2, 4])
def test_v1_1_items_not_in_the_shop_are_skipped(strategy, rnd):
    assert "droplet_1" in load_strategy(strategy).priority
    for money in range(0, 41):
        bot = HeuristicBot(RS11, 20, 4, strategy, seed=1)
        actions = play_shop(bot, shop_state11(money, rnd=rnd))
        assert "buy:droplet_1" not in actions


@pytest.mark.parametrize("strategy", ["points", "blue", "green", "cleaner", "balanced"])
@pytest.mark.parametrize("rnd", [2, 4])
def test_v1_1_shop_is_legal_and_ends(strategy, rnd):
    for money in range(0, 41):
        bot = HeuristicBot(RS11, 20, 4, strategy, seed=1)
        actions = play_shop(bot, shop_state11(money, rnd=rnd))
        assert actions[-1] == DONE and len(actions) <= 20


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


# --- v1 games unchanged (golden results.csv) ----------------------------------

GOLDEN_V1 = Path(__file__).parent / "fixtures" / "golden" / "v1_bots_results.csv"
GOLDEN_V1_BOTS = (
    "bot:draw20-pts1-points,bot:draw20-pts1-cleaner,bot:draw20-pts4-blue,"
    "bot:draw30-pts3-green,bot:draw20-pts6-cleaner,bot:draw30-pts4-balanced"
)


def test_v1_tournament_matches_the_golden_results_csv(tmp_path):
    import csv

    r = runner.invoke(
        app,
        [
            "tournament",
            "--bots",
            GOLDEN_V1_BOTS,
            "--rules",
            "v1",
            "--games",
            "10",
            "--seed",
            "7",
            "--name",
            "v1golden",
            "--out",
            str(tmp_path),
        ],
    )
    assert r.exit_code == 0, r.output
    (results,) = tmp_path.glob("*/results.csv")
    with GOLDEN_V1.open(encoding="utf-8", newline="") as f:
        golden = list(csv.DictReader(f))
    with results.open(encoding="utf-8", newline="") as f:
        new = list(csv.DictReader(f))
    assert len(golden) == len(new) == 150
    for column in golden[0]:
        assert [row[column] for row in golden] == [row.get(column) for row in new], column
