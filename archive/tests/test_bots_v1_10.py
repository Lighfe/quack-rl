"""Bots, report odds, simulation statistics and tournament under ruleset v1.10."""

import csv
from collections import Counter

import pytest
from test_engine_v1_10 import play_brew
from typer.testing import CliRunner

from quack_rl.bots import STRATEGIES, HeuristicBot, Strategy, explosion_chance
from quack_rl.cli.main import app
from quack_rl.components.chips import Yellow
from quack_rl.engine import (
    DRAW,
    PUT_BACK_DRAW,
    PUT_BACK_STOP,
    STOP,
    Phase,
    RngChance,
    ScriptedChance,
    Status,
    buy,
    legal_actions,
    new_game,
    play,
    step,
)
from quack_rl.record import read_games
from quack_rl.report import _brew_outcomes
from quack_rl.rules import load_ruleset
from quack_rl.runner import play_game
from quack_rl.simgame import play_sim_game
from quack_rl.tournament import BASE_COLUMNS, csv_columns, seat_columns

RS = load_ruleset("v1.10")
runner = CliRunner()


# --- full games -----------------------------------------------------------------------------


@pytest.mark.parametrize("strategy", sorted(STRATEGIES))
def test_heuristic_bot_plays_full_games_on_v1_10_in_both_orders(strategy):
    bot = f"bot:draw20-pts1-{strategy}"
    for seed in range(1, 11):  # 10 seeds x 2 orders = 20 games
        for p1, p2 in ((bot, "bot:random"), ("bot:random", bot)):
            final, _, _ = play_sim_game(
                RS, rules="v1.10", rounds=9, overrides={}, p1=p1, p2=p2, game_seed=seed
            )
            assert final.winner is not None  # an illegal action would have raised


def test_random_bot_plays_full_games_on_v1_10():
    for seed in range(1, 21):
        final, _, _ = play_sim_game(
            RS,
            rules="v1.10",
            rounds=9,
            overrides={},
            p1="bot:random",
            p2="bot:random",
            game_seed=seed,
        )
        assert final.winner is not None


# --- yellow look-ahead --------------------------------------------------------------------


def brew_state(placed, white_total, bag, hand=()):
    s = new_game(RS)
    s.phase = Phase.BREW
    p = s.players["p1"]
    p.placed, p.white_total, p.bag, p.hand = list(placed), white_total, dict(bag), list(hand)
    p.placed_fields = [3] * len(placed)
    return s


POT = ["white_3", "white_3", "white_1"]  # white total 7 = the limit, last chip white


def test_stop_rule_uses_the_bag_after_the_yellow_put_back():
    # Engine: the pot is at 7, p1 draws yellow_1 and the put-back returns white_1 to the bag.
    s = brew_state(POT, 7, {"yellow_1": 1, "white_2": 1})
    s.players["p1"].placed_fields = [3, 6, 7]
    s.players["p2"].status = Status.STOPPED
    r = step(s, RS, {"p1": DRAW, "p2": "wait"}, ScriptedChance(["yellow_1"]))
    p = r.state.players["p1"]
    assert p.white_total == 6 and p.bag == {"white_2": 1, "white_1": 1}  # white_1 is back
    bot = HeuristicBot(RS, draw_limit=60)
    # after the put-back: white_2 explodes (8 > 7), white_1 does not: 1 of 2 = 50 percent
    assert explosion_chance(p.bag, p.white_total, RS, p.placed[-1]) == pytest.approx(0.5)
    assert bot.choose(r.state, "p1", [DRAW, STOP]) == DRAW
    # the old bag (white_1 not back): 100 percent, the same bot would stop
    old = r.state
    old.players["p1"].bag = {"white_2": 1}
    assert bot.choose(old, "p1", [DRAW, STOP]) == STOP


def test_explosion_chance_counts_a_yellow_that_pulls_a_white_chip(monkeypatch):
    # Yellow weighs 0 in v1.10, so the put-back is seen only when the weight is above 0.
    monkeypatch.setattr(Yellow, "explosion_weight", lambda self, chip: 1)
    bag = {"yellow_1": 9, "white_1": 1}
    assert explosion_chance(bag, 7, RS) == 1.0  # without the put-back: 7 + 1 > 7 for yellow
    assert explosion_chance(bag, 7, RS, "white_1") == pytest.approx(0.1)  # 7 + 1 - 1 = 7
    s = brew_state(POT, 7, bag)
    assert HeuristicBot(RS, draw_limit=20).choose(s, "p1", [DRAW, STOP]) == DRAW


def test_pick_step_plays_the_yellow_chip_that_pulls_a_white_chip(monkeypatch):
    monkeypatch.setattr(Yellow, "explosion_weight", lambda self, chip: 1)
    s = brew_state(POT, 7, {"white_1": 3}, hand=["yellow_1"])
    legal = [play(0), PUT_BACK_DRAW, PUT_BACK_STOP]
    # old rule (no put-back): 7 + 1 > 7, every chip explodes, the bot would put back and stop
    assert HeuristicBot(RS).choose(s, "p1", legal) == play(0)
    s.players["p1"].placed = ["orange_1"]  # control: no white chip before, yellow explodes
    assert HeuristicBot(RS).choose(s, "p1", legal) == PUT_BACK_STOP


# --- shop strategies: black, yellow, purple ------------------------------------------------


COLOURS = Strategy("colours", priority=("black_1", "yellow_2", "purple_1", "yellow_1"))


def shop_state(round_, money=30):
    s = new_game(RS)
    s.phase, s.round = Phase.SHOP, round_
    for p in s.players.values():
        p.money, p.status = money, Status.STOPPED
        p.field = p.final_field = 3
    return s


def test_a_strategy_buys_black_yellow_and_purple_in_a_game():
    bought: Counter[str] = Counter()
    first_round: dict[str, int] = {}

    def on_step(result, _ms):
        for e in result.events:
            if e.get("kind") == "buy":
                bought[e["item"]] += 1
                first_round[e["item"]] = min(first_round.get(e["item"], 99), result.round)

    for seed in range(1, 6):
        seats = {s: HeuristicBot(RS, 20, 1, COLOURS, seed) for s in ("p1", "p2")}
        play_game(RS, seats, RngChance(seed), on_step)
    assert bought["black_1"] and bought["purple_1"]
    assert bought["yellow_1"] + bought["yellow_2"]
    assert first_round["purple_1"] >= 3
    assert first_round.get("yellow_1", 2) >= 2 and first_round.get("yellow_2", 2) >= 2


def test_a_strategy_never_buys_an_item_below_its_minimum_round():
    bot = HeuristicBot(RS, 20, 99, Strategy("purple_first", priority=("purple_1", "black_1")))
    for round_ in (1, 2):
        s = shop_state(round_)
        legal = legal_actions(s, RS, "p1")
        assert buy("purple_1") not in legal
        assert bot.choose(s, "p1", legal) == buy("black_1")  # no error, the next item is bought
    s = shop_state(3)
    assert bot.choose(s, "p1", legal_actions(s, RS, "p1")) == buy("purple_1")


def test_a_strategy_with_only_a_late_item_does_not_name_it_before_its_round():
    bot = HeuristicBot(RS, 20, 99, Strategy("purple_only", priority=("purple_1",)))
    for round_ in (1, 2):
        s = shop_state(round_)
        action = bot.choose(s, "p1", legal_actions(s, RS, "p1"))
        assert action != buy("purple_1") and action in legal_actions(s, RS, "p1")


# --- report odds against the engine -----------------------------------------------------------


def resolve_pots(p1_placed, p2_placed):
    s = new_game(RS)
    s.phase = Phase.RESOLVE
    for seat, placed in (("p1", p1_placed), ("p2", p2_placed)):
        p = s.players[seat]
        p.field = p.final_field = 7 if seat == "p1" else 3  # only p1 rolls the die; no ruby
        p.placed = list(placed)
        p.status = Status.STOPPED
    r = step(s, RS, None, ScriptedChance(["money_1"]))
    return r.state.players["p1"]


def test_odds_match_the_engine_for_black():
    ((key, chance),) = _brew_outcomes(RS, (("black_1", 1),), 100).items()
    assert chance == 1.0
    engine = resolve_pots(["black_1"], [])  # the odds are for one player: the other pot is empty
    assert (key[2], key[3]) == (engine.droplet_halves, engine.points) == (3, 0)


@pytest.mark.parametrize("count", [1, 2, 3])
def test_odds_match_the_engine_for_purple(count):
    ((key, chance),) = _brew_outcomes(RS, (("purple_1", count),), 100).items()
    assert chance == 1.0
    engine = resolve_pots(["purple_1"] * count, [])
    assert (key[2], key[3]) == (engine.droplet_halves, engine.points)
    assert engine.points > 0


def test_odds_match_the_engine_for_yellow():
    out = _brew_outcomes(RS, (("white_2", 1), ("yellow_1", 1)), 100)
    # yellow first: yellow, white (advance 1 + 2); white first: white, yellow pulls it back,
    # white drawn again (advance 2 + 1 + 2)
    assert out == {(3, False, 0, 0): 0.5, (5, False, 0, 0): 0.5}
    bags = [{"white_2": 1, "yellow_1": 1}, {"white_1": 1}]
    for draws, advance in ((["yellow_1", "white_2"], 3), (["white_2", "yellow_1", "white_2"], 5)):
        s, _ = play_brew(bags, draws)
        assert s.players["p1"].field == advance and s.players["p1"].white_total == 2 * (
            draws[-1] == "white_2"
        )


# --- simulation statistics ----------------------------------------------------------------------


def test_statistics_equal_the_totals_of_the_record(monkeypatch, tmp_path):
    monkeypatch.setitem(STRATEGIES, "colours", COLOURS)
    bot = "bot:draw30-pts1-colours"
    saw: set[str] = set()
    for seed in range(1, 6):
        path = tmp_path / f"{seed}.jsonl"
        with path.open("w", encoding="utf-8") as f:
            final, _, stats = play_sim_game(
                RS, rules="v1.10", rounds=9, overrides={}, p1=bot, p2=bot, game_seed=seed, stream=f
            )
        (game,) = read_games(path)
        assert game.footer is not None
        events = [e for st in game.steps for e in st.events]
        saw |= {e["kind"] for e in events}
        for seat in ("p1", "p2"):
            assert stats.points[seat][9] == game.footer.points[seat] == final.players[seat].points
            assert stats.droplet_halves[seat][9] == final.players[seat].droplet_halves
            # the points of every round end are the totals at that time, never going down
            values = [stats.points[seat][k] for k in range(1, 10)]
            assert values == sorted(values)
    assert "pot_round_end" in saw and "pot_put_back" in saw


# --- tournament -----------------------------------------------------------------------------------


def test_columns_come_from_the_ruleset():
    new = {c.id for c in RS.chips if c.colour in ("black", "yellow", "purple")}
    shop = {i.id for i in RS.shop if i.chip in new}
    assert shop and new
    columns = csv_columns(RS) + seat_columns(RS)
    for item in shop:
        assert f"p1_buy_{item}" in columns and f"p2_buy_{item}" in columns
    for chip in new:
        assert f"bag_{chip}" in columns
    assert csv_columns(RS) == [
        *BASE_COLUMNS,
        *(f"{s}_buy_{i.id}" for s in ("p1", "p2") for i in RS.shop),
        "p1_draws",
        "p2_draws",
    ]
    v1 = load_ruleset("v1")
    assert not [c for c in csv_columns(v1) + seat_columns(v1) if "black" in c or "purple" in c]
    assert [c for c in seat_columns(v1) if c.startswith("bag_")] == [
        f"bag_{c.id}" for c in v1.chips
    ]


def test_tournament_runs_on_v1_10_with_the_new_columns(monkeypatch, tmp_path):
    import pyarrow.parquet as pq

    monkeypatch.setitem(STRATEGIES, "colours", COLOURS)
    result = runner.invoke(
        app,
        [
            "tournament",
            "--rules",
            "v1.10",
            "--games",
            "4",
            "--seed",
            "3",
            "--out",
            str(tmp_path),
            "--bots",
            "bot:draw20-pts4-colours,bot:draw30-pts3-balanced,bot:random",
        ],
    )
    assert result.exit_code == 0, result.output
    run = next(p for p in tmp_path.iterdir() if p.is_dir())
    with (run / "results.csv").open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        header = list(reader.fieldnames or [])
    assert header == csv_columns(RS)
    assert len(rows) == 3 * 4
    assert "p1_buy_black_1" in header and "p2_buy_purple_1" in header
    assert "p1_buy_yellow_1" in header
    table = pq.read_table(run / "seats.parquet")
    assert table.column_names == seat_columns(RS)
    assert "bag_black_1" in table.column_names and "bag_yellow_4" in table.column_names
