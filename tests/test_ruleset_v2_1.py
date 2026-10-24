"""Ruleset v2.1: the point board with rat tails (ruleset data only) and the new die."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from quack_rl.rules import SUPPORTED_RULES_VERSIONS, PointBoard, load_ruleset

RS = load_ruleset("v2.1")
RULES_DOC = Path(__file__).resolve().parents[1] / "docs" / "rules" / "rules-v2.1.md"
TAILS = [1, 4, 7, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32, 34, 36, 38, 40, 42, 44, 46, 48]


def test_v2_loads():
    assert "v2.1" in SUPPORTED_RULES_VERSIONS
    assert RS.version == "v2.1"
    assert RS.point_board is not None
    assert RS.point_board.fields == 50
    assert RS.point_board.rat_tails == TAILS
    assert len(RS.point_board.rat_tails) == 23
    assert RS.point_board.laps == 2
    assert RS.point_board.max_points == 100


def test_v2_die_weights():
    faces = {f.id: f for f in RS.die}
    assert {k: f.weight for k, f in faces.items()} == {
        "orange_1": 1, "droplet_1": 1, "droplet_half": 1, "point_1": 2, "point_2": 1,
    }  # fmt: skip
    assert sum(f.weight for f in RS.die) == 6
    assert faces["orange_1"].kind == "chip" and faces["orange_1"].chip == "orange_1"
    assert faces["droplet_1"].halves == 2 and faces["droplet_half"].halves == 1
    assert (faces["point_1"].kind, faces["point_1"].points) == ("points", 1)
    assert (faces["point_2"].kind, faces["point_2"].points) == ("points", 2)


def test_tail_outside_board_refused():
    base = RS.model_dump()
    bad = {**base, "point_board": {"fields": 50, "rat_tails": [*TAILS, 50], "laps": 2}}
    with pytest.raises(ValidationError):
        type(RS).model_validate(bad)
    with pytest.raises(ValidationError):
        PointBoard.model_validate({"fields": 50, "rat_tails": [-1]})


def test_tails_must_increase_strictly():
    for tails in ([4, 1], [1, 1]):
        with pytest.raises(ValidationError):
            PointBoard.model_validate({"fields": 50, "rat_tails": tails})


def test_laps_and_fields_at_least_one():
    for bad in ({"fields": 0, "rat_tails": []}, {"fields": 5, "rat_tails": [], "laps": 0}):
        with pytest.raises(ValidationError):
            PointBoard.model_validate(bad)


def test_point_board_values_are_strict_integers():
    with pytest.raises(ValidationError):
        PointBoard.model_validate({"fields": "50", "rat_tails": [1]})
    with pytest.raises(ValidationError):
        PointBoard.model_validate({"fields": 50, "rat_tails": ["1"]})
    with pytest.raises(ValidationError):
        PointBoard.model_validate({"fields": 50, "rat_tails": [1], "laps": "2"})
    assert load_ruleset("v2.1").point_board is not None


def test_rules_doc_agrees_with_the_file():
    text = RULES_DOC.read_text(encoding="utf-8")
    assert "Rules version: `v2.1`" in text
    assert "Changes from v1.11" in text
    for face in RS.die:
        chance = f"{face.weight}/6"
        reward = {
            "orange_1": "Receive 1 Orange 1 chip (into the bag)",
            "droplet_1": "Droplet +1",
            "droplet_half": "Droplet +0.5",
            "point_1": "+1 victory point",
            "point_2": "+2 victory points",
        }[face.id]
        assert f"| {face.id} | {chance} | {reward} |" in text, face.id
    board = RS.point_board
    assert board is not None
    assert f"(`fields = {board.fields}`)" in text
    assert f"(`laps = {board.laps}`)" in text
    assert f"{board.fields * board.laps}" in text
    assert f"| {', '.join(str(t) for t in board.rat_tails)} |" in text
    assert f"({len(board.rat_tails)} tails" in text
