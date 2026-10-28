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

V2 = load_ruleset("v2.3")
BOOK = "test_book"
# blue gets the orange component here (no placement bonus), so the engine must differ from v2.
COMPONENTS = {**get_spellbook(V2.spellbook), "blue": "orange@1"}


def _data(spellbook=None):
    """The v2.3 data with another spellbook; the default is the spellbook of v2.3 itself."""
    data = V2.model_dump()
    if spellbook is not None:
        data["spellbook"] = spellbook
    return data


def _brew_game(rs):
    """A new game after the first card (a card without effect), at the first brew step."""
    return step(new_game(rs), rs, None, ScriptedChance(["card_16"])).state


@pytest.fixture
def book():
    register_spellbook(BOOK, COMPONENTS)
    try:
        yield BOOK
    finally:
        unregister_spellbook(BOOK)


def test_v2_3_names_a_spellbook_that_gives_each_colour_its_component():
    assert V2.spellbook == 1
    assert all(V2.component_name(c) == get_spellbook(1)[c.colour] for c in V2.chips)


def test_spellbook_gives_the_component_of_a_colour(book):
    rs = Ruleset.model_validate(_data(book))
    assert {c.id: rs.component_name(c) for c in rs.chips}["blue_1"] == "orange@1"


def test_ruleset_without_a_spellbook_fails():
    data = _data()
    del data["spellbook"]
    with pytest.raises(ValidationError, match="spellbook"):
        Ruleset.model_validate(data)


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


@pytest.fixture
def bonus_book():
    # blue gets a test component with a placement bonus: +1 after a chip of another value than 1
    from quack_rl.components import Component, register, registry

    @register
    class _Bonus(Component):
        name = "test_bonus@1"

        def place_bonus(self, chip, previous, pot=()):
            return 1 if previous is not None and previous.value != 1 else 0

    register_spellbook("test_bonus", {**COMPONENTS, "blue": "test_bonus@1"})
    try:
        yield "test_bonus"
    finally:
        unregister_spellbook("test_bonus")
        registry._REGISTRY.pop("test_bonus@1", None)


def test_engine_reads_component_through_spellbook(book, bonus_book):
    spell = _with_blue_in_bag(_data(book))
    bonus = _with_blue_in_bag(_data(bonus_book))
    # The second blue chip (value 2) follows a value-4 chip: +1 with the bonus component only.
    assert _fields_after_two_blue_draws(bonus) == 7
    assert _fields_after_two_blue_draws(spell) == 6


GREEN_BLUE_BOOK = "test_green_blue"


@pytest.fixture
def green_blue_book():
    # blue gets the green component (a ruby for each of the last two placed chips)
    register_spellbook(GREEN_BLUE_BOOK, {**COMPONENTS, "blue": "green@1"})
    try:
        yield GREEN_BLUE_BOOK
    finally:
        unregister_spellbook(GREEN_BLUE_BOOK)


def test_resolve_reads_component_through_spellbook(green_blue_book):
    from quack_rl.engine.resolve import apply_resolve
    from quack_rl.engine.state import Status

    def green_bonuses(rs):
        state = new_game(rs)
        for p in state.players.values():
            p.placed = ["blue_4", "blue_2"]
            p.final_field = 0
            p.status = Status.EXPLODED  # no bonus die roll
        events: list = []
        apply_resolve(state, rs, ScriptedChance([]), events)
        return [e for e in events if e["kind"] == "round_end_bonus"]

    assert green_bonuses(Ruleset.model_validate(_data())) == []
    assert len(green_bonuses(Ruleset.model_validate(_data(green_blue_book)))) == 4  # 2 chips x 2 seats
