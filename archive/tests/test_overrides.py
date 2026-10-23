"""Moved from tests/test_overrides.py (#170): the v1 golden record has no `overrides` field."""

from pathlib import Path

from quack_rl.record import read_games, verify_game

GOLDEN = Path(__file__).parent / "fixtures" / "golden" / "v1_random_seed7.jsonl"


def test_golden_record_without_the_field_still_verifies():
    (game,) = read_games(GOLDEN)
    assert "overrides" not in GOLDEN.read_text().splitlines()[0]
    assert game.header.overrides == {}
    assert verify_game(game) == []
