import io
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from helpers import RS

from quack_rl.bots import RandomBot
from quack_rl.engine import RngChance
from quack_rl.record import (
    GameRecorder,
    HeaderLine,
    LocalRecordStore,
    RecordFormatError,
    SeatInfo,
    berlin_stamp,
    read_games,
    record_json_schema,
)
from quack_rl.runner import play_game


def header(game_id="g1", seed=5):
    return HeaderLine(
        game_id=game_id,
        schema_version=1,
        rules_version="v1",
        seed=seed,
        mode="sim",
        seats={
            "p1": SeatInfo(kind="bot", name="random"),
            "p2": SeatInfo(kind="bot", name="random"),
        },
        ui={},
        engine_version="0.1.0",
        started_at="2026-10-08T21:15:03+02:00",
    )


def record_game(stream, game_id="g1", seed=5):
    rec = GameRecorder(stream, header(game_id, seed))
    final = play_game(RS, {"p1": RandomBot(1), "p2": RandomBot(2)}, RngChance(seed), rec.on_step)
    rec.close(final)
    return final


def step_json(game_id="g1", n=1):
    return json.dumps(
        {
            "type": "step",
            "game_id": game_id,
            "n": n,
            "round": 1,
            "phase": "brew",
            "legal": None,
            "actions": None,
            "chance": [],
            "events": [],
        }
    )


def footer_json(game_id="g1"):
    return json.dumps(
        {
            "type": "footer",
            "game_id": game_id,
            "points": {"p1": 1, "p2": 2},
            "final_fields": {"p1": 3, "p2": None},
            "winner": "p2",
        }
    )


def header_json(game_id="g1"):
    return header(game_id).model_dump_json()


def test_every_line_is_json_with_game_id_and_type(tmp_path):
    path = tmp_path / "g.jsonl"
    with path.open("w", encoding="utf-8") as f:
        record_game(f)
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert lines[0]["type"] == "header" and lines[-1]["type"] == "footer"
    assert all(line["game_id"] == "g1" for line in lines)
    assert {line["type"] for line in lines[1:-1]} == {"step"}


def test_round_trip_one_game(tmp_path):
    path = tmp_path / "g.jsonl"
    with path.open("w", encoding="utf-8") as f:
        final = record_game(f)
    (game,) = read_games(path)
    assert game.footer is not None and game.footer.winner == final.winner
    assert game.steps[0].n == 1 and game.steps[-1].n == len(game.steps)
    assert [s.n for s in game.steps] == list(range(1, len(game.steps) + 1))
    assert game.steps[0].actions == {"p1": "draw", "p2": "draw"}


def test_a_shard_holds_several_games(tmp_path):
    path = tmp_path / "shard-0001.jsonl"
    with path.open("w", encoding="utf-8") as f:
        record_game(f, "g1", 5)
        record_game(f, "g2", 6)
    assert [g.header.game_id for g in read_games(path)] == ["g1", "g2"]


def test_an_aborted_game_has_no_footer(tmp_path):
    path = tmp_path / "g.jsonl"
    with path.open("w", encoding="utf-8") as f:
        GameRecorder(f, header())
    (game,) = read_games(path)
    assert game.footer is None and game.steps == []


def test_step_line_without_header_is_an_error(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text(step_json("x") + "\n")
    with pytest.raises(RecordFormatError):
        list(read_games(path))


def test_invalid_json_line_is_a_record_format_error(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text(header_json() + "\n{not json\n")
    with pytest.raises(RecordFormatError) as info:
        list(read_games(path))
    assert f"{path}:2" in str(info.value)
    assert type(info.value) is RecordFormatError


def test_step_line_after_footer_is_a_record_format_error(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text("\n".join([header_json(), step_json(), footer_json(), step_json(n=2)]) + "\n")
    with pytest.raises(RecordFormatError) as info:
        list(read_games(path))
    assert f"{path}:4" in str(info.value)


def test_step_line_with_other_game_id_is_a_record_format_error(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text("\n".join([header_json("g1"), step_json("g2")]) + "\n")
    with pytest.raises(RecordFormatError) as info:
        list(read_games(path))
    assert f"{path}:2" in str(info.value)


def test_footer_line_with_other_game_id_is_a_record_format_error(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text("\n".join([header_json("g1"), step_json("g1"), footer_json("g2")]) + "\n")
    with pytest.raises(RecordFormatError) as info:
        list(read_games(path))
    assert f"{path}:3" in str(info.value)


def test_header_after_unfinished_game_starts_a_new_game(tmp_path):
    path = tmp_path / "g.jsonl"
    lines = [header_json("g1"), step_json("g1"), "", header_json("g2"), "   ", footer_json("g2")]
    path.write_text("\n".join(lines) + "\n")
    games = list(read_games(path))
    assert [g.header.game_id for g in games] == ["g1", "g2"]
    assert games[0].footer is None and len(games[0].steps) == 1
    assert games[1].footer is not None and games[1].steps == []


def test_berlin_stamp_uses_summer_and_winter_offsets():
    summer = datetime(2026, 10, 8, 19, 15, 3, tzinfo=ZoneInfo("UTC"))
    winter = datetime(2026, 11, 8, 20, 15, 3, tzinfo=ZoneInfo("UTC"))
    assert berlin_stamp(summer) == "2026-10-08_21-15-03+0200"
    assert berlin_stamp(winter) == "2026-11-08_21-15-03+0100"


def test_local_store_paths(tmp_path):
    store = LocalRecordStore(tmp_path)
    now = datetime(2026, 10, 8, 19, 15, 3, tzinfo=ZoneInfo("UTC"))
    play_path = store.new_play_path("v1", now)
    assert play_path.parent == tmp_path / "v1" / "play"
    assert play_path.name.startswith("2026-10-08_21-15-03+0200_") and play_path.suffix == ".jsonl"
    sim_dir = store.new_sim_dir("v1", now)
    assert sim_dir.parent == tmp_path / "v1" / "sim" and sim_dir.is_dir()
    assert sim_dir.name.startswith("2026-10-08_21-15-03+0200_")
    assert store.shard_path(sim_dir, 1).name == "shard-0001.jsonl"


def test_json_schema_is_available():
    schema = record_json_schema()
    assert "header" in json.dumps(schema) and "footer" in json.dumps(schema)
    assert "step" in json.dumps(schema)


def test_decision_ms_is_written_only_when_given():
    buf = io.StringIO()
    record_game(buf)
    lines = [json.loads(line) for line in buf.getvalue().splitlines()]
    steps = [line for line in lines if line["type"] == "step"]
    assert steps and all(s["decision_ms"] is None for s in steps)


def test_record_package_reexports_all_produced_names():
    import quack_rl.record as record

    names = [
        "RECORD_SCHEMA_VERSION",
        "SeatInfo",
        "HeaderLine",
        "StepLine",
        "FooterLine",
        "record_json_schema",
        "GameRecorder",
        "berlin_stamp",
        "berlin_iso",
        "new_game_id",
        "RecordStore",
        "LocalRecordStore",
        "RecordedGame",
        "read_games",
        "RecordFormatError",
    ]
    for name in names:
        assert hasattr(record, name), name
        assert name in record.__all__, name
    assert record.RECORD_SCHEMA_VERSION == 1
