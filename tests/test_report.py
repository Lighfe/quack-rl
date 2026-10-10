import csv
import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from quack_rl.cli.main import app
from quack_rl.report import (
    CONFIRM_TEST,
    CONFIRM_TOLERANCE,
    baseline_maximum,
    build_report,
    _points_for_money,
    realistic_baseline_maximum,
    wilson,
)
from quack_rl.rules import apply_overrides, load_ruleset, with_rounds
from quack_rl.tournament import CSV_COLUMNS, TournamentConfig, write_run

FIXTURE = Path(__file__).parent / "fixtures" / "report"
runner = CliRunner()


@pytest.fixture
def run(tmp_path):
    folder = tmp_path / "run"
    shutil.copytree(FIXTURE, folder)
    return folder


def write_rows(folder: Path, rows: list[dict]) -> None:
    with (folder / "results.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def seat_rows(p1_wins: int, p2_wins: int, draws: int = 0) -> list[dict]:
    rows = []
    for winner in ["p1"] * p1_wins + ["p2"] * p2_wins + ["draw"] * draws:
        r = dict.fromkeys(CSV_COLUMNS, 0)
        r.update(
            pairing="seatcheck:draw30-pts3-blue",
            p1="draw30-pts3-blue",
            p2="draw30-pts3-blue",
            sweep_value="",
            winner=winner,
        )
        rows.append(r)
    return rows


def test_wilson_known_case():
    lo, hi = wilson(50, 100)
    assert (round(100 * lo, 1), round(100 * hi, 1)) == (40.4, 59.6)


def test_ranking_order_and_sections(run):
    text = build_report(run)
    ranking = text.split("== Ranking ==")[1].split("==")[0]
    bots = [line.split()[0] for line in ranking.splitlines() if line.startswith("draw")]
    assert bots == ["draw30-pts3-blue", "draw30-pts1-points", "draw15-pts3-blue"]
    assert "60.4%" in ranking and "n=24" in ranking  # 14 wins and a draw of 24
    assert "52.1%" in ranking  # 12 wins and a draw of 24
    for heading in (
        "== Sweeps: blue ==",
        "== Item usage of winning bots ==",
        "== Explosion share and game length ==",
        "== Seat check ==",
        "== Baseline ==",
    ):
        assert heading in text
    assert "== Sweeps: green ==" not in text  # a strategy absent from the run is left out


def test_sweep_cell_value(run):
    text = build_report(run)
    by_limit = text.split("-- blue: by draw limit --")[1].split("--")[0]
    (row,) = [line for line in by_limit.splitlines() if line.startswith("30 ")]
    assert "n=24 | expl 5.6% | pts 16.0" in row  # 12 of 216 potions, 385 points of 24 games
    combined = text.split("draw limit (rows) x points round (columns) --")[1]
    assert "pts 3" in combined


def test_item_usage_and_length(run):
    text = build_report(run)
    items = text.split("== Item usage of winning bots ==")[1].split("==")[0]
    assert "blue_1" in items and "points_2" in items
    blue_1 = [line for line in items.splitlines() if line.startswith("blue_1")][0].split()
    assert blue_1[1:] == ["2.00", "0.00"]  # columns blue, points
    length = text.split("== Explosion share and game length ==")[1]
    overall = [line for line in length.splitlines() if line.startswith("overall")][0]
    assert "11.00" in overall  # 5 + 6 draws in every game


def test_seat_check_deviation_and_ok(run):
    write_rows(run, seat_rows(70, 30))
    deviation = build_report(run)
    assert "Seat check: DEVIATION" in deviation and "n=100" in deviation
    write_rows(run, seat_rows(52, 48))
    assert "Seat check: OK" in build_report(run)


def test_no_seat_check_line(run):
    assert "Seat check: no seatcheck run in this folder" in build_report(run)


def test_baseline_lines(run):
    text = build_report(run)
    base = text.split("== Baseline ==")[1]
    assert "Simulated average final points: 15.2" in base  # 365 points in 24 games
    assert "Calculated maximum" in base and "Difference" in base
    rows = [
        r
        for r in csv.DictReader((run / "results.csv").open())
        if "points" not in r["p1"] and "points" not in r["p2"]
    ]
    write_rows(run, rows)
    assert "is not in this run" in build_report(run).split("== Baseline ==")[1]


def test_baseline_maximum_v1():
    rs = with_rounds(load_ruleset("v1"), 9)
    # 8 rounds: money 35 + 1 -> 36, three purchases: 22 + 13 = 35 money -> 15 points, +1 die point
    # last round: 36 * 150 // 100 = 54 -> 22 + 22 + 6 = 50 money -> 22 points (10+10+2), +1
    assert baseline_maximum(rs) == 8 * (15 + 1) + (22 + 1)


def number_after(text: str, label: str) -> float:
    (line,) = [x for x in text.splitlines() if x.startswith(label)]
    return float(line.rsplit(":", 1)[1])


def test_loose_bound_stays_and_is_labelled():
    assert "loose upper bound" in baseline_maximum.__doc__.lower()


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
    cheap = realistic_baseline_maximum(apply_overrides(rs, {"shop.points_2.price": "1"}))
    assert cheap > realistic_baseline_maximum(rs)


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


def test_baseline_labels_and_order(run):
    base = build_report(run).split("== Baseline ==")[1].strip().splitlines()
    starts = [
        "Baseline draw30-pts1-points: 24 games",
        "Simulated average final points:",
        "Calculated maximum (realistic, ",
        "Difference (maximum - simulated):",
        "The maximum is confirmed by simulation in ",
        "Calculated maximum (loose upper bound",
    ]
    assert len(base) == len(starts)
    for line, start in zip(base, starts, strict=True):
        assert line.startswith(start), (line, start)
    assert CONFIRM_TEST in base[4] and f"{100 * CONFIRM_TOLERANCE:.0f}%" in base[4]
    assert number_after("\n".join(base), "Calculated maximum (loose") == 151.0


def test_baseline_maximum_is_games_weighted_over_a_sweep(run):
    config = json.loads((run / "config.json").read_text())
    config["sweep"] = {"param": "shop.points_2.price", "values": ["1", "6"]}
    (run / "config.json").write_text(json.dumps(config))
    rows = []
    for value, games in (("1", 2), ("6", 1)):
        for _ in range(games):
            r = dict.fromkeys(CSV_COLUMNS, 0)
            r.update(
                pairing="draw30-pts1-points vs draw30-pts3-blue",
                p1="draw30-pts1-points",
                p2="draw30-pts3-blue",
                sweep_value=value,
                winner="p1",
                p1_points=10,
            )
            rows.append(r)
    write_rows(run, rows)
    rs = with_rounds(load_ruleset("v1"), 9)
    low = realistic_baseline_maximum(apply_overrides(rs, {"shop.points_2.price": "1"}))
    high = realistic_baseline_maximum(apply_overrides(rs, {"shop.points_2.price": "6"}))
    assert low != high
    base = build_report(run).split("== Baseline ==")[1]
    expected = (2 * low + high) / 3
    assert number_after(base, "Calculated maximum (realistic") == pytest.approx(expected, abs=0.05)


def test_missing_column_and_files(run, tmp_path):
    text = (run / "results.csv").read_text()
    (run / "results.csv").write_text(text.replace("p1_draws", "p1_dr", 1))
    result = runner.invoke(app, ["report", str(run)])
    assert result.exit_code != 0
    assert "Error:" in result.output and "p1_draws" in result.output
    assert "Traceback" not in result.output and not (run / "report.txt").exists()
    result = runner.invoke(app, ["report", str(tmp_path / "nothing")])
    assert result.exit_code != 0 and result.output.startswith("Error:")


def test_report_cli_writes_file_and_is_deterministic(run):
    first = runner.invoke(app, ["report", str(run)])
    assert first.exit_code == 0, first.output
    written = (run / "report.txt").read_bytes()
    assert written.decode() == first.output
    second = runner.invoke(app, ["report", str(run)])
    assert (run / "report.txt").read_bytes() == written == second.output.encode()


def test_new_columns_match_the_record(tmp_path):
    from quack_rl.record import read_games

    config = TournamentConfig(
        bots=("bot:draw30-pts3-blue", "bot:draw15-pts1-balanced"),
        games=2,
        seed=3,
        keep_records=True,
        sample_size=0,
    )
    folder, rows = write_run(config, tmp_path)
    assert list(rows[0]) == CSV_COLUMNS
    games = [g for s in sorted((folder / "records").glob("*.gz")) for g in read_games(s)]
    assert len(games) == len(rows)
    for row, game in zip(rows, games, strict=True):
        events = [e for step in game.steps for e in step.events]
        for seat in ("p1", "p2"):
            buys = sum(1 for e in events if e["kind"] == "buy" and e["seat"] == seat)
            placed = sum(1 for e in events if e["kind"] == "place" and e["seat"] == seat)
            assert sum(v for k, v in row.items() if k.startswith(f"{seat}_buy_")) == buys
            assert row[f"{seat}_draws"] == placed


def test_missing_p1_buy_column_is_an_error(run):
    with (run / "results.csv").open(newline="") as f:
        rows = list(csv.reader(f))
    drop = rows[0].index("p1_buy_blue_1")
    (run / "results.csv").write_text(
        "".join(",".join(c for i, c in enumerate(r) if i != drop) + "\n" for r in rows)
    )
    result = runner.invoke(app, ["report", str(run)])
    assert result.exit_code != 0
    assert "Error:" in result.output and "p1_buy_blue_1" in result.output
    assert not (run / "report.txt").exists()


def test_item_missing_for_both_seats_is_an_error(run):
    with (run / "results.csv").open(newline="") as f:
        rows = list(csv.reader(f))
    drop = {rows[0].index("p1_buy_blue_1"), rows[0].index("p2_buy_blue_1")}
    (run / "results.csv").write_text(
        "".join(",".join(c for i, c in enumerate(r) if i not in drop) + "\n" for r in rows)
    )
    result = runner.invoke(app, ["report", str(run)])
    assert result.exit_code != 0
    assert "Error:" in result.output and "blue_1" in result.output
    assert "Traceback" not in result.output
    assert not (run / "report.txt").exists()


def test_seat_check_only_run_fills_bot_sections(run):
    rows = seat_rows(3, 2, 1)
    rows[0].update(p1_points=9, p2_points=2, p1_draws=4, p2_draws=5, p1_buy_blue_1=2)
    write_rows(run, rows)
    text = build_report(run)
    assert "No games." not in text
    assert "No heuristic bot" not in text
    assert "Seat check: " in text and "draw30-pts3-blue" in text
    explosions = text.split("== Explosion share and game length ==")[1]
    assert "blue" in explosions and "overall" in explosions
    items = text.split("== Item usage of winning bots ==")[1]
    assert "blue_1" in items and "-" in items
