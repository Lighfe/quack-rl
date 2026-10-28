"""Golden replay of a stored v2.1 game: the record replays to the same events and final state.

The record is `tests/fixtures/golden/v2_1_random_seed7.jsonl` (regenerate it on purpose with
`tests/fixtures/make_golden.py`). A rule number or an engine step that changes the outcome fails here.
"""

from pathlib import Path

from quack_rl.record import read_games, verify_game, verify_seed

GOLDEN = Path(__file__).parent / "fixtures" / "golden" / "v2_1_random_seed7.jsonl"

# Stored result of the game (the footer of the record)
FINAL_POINTS = {"p1": 17, "p2": 10}
FINAL_FIELDS = {"p1": 10, "p2": 8}


def golden():
    (game,) = read_games(GOLDEN)
    return game


def event_kinds(game) -> set[str]:
    return {e["kind"] for s in game.steps for e in s.events}


def test_stored_game_replays_to_the_stored_final_state():
    game = golden()
    assert game.header.rules_version == "v2.1"
    assert verify_game(game) == []  # every event and legal set equals the replay, the footer matches
    assert verify_seed(game) == []  # the chance outcomes equal what the seed gives
    end = [e for s in game.steps for e in s.events if e["kind"] == "game_end"]
    assert len(end) == 1
    assert end[0]["points"] == FINAL_POINTS and end[0]["final_fields"] == FINAL_FIELDS
    assert end[0]["winner"] == "p1"


def test_stored_game_has_six_cards_a_flask_use_and_a_ruby_drop():
    game = golden()
    cards = {e["card"] for s in game.steps for e in s.events if e["kind"] == "card_draw"}
    assert len(cards) >= 6
    kinds = event_kinds(game)
    assert {"card_draw", "use_flask", "ruby_drop"} <= kinds


def test_stored_game_closes_idle_shops_without_asking():
    """Issue #203: an idle seat gets an automatic done and then only `wait` in the shop."""
    game = golden()
    autos = [
        (s, e) for s in game.steps for e in s.events if e["kind"] == "done" and e.get("auto")
    ]
    assert autos
    for s, e in autos:
        if s.phase == "shop":  # closed after a shop step: the seat was not asked for done
            assert s.actions[e["seat"]] != "done"
        later = [x for x in game.steps if x.n > s.n and x.round == s.round and x.phase == "shop"]
        for x in later:
            assert x.legal[e["seat"]] == ["wait"] and x.actions[e["seat"]] == "wait"


def test_a_changed_rule_number_changes_the_outcome():
    game = golden()
    game.header.overrides = {"shop.orange_1.price": "4"}
    problems = verify_game(game)
    assert problems  # the replay no longer equals the stored game


def test_a_changed_explosion_limit_changes_the_outcome():
    game = golden()
    game.header.overrides = {"explosion_limit": "5"}
    assert verify_game(game)


# --- a stored layout 8 sample ----------------------------------------------------------

SAMPLE = GOLDEN.parent / "layout8_sample.json"


def state_of_sample(sample, rs):
    from quack_rl.engine import new_game, step
    from quack_rl.record import RecordedChance

    state = new_game(rs)
    for line in golden().steps[: sample["after_step"]]:
        state = step(state, rs, line.actions, RecordedChance(line.chance)).state
    return state


def test_layout8_sample_names_and_vector_match_value_for_value():
    import json

    from quack_rl.rl import BOARD_LAYOUT, observe, vector_names, vectorize
    from quack_rl.rules import load_ruleset

    sample = json.loads(SAMPLE.read_text(encoding="utf-8"))
    rs = load_ruleset("v2.1")
    assert sample["layout"] == BOARD_LAYOUT == 8
    state = state_of_sample(sample, rs)
    names = vector_names(rs)
    vector = vectorize(observe(state, rs, sample["seat"]), rs)
    assert names == sample["names"]
    assert len(vector) == len(sample["values"]) == len(names)
    wrong = [
        (n, got, want)
        for n, got, want in zip(names, vector.tolist(), sample["values"])
        if got != want
    ]
    assert wrong == []
