"""Moved from tests/test_report.py (#170): the baseline maximum counts points items of the shop.

Ruleset v2 has no points items (it scores on the points board), so these tests of the
calculated maximum for a bot that buys only points items check behaviour v2 does not have.
"""

import json

import pytest

from quack_rl.report import (
    _points_for_money,
    baseline_maximum,
    build_report,
    realistic_baseline_maximum,
)
from quack_rl.rules import apply_overrides, load_ruleset, with_rounds
from quack_rl.tournament import CSV_COLUMNS

def test_baseline_maximum_v1():
    rs = with_rounds(load_ruleset("v1"), 9)
    # 8 rounds: money 35 + 1 -> 36, three purchases: 22 + 13 = 35 money -> 15 points, +1 die point
    # last round: 36 * 150 // 100 = 54 -> 22 + 22 + 6 = 50 money -> 22 points (10+10+2), +1
    assert baseline_maximum(rs) == 8 * (15 + 1) + (22 + 1)


@pytest.mark.slow
def test_realistic_maximum_v1_is_between_baseline_and_loose_bound(run):
    rs = load_ruleset("v1")
    realistic = realistic_baseline_maximum(rs)
    base = build_report(run).split("== Baseline ==")[1]
    simulated = number_after(base, "Simulated average final points")  # 15.2 in the fixture
    assert simulated < realistic < baseline_maximum(rs) == 151
    assert 20 < realistic < 35  # the draw limit sweep in test_baseline_maximum.py shows 25 to 27


def test_realistic_maximum_other_rulesets():
    rs = load_ruleset("v1")
    one = realistic_baseline_maximum(with_rounds(rs, 1))
    three = realistic_baseline_maximum(with_rounds(rs, 3))
    assert 0 < one <= three
    # 3 rounds instead of 9: the same check (a cheaper shop raises the maximum), much faster
    cheap = realistic_baseline_maximum(
        apply_overrides(with_rounds(rs, 3), {"shop.points_2.price": "1"})
    )
    assert cheap > three


def test_purchase_tie_is_the_average_over_the_tied_items():
    # The bot picks one of the items with the most points at random, not the cheapest.
    rs = load_ruleset("v1")
    a = next(i for i in rs.shop if i.kind == "points")
    cheap = a.model_copy(update={"id": "t_cheap", "price": 2, "points": 2})
    dear = a.model_copy(update={"id": "t_dear", "price": 6, "points": 2})
    one = rs.model_copy(update={"shop": [cheap, dear], "max_purchases": 1})
    two = rs.model_copy(update={"shop": [cheap, dear], "max_purchases": 2})
    assert _points_for_money(one, 6) == 2
    # cheap first: 2 + 2 (4 money left buys cheap again); dear first: 2 + nothing; average 3
    assert _points_for_money(two, 6) == 3


def test_realistic_maximum_one_round_by_hand():
    # Round 1 is also the last round (money x 1.5), with at most 3 purchases: a short brew
    # gives a few points, far below the loose bound of one round.
    value = realistic_baseline_maximum(with_rounds(load_ruleset("v1"), 1))
    assert 2 < value < 12


def test_baseline_maximum_is_games_weighted_over_a_sweep(run):
    config = json.loads((run / "config.json").read_text())
    config["sweep"] = {"param": "shop.points_2.price", "values": ["1", "6"]}
    config["rounds"] = 3  # the maximum is calculated per round count; 3 rounds are much faster
    (run / "config.json").write_text(json.dumps(config))
    rows = []
    for value, games in (("1", 2), ("6", 1)):
        for _ in range(games):
            r = dict.fromkeys(CSV_COLUMNS, 0)
            r.update(
                pairing="draw20-pts1-points vs draw30-pts3-blue",
                p1="draw20-pts1-points",
                p2="draw30-pts3-blue",
                sweep_value=value,
                winner="p1",
                p1_points=10,
            )
            rows.append(r)
    write_rows(run, rows)
    rs = with_rounds(load_ruleset("v1"), 3)
    low = realistic_baseline_maximum(apply_overrides(rs, {"shop.points_2.price": "1"}))
    high = realistic_baseline_maximum(apply_overrides(rs, {"shop.points_2.price": "6"}))
    assert low != high
    base = build_report(run).split("== Baseline ==")[1]
    expected = (2 * low + high) / 3
    assert number_after(base, "Calculated maximum (realistic") == pytest.approx(expected, abs=0.05)
