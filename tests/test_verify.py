import copy
from pathlib import Path

import quack_rl.record as record
from quack_rl.record import read_games, verify_game, verify_seed

GOLDEN = Path(__file__).parent / "fixtures" / "golden" / "v1_random_seed7.jsonl"


def golden():
    (game,) = read_games(GOLDEN)
    return game


def first_step_with_draw(game):
    return next(s for s in game.steps if any(c["kind"] == "draw_chip" for c in s.chance))


def test_golden_record_verifies():
    assert verify_game(golden()) == []


def test_golden_record_matches_its_seed():
    assert verify_seed(golden()) == []


def test_unsupported_rules_version_is_refused():
    game = golden()
    game.header.rules_version = "v9"
    assert verify_game(game) == ["unsupported rules version 'v9'"]


def test_seed_check_refuses_unsupported_rules_version():
    game = golden()
    game.header.rules_version = "v9"
    assert verify_seed(game) == ["unsupported rules version 'v9'"]


def test_impossible_chip_draw_is_rejected():
    game = copy.deepcopy(golden())
    first_step_with_draw(game).chance[0]["value"] = "blue_4"  # not in the start bag
    problems = verify_game(game)
    assert problems and "not in the bag" in problems[0]


def test_extra_chance_outcome_is_rejected():
    game = copy.deepcopy(golden())
    s = first_step_with_draw(game)
    s.chance.append({"seat": "p1", "kind": "die", "value": "money_1"})
    problems = verify_game(game)
    assert problems and "extra chance outcome" in problems[0]


def test_missing_chance_outcome_is_rejected():
    game = copy.deepcopy(golden())
    first_step_with_draw(game).chance.clear()
    problems = verify_game(game)
    assert problems and "missing chance outcome" in problems[0]


def test_chance_outcome_with_wrong_kind_does_not_fit():
    game = copy.deepcopy(golden())
    first_step_with_draw(game).chance[0]["kind"] = "die"
    problems = verify_game(game)
    assert problems and "does not fit" in problems[0]


def test_chance_outcome_with_wrong_seat_does_not_fit():
    game = copy.deepcopy(golden())
    outcome = first_step_with_draw(game).chance[0]
    outcome["seat"] = "p2" if outcome["seat"] == "p1" else "p1"
    problems = verify_game(game)
    assert problems and "does not fit" in problems[0]


def test_changed_event_is_reported():
    game = copy.deepcopy(golden())
    game.steps[0].events[0]["to"] = 40
    problems = verify_game(game)
    assert problems and "events differ" in problems[0]


def test_changed_legal_actions_are_reported():
    game = copy.deepcopy(golden())
    game.steps[0].legal = {"p1": ["draw", "stop"], "p2": ["draw"]}
    problems = verify_game(game)
    assert problems and "legal actions differ" in problems[0]


def test_incomplete_game_is_reported_not_crashing():
    game = copy.deepcopy(golden())
    game.steps = game.steps[:10]
    game.footer = None
    assert verify_game(game) == ["incomplete game: no footer"]


def test_wrong_footer_is_reported():
    game = copy.deepcopy(golden())
    assert game.footer is not None
    game.footer.winner = "p2" if game.footer.winner != "p2" else "p1"
    assert any("footer" in p for p in verify_game(game))


def test_step_problems_name_the_step():
    game = copy.deepcopy(golden())
    s = first_step_with_draw(game)
    s.chance.clear()
    (problem,) = verify_game(game)
    assert problem.startswith(f"step {s.n}:")


def test_replay_names_are_exported():
    for name in ("ChanceMismatch", "RecordedChance", "verify_game", "verify_seed"):
        assert name in record.__all__
        assert hasattr(record, name)
