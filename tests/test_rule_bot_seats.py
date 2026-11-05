"""The bot name form `bot:<strategy>-draw<limit>-pts<round>` everywhere (issue #270).

The old heuristic bot and its form `draw<limit>-pts<round>-<strategy>` are gone; every caller
builds a `RuleBot`. The old-form names below are inputs of rejection tests only.
"""

import csv
import importlib.util
import re
from pathlib import Path

import pytest
import typer
from helpers import RS
from typer.testing import CliRunner

from quack_rl.cli.main import app
from quack_rl.cli.seats import BOT_FORM, check_seat, parse_seat
from quack_rl.rl.opponents import make_opponent
from quack_rl.tournament import TournamentError, field_specs

ROOT = Path(__file__).parent.parent
runner = CliRunner()
OLD_CLASS = "Heuristic" + "Bot"  # split, so this file does not name the old class
OLD_FORM = re.compile(r"draw[0-9]+-pts[0-9]+-[a-z]|" + OLD_CLASS)
BASELINE = "topchip-draw20-pts1"


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- seats -----------------------------------------------------------------------------------


def test_bot_form_names_the_new_order():
    assert BOT_FORM == "bot:<strategy>-draw<percent>-pts<round>"


@pytest.mark.parametrize(
    "spec", ["bot:topchip-draw20-pts4", "bot:spendmost-draw0-pts6", "bot:blackpurple-draw100-pts9"]
)
def test_check_seat_accepts_the_new_form(spec):
    check_seat(spec)


@pytest.mark.parametrize(
    "spec", ["bot:draw20-pts1-points", "bot:draw30-pts3-blue", "bot:nosuch-draw20-pts4"]
)
def test_check_seat_rejects_the_old_form_and_names_the_new_one(spec):
    with pytest.raises(typer.BadParameter) as err:
        check_seat(spec)
    assert BOT_FORM in str(err.value)
    assert spec in str(err.value)


def test_parse_seat_builds_a_rule_bot():
    from quack_rl.bots import RuleBot

    bot = parse_seat("bot:spendmost-draw0-pts6", 3, rs=RS)
    assert isinstance(bot, RuleBot)
    assert bot.name == "spendmost-draw0-pts6"
    assert bot.params["strategy"] == "spendmost"
    assert bot.params["draw_limit"] == 0
    assert bot.params["points_round"] == 6
    assert bot.params["seed"] == 3


@pytest.mark.parametrize("name", ["spendmost-draw0-pts6", "bot:spendmost-draw0-pts6"])
def test_make_opponent_builds_a_rule_bot(name):
    from quack_rl.bots import RuleBot

    bot = make_opponent(name, seed=1)
    assert isinstance(bot, RuleBot)
    assert bot.name == "spendmost-draw0-pts6"


def test_make_opponent_rejects_the_old_form():
    with pytest.raises(ValueError, match=re.escape("<strategy>-draw<percent>-pts<round>")):
        make_opponent("draw20-pts1-points")


def test_cli_rejects_the_old_form_cleanly(tmp_path):
    result = runner.invoke(
        app, ["simulate", "--p1", "bot:draw20-pts1-points", "--games", "1", "--out", str(tmp_path)]
    )
    assert result.exit_code != 0
    assert "bot:draw20-pts1-points" in result.output
    assert "Traceback" not in result.output


# --- package exports -------------------------------------------------------------------------


def test_package_exports_the_rule_bot_api():
    import quack_rl.bots as bots
    from quack_rl.bots import (
        STRATEGIES,
        RandomBot,
        RuleBot,
        bot_name,
        core,
        explosion_chance,
        parse_bot_name,
        rule_bot,
        strategy,
    )

    assert RuleBot is rule_bot.RuleBot
    assert bot_name is rule_bot.bot_name and parse_bot_name is rule_bot.parse_bot_name
    assert STRATEGIES is strategy.STRATEGIES
    assert explosion_chance is core.explosion_chance
    assert RandomBot(1).choose is not None
    assert bot_name("topchip", 20, 4) == "topchip-draw20-pts4"
    assert parse_bot_name("bot:topchip-draw20-pts4") == ("topchip", 20, 4)
    assert not hasattr(bots, OLD_CLASS)


def test_heuristic_module_is_gone():
    assert not (ROOT / "src" / "quack_rl" / "bots" / "heuristic.py").exists()
    assert importlib.util.find_spec("quack_rl.bots.heuristic") is None


# --- fields ----------------------------------------------------------------------------------


def test_full_field_has_19_specs():
    specs = field_specs("full")
    expected = [
        f"bot:{s}-draw{d}-pts{p}"
        for s in ("topchip", "spendmost", "blackpurple")
        for d in (0, 20, 40)
        for p in (4, 6)
    ] + ["bot:random"]
    assert list(specs) == expected
    assert len(specs) == 19 == len(set(specs))
    for spec in specs:
        check_seat(spec)


def test_small_field_has_13_specs():
    specs = field_specs("small")
    expected = [
        f"bot:{s}-draw{d}-pts{p}"
        for s in ("topchip", "spendmost", "blackpurple")
        for d in (10, 20)
        for p in (4, 6)
    ] + ["bot:random"]
    assert list(specs) == expected
    assert len(specs) == 13 == len(set(specs))


def test_unknown_field_is_an_error():
    with pytest.raises(TournamentError, match="nosuch"):
        field_specs("nosuch")


def test_readme_field_line_states_19_and_13():
    (line,) = [x for x in (ROOT / "README.md").read_text().splitlines() if "(`--field`)" in x]
    assert "`full` (19 bots" in line and "`small` (13 bots" in line


def test_tournament_with_the_new_form_runs(tmp_path):
    result = runner.invoke(
        app,
        [
            "tournament",
            "--bots",
            "bot:blackpurple-draw40-pts4,bot:random",
            "--games",
            "4",
            "--seed",
            "1",
            "--out",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    (results,) = tmp_path.glob("*/results.csv")
    with results.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 4
    assert {r["p1"] for r in rows} | {r["p2"] for r in rows} == {
        "blackpurple-draw40-pts4",
        "random",
    }


# --- the old default bot ---------------------------------------------------------------------


def test_report_baseline_is_topchip_draw20_pts1():
    from quack_rl import report

    assert report.BASELINE_NAME == BASELINE
    assert report.SWEEP_STRATEGIES == ("topchip", "spendmost", "blackpurple")


def test_selfplay_evaluation_opponent():
    from quack_rl.rl import selfplay

    assert selfplay.HEURISTIC_OPPONENT == f"bot:{BASELINE}"


def test_offline_evaluation_opponent():
    pytest.importorskip("torch")
    from quack_rl.rl import offline

    assert offline.HEURISTIC_OPPONENT == f"bot:{BASELINE}"


def test_build_dataset_bot():
    assert load_script("build_dataset").BOT == f"bot:{BASELINE}"


def test_train_selfplay_evaluation_label():
    assert f'("bot:{BASELINE}", result.against_heuristic)' in (
        ROOT / "scripts" / "train_selfplay.py"
    ).read_text()


def test_readme_play_example():
    assert f"uv run quack-rl play --p2 bot:{BASELINE}" in (ROOT / "README.md").read_text()


def test_measure_speed_bots():
    assert load_script("measure_speed").BOTS == (
        "bot:random",
        "bot:topchip-draw30-pts3",
        "bot:spendmost-draw30-pts3",
        "bot:blackpurple-draw30-pts3",
    )


# --- no old form left ------------------------------------------------------------------------


def _files(*parts: str):
    for part in parts:
        path = ROOT / part
        if path.is_file():
            yield path
        else:
            yield from (p for p in path.rglob("*") if p.is_file() and "__pycache__" not in p.parts)


def test_no_old_form_in_code_scripts_readme_and_skills():
    hits = [
        f"{p.relative_to(ROOT)}:{n}"
        for p in _files("src", "scripts", "README.md", ".agents")
        for n, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1)
        if OLD_FORM.search(line)
    ]
    assert hits == []


def test_old_form_in_tests_only_in_the_rejection_tests():
    allowed = {"test_rule_bot.py", "test_rule_bot_seats.py"}
    hits = {
        p.name
        for p in _files("tests")
        if p.suffix in (".py", ".csv", ".json", ".jsonl")
        and OLD_FORM.search(p.read_text(encoding="utf-8", errors="ignore"))
    }
    assert hits <= allowed


# --- stale RL reports ------------------------------------------------------------------------

STALE = (
    "2026-10-offline-rl.md",
    "2026-10-rl-env-test.md",
    "2026-10-rl-vs-bots.md",
    "2026-10-selfplay.md",
)


@pytest.mark.parametrize("name", STALE)
def test_stale_reports_are_archived(name):
    assert (ROOT / "archive" / "docs" / "analysis" / name).is_file()
    assert not (ROOT / "docs" / "analysis" / name).exists()


def test_readme_names_the_stale_reports_only_by_the_archive_path():
    text = (ROOT / "README.md").read_text()
    for name in STALE:
        assert f"archive/docs/analysis/{name}" in text
        for m in re.finditer(re.escape(name), text):
            assert text[: m.start()].endswith("archive/docs/analysis/"), name
    assert "`docs/analysis/`" not in text
