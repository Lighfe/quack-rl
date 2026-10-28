"""Ruleset v2.3: the file, the point board, the die and the rules document."""

import re
import tomllib
from importlib import resources
from pathlib import Path

import pytest
from pydantic import ValidationError

from quack_rl.rules import SUPPORTED_RULES_VERSIONS, PointBoard, load_ruleset

RS = load_ruleset("v2.3")
RULES_DOC = Path(__file__).resolve().parents[1] / "docs" / "rules" / "rules-v2.3.md"
TAILS = [1, 4, 7, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32, 34, 36, 38, 40, 42, 44, 46, 48]


def toml_data() -> dict:
    text = resources.files("quack_rl.rules").joinpath("v2.3.toml").read_text(encoding="utf-8")
    return tomllib.loads(text)


def test_v2_3_is_the_only_ruleset_and_loads():
    assert SUPPORTED_RULES_VERSIONS == ("v2.3",)
    assert RS.version == "v2.3"
    assert RS.point_board.fields == 50
    assert RS.point_board.rat_tails == TAILS
    assert RS.point_board.laps == 2
    assert RS.point_board.max_points == 100


def test_v2_3_file_has_no_ruby_step_switch_and_a_whole_step_die_face():
    data = toml_data()
    assert data["version"] == "v2.3"
    assert "ruby_step" not in data
    droplet = next(f for f in data["die"] if f["kind"] == "droplet")
    assert droplet == {"id": "droplet_1", "weight": 1, "kind": "droplet", "droplet": 1}
    assert isinstance(droplet["droplet"], int)


def test_v2_3_die_weights():
    faces = {f.id: f for f in RS.die}
    assert {k: f.weight for k, f in faces.items()} == {
        "orange_1": 1, "droplet_1": 1, "ruby_1": 1, "point_1": 2, "point_2": 1,
    }  # fmt: skip
    assert faces["droplet_1"].droplet == 1 and faces["ruby_1"].rubies == 1


def test_tail_outside_board_refused():
    with pytest.raises(ValidationError):
        PointBoard.model_validate({"fields": 50, "rat_tails": [*TAILS, 50], "laps": 2})


def test_rules_doc_v2_3_agrees_with_the_file():
    doc = RULES_DOC.read_text(encoding="utf-8")
    assert doc.startswith("# Quack RL rules v2.3")
    assert "Rules version: `v2.3`" in doc
    assert "**the only** ruleset and **the default**" in doc
    # black: equal counts droplet +1 each, the larger count droplet +1 and 1 ruby
    black = doc.split("#### Black", 1)[1].split("####", 1)[0]
    assert "each of the two players advances the droplet by 1" in black
    assert "advances the droplet by 1 and gets 1 ruby" in black
    assert "3 rubies" not in black
    # whole steps, the ruby step without a switch
    rules = doc.split("## 7. Changes from v2.2", 1)[0]
    assert "halves" not in rules and "two halves" not in rules
    assert "It moves in whole steps and is counted in whole steps" in rules
    ruby = doc.split("### 4.4a Ruby step", 1)[1].split("### 4.5", 1)[0]
    assert "there is no switch" in ruby and "ruby_step" not in ruby
    assert "`ruby_drop`" in ruby and "`refill_flask`" in ruby and "`done`" in ruby
    assert f"(`ruby_cost = {RS.ruby_cost}`)" in ruby
    # the die table
    for face in RS.die:
        reward = {
            "orange_1": "Receive 1 Orange 1 chip (into the bag)",
            "droplet_1": f"Droplet +{face.droplet}",
            "ruby_1": "+1 ruby",
            "point_1": "+1 victory point",
            "point_2": "+2 victory points",
        }[face.id]
        assert f"| {face.id} | {face.weight}/6 | {reward} |" in doc, face.id
    # the shop table: the same rows as the file
    rows = re.findall(r"^\| \S+ ([A-Z][a-z]+ \d+) \| (\d+) \| (\d+) \|$", doc, flags=re.M)
    want = [
        (f"{RS.chip(i.chip).colour.title()} {RS.chip(i.chip).value}", str(i.price), str(i.min_round))
        for i in RS.shop
    ]
    assert rows == want
    # the point board
    board = RS.point_board
    assert f"(`fields = {board.fields}`)" in doc
    assert f"| {', '.join(str(t) for t in board.rat_tails)} |" in doc
    assert "## 7. Changes from v2.2" in doc
