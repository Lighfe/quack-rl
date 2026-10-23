"""Ruleset v1.1: new prices, no shop droplet, at most 2 chips of different colours per round."""

import csv
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from quack_rl.bots import HeuristicBot
from quack_rl.cli.main import app
from quack_rl.engine import (
    DONE,
    WAIT,
    GameState,
    Phase,
    RngChance,
    ScriptedChance,
    Status,
    buy,
    legal_actions,
    new_game,
    state_from_dict,
    state_to_dict,
    step,
)
from quack_rl.report import _points_for_money, baseline_maximum, realistic_baseline_maximum
from quack_rl.rules import apply_overrides, load_ruleset, with_rounds
from quack_rl.runner import play_game
from quack_rl.simgame import play_sim_game

RS11 = load_ruleset("v1.1")
RS1 = load_ruleset("v1")
runner = CliRunner()
TRACEBACK = "Traceback (most recent call last)"
RULES_DOC = Path(__file__).resolve().parents[1] / "docs" / "rules" / "rules-v1.1.md"

V11_PRICES = {
    "orange_1": 3,
    "blue_1": 5,
    "blue_2": 8,
    "blue_4": 15,
    "green_1": 4,
    "green_2": 9,
    "green_4": 13,
    "remove_white_1": 14,
    "points_2": 7,
    "points_5": 13,
    "points_10": 21,
}


def act(state: GameState, p1: str, p2: str, rs=RS11, *chance: str):
    return step(state, rs, {"p1": p1, "p2": p2}, ScriptedChance(chance)).state


def shop_state(p1_money=100, p2_money=0, rs=RS11) -> GameState:
    s = new_game(rs)
    s.phase = Phase.SHOP
    for seat, money in (("p1", p1_money), ("p2", p2_money)):
        p = s.players[seat]
        p.money, p.status = money, Status.STOPPED
        p.placed = ["white_1", "white_2"]
        p.bag["white_1"] -= 1
        p.bag["white_2"] -= 1
        p.field = p.final_field = 3
    return s


def chip_buys(legal: list[str], rs=RS11) -> set[str]:
    return {
        a.removeprefix("buy:")
        for a in legal
        if a.startswith("buy:") and rs.shop_item(a.removeprefix("buy:")).kind == "chip"
    }


# --- ruleset data --------------------------------------------------------------


def test_load_v1_1():
    assert RS11.version == "v1.1"


def test_v1_1_prices_and_no_shop_droplet():
    assert {i.id: i.price for i in RS11.shop} == V11_PRICES
    assert "droplet_1" not in {i.id for i in RS11.shop}
    for item_id, price in V11_PRICES.items():
        assert RS11.shop_item(item_id).price == price


def test_v1_1_shop_rule_fields():
    assert RS11.max_purchases is None
    assert RS11.max_chip_purchases == 2
    assert RS11.distinct_chip_colours is True


def test_v1_shop_rule_fields_keep_their_meaning():
    assert RS1.max_purchases == 3
    assert RS1.max_chip_purchases is None
    assert RS1.distinct_chip_colours is False


def test_v1_1_die_is_the_v1_die():
    assert RS11.die == RS1.die
    assert {"droplet_1", "droplet_half"} <= {f.id for f in RS11.die}


def test_every_other_number_equals_v1():
    named = {"version", "shop", "max_purchases", "max_chip_purchases", "distinct_chip_colours"}
    a = {k: v for k, v in RS1.model_dump().items() if k not in named}
    b = {k: v for k, v in RS11.model_dump().items() if k not in named}
    assert a == b
    # the shop items other than the prices and the dropped droplet are the same too
    v1_shop = {i.id: i.model_dump(exclude={"price"}) for i in RS1.shop if i.id != "droplet_1"}
    v11_shop = {i.id: i.model_dump(exclude={"price"}) for i in RS11.shop}
    assert v1_shop == v11_shop


# --- the shop rule ---------------------------------------------------------------


def test_one_chip_per_colour_per_round():
    s = act(shop_state(), buy("green_1"), DONE)
    legal = legal_actions(s, RS11, "p1")
    chips = chip_buys(legal)
    assert not any(c.startswith("green_") for c in chips)
    assert {"blue_1", "blue_2", "blue_4", "orange_1"} <= chips


def test_other_colour_needs_the_money():
    s = act(shop_state(p1_money=8), buy("green_1"), DONE)  # 4 left
    chips = chip_buys(legal_actions(s, RS11, "p1"))
    assert chips == {"orange_1"}  # blue_1 costs 5


def test_after_two_chips_no_chip_but_points_and_remove_stay_legal():
    s = act(shop_state(), buy("green_1"), DONE)
    s = act(s, buy("blue_1"), WAIT)
    legal = legal_actions(s, RS11, "p1")
    assert chip_buys(legal) == set()
    for item in ("points_2", "points_5", "points_10", "remove_white_1"):
        assert buy(item) in legal
    assert DONE in legal


def test_remove_white_1_needs_a_white_1():
    s = shop_state()
    p = s.players["p1"]
    p.placed = ["white_2"]
    p.bag.pop("white_1")
    assert buy("remove_white_1") not in legal_actions(s, RS11, "p1")
    p.bag["white_1"] = 1
    assert buy("remove_white_1") in legal_actions(s, RS11, "p1")


def test_more_than_three_purchases_and_only_done_ends_the_shop():
    s = act(shop_state(), buy("green_1"), DONE)
    for item in ("blue_1", "points_2", "points_2", "points_5"):
        s = act(s, buy(item), WAIT)
        assert s.phase is Phase.SHOP
        assert not s.players["p1"].shop_done
    p = s.players["p1"]
    assert p.purchases == 5
    assert p.points == 2 + 2 + 5
    assert p.money == 100 - 4 - 5 - 7 - 7 - 13
    s = act(s, DONE, WAIT)
    assert s.phase is Phase.BREW and s.round == 2


def test_chip_count_and_colours_reset_at_round_end():
    s = act(shop_state(), buy("green_1"), DONE)
    s = act(s, buy("blue_1"), WAIT)
    s = act(s, DONE, WAIT)
    p = s.players["p1"]
    assert (p.chip_purchases, p.chip_colours) == (0, [])
    # play to the next shop: p1 has money again
    s.phase = Phase.SHOP
    for seat in ("p1", "p2"):
        s.players[seat].status = Status.STOPPED
        s.players[seat].final_field = 3
        s.players[seat].shop_done = False
    s.players["p1"].money = 20
    chips = chip_buys(legal_actions(s, RS11, "p1"))
    assert {"green_1", "green_2", "blue_1", "blue_2"} <= chips


def test_bonus_die_chip_does_not_count():
    s = new_game(RS11)
    s.phase = Phase.RESOLVE
    for p in s.players.values():
        p.status = Status.STOPPED
        p.placed = ["white_1"]
        p.bag["white_1"] -= 1
        p.field = p.final_field = 1
    # both seats are tied for the furthest field, so both roll: p1 gets an Orange 1 chip
    r = step(s, RS11, None, ScriptedChance(["orange_1", "point_1"]))
    p1 = r.state.players["p1"]
    assert r.state.phase is Phase.SHOP
    assert p1.bag["orange_1"] == RS11.start_bag["orange_1"] + 1
    assert (p1.chip_purchases, p1.chip_colours) == (0, [])
    p1.money = 20
    assert {"orange_1", "green_1", "blue_1"} <= chip_buys(legal_actions(r.state, RS11, "p1"))


def test_only_chip_kind_items_count():
    s = act(shop_state(), buy("points_2"), DONE)
    s = act(s, buy("remove_white_1"), WAIT)
    p = s.players["p1"]
    assert (p.chip_purchases, p.chip_colours) == (0, [])
    s = act(s, buy("orange_1"), WAIT)
    assert (s.players["p1"].chip_purchases, s.players["p1"].chip_colours) == (1, ["orange"])


def test_v1_still_has_three_purchases_and_no_colour_rule():
    s = act(shop_state(rs=RS1), buy("green_1"), DONE, RS1)
    assert buy("green_2") in legal_actions(s, RS1, "p1")
    s = act(s, buy("green_2"), WAIT, RS1)
    s = act(s, buy("green_1"), WAIT, RS1)
    assert s.phase is Phase.BREW  # the third purchase ends p1's shop, p2 is done


def test_state_without_new_counters_still_loads():
    data = state_to_dict(shop_state())
    for p in data["players"].values():
        p.pop("chip_purchases")
        p.pop("chip_colours")
    restored = state_from_dict(data)
    assert restored.players["p1"].chip_purchases == 0
    assert restored.players["p1"].chip_colours == []


# --- overrides ------------------------------------------------------------------


def test_set_max_chip_purchases_on_v1_1():
    rs = apply_overrides(RS11, {"max_chip_purchases": "1"})
    assert rs.max_chip_purchases == 1
    s = act(shop_state(rs=rs), buy("green_1"), DONE, rs)
    assert chip_buys(legal_actions(s, rs, "p1"), rs) == set()


def test_set_max_purchases_on_v1_still_works():
    assert apply_overrides(RS1, {"max_purchases": "2"}).max_purchases == 2


def test_set_absent_max_purchases_on_v1_1_is_a_clean_refusal(tmp_path):
    with pytest.raises(ValueError, match="max_purchases"):
        apply_overrides(RS11, {"max_purchases": "3"})
    result = runner.invoke(
        app,
        ["simulate", "--rules", "v1.1", "--games", "1", "--set", "max_purchases=3"]
        + ["--out", str(tmp_path)],
    )
    assert result.exit_code == 2
    assert "max_purchases" in result.output
    assert TRACEBACK not in result.output
    assert not list(tmp_path.glob("**/*.jsonl"))


def test_cli_set_max_chip_purchases_on_v1_1(tmp_path):
    result = runner.invoke(
        app,
        ["simulate", "--rules", "v1.1", "--games", "2", "--set", "max_chip_purchases=1"]
        + ["--out", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output


# --- bots and commands ------------------------------------------------------------


def test_two_heuristic_bots_finish_a_v1_1_game():
    seats = {
        "p1": HeuristicBot(RS11, 30, 3, "blue", seed=1),
        "p2": HeuristicBot(RS11, 20, 1, "points", seed=2),
    }
    final = play_game(RS11, seats, RngChance(11), lambda r, ms: None)
    assert final.phase is Phase.GAME_OVER
    assert final.winner in ("p1", "p2", "draw")


def test_simulate_v1_1_writes_records_that_pass_the_seed_check(tmp_path):
    result = runner.invoke(
        app,
        ["simulate", "--rules", "v1.1", "--games", "3", "--seed", "2"]
        + ["--p1", "bot:draw30-pts3-blue", "--p2", "bot:random", "--out", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    shards = sorted((tmp_path / "v1.1" / "sim").glob("*/shard-*.jsonl"))
    assert shards
    v = runner.invoke(app, ["verify", str(shards[0]), "--seed-check"])
    assert v.exit_code == 0, v.output
    assert "3 games ok" in v.output


def test_play_v1_1_with_two_bot_seats(tmp_path):
    result = runner.invoke(
        app,
        ["play", "--rules", "v1.1", "--seed", "4", "--p1", "bot:random"]
        + ["--p2", "bot:draw30-pts3-blue", "--out", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    files = sorted((tmp_path / "v1.1" / "play").glob("*.jsonl"))
    assert len(files) == 1
    v = runner.invoke(app, ["verify", str(files[0]), "--seed-check"])
    assert v.exit_code == 0, v.output


def test_tournament_v1_1_has_no_droplet_column_and_reports(tmp_path):
    result = runner.invoke(
        app,
        ["tournament", "--rules", "v1.1", "--games", "2", "--seed", "5"]
        + ["--bots", "bot:draw30-pts1-points,bot:draw30-pts3-blue", "--out", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    (run,) = [p for p in tmp_path.iterdir() if p.is_dir()]
    with (run / "results.csv").open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        columns = reader.fieldnames or []
    assert rows
    assert not any("buy_droplet_1" in c for c in columns)
    assert "p1_buy_points_10" in columns
    rep = runner.invoke(app, ["report", str(run)])
    assert rep.exit_code == 0, rep.output
    assert TRACEBACK not in rep.output


# --- v1 unchanged -------------------------------------------------------------------


@pytest.mark.parametrize(
    "p1, p2, seed, expected",
    [
        # values read from the base commit efd595a, before the engine change
        ("bot:random", "bot:random", 7, (2, 3, "p2")),
        ("bot:draw30-pts3-blue", "bot:draw20-pts1-points", 11, (32, 20, "p1")),
    ],
)
def test_v1_fixed_seed_games_are_unchanged(p1, p2, seed, expected):
    final, _, _ = play_sim_game(
        RS1, rules="v1", rounds=9, overrides={}, p1=p1, p2=p2, game_seed=seed
    )
    assert (final.players["p1"].points, final.players["p2"].points, final.winner) == expected


# --- report without max_purchases -----------------------------------------------------


def test_points_for_money_without_a_purchase_cap():
    # 54 money, items (price, points) 21/10, 13/5, 7/2; the bot buys the item with the most
    # points it can afford: 21 (33 left), 21 (12 left), 7 (5 left): 10 + 10 + 2 = 22
    assert _points_for_money(RS11, 54) == 22
    # v1 prices 22/10, 13/5, 6/2 and a cap of 3 purchases: 3 x 22 = 66 of 70 money -> 30
    assert _points_for_money(RS1, 70) == 30
    # without the cap: 21 * 3 = 63 (7 left), then 7: 10 * 3 + 2 = 32
    assert _points_for_money(RS11, 70) == 32


def test_baseline_maximum_without_a_purchase_cap():
    # one round, money x 3 in the last round: (35 best field + 1 money face) * 300 // 100 = 108
    # best points for 108 with 21/10, 13/5, 7/2 and no cap: 5 x 21 = 105 -> 50
    # (4 x 21 + 13 + 7 = 104 -> 47; 3 x 21 + 3 x 13 = 102 -> 45); plus the best points face 1
    rs = apply_overrides(with_rounds(RS11, 1), {"last_round_money_percent": "300"})
    assert baseline_maximum(rs) == 51.0
    # the same ruleset with a cap of 3 purchases: 3 x 21 -> 30, plus 1
    capped = rs.model_copy(update={"max_purchases": 3})
    assert baseline_maximum(capped) == 31.0


def test_realistic_baseline_maximum_runs_without_a_purchase_cap():
    value = realistic_baseline_maximum(with_rounds(RS11, 2))
    assert 0 < value < baseline_maximum(with_rounds(RS11, 2))


# --- rules document ------------------------------------------------------------------

SHOP_LABELS = {
    "orange_1": "Orange 1",
    "blue_1": "Blue 1",
    "blue_2": "Blue 2",
    "blue_4": "Blue 4",
    "green_1": "Green 1",
    "green_2": "Green 2",
    "green_4": "Green 4",
    "remove_white_1": "Remove one White 1",
    "points_2": "2 victory points",
    "points_5": "5 victory points",
    "points_10": "10 victory points",
}


def test_rules_doc_v1_1():
    doc = RULES_DOC.read_text(encoding="utf-8")
    assert "Rules version: `v1.1`" in doc
    for item_id, label in SHOP_LABELS.items():
        pattern = rf"\|[^|\n]*{re.escape(label)}\s*\|\s*{V11_PRICES[item_id]}\s*\|"
        assert re.search(pattern, doc), item_id
    assert "Advance droplet by 1 |" not in doc
    assert "At most 3 purchases per player per round" not in doc
    assert "At most 2 chips per player per round" in doc
    assert "different colours" in doc
    assert "no count limit" in doc
    line = "Ruby fields: " + ", ".join(str(f) for f in RS11.rubies) + "."
    assert line in doc
