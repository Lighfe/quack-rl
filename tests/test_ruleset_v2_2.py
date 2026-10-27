"""Ruleset v2.2: the file, the model field `ruby_step` and the rules document."""

import re
import tomllib
from importlib import resources
from pathlib import Path

from quack_rl.rules import Ruleset, load_ruleset

DOCS = Path(__file__).resolve().parents[1] / "docs" / "rules"
RULES_DOC = DOCS / "rules-v2.2.md"
RS = load_ruleset("v2.2")


def test_v2_2_file_sets_ruby_step_as_a_toml_bool():
    text = resources.files("quack_rl.rules").joinpath("v2.2.toml").read_text(encoding="utf-8")
    data = tomllib.loads(text)
    assert data["version"] == "v2.2" and data["ruby_step"] is True
    assert RS.ruby_step is True


def test_v2_1_loads_with_the_old_safe_default():
    text = resources.files("quack_rl.rules").joinpath("v2.1.toml").read_text(encoding="utf-8")
    assert "ruby_step" not in tomllib.loads(text)
    assert load_ruleset("v2.1").ruby_step is False
    data = RS.model_dump()
    del data["ruby_step"]
    assert Ruleset.model_validate(data).ruby_step is False


def test_rules_doc_v2_2_agrees_with_the_file():
    doc = RULES_DOC.read_text(encoding="utf-8")
    assert "Rules version: `v2.2`" in doc
    assert "`ruby_step = true`" in doc
    assert "### 4.4a Ruby step" in doc
    assert "Brew → Resolve → Shop → Ruby step → Reset" in doc
    assert "## 7. Changes from v2.1" in doc
    assert "**the default**" in doc
    assert f"(`ruby_cost = {RS.ruby_cost}`)" in doc
    # the shop table: the same rows as the file
    rows = re.findall(r"^\| \S+ ([A-Z][a-z]+ \d+) \| (\d+) \| (\d+) \|$", doc, flags=re.M)
    want = [
        (f"{RS.chip(i.chip).colour.title()} {RS.chip(i.chip).value}", str(i.price), str(i.min_round))
        for i in RS.shop
    ]
    assert rows == want
    # the shop section names no ruby spend any more, the ruby step names both
    shop = doc.split("### 4.4 Shop", 1)[1].split("### 4.4a", 1)[0]
    assert "**Ruby drop**" not in shop and "**Refill flask**" not in shop
    ruby = doc.split("### 4.4a Ruby step", 1)[1].split("### 4.5", 1)[0]
    assert "`ruby_drop`" in ruby and "`refill_flask`" in ruby and "`done`" in ruby


def test_rules_doc_v2_2_differs_from_v2_1_only_where_the_ruby_step_needs():
    old = (DOCS / "rules-v2.1.md").read_text(encoding="utf-8")
    new = RULES_DOC.read_text(encoding="utf-8")
    # the sections that tables come from are the same (components and the round cards)
    for start, end in (("## 1. Components", "### Shop"), ("### Round cards", None)):
        a = old.split(start, 1)[1]
        b = new.split(start, 1)[1]
        if end:
            a, b = a.split(end, 1)[0], b.split(end, 1)[0]
        assert a == b, start
