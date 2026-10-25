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
from quack_rl.engine import DONE, DRAW, STOP, Phase, ScriptedChance, new_game, step
from quack_rl.rules import load_ruleset

RS = load_ruleset("v2.1")
runner = CliRunner()


def brew_state(bag, white_total, placed=("white_1",)):
    # v2.1 opens with the card step; a card without effect leads to the first brew step
    state = step(new_game(RS), RS, None, ScriptedChance(["card_16"])).state
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








def test_strategy_priority_before_points_round():
    from quack_rl.bots import Strategy

    bot = HeuristicBot(RS, 30, 5, Strategy("t", ("blue_1", "green_1")), seed=1)
    state = shop_state(10, rnd=1)
    assert bot.choose(state, "p1", shop_legal(state)) == "buy:blue_1"


def test_done_when_nothing_affordable():
    bot = HeuristicBot(RS, 30, 1, "points", seed=1)
    state = shop_state(2)
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
    assert bot.name == BASELINE_NAME == "draw20-pts1-points"
    assert bot.params["draw_limit"] == 20
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
        ["simulate", "--rules", "v2.1", "--p1", p1, "--p2", p2, "--games", games, "--seed", seed, "--out", str(out)],
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
    for x, y in zip(ra, rb, strict=True):
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










@pytest.mark.parametrize("strategy", ["blue", "green", "cleaner", "balanced"])
def test_strategy_games_verify(tmp_path, strategy):
    r = sim(tmp_path, f"bot:draw30-pts3-{strategy}", "bot:random", games="3")
    assert r.exit_code == 0, r.output
    (shard,) = tmp_path.glob("**/shard-0001.jsonl")
    v = runner.invoke(app, ["verify", str(shard)])
    assert v.exit_code == 0, v.output
    assert "3 games ok" in v.output


# --- v1.1 chip rule (max_chip_purchases) --------------------------------------

RS = load_ruleset("v2.1")


def shop_state11(money, rnd, rs=RS):
    state = new_game(rs)
    state.phase = Phase.SHOP
    state.round = rnd
    state.players["p1"].money = money
    state.players["p2"].rubies = rs.ruby_cost  # p2 keeps a ruby drop, so p2's shop stays open
    return state


def legal11(state, rs=RS):
    from quack_rl.engine import legal_actions

    return legal_actions(state, rs, "p1")


def apply11(state, action, rs=RS):
    """Apply one shop action of p1 with the engine (p2 waits and keeps its shop open, so the
    round does not end)."""
    from quack_rl.engine.shop import apply_shop

    apply_shop(state, rs, {"p1": action, "p2": "wait"}, [])


def play_shop(bot, state, rs=RS, limit=20):
    """The bot's actions until p1's shop is closed, each checked against the legal list of its
    step. The shop closes with the bot's `done`, or without asking once nothing but `done` is
    left (issue #203)."""
    actions = []
    for _ in range(limit):
        legal = legal11(state, rs)
        action = bot.choose(state, "p1", legal)
        assert action in legal, (action, legal)
        actions.append(action)
        apply11(state, action, rs)
        if state.players["p1"].shop_done:
            return actions
    raise AssertionError(f"no done after {limit} actions: {actions}")








def test_v1_1_before_points_round_strategy_list_first():
    bot = HeuristicBot(RS, 20, 4, "blue", seed=1)
    state = shop_state11(20, rnd=2)
    assert bot.choose(state, "p1", legal11(state)) == "buy:blue_4"








@pytest.mark.parametrize("strategy", ["green", "balanced"])
@pytest.mark.parametrize("rnd", [2, 4])
def test_v1_1_items_not_in_the_shop_are_skipped(strategy, rnd):
    assert "droplet_1" in load_strategy(strategy).priority
    for money in range(0, 41):
        bot = HeuristicBot(RS, 20, 4, strategy, seed=1)
        actions = play_shop(bot, shop_state11(money, rnd=rnd))
        assert "buy:droplet_1" not in actions


@pytest.mark.parametrize("strategy", ["points", "blue", "green", "cleaner", "balanced"])
@pytest.mark.parametrize("rnd", [2, 4])
def test_v1_1_shop_is_legal_and_ends(strategy, rnd):
    for money in range(0, 41):
        bot = HeuristicBot(RS, 20, 4, strategy, seed=1)
        state = shop_state11(money, rnd=rnd)
        actions = play_shop(bot, state)
        assert state.phase is Phase.SHOP and state.players["p1"].shop_done
        assert DONE not in actions[:-1] and len(actions) <= 20




# --- v1 games unchanged (golden results.csv) ----------------------------------

GOLDEN_V1 = Path(__file__).parent / "fixtures" / "golden" / "v2_1_bots_results.csv"
GOLDEN_V1_BOTS = (
    "bot:draw20-pts1-points,bot:draw20-pts1-cleaner,bot:draw20-pts4-blue,"
    "bot:draw30-pts3-green,bot:draw20-pts6-cleaner,bot:draw30-pts4-balanced"
)


@pytest.mark.slow
def test_v1_tournament_matches_the_golden_results_csv(tmp_path):
    import csv

    r = runner.invoke(
        app,
        [
            "tournament",
            "--bots",
            GOLDEN_V1_BOTS,
            "--rules",
            "v2.1",
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


# --- v1.8: explosion choice by round, no points in the shop ----------------------

from quack_rl.bots import RandomBot  # noqa: E402
from quack_rl.engine import (  # noqa: E402
    TAKE_MONEY,
    TAKE_POINTS,
    WAIT,
    RngChance,  # noqa: E402
    Status,
    legal_actions,
)
from quack_rl.runner import play_game  # noqa: E402

RS = load_ruleset("v2.1")


def choice_state(rnd):
    state = new_game(RS)
    state.phase = Phase.CHOICE
    state.round = rnd
    state.players["p1"].status = Status.EXPLODED
    state.players["p1"].final_field = 3
    return state


def choice_action(bot, rnd):
    state = choice_state(rnd)
    legal = legal_actions(state, RS, "p1")
    assert legal == [TAKE_MONEY, TAKE_POINTS]
    return bot.choose(state, "p1", legal)


def test_v18_choice_money_before_points_round_points_from_it():
    bot = HeuristicBot(RS, 20, 4, "green", seed=1)
    assert bot.name == "draw20-pts4-green"
    assert choice_action(bot, 3) == TAKE_MONEY
    assert choice_action(bot, 4) == TAKE_POINTS
    assert choice_action(bot, 9) == TAKE_POINTS


def test_v18_pts1_takes_points_every_round():
    bot = HeuristicBot(RS, 20, 1, "points", seed=1)
    assert all(choice_action(bot, r) == TAKE_POINTS for r in range(1, RS.rounds + 1))


def test_v18_points_round_beyond_last_round_takes_money_every_round():
    bot = HeuristicBot(RS, 20, 12, "points", seed=1)
    assert all(choice_action(bot, r) == TAKE_MONEY for r in range(1, RS.rounds + 1))


def test_v18_choice_wait_for_a_player_who_did_not_explode():
    state = choice_state(2)
    state.players["p1"].status = Status.STOPPED
    bot = HeuristicBot(RS, 20, 1, "points", seed=1)
    assert bot.choose(state, "p1", legal_actions(state, RS, "p1")) == WAIT


def v18_shop_state(money, rnd):
    state = new_game(RS)
    state.phase = Phase.SHOP
    state.round = rnd
    state.players["p1"].money = money
    return state


def test_v18_shop_never_buys_points():
    shop_ids = {i.id for i in RS.shop}
    for strategy in STRATEGIES:
        bot = HeuristicBot(RS, 20, 1, strategy, seed=1)
        for rnd in range(1, RS.rounds):  # the last round has no shop
            for money in range(0, 40):
                state = v18_shop_state(money, rnd)
                legal = legal_actions(state, RS, "p1")
                action = bot.choose(state, "p1", legal)
                assert action in legal
                if action.startswith("buy:"):
                    assert action.removeprefix("buy:") in shop_ids
                    assert RS.shop_item(action.removeprefix("buy:")).kind != "points"


@pytest.mark.parametrize("strategy", sorted(STRATEGIES))
def test_v18_game_with_each_strategy_has_no_illegal_action(strategy):
    for seed in range(5):
        seats = {
            "p1": HeuristicBot(RS, 30, 4, strategy, seed=seed),
            "p2": HeuristicBot(RS, 20, 1, "points", seed=seed + 100),
        }
        bought = []

        def on_step(result, _ms, bought=bought):
            bought.extend(e["item"] for e in result.events if e.get("kind") == "buy")

        final = play_game(RS, seats, RngChance(seed), on_step)  # an illegal action raises
        assert final.phase is Phase.GAME_OVER
        assert set(bought) <= {i.id for i in RS.shop}


def test_random_bot_plays_many_seeded_v18_games():
    for seed in range(40):
        seats = {"p1": RandomBot(seed=seed), "p2": RandomBot(seed=seed + 1000)}
        assert play_game(RS, seats, RngChance(seed)).phase is Phase.GAME_OVER


# --- v1.9: the pick step --------------------------------------------------------------------

RS = load_ruleset("v2.1")
PICK_LEGAL = ["play:0", "play:1", "put_back_draw", "put_back_stop"]


def pick_state(hand, bag=None, white_total=0, field=0, placed=(), pot_field=None):
    state = step(new_game(RS), RS, None, ScriptedChance(["card_16"])).state
    p = state.players["p1"]
    p.hand = list(hand)
    p.bag = dict(bag or {})
    p.white_total = white_total
    p.field = field
    p.placed = list(placed)
    return state


def pick(state, draw_limit=20):
    bot = HeuristicBot(RS, draw_limit=draw_limit)
    return bot.choose(state, "p1", PICK_LEGAL)


def test_pick_plays_the_highest_advance():
    assert pick(pick_state(["white_1", "orange_6"])) == "play:1"
    assert pick(pick_state(["orange_6", "white_1"])) == "play:0"


def test_pick_tie_goes_to_the_lowest_slot():
    assert pick(pick_state(["orange_1", "orange_1"])) == "play:0"


def test_pick_all_explode_stops_even_at_draw_limit_100():
    state = pick_state(
        ["white_3", "white_2"], bag={"white_1": 3}, white_total=RS.explosion_limit - 1
    )
    assert pick(state, draw_limit=100) == "put_back_stop"


def test_pick_advance_zero_draws_or_stops_by_the_chance_with_the_hand_back():
    # field 53: every advance is 0. White total 6, limit 7: white_2 explodes, white_1 does not.
    hand = ["white_1", "white_1"]
    safe = pick_state(hand, bag={"white_1": 8, "white_2": 2}, white_total=6, field=53)
    # bag plus hand: 2 of 12 explode (16.7%)
    assert pick(safe, draw_limit=20) == "put_back_draw"
    risky = pick_state(hand, bag={"white_1": 4, "white_2": 6}, white_total=6, field=53)
    # 6 of 12 explode (50%)
    assert pick(risky, draw_limit=20) == "put_back_stop"


def test_pick_stop_rule_counts_the_hand_in_the_bag():
    # bag alone: 1 of 4 explodes (25%) -> Stop at 20%; with the hand (2 safe chips) 1 of 6 -> Draw
    state = pick_state(
        ["white_1", "white_1"], bag={"white_1": 3, "white_2": 1}, white_total=6, field=53
    )
    assert pick(state, draw_limit=20) == "put_back_draw"


def test_pick_red_beats_orange_with_three_orange_in_the_pot():
    state = pick_state(["orange_1", "red_1"], white_total=0, placed=["orange_1"] * 3, field=3)
    assert pick(state) == "play:1"


def test_random_bot_answers_all_three_kinds_at_the_pick_step():
    from quack_rl.bots import RandomBot

    state = pick_state(["white_1", "orange_1"])
    kinds = set()
    for seed in range(60):
        action = RandomBot(seed).choose(state, "p1", PICK_LEGAL)
        assert action in PICK_LEGAL
        kinds.add("play" if action.startswith("play:") else action)
    assert kinds == {"play", "put_back_draw", "put_back_stop"}


def test_parse_bot_name_is_unchanged():
    assert parse_bot_name("bot:draw30-pts3-blue") == (30, 3, "blue")


# --- v1.9: full games -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "p1,p2",
    [
        ("bot:draw20-pts1-blue", "bot:draw30-pts3-balanced"),
        ("bot:draw20-pts1-blue", "bot:random"),
        ("bot:random", "bot:random"),
    ],
)
def test_v1_9_full_games_reach_the_end_with_legal_actions(p1, p2, tmp_path):
    from quack_rl.record import read_games
    from quack_rl.simgame import play_sim_game

    saw_hand = False
    for seed in range(1, 7):
        path = tmp_path / f"{seed}.jsonl"
        with path.open("w", encoding="utf-8") as f:
            final, _, _ = play_sim_game(
                RS, rules="v2.1", rounds=9, overrides={}, p1=p1, p2=p2, game_seed=seed, stream=f
            )
        assert final.winner is not None  # an illegal action would have raised
        (game,) = read_games(path)
        assert game.footer is not None
        saw_hand = saw_hand or any(
            e.get("kind") == "hand" for step in game.steps for e in step.events
        )
    assert saw_hand


def test_v1_9_tournament_runs_all_pairs(tmp_path):
    result = runner.invoke(
        app,
        [
            "tournament",
            "--rules",
            "v2.1",
            "--games",
            "4",
            "--seed",
            "3",
            "--out",
            str(tmp_path),
            "--bots",
            "bot:draw20-pts1-blue,bot:draw30-pts3-balanced,bot:random",
        ],
    )
    assert result.exit_code == 0, result.output
    run = next(p for p in tmp_path.iterdir() if p.is_dir())
    rows = (run / "results.csv").read_text(encoding="utf-8").strip().splitlines()
    assert len(rows) == 1 + 3 * 4
