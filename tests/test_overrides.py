import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from quack_rl.cli import human
from quack_rl.cli.main import app
from quack_rl.record import read_games, verify_game
from quack_rl.rules import apply_overrides, load_ruleset

runner = CliRunner()
GOLDEN = Path(__file__).parent / "fixtures" / "golden" / "v1_random_seed7.jsonl"


def price(rs, item="orange_1"):
    return rs.shop_item(item).price


def games_of(out: Path):
    return [g for p in sorted(out.glob("**/*.jsonl")) for g in read_games(p)]


def sim(out, *extra, games="3"):
    return runner.invoke(
        app, ["simulate", "--games", games, "--seed", "3", "--out", str(out), *extra]
    )


# --- the function ---------------------------------------------------------------


def test_override_changes_the_copy_and_not_the_original():
    rs = load_ruleset("v1")
    assert price(rs) == 3
    new = apply_overrides(rs, {"shop.orange_1.price": "4"})
    assert price(new) == 4
    assert price(rs) == 3


def test_several_overrides_apply_and_empty_map_is_equal():
    rs = load_ruleset("v1")
    new = apply_overrides(rs, {"explosion_limit": "8", "shop.orange_1.price": "4"})
    assert new.explosion_limit == 8 and price(new) == 4
    assert apply_overrides(rs, {}) == rs


def test_typed_values_are_accepted():
    rs = load_ruleset("v1")
    assert price(apply_overrides(rs, {"shop.orange_1.price": 5})) == 5


@pytest.mark.parametrize(
    "key,value",
    [
        ("shop.nope.price", "1"),
        ("nope", "1"),
        ("shop.orange_1.nope", "1"),
        ("explosion_limit", "abc"),
        ("explosion_limit", "0"),  # validation: explosion_limit >= 1
        ("shop.orange_1.price", "-1"),  # validation: price >= 0
        ("shop", "1"),
        ("start_bag.nope", "1"),
    ],
)
def test_bad_overrides_fail_with_the_key(key, value):
    with pytest.raises(ValueError) as e:
        apply_overrides(load_ruleset("v1"), {key: value})
    assert key in str(e.value)


@pytest.mark.parametrize("key,flag", [("rounds", "--rounds"), ("version", "--rules")])
def test_rounds_and_version_are_refused_with_a_pointer(key, flag):
    with pytest.raises(ValueError, match=flag):
        apply_overrides(load_ruleset("v1"), {key: "3"})


# --- the commands ---------------------------------------------------------------


def test_simulate_set_stores_overrides_and_verify_passes(tmp_path):
    result = sim(tmp_path, "--set", "shop.orange_1.price=4", "--set", "explosion_limit=8")
    assert result.exit_code == 0, result.output
    games = games_of(tmp_path)
    assert len(games) == 3
    for g in games:
        assert g.header.rules_version == "v1"
        assert g.header.overrides == {"shop.orange_1.price": "4", "explosion_limit": "8"}
        assert verify_game(g) == []
    path = next(tmp_path.glob("**/*.jsonl"))
    assert runner.invoke(app, ["verify", str(path)]).exit_code == 0


def test_play_set_stores_overrides(tmp_path, monkeypatch):
    keys = iter("ds0" * 5000)
    monkeypatch.setattr(human, "default_read_key", lambda: next(keys))
    result = runner.invoke(
        app, ["play", "--seed", "4", "--out", str(tmp_path), "--set", "shop.orange_1.price=4"]
    )
    assert result.exit_code == 0, result.output
    (game,) = games_of(tmp_path)
    assert game.header.overrides == {"shop.orange_1.price": "4"}
    assert verify_game(game) == []


def test_no_set_gives_empty_overrides(tmp_path):
    assert sim(tmp_path).exit_code == 0
    raw = json.loads(next(tmp_path.glob("**/*.jsonl")).read_text().splitlines()[0])
    assert raw.get("overrides", {}) == {}


def test_golden_record_without_the_field_still_verifies():
    (game,) = read_games(GOLDEN)
    assert "overrides" not in GOLDEN.read_text().splitlines()[0]
    assert game.header.overrides == {}
    assert verify_game(game) == []


@pytest.mark.parametrize(
    "args,fragment",
    [
        (["--set", "shop.nope.price=1"], "shop.nope.price"),
        (["--set", "explosion_limit=abc"], "explosion_limit"),
        (["--set", "explosion_limit=0"], "explosion_limit"),
        (["--set", "noequals"], "noequals"),
        (["--set", "rounds=3"], "--rounds"),
        (["--set", "version=v1"], "--rules"),
    ],
)
def test_bad_set_fails_and_writes_no_record(tmp_path, args, fragment):
    result = sim(tmp_path, *args)
    assert result.exit_code != 0
    assert fragment in result.output
    assert "Traceback" not in result.output
    assert list(tmp_path.glob("**/*.jsonl")) == []


def test_bad_set_in_play_fails_and_writes_no_record(tmp_path):
    result = runner.invoke(
        app, ["play", "--out", str(tmp_path), "--p1", "bot:random", "--set", "nope=1"]
    )
    assert result.exit_code != 0
    assert "nope" in result.output
    assert list(tmp_path.glob("**/*.jsonl")) == []


def test_edited_overrides_make_verify_fail(tmp_path):
    assert sim(tmp_path, "--set", "shop.orange_1.price=1", games="5").exit_code == 0
    path = next(tmp_path.glob("**/*.jsonl"))
    original = path.read_text().splitlines()
    for edit in ({"shop.orange_1.price": "9"}, None):
        lines = list(original)
        failed = 0
        out_lines = []
        for line in lines:
            raw = json.loads(line)
            if raw["type"] == "header":
                if edit is None:
                    del raw["overrides"]
                else:
                    raw["overrides"] = edit
            out_lines.append(json.dumps(raw))
        edited = tmp_path / "edited.jsonl"
        edited.write_text("\n".join(out_lines) + "\n")
        result = runner.invoke(app, ["verify", str(edited)])
        assert result.exit_code != 0, result.output
        assert "differ" in result.output
