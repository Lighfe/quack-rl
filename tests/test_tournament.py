import csv
import gzip
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import quack_rl.cli.main as cli_main
from quack_rl.cli.main import app
from quack_rl.record import read_games
from quack_rl.tournament import (
    CSV_COLUMNS,
    TournamentConfig,
    TournamentError,
    parse_sweep,
    validate,
    verify_sample,
)

runner = CliRunner()
BOTS = "bot:draw30-pts3-blue,bot:draw15-pts8-cleaner,bot:random"
TRACEBACK = "Traceback (most recent call last)"


def tour(out: Path, *extra: str, bots: str = BOTS, games: str = "3"):
    return runner.invoke(
        app,
        ["tournament", "--bots", bots, "--games", games, "--seed", "5", "--out", str(out), *extra],
    )


def runs(out: Path) -> list[Path]:
    return sorted(p for p in out.glob("*") if p.is_dir())


def read_rows(run: Path) -> list[dict]:
    with (run / "results.csv").open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_help_lists_every_input():
    result = runner.invoke(app, ["tournament", "--help"])
    assert result.exit_code == 0
    for option in (
        "--bots",
        "--games",
        "--seed",
        "--rules",
        "--set",
        "--sweep",
        "--workers",
        "--name",
        "--seat-check",
        "--keep-records",
        "--sample-size",
    ):
        assert option in result.output, option


def test_run_writes_config_and_results(tmp_path):
    result = tour(tmp_path, "--name", "demo", "--set", "shop.orange_1.price=9")
    assert result.exit_code == 0, result.output
    (run,) = runs(tmp_path)
    assert run.name.endswith("-demo")
    config = json.loads((run / "config.json").read_text(encoding="utf-8"))
    assert config["bots"] == BOTS.split(",")
    assert config["games"] == 3 and config["seed"] == 5 and config["rules"] == "v1"
    assert config["overrides"] == {"shop.orange_1.price": "9"}
    assert config["sweep"] is None and config["workers"] == 1
    rows = read_rows(run)
    assert len(rows) == 3 * 3  # 3 pairings, 3 games each
    assert list(rows[0]) == CSV_COLUMNS
    assert {r["winner"] for r in rows} <= {"p1", "p2", "draw"}
    assert all(r["sweep_value"] == "" for r in rows)  # no sweep: the column is empty
    assert not (run / "records").exists()  # no records by default
    assert not (run / "report.txt").exists()
    row = rows[0]
    assert row["pairing"] == "draw30-pts3-blue vs draw15-pts8-cleaner"
    assert (row["game"], row["seed"]) == ("0", "5")


def test_pairings_are_all_pairs_with_fixed_seats(tmp_path):
    assert tour(tmp_path, "--sweep", "draw_limit=20,40").exit_code == 0
    rows = read_rows(runs(tmp_path)[0])
    for value in ("20", "40"):
        pairings = {r["pairing"] for r in rows if r["sweep_value"] == value}
        assert len(pairings) == 3 * 2 // 2  # N*(N-1)/2 with N = 3
    firsts = {r["p1"] for r in rows}
    assert "random" in {r["p2"] for r in rows}
    assert "random" not in firsts  # seats are not swapped: the last bot is never on seat 1


def test_sweep_over_bot_parameter_rewrites_bot_names(tmp_path):
    assert tour(tmp_path, "--sweep", "points_round=2,5").exit_code == 0
    rows = read_rows(runs(tmp_path)[0])
    assert {r["sweep_value"] for r in rows} == {"2", "5"}
    for r in rows:
        if r["sweep_value"] == "5":
            assert "-pts5-" in r["p1"]
        if r["p2"] != "random":
            assert f"-pts{r['sweep_value']}-" in r["p2"]


def test_sweep_over_ruleset_override_is_recorded_in_the_rows(tmp_path):
    result = tour(tmp_path, "--sweep", "shop.orange_1.price=6,9", "--keep-records")
    assert result.exit_code == 0, result.output
    (run,) = runs(tmp_path)
    assert {r["sweep_value"] for r in read_rows(run)} == {"6", "9"}
    seen = set()
    for shard in (run / "records").glob("*.jsonl.gz"):
        for g in read_games(shard):
            seen.add(g.header.overrides["shop.orange_1.price"])
    assert seen == {"6", "9"}


def test_bad_sweep_values_are_rejected_without_a_run_folder(tmp_path):
    for sweep in ("shop.nope.price=1,2", "draw_limit=a,b", "draw_limit=30,200", "x", "draw_limit="):
        result = tour(tmp_path, "--sweep", sweep)
        assert result.exit_code != 0, sweep
        assert TRACEBACK not in result.output
    assert not list(tmp_path.glob("*"))


@pytest.mark.parametrize(
    "bots",
    ["bot:random", "bot:random,bot:random", "bot:random,bot:draw30-pts3-blue,bot:random"],
)
def test_one_bot_or_repeated_bot_is_rejected_with_no_run_folder(tmp_path, bots):
    result = tour(tmp_path, bots=bots)
    assert result.exit_code != 0
    assert "Error:" in result.output and TRACEBACK not in result.output
    assert not list(tmp_path.glob("*"))


def test_unknown_or_human_bot_is_rejected(tmp_path):
    for bots in ("bot:random,human", "bot:random,bot:nonsense", "bot:random,random"):
        result = tour(tmp_path, bots=bots)
        assert result.exit_code != 0, bots
        assert TRACEBACK not in result.output
    assert not list(tmp_path.glob("*"))


def test_seat_check_has_one_marked_pairing_per_bot(tmp_path):
    result = tour(tmp_path, "--seat-check")
    assert result.exit_code == 0, result.output
    rows = read_rows(runs(tmp_path)[0])
    assert len(rows) == 3 * 3
    assert all(r["pairing"].startswith("seatcheck:") for r in rows)
    assert all(r["p1"] == r["p2"] for r in rows)
    assert len({r["pairing"] for r in rows}) == 3


def test_seat_check_allows_a_single_bot(tmp_path):
    assert tour(tmp_path, "--seat-check", bots="bot:random").exit_code == 0


def test_same_inputs_give_the_same_results_csv(tmp_path):
    assert tour(tmp_path / "a", "--sweep", "draw_limit=20,40").exit_code == 0
    assert tour(tmp_path / "b", "--sweep", "draw_limit=20,40").exit_code == 0
    (a,), (b,) = runs(tmp_path / "a"), runs(tmp_path / "b")
    assert (a / "results.csv").read_bytes() == (b / "results.csv").read_bytes()
    ca = json.loads((a / "config.json").read_text())
    cb = json.loads((b / "config.json").read_text())
    ca.pop("created_at"), cb.pop("created_at")
    assert ca == cb


def test_two_runs_in_one_folder_do_not_collide(tmp_path):
    assert tour(tmp_path, "--name", "x").exit_code == 0
    assert tour(tmp_path, "--name", "x").exit_code == 0
    assert len(runs(tmp_path)) == 2


def test_one_and_two_workers_give_byte_identical_results(tmp_path):
    assert tour(tmp_path / "w1", "--workers", "1", "--sweep", "points_round=2,6").exit_code == 0
    r2 = tour(tmp_path / "w2", "--workers", "2", "--sweep", "points_round=2,6")
    assert r2.exit_code == 0, r2.output
    (a,), (b,) = runs(tmp_path / "w1"), runs(tmp_path / "w2")
    assert (a / "results.csv").read_bytes() == (b / "results.csv").read_bytes()
    assert json.loads((b / "config.json").read_text())["workers"] == 2


def test_bad_workers_and_games_are_rejected(tmp_path):
    assert tour(tmp_path, "--workers", "0").exit_code != 0
    assert tour(tmp_path, games="0").exit_code != 0
    assert tour(tmp_path, "--name", "../x").exit_code != 0
    assert not list(tmp_path.glob("*"))


def test_sample_is_rebuilt_and_verified(tmp_path):
    result = tour(tmp_path, "--sample-size", "4")
    assert result.exit_code == 0, result.output
    assert "4 sampled games rebuilt from the seed: ok" in result.output


def test_sample_mismatch_exits_non_zero_and_names_the_game(tmp_path, monkeypatch):
    real = cli_main.write_run

    def tampered(config, out):
        run_dir, rows = real(config, out)
        for row in rows:  # change a stored result: every game is in the sample
            row["p1_points"] += 1
        return run_dir, rows

    monkeypatch.setattr(cli_main, "write_run", tampered)
    result = tour(tmp_path, "--sample-size", "100")
    assert result.exit_code == 1
    assert "MISMATCH game 0 (seed 5) of pairing" in result.output
    assert TRACEBACK not in result.output


def test_verify_sample_unit_reports_a_changed_row():
    config = TournamentConfig(bots=("bot:random", "bot:draw30-pts3-blue"), games=2, seed=1)
    from quack_rl.tournament import run_games

    rows = run_games(config)
    assert verify_sample(config, rows) == []
    rows[1]["winner"] = "p2" if rows[1]["winner"] != "p2" else "p1"
    problems = verify_sample(config, rows)
    assert len(problems) == 1 and "game 1 (seed 2)" in problems[0]


def test_keep_records_writes_gzipped_shards_that_verify(tmp_path):
    result = tour(tmp_path, "--keep-records")
    assert result.exit_code == 0, result.output
    (run,) = runs(tmp_path)
    shards = sorted((run / "records").glob("shard-*.jsonl.gz"))
    assert len(shards) == 3
    games = [g for s in shards for g in read_games(s)]
    assert len(games) == 9 and all(g.footer for g in games)
    good = runner.invoke(app, ["verify", str(shards[0]), "--seed-check"])
    assert good.exit_code == 0, good.output
    assert "3 games ok" in good.output


def test_verify_fails_on_a_shard_with_one_changed_byte(tmp_path):
    assert tour(tmp_path, "--keep-records").exit_code == 0
    shard = next((runs(tmp_path)[0] / "records").glob("shard-*.jsonl.gz"))
    data = bytearray(shard.read_bytes())
    data[len(data) // 2] ^= 0xFF
    shard.write_bytes(bytes(data))
    result = runner.invoke(app, ["verify", str(shard)])
    assert result.exit_code != 0
    assert TRACEBACK not in result.output
    assert result.exception is None or isinstance(result.exception, SystemExit)


def test_verify_fails_on_a_gzip_shard_with_a_changed_game_byte(tmp_path):
    assert tour(tmp_path, "--keep-records").exit_code == 0
    shard = next((runs(tmp_path)[0] / "records").glob("shard-*.jsonl.gz"))
    text = gzip.decompress(shard.read_bytes()).decode()
    changed = text.replace('"winner":"p1"', '"winner":"p2"', 1)
    if changed == text:
        changed = text.replace('"winner":"p2"', '"winner":"p1"', 1)
    shard.write_bytes(gzip.compress(changed.encode()))
    assert runner.invoke(app, ["verify", str(shard)]).exit_code != 0


def test_parse_sweep():
    assert parse_sweep("draw_limit=15,30").values == ("15", "30")
    for bad in ("", "a", "a=", "a=1,,2", "=1", "a=1,1"):
        with pytest.raises(TournamentError):
            parse_sweep(bad)


def test_validate_rejects_sweep_that_is_also_set():
    config = TournamentConfig(
        bots=("bot:random", "bot:draw30-pts3-blue"),
        games=1,
        seed=0,
        overrides={"shop.orange_1.price": "9"},
        sweep=parse_sweep("shop.orange_1.price=6,7"),
    )
    with pytest.raises(TournamentError):
        validate(config)


def test_full_field_is_the_25_specs_in_order():
    from quack_rl.bots import parse_bot_name
    from quack_rl.tournament import field_specs

    specs = field_specs("full")
    expected = [
        f"bot:draw{limit}-pts{rnd}-{strategy}"
        for limit in (0, 20, 40)
        for rnd in (4, 7)
        for strategy in ("blue", "green", "cleaner", "balanced")
    ] + ["bot:draw20-pts1-points"]
    assert list(specs) == expected
    assert len(specs) == 25 and len(set(specs)) == 25
    assert specs[0] == "bot:draw0-pts4-blue" and specs[23] == "bot:draw40-pts7-balanced"
    for spec in specs:
        parse_bot_name(spec)


def _capture_config(monkeypatch):
    seen = {}

    def fake_write_run(config, out):
        seen["config"] = config
        raise TournamentError("stop here")

    monkeypatch.setattr(cli_main, "write_run", fake_write_run)
    return seen


def test_field_full_without_bots_expands_to_25_specs(monkeypatch, tmp_path):
    from quack_rl.tournament import field_specs

    seen = _capture_config(monkeypatch)
    runner.invoke(app, ["tournament", "--field", "full", "--out", str(tmp_path)])
    assert seen["config"].bots == field_specs("full")


def test_field_then_bots_adds_extra_bot_after_the_field(monkeypatch, tmp_path):
    seen = _capture_config(monkeypatch)
    runner.invoke(
        app, ["tournament", "--field", "full", "--bots", "bot:random", "--out", str(tmp_path)]
    )
    bots = seen["config"].bots
    assert len(bots) == 26 and bots[-1] == "bot:random" and bots[0] == "bot:draw0-pts4-blue"


def test_field_with_a_bot_of_the_field_is_a_duplicate_error(tmp_path):
    result = runner.invoke(
        app,
        ["tournament", "--field", "full", "--bots", "bot:draw0-pts4-blue", "--out", str(tmp_path)],
    )
    assert result.exit_code == 2
    assert "Error:" in result.output and "the field lists a bot twice" in result.output
    assert TRACEBACK not in result.output
    assert not list(tmp_path.glob("*"))


def test_neither_field_nor_bots_is_an_error(tmp_path):
    result = runner.invoke(app, ["tournament", "--out", str(tmp_path)])
    assert result.exit_code == 2
    assert "Error:" in result.output and "--field" in result.output and "--bots" in result.output
    assert TRACEBACK not in result.output


def test_unknown_field_lists_known_names(tmp_path):
    result = runner.invoke(app, ["tournament", "--field", "nope", "--out", str(tmp_path)])
    assert result.exit_code == 2
    assert "Error:" in result.output and "full" in result.output
    assert TRACEBACK not in result.output
    assert not list(tmp_path.glob("*"))


def test_config_json_of_a_field_run_stores_the_specs(tmp_path):
    from quack_rl.tournament import field_specs, write_run

    run_dir, _ = write_run(
        TournamentConfig(bots=field_specs("full")[:2], games=1, seed=1, sample_size=0), tmp_path
    )
    config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    assert config["bots"] == list(field_specs("full")[:2])
    assert all(b.startswith("bot:") for b in config["bots"])


def test_help_documents_field():
    result = runner.invoke(app, ["tournament", "--help"])
    assert "--field" in result.output and "full" in result.output


def test_game_seed_is_unique_across_pairings_and_sweep_values(tmp_path):
    # 3 bots = 3 pairings, 2 sweep values, 3 games each
    assert tour(tmp_path, "--sweep", "points_round=2,6").exit_code == 0
    (run,) = runs(tmp_path)
    seeds = [row["seed"] for row in read_rows(run)]
    assert len(seeds) == 18
    assert len(set(seeds)) == len(seeds)


def test_game_seed_formula_is_stored_and_followed(tmp_path):
    from quack_rl.tournament import game_seed

    assert tour(tmp_path, "--sweep", "points_round=2,6").exit_code == 0
    (run,) = runs(tmp_path)
    config = json.loads((run / "config.json").read_text())
    assert "seed_scheme" in config
    rows = read_rows(run)
    # order of rows: sweep value, pairing, game; 3 pairings, 3 games
    expected = [game_seed(5, v, p, g, 3, 3) for v in range(2) for p in range(3) for g in range(3)]
    assert [int(r["seed"]) for r in rows] == expected


def test_seat_check_seeds_are_unique(tmp_path):
    assert tour(tmp_path, "--seat-check", "--sweep", "points_round=2,6").exit_code == 0
    (run,) = runs(tmp_path)
    seeds = [row["seed"] for row in read_rows(run)]
    assert len(seeds) == 18 and len(set(seeds)) == 18


def test_keep_records_with_new_seeds_pass_seed_check(tmp_path):
    assert tour(tmp_path, "--keep-records", "--sweep", "points_round=2,6").exit_code == 0
    (run,) = runs(tmp_path)
    for shard in sorted((run / "records").glob("*.jsonl.gz")):
        assert runner.invoke(app, ["verify", str(shard), "--seed-check"]).exit_code == 0


def _play(seed, p1="bot:draw30-pts3-blue", p2="bot:random"):
    import io

    from quack_rl.rules import load_ruleset
    from quack_rl.simgame import play_sim_game

    rs = load_ruleset("v1")
    buf = io.StringIO()
    play_sim_game(
        rs, rules="v1", rounds=9, overrides={}, p1=p1, p2=p2, game_seed=seed, stream=buf
    )
    lines = [json.loads(x) for x in buf.getvalue().splitlines()]
    for line in lines:
        for key in ("game_id", "started_at", "finished_at"):
            line.pop(key, None)
    return lines


def test_same_seed_same_bots_give_the_same_record():
    assert _play(7) == _play(7)


def test_different_seeds_give_different_games():
    assert _play(7) != _play(8)


def test_results_csv_is_byte_identical_for_one_and_two_workers(tmp_path):
    assert tour(tmp_path / "w1", "--workers", "1", "--games", "2").exit_code == 0
    assert tour(tmp_path / "w2", "--workers", "2", "--games", "2").exit_code == 0
    (a,), (b,) = runs(tmp_path / "w1"), runs(tmp_path / "w2")
    assert (a / "results.csv").read_bytes() == (b / "results.csv").read_bytes()
