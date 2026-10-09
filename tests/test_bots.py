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
