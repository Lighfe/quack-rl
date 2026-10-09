"""Game records as JSON Lines: format, writer, store, reader and verify (spec 6.1, 6.2)."""

from quack_rl.record.reader import RecordedGame, RecordFormatError, read_games
from quack_rl.record.replay import ChanceMismatch, RecordedChance, verify_game, verify_seed
from quack_rl.record.schema import (
    RECORD_SCHEMA_VERSION,
    FooterLine,
    HeaderLine,
    SeatInfo,
    StepLine,
    record_json_schema,
)
from quack_rl.record.store import (
    LocalRecordStore,
    RecordStore,
    berlin_iso,
    berlin_stamp,
    new_game_id,
)
from quack_rl.record.writer import GameRecorder

__all__ = [
    "RECORD_SCHEMA_VERSION",
    "ChanceMismatch",
    "FooterLine",
    "GameRecorder",
    "HeaderLine",
    "LocalRecordStore",
    "RecordFormatError",
    "RecordStore",
    "RecordedChance",
    "RecordedGame",
    "SeatInfo",
    "StepLine",
    "berlin_iso",
    "berlin_stamp",
    "new_game_id",
    "read_games",
    "record_json_schema",
    "verify_game",
    "verify_seed",
]
