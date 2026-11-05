import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from quack_rl.bots import STRATEGIES, RuleBot, explosion_chance
from quack_rl.cli.main import app
from quack_rl.engine import DONE, DRAW, STOP, Phase, ScriptedChance, new_game, step
from quack_rl.rules import load_ruleset

RS = load_ruleset("v2.3")
runner = CliRunner()


def brew_state(bag, white_total, placed=("white_1",)):
    # v2.3 opens with the card step; a card without effect leads to the first brew step
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
    bot = RuleBot(RS, "topchip", limit, 1, seed=1)
    assert bot.choose(brew_state(BAG, 5), "p1", [DRAW, STOP]) == expected


def test_draw_when_stop_not_legal():
    bot = RuleBot(RS, "topchip", 0, 1, seed=1)
    state = brew_state(BAG, 5, placed=())
    assert bot.choose(state, "p1", [DRAW]) == DRAW


# --- shop rule ----------------------------------------------------------------


@pytest.mark.parametrize("strategy", sorted(STRATEGIES))
def test_done_when_nothing_affordable(strategy):
    bot = RuleBot(RS, strategy, 30, 1, seed=1)
    state = shop_state(2)
    assert bot.choose(state, "p1", shop_legal(state)) == DONE


@pytest.mark.parametrize("strategy", sorted(STRATEGIES))
def test_bot_returns_only_legal_actions(strategy):
    bot = RuleBot(RS, strategy, 30, 1, seed=1)
    for money in range(0, 40):
        state = shop_state(money)
        legal = shop_legal(state)
        assert bot.choose(state, "p1", legal) in legal


# --- CLI ----------------------------------------------------------------------


def sim(out, p1, p2, seed="4", games="4"):
    return runner.invoke(
        app,
        ["simulate", "--rules", "v2.3", "--p1", p1, "--p2", p2, "--games", games, "--seed", seed, "--out", str(out)],
    )


def records(out: Path):
    lines = []
    for shard in sorted(out.glob("**/shard-*.jsonl")):
        lines += [json.loads(x) for x in shard.read_text().splitlines()]
    return lines


@pytest.mark.parametrize(
    "spec", ["bot:topchip-draw30", "bot:nosuch-draw30-pts3", "bot:topchip-drawx-pts3"]
)
def test_bad_bot_spec_fails_clean(tmp_path, spec):
    result = sim(tmp_path, spec, "bot:random")
    assert result.exit_code != 0
    assert "Traceback" not in result.output
    assert spec in result.output
    assert result.exception is None or isinstance(result.exception, SystemExit)


def test_bad_bot_spec_in_play(tmp_path):
    result = runner.invoke(
        app, ["play", "--p1", "bot:topchip-draw30", "--p2", "bot:random", "--out", str(tmp_path)]
    )
    assert result.exit_code != 0
    assert "bot:topchip-draw30" in result.output
    assert "Traceback" not in result.output


def test_simulate_same_seed_same_records(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    for out in (a, b):
        r = sim(out, "bot:topchip-draw30-pts1", "bot:topchip-draw50-pts3")
        assert r.exit_code == 0, r.output

    def strip(lines):
        return [
            {k: v for k, v in line.items() if k not in ("game_id", "started_at", "finished_at")}
            for line in lines
        ]

    assert strip(records(a)) == strip(records(b))


def test_header_has_bot_params(tmp_path):
    r = sim(tmp_path, "bot:topchip-draw30-pts1", "bot:topchip-draw50-pts3", games="1")
    assert r.exit_code == 0, r.output
    header = records(tmp_path)[0]
    p1 = header["seats"]["p1"]
    assert p1["name"] == "topchip-draw30-pts1"
    assert p1["params"]["draw_limit"] == 30
    assert p1["params"]["points_round"] == 1
    assert p1["params"]["strategy"] == "topchip"
    assert header["seats"]["p2"]["params"]["draw_limit"] == 50


def test_verify_passes_on_bot_game(tmp_path):
    r = sim(tmp_path, "bot:topchip-draw30-pts1", "bot:topchip-draw50-pts1", games="3")
    assert r.exit_code == 0, r.output
    (shard,) = tmp_path.glob("**/shard-0001.jsonl")
    v = runner.invoke(app, ["verify", str(shard)])
    assert v.exit_code == 0, v.output
    assert "3 games ok" in v.output


def test_simulate_same_seed_only_ids_and_times_differ(tmp_path):
    # game_id is random and the times are clock values, by design (verify --game selects
    # by id). Everything else must be identical, including the full step lines.
    a, b = tmp_path / "a", tmp_path / "b"
    for out in (a, b):
        r = sim(out, "bot:topchip-draw30-pts1", "bot:topchip-draw50-pts3")
        assert r.exit_code == 0, r.output
    ra, rb = records(a), records(b)
    assert len(ra) == len(rb) > 1
    assert ra[0]["game_id"] != rb[0]["game_id"]
    for x, y in zip(ra, rb, strict=True):
        for key in ("game_id", "started_at", "finished_at"):
            x.pop(key, None)
            y.pop(key, None)
        assert x == y


# --- the three shop strategies -----------------------------------------------------


@pytest.mark.parametrize("strategy", sorted(STRATEGIES))
def test_all_specs_run_as_seats(tmp_path, strategy):
    for draw in (15, 50):
        for pts in (3, 8):
            spec = f"bot:{strategy}-draw{draw}-pts{pts}"
            out = tmp_path / spec.replace(":", "_")
            r = sim(out, spec, "bot:random", games="1")
            assert r.exit_code == 0, r.output
            header = records(out)[0]
            assert f"bot:{header['seats']['p1']['name']}" == spec


@pytest.mark.parametrize("strategy", sorted(STRATEGIES))
def test_strategy_games_verify(tmp_path, strategy):
    r = sim(tmp_path, f"bot:{strategy}-draw30-pts3", "bot:random", games="3")
    assert r.exit_code == 0, r.output
    (shard,) = tmp_path.glob("**/shard-0001.jsonl")
    v = runner.invoke(app, ["verify", str(shard)])
    assert v.exit_code == 0, v.output
    assert "3 games ok" in v.output


# --- v1.1 chip rule (max_chip_purchases) --------------------------------------

RS = load_ruleset("v2.3")


def shop_state11(money, rnd, rs=RS):
    state = new_game(rs)
    state.phase = Phase.SHOP
    state.round = rnd
    state.players["p1"].money = money
    state.players["p2"].money = 40  # p2 can still buy a chip, so p2's shop stays open
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


@pytest.mark.parametrize("strategy", sorted(STRATEGIES))
@pytest.mark.parametrize("rnd", [2, 4])
def test_v1_1_shop_is_legal_and_ends(strategy, rnd):
    for money in range(0, 41):
        bot = RuleBot(RS, strategy, 20, 4, seed=1)
        state = shop_state11(money, rnd=rnd)
        actions = play_shop(bot, state)
        assert state.phase is Phase.SHOP and state.players["p1"].shop_done
        assert DONE not in actions[:-1] and len(actions) <= 20


# --- v1 games unchanged (golden results.csv) ----------------------------------

GOLDEN_V1 = Path(__file__).parent / "fixtures" / "golden" / "v2_3_bots_results.csv"
GOLDEN_V1_BOTS = (
    "bot:topchip-draw20-pts1,bot:blackpurple-draw20-pts1,bot:topchip-draw20-pts4,"
    "bot:spendmost-draw30-pts3,bot:blackpurple-draw20-pts6,bot:spendmost-draw30-pts4"
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
            "v2.3",
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

RS = load_ruleset("v2.3")


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
    bot = RuleBot(RS, "spendmost", 20, 4, seed=1)
    assert bot.name == "spendmost-draw20-pts4"
    assert choice_action(bot, 3) == TAKE_MONEY
    assert choice_action(bot, 4) == TAKE_POINTS
    assert choice_action(bot, 9) == TAKE_POINTS


def test_v18_pts1_takes_points_every_round():
    bot = RuleBot(RS, "topchip", 20, 1, seed=1)
    assert all(choice_action(bot, r) == TAKE_POINTS for r in range(1, RS.rounds + 1))


def test_v18_points_round_beyond_last_round_takes_money_every_round():
    bot = RuleBot(RS, "topchip", 20, 12, seed=1)
    assert all(choice_action(bot, r) == TAKE_MONEY for r in range(1, RS.rounds + 1))


def test_v18_choice_wait_for_a_player_who_did_not_explode():
    state = choice_state(2)
    state.players["p1"].status = Status.STOPPED
    bot = RuleBot(RS, "topchip", 20, 1, seed=1)
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
        bot = RuleBot(RS, strategy, 20, 1, seed=1)
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
            "p1": RuleBot(RS, strategy, 30, 4, seed=seed),
            "p2": RuleBot(RS, "topchip", 20, 1, seed=seed + 100),
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

RS = load_ruleset("v2.3")
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
    bot = RuleBot(RS, "topchip", draw_limit, 1)
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


# --- v1.9: full games -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "p1,p2",
    [
        ("bot:topchip-draw20-pts1", "bot:blackpurple-draw30-pts3"),
        ("bot:topchip-draw20-pts1", "bot:random"),
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
                RS, rules="v2.3", rounds=9, overrides={}, p1=p1, p2=p2, game_seed=seed, stream=f
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
            "v2.3",
            "--games",
            "4",
            "--seed",
            "3",
            "--out",
            str(tmp_path),
            "--bots",
            "bot:topchip-draw20-pts1,bot:blackpurple-draw30-pts3,bot:random",
        ],
    )
    assert result.exit_code == 0, result.output
    run = next(p for p in tmp_path.iterdir() if p.is_dir())
    rows = (run / "results.csv").read_text(encoding="utf-8").strip().splitlines()
    assert len(rows) == 1 + 3 * 4
