import pytest
from pydantic import ValidationError

from quack_rl.engine import DRAW, ScriptedChance, new_game, step
from quack_rl.rules import (
    Ruleset,
    UnknownSpellbook,
    load_ruleset,
    register_spellbook,
    registered_spellbooks,
    unregister_spellbook,
)

V1 = load_ruleset("v1")
BOOK = "test_book"
# blue gets the orange component here (no placement bonus), so the engine must differ from v1.
COMPONENTS = {
    "white": "white@1",
    "orange": "orange@1",
    "blue": "orange@1",
    "green": "green@1",
}


@pytest.fixture
def book():
    register_spellbook(BOOK, COMPONENTS)
    try:
        yield BOOK
    finally:
        unregister_spellbook(BOOK)


def _data(spellbook=None, keep_component=False):
    data = V1.model_dump()
    if spellbook is not None:
        data["spellbook"] = spellbook
    if not keep_component:
        for chip in data["chips"]:
            chip["component"] = None if spellbook else chip["component"]
    return data


def test_old_rulesets_have_no_spellbook():
    for version in ("v1", "v1.1", "v1.8"):
        rs = load_ruleset(version)
        assert rs.spellbook is None
        assert all(rs.component_name(c) == c.component for c in rs.chips)


def test_spellbook_without_chip_components_loads(book):
    rs = Ruleset.model_validate(_data(book))
    assert all(c.component is None for c in rs.chips)
    assert {c.id: rs.component_name(c) for c in rs.chips}["blue_1"] == "orange@1"


def test_spellbook_and_chip_component_together_fail(book):
    with pytest.raises(ValidationError) as e:
        Ruleset.model_validate(_data(book, keep_component=True) | {"spellbook": book})
    message = str(e.value)
    assert book in message
    assert "white_1" in message or "chip" in message


def test_error_names_spellbook_and_chip(book):
    data = V1.model_dump()
    data["spellbook"] = book
    with pytest.raises(ValidationError, match=rf"(?s)chip {data['chips'][0]['id']}.*{book}"):
        Ruleset.model_validate(data)


def test_unregistered_spellbook_fails():
    with pytest.raises(ValidationError, match="no_such_book"):
        Ruleset.model_validate(_data("no_such_book"))
    assert issubclass(UnknownSpellbook, ValueError)


def test_spellbook_missing_a_colour_fails():
    register_spellbook("test_short", {"white": "white@1", "orange": "orange@1"})
    try:
        with pytest.raises(ValidationError, match="blue"):
            Ruleset.model_validate(_data("test_short"))
    finally:
        unregister_spellbook("test_short")


def test_chip_without_component_and_without_spellbook_fails():
    data = V1.model_dump()
    data["chips"][0]["component"] = None
    with pytest.raises(ValidationError, match="component"):
        Ruleset.model_validate(data)


def test_white_and_orange_fixed_in_every_spellbook(book):
    books = registered_spellbooks()
    assert book in books
    for components in books.values():
        assert components["white"] == "white@1"
        assert components["orange"] == "orange@1"


def test_register_refuses_changed_white_or_orange():
    with pytest.raises(ValueError, match="white"):
        register_spellbook("test_bad", {**COMPONENTS, "white": "green@1"})
    with pytest.raises(ValueError, match="orange"):
        register_spellbook("test_bad", {k: v for k, v in COMPONENTS.items() if k != "orange"})
    assert "test_bad" not in registered_spellbooks()


def test_test_spellbook_is_removed_after_use():
    assert BOOK not in registered_spellbooks()


def _with_blue_in_bag(data):
    data["start_bag"] = {**data["start_bag"], "blue_4": 1, "blue_2": 1}
    return Ruleset.model_validate(data)


def _fields_after_two_blue_draws(rs):
    state = new_game(rs)
    for chip in ("blue_4", "blue_2"):
        state = step(state, rs, {"p1": DRAW, "p2": DRAW}, ScriptedChance([chip, "white_1"])).state
    return state.players["p1"].field


def test_engine_reads_component_through_spellbook(book):
    spell = _with_blue_in_bag(_data(book))
    legacy = _with_blue_in_bag(V1.model_dump())
    # Without a spellbook the second blue chip (value 2) follows a value-4 chip and gets +1.
    assert _fields_after_two_blue_draws(legacy) == 7
    assert _fields_after_two_blue_draws(spell) == 6
