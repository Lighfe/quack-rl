import pytest
from pydantic import ValidationError

from quack_rl.engine import DRAW, ScriptedChance, new_game, step
from quack_rl.rules import (
    Ruleset,
    UnknownSpellbook,
    get_spellbook,
    load_ruleset,
    register_spellbook,
    registered_spellbooks,
    unregister_spellbook,
)

V2 = load_ruleset("v2")
BOOK = "test_book"
# blue gets the orange component here (no placement bonus), so the engine must differ from v2.
COMPONENTS = {**get_spellbook(V2.spellbook), "blue": "orange@1"}


def _legacy_data(blue="blue@1"):
    """v2 without a spellbook: each chip names its component (blue as in the first rules)."""
    data = V2.model_dump()
    data["spellbook"] = None
    for chip in data["chips"]:
        name = V2.component_name(V2.chip(chip["id"]))
        chip["component"] = blue if chip["colour"] == "blue" else name
    return data


def _brew_game(rs):
    """A new game after the first card (a card without effect), at the first brew step."""
    return step(new_game(rs), rs, None, ScriptedChance(["card_8_to_12"])).state


@pytest.fixture
def book():
    register_spellbook(BOOK, COMPONENTS)
    try:
        yield BOOK
    finally:
        unregister_spellbook(BOOK)


def _data(spellbook=None, keep_component=False):
    data = _legacy_data()
    if spellbook is not None:
        data["spellbook"] = spellbook
    if spellbook is not None and not keep_component:
        for chip in data["chips"]:
            del chip["component"]  # the key is absent, not None
    return data


def test_v2_names_a_spellbook_and_a_ruleset_without_one_names_each_component():
    assert V2.spellbook == 1
    assert all(c.component is None for c in V2.chips)
    assert all(V2.component_name(c) == get_spellbook(1)[c.colour] for c in V2.chips)
    legacy = Ruleset.model_validate(_legacy_data())
    assert legacy.spellbook is None
    assert all(legacy.component_name(c) == c.component for c in legacy.chips)


def test_spellbook_without_chip_components_loads(book):
    data = _data(book)
    assert all("component" not in chip for chip in data["chips"])
    rs = Ruleset.model_validate(data)
    assert all(c.component is None for c in rs.chips)
    assert {c.id: rs.component_name(c) for c in rs.chips}["blue_1"] == "orange@1"


def test_spellbook_and_chip_component_together_fail(book):
    with pytest.raises(ValidationError) as e:
        Ruleset.model_validate(_data(book, keep_component=True) | {"spellbook": book})
    message = str(e.value)
    assert book in message
    assert "white_1" in message or "chip" in message


def test_error_names_spellbook_and_chip():
    short = {k: v for k, v in COMPONENTS.items() if k != "red"}
    register_spellbook("test_no_red", short)
    try:
        first_red = next(c.id for c in V2.chips if c.colour == "red")
        with pytest.raises(ValidationError, match=rf"(?s)chip {first_red}.*test_no_red"):
            Ruleset.model_validate(_data("test_no_red"))
    finally:
        unregister_spellbook("test_no_red")


def test_unregistered_spellbook_fails():
    with pytest.raises(ValidationError, match="no_such_book"):
        Ruleset.model_validate(_data("no_such_book"))
    assert issubclass(UnknownSpellbook, ValueError)


def test_spellbook_missing_a_colour_fails():
    register_spellbook("test_short", {"white": "white@1", "orange": "orange@1"})
    try:
        with pytest.raises(ValidationError, match="has no colour"):
            Ruleset.model_validate(_data("test_short"))
    finally:
        unregister_spellbook("test_short")


def test_chip_without_component_and_without_spellbook_fails():
    data = _legacy_data()
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
    state = _brew_game(rs)
    for chip in ("blue_4", "blue_2"):
        state = step(state, rs, {"p1": DRAW, "p2": DRAW}, ScriptedChance([chip, "white_1"])).state
    return state.players["p1"].field


def test_engine_reads_component_through_spellbook(book):
    spell = _with_blue_in_bag(_data(book))
    legacy = _with_blue_in_bag(_legacy_data())
    # Blue as blue@1: the second blue chip (value 2) follows a value-4 chip and gets +1.
    assert _fields_after_two_blue_draws(legacy) == 7
    assert _fields_after_two_blue_draws(spell) == 6


GREEN_BLUE_BOOK = "test_green_blue"


@pytest.fixture
def green_blue_book():
    # blue gets the green component (droplet halves for the last two placed chips)
    register_spellbook(GREEN_BLUE_BOOK, {**COMPONENTS, "blue": "green@1"})
    try:
        yield GREEN_BLUE_BOOK
    finally:
        unregister_spellbook(GREEN_BLUE_BOOK)


def test_resolve_reads_component_through_spellbook(green_blue_book):
    from quack_rl.engine.resolve import apply_resolve
    from quack_rl.engine.state import Status

    def halves(rs):
        state = new_game(rs)
        for p in state.players.values():
            p.placed = ["blue_4", "blue_2"]
            p.final_field = 0
            p.status = Status.EXPLODED  # no bonus die roll
        events: list = []
        apply_resolve(state, rs, ScriptedChance([]), events)
        return [e for e in events if e["kind"] == "round_end_bonus"]

    assert halves(Ruleset.model_validate(_legacy_data())) == []
    assert len(halves(Ruleset.model_validate(_data(green_blue_book)))) == 4  # 2 chips x 2 seats


def test_report_reads_component_through_spellbook(green_blue_book):
    from quack_rl.report import _brew_outcomes

    def green_halves(rs):
        out = _brew_outcomes(rs, (("blue_4", 1), ("blue_2", 1)), 100)
        return {key[2] for key in out}

    assert green_halves(Ruleset.model_validate(_legacy_data())) == {0}
    assert green_halves(Ruleset.model_validate(_data(green_blue_book))) == {2}
