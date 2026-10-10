"""Tests for the marimo notebook notebooks/tournament_run.py (issue #44).

The run fixtures are hand-made and written to `tmp_path`: results.csv with the columns of
`quack-rl tournament`, and seats.parquet through the tournament writer, so both have the
layout of the README sections "Tournament run folder" and "`seats.parquet`".
"""

import csv
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import polars as pl
import pytest

from quack_rl.report import build_report
from quack_rl.rules import load_ruleset, with_rounds
from quack_rl.tournament import CSV_COLUMNS, write_seats_parquet

ROOT = Path(__file__).resolve().parent.parent
NOTEBOOK = ROOT / "notebooks" / "tournament_run.py"
ROUNDS = 3
RULESET = with_rounds(load_ruleset("v1"), ROUNDS)
CHIPS = [c.id for c in RULESET.chips]

A = "draw10-pts4-blue"
B = "draw20-pts6-green"


def _load_notebook():
    spec = importlib.util.spec_from_file_location("tournament_run_notebook", NOTEBOOK)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


nb = _load_notebook()


# (pairing, p1, p2, winner, p1_points, p2_points, sweep_value)
GAMES = [
    (f"{A} vs {B}", A, B, "p1", 30, 20, ""),
    (f"{B} vs {A}", B, A, "draw", 25, 25, ""),  # the draw; A sits in p2 here, in p1 above
    (f"{A} vs {A}", A, A, "p2", 10, 40, ""),  # the same bot in both seats
    (f"seatcheck:{B}", B, B, "p1", 99, 0, ""),  # left out
]
SEATCHECK_GAMES = [
    (f"seatcheck:{B}", B, B, "p1", 99, 0, ""),
    (f"seatcheck:{B}", B, B, "draw", 30, 30, ""),
]

# per game: (p1 seat, p2 seat); a seat is (money per round, points per round, bag counts)
SEATS = [
    (
        ([5, 7, 9], [1, 3, 30], {"white_1": 4, "orange_1": 1, "blue_1": 2}),
        ([6, 8, 10], [2, 5, 20], {"white_1": 4, "green_1": 3}),
    ),
    (
        ([4, 6, 8], [3, 9, 25], {"white_1": 5, "green_1": 1}),
        ([7, 9, 11], [2, 6, 25], {"white_1": 4, "orange_1": 3}),
    ),
    (
        ([3, 5, 7], [0, 2, 10], {"white_1": 6, "blue_1": 2}),
        ([9, 11, 13], [4, 10, 40], {"white_1": 2, "blue_1": 4}),
    ),
    (
        ([100, 100, 100], [50, 60, 99], {"white_1": 100}),
        ([0, 0, 0], [0, 0, 0], {}),
    ),
]
SEATCHECK_SEATS = [
    SEATS[3],
    (
        ([2, 2, 2], [10, 20, 30], {"white_1": 10}),
        ([4, 4, 4], [10, 20, 30], {"white_1": 20}),
    ),
]


def results_rows(games) -> list[dict]:
    rows = []
    for i, (pairing, p1, p2, winner, pts1, pts2, sweep) in enumerate(games):
        row = dict.fromkeys(CSV_COLUMNS, 0)
        row.update(
            pairing=pairing,
            p1=p1,
            p2=p2,
            game=i,
            seed=1000 + i,
            sweep_value=sweep,
            winner=winner,
            p1_points=pts1,
            p2_points=pts2,
        )
        rows.append(row)
    return rows


def seat_rows(games, seats) -> list[dict]:
    rows = []
    for i, ((pairing, p1, p2, *_rest), pair) in enumerate(zip(games, seats, strict=True)):
        sweep = _rest[-1]
        for seat, bot, (money, points, bag) in zip(("p1", "p2"), (p1, p2), pair, strict=True):
            row = {
                "pairing": pairing,
                "sweep_value": sweep,
                "game": i,
                "seed": 1000 + i,
                "seat": seat,
                "bot": bot,
            }
            for k in range(1, ROUNDS + 1):
                row[f"money_r{k}"] = money[k - 1]
                row[f"points_r{k}"] = points[k - 1]
            for chip in CHIPS:
                row[f"bag_{chip}"] = bag.get(chip, 0)
            rows.append(row)
    return rows


def write_run(folder: Path, games, seats, with_seats: bool = True) -> Path:
    folder.mkdir(parents=True)
    config = {
        "bots": [f"bot:{A}", f"bot:{B}"],
        "games": 1,
        "seed": 1000,
        "rules": "v1",
        "rounds": ROUNDS,
        "overrides": {},
        "sweep": None,
        "workers": 1,
        "seat_check": False,
        "name": "notebook-fixture",
    }
    (folder / "config.json").write_text(json.dumps(config), encoding="utf-8")
    with (folder / "results.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(results_rows(games))
    if with_seats:
        write_seats_parquet(folder / "seats.parquet", seat_rows(games, seats), RULESET)
    return folder


@pytest.fixture
def run(tmp_path) -> Path:
    return write_run(tmp_path / "2026-10-10_12-00-00+0200-fixture", GAMES, SEATS)


@pytest.fixture
def seatcheck_run(tmp_path) -> Path:
    return write_run(tmp_path / "seatcheck-only", SEATCHECK_GAMES, SEATCHECK_SEATS)


def read(folder: Path) -> tuple[pl.DataFrame, pl.DataFrame]:
    return nb.read_results(folder / "results.csv"), pl.read_parquet(folder / "seats.parquet")


def rows_by_bot(df: pl.DataFrame) -> dict[str, dict]:
    return {r["bot"]: r for r in df.iter_rows(named=True)}


# --- ranking ---------------------------------------------------------------------------


def test_ranking_values_and_order(run):
    results, _ = read(run)
    ranked = nb.ranking(results)
    assert ranked.columns == ["bot", "win_rate", "low", "high", "avg_points", "games"]
    assert ranked["bot"].to_list() == [A, B]  # sorted by win rate; seat check row left out
    a, b = ranked.row(0, named=True), ranked.row(1, named=True)
    # A: win (p1), draw (p2), loss (p1) and win (p2) in the game against itself
    assert a["games"] == 4
    assert a["win_rate"] == pytest.approx(0.625)
    assert a["low"] == pytest.approx(0.2194265181)
    assert a["high"] == pytest.approx(0.9081007718)
    assert a["avg_points"] == pytest.approx(26.25)
    # B: loss (p2) and draw (p1); the seat check game (a p1 win with 99 points) is left out
    assert b["games"] == 2
    assert b["win_rate"] == pytest.approx(0.25)
    assert b["low"] == pytest.approx(0.0266773417)
    assert b["high"] == pytest.approx(0.8021325464)
    assert b["avg_points"] == pytest.approx(22.5)


def test_ranking_uses_seat_check_rows_when_run_has_only_those(seatcheck_run):
    results, _ = read(seatcheck_run)
    ranked = nb.ranking(results)
    assert ranked["bot"].to_list() == [B]
    b = ranked.row(0, named=True)
    # 2 games, B in both seats: win + loss + draw + draw = 2 wins of 4
    assert b["games"] == 4
    assert b["win_rate"] == pytest.approx(0.5)
    assert b["low"] == pytest.approx(0.1500389877)
    assert b["high"] == pytest.approx(0.8499610123)
    assert b["avg_points"] == pytest.approx(39.75)


def test_ranking_order_ties_by_points_then_name():
    games = [
        ("x", "c", "a", "draw", 10, 10, ""),
        ("y", "b", "d", "draw", 20, 5, ""),
    ]
    ranked = nb.ranking(pl.DataFrame(results_rows(games)))
    # all at 50%: b (20 pts), then a and c (10 pts, by name), then d (5 pts)
    assert ranked["bot"].to_list() == ["b", "a", "c", "d"]


def test_ranking_pools_sweep_values():
    games = [
        (f"{A} vs {B}", A, B, "p1", 10, 0, "1"),
        (f"{A} vs {B}", A, B, "p2", 0, 10, "2"),
    ]
    ranked = rows_by_bot(nb.ranking(pl.DataFrame(results_rows(games))))
    assert set(ranked) == {A, B}
    assert ranked[A]["games"] == 2 and ranked[A]["win_rate"] == pytest.approx(0.5)


def _report_ranking(folder: Path) -> dict[str, tuple[float, float, float, float, int]]:
    text = build_report(folder)
    section = text.split("== Ranking ==")[1].split("\n\n")[0]
    pattern = re.compile(
        r"^(\S+)\s+(\d+)\s+([\d.]+)% \[([\d.]+)-([\d.]+)%\] n=\d+\s+([\d.]+)$", re.M
    )
    return {
        m[1]: (float(m[3]), float(m[4]), float(m[5]), float(m[6]), int(m[2]))
        for m in pattern.finditer(section)
    }


@pytest.mark.parametrize("which", ["run", "seatcheck_run"])
def test_ranking_matches_quack_rl_report(which, request):
    folder = request.getfixturevalue(which)
    expected = _report_ranking(folder)
    assert expected  # the report printed a ranking
    results, _ = read(folder)
    ranked = nb.ranking(results)
    got = {
        r["bot"]: (
            round(100 * r["win_rate"], 1),
            round(100 * r["low"], 1),
            round(100 * r["high"], 1),
            round(r["avg_points"], 1),
            r["games"],
        )
        for r in ranked.iter_rows(named=True)
    }
    assert got == expected
    assert ranked["bot"].to_list() == list(expected)  # same order as the report


# --- end bags --------------------------------------------------------------------------


def test_end_bags(run):
    _, seats = read(run)
    bags = nb.end_bags(seats)
    assert bags.columns == ["bot", *CHIPS, "games"]  # chip ids in file order
    got = rows_by_bot(bags)
    assert set(got) == {A, B}
    expected = {
        A: {"white_1": 4.0, "orange_1": 1.0, "blue_1": 2.0, "games": 4},
        B: {"white_1": 4.5, "green_1": 2.0, "games": 2},
    }
    for bot, values in expected.items():
        for column in [*CHIPS, "games"]:
            assert got[bot][column] == pytest.approx(values.get(column, 0.0)), (bot, column)


def test_end_bags_seat_check_only(seatcheck_run):
    _, seats = read(seatcheck_run)
    got = rows_by_bot(nb.end_bags(seats))
    assert got[B]["games"] == 4
    assert got[B]["white_1"] == pytest.approx(32.5)


def test_end_bags_chip_ids_come_from_columns():
    seats = pl.DataFrame(
        {"pairing": ["p"], "bot": ["x"], "bag_zeta": [3], "bag_alpha": [1], "money_r1": [2]}
    )
    assert nb.end_bags(seats).columns == ["bot", "zeta", "alpha", "games"]


# --- per bot rounds --------------------------------------------------------------------


def test_per_bot_rounds(run):
    _, seats = read(run)
    rounds = nb.per_bot_rounds(seats)
    assert rounds.columns == ["bot", "round", "money", "points", "games"]
    assert rounds.height == 2 * ROUNDS  # long form: one row per bot and round
    got = {(r["bot"], r["round"]): r for r in rounds.iter_rows(named=True)}
    expected = {
        (A, 1): (6.0, 1.75, 4),
        (A, 2): (8.0, 5.25, 4),
        (A, 3): (10.0, 26.25, 4),
        (B, 1): (5.0, 2.5, 2),
        (B, 2): (7.0, 7.0, 2),
        (B, 3): (9.0, 22.5, 2),
    }
    assert set(got) == set(expected)
    for key, (money, points, games) in expected.items():
        assert got[key]["money"] == pytest.approx(money), key
        assert got[key]["points"] == pytest.approx(points), key
        assert got[key]["games"] == games, key


def test_per_bot_rounds_seat_check_only(seatcheck_run):
    _, seats = read(seatcheck_run)
    got = {(r["bot"], r["round"]): r for r in nb.per_bot_rounds(seats).iter_rows(named=True)}
    assert got[(B, 1)]["money"] == pytest.approx(26.5)
    assert got[(B, 3)]["points"] == pytest.approx(39.75)
    assert got[(B, 3)]["games"] == 4


def test_per_bot_rounds_rounds_come_from_columns():
    seats = pl.DataFrame(
        {
            "pairing": ["p", "p"],
            "bot": ["x", "x"],
            **{f"money_r{k}": [k, k + 2] for k in range(1, 6)},
            **{f"points_r{k}": [10 * k, 0] for k in range(1, 6)},
        }
    )
    rounds = nb.per_bot_rounds(seats)
    assert rounds["round"].to_list() == [1, 2, 3, 4, 5]
    assert rounds["money"].to_list() == pytest.approx([2, 3, 4, 5, 6])


def test_round_chart_with_no_bot_selected(run):
    _, seats = read(run)
    rounds = nb.per_bot_rounds(seats)
    for column in ("money", "points"):
        empty = nb.round_chart(rounds, [], column, "title").to_dict()
        assert empty["datasets"] == {} or all(v == [] for v in empty["datasets"].values())
        full = nb.round_chart(rounds, [A, B], column, "title").to_dict()
        assert sum(len(v) for v in full["datasets"].values()) == 2 * ROUNDS


# --- run folder choice -----------------------------------------------------------------


def test_run_folders_lists_only_complete_folders(tmp_path):
    root = tmp_path / "tournaments"
    write_run(root / "2026-10-10_10-00-00+0200-a", GAMES, SEATS)
    write_run(root / "2026-10-10_11-00-00+0200-b", GAMES, SEATS)
    write_run(root / "2026-10-10_12-00-00+0200-old", GAMES, SEATS, with_seats=False)
    names = [p.name for p in nb.run_folders(root)]
    assert names == ["2026-10-10_10-00-00+0200-a", "2026-10-10_11-00-00+0200-b"]
    assert nb.run_folders(tmp_path / "missing") == []
    assert nb.missing_files(root / "2026-10-10_12-00-00+0200-old") == ["seats.parquet"]


# --- whole notebook --------------------------------------------------------------------


def export(folder: Path, out: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "marimo",
            "export",
            "html",
            str(NOTEBOOK),
            "-o",
            str(out),
            "--",
            "--run-folder",
            str(folder),
        ],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=ROOT,
    )


def test_notebook_runs_on_a_run_folder(run, tmp_path):
    out = tmp_path / "out.html"
    proc = export(run, out)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    html = out.read_text(encoding="utf-8")
    assert "notebook-fixture" in html  # the run name from config.json
    assert A in html and B in html


def test_notebook_without_seats_parquet_shows_message(tmp_path):
    folder = write_run(tmp_path / "before-43-run", GAMES, SEATS, with_seats=False)
    out = tmp_path / "out.html"
    proc = export(folder, out)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    html = out.read_text(encoding="utf-8")
    assert "before-43-run" in html
    assert "lacks seats.parquet" in html
