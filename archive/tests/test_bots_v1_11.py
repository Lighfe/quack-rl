"""Bots, balance report and tournament under ruleset v1.11 (round-start cards), issue #145."""

import csv
import json
from fractions import Fraction

import pytest

from quack_rl.bots import STRATEGIES, HeuristicBot, RandomBot, explosion_chance
from quack_rl.bots.heuristic import RESTART_BELOW
from quack_rl.engine import (
    CARD_DROP_2,
    CARD_DROP_END,
    CONTINUE,
    DRAW,
    RESTART,
    STOP,
    Phase,
    RngChance,
    ScriptedChance,
    explosion_limit,
    legal_actions,
    new_game,
    step,
)
from quack_rl.record import read_games
from quack_rl.report import (
    _brew_outcomes,
    _round_limits,
    build_report,
    realistic_baseline_maximum,
)
from quack_rl.rules import load_ruleset, with_rounds
from quack_rl.runner import play_game
from quack_rl.tournament import TournamentConfig, csv_columns, write_run

RS = load_ruleset("v1.11")
EFFECT_CARDS = [f"card_{n}" for n in range(1, 8)]
SEEDS = range(1, 13)  # fixed: 12 seeds x 2 orders; each game draws 9 of the 12 cards


def play_logged(p1, p2, seed):
    """Play one game; return the final state and the list of all step events."""
    events: list[dict] = []
    final = play_game(RS, {"p1": p1, "p2": p2}, RngChance(seed), lambda r, _: events.extend(r.events))
    return final, events


# --- full games ---------------------------------------------------------------------------


def make(kind, seed):
    if kind == "random":
        return RandomBot(seed)
    return HeuristicBot(RS, 20, 1, kind, seed=seed)


@pytest.mark.parametrize("kind", ["random", *sorted(STRATEGIES)])
def test_bot_plays_full_v1_11_games_and_meets_every_effect_card(kind):
    drawn: set[str] = set()
    for seed in SEEDS:
        for order in (0, 1):
            bots = [make(kind, 2 * seed + 1), make("random", 2 * seed + 2)]
            if order:
                bots.reverse()
            final, events = play_logged(bots[0], bots[1], seed)  # an illegal action would raise
            assert final.phase is Phase.GAME_OVER and final.winner is not None
            drawn |= {e["card"] for e in events if e["kind"] == "card_draw"}
    assert set(EFFECT_CARDS) <= drawn


def test_heuristic_bots_restart_and_decline_in_full_games():
    kinds = set()
    for seed in range(1, 40):
        bot = HeuristicBot(RS, 20, 1, "points", seed=seed)
        _, events = play_logged(bot, HeuristicBot(RS, 50, 1, "points", seed=seed + 1), seed)
        kinds |= {e["kind"] for e in events if e["kind"] in ("restart", "restart_continue")}
    assert kinds == {"restart", "restart_continue"}


# --- heuristic bot: card choice and restart -------------------------------------------------


def card_state(card):
    s = step(new_game(RS), RS, None, ScriptedChance([card])).state
    return s


def restart_state(bag, white_total, moved):
    """Round of card 2, both players at 5 chips, the restart is offered."""
    s = card_state("card_2")
    s.phase = Phase.RESTART
    for p in s.players.values():
        p.bag = dict(bag)
        p.placed = ["white_1"] * 5
        p.placed_fields = [1, 2, 3, 4, 5]
        p.white_total = white_total
        p.field = moved
        p.restart_offered = p.restart_pending = True
    return s


@pytest.mark.parametrize(
    ("card", "expected"), [("card_6", CARD_DROP_2), ("card_5", CARD_DROP_END)]
)
def test_card_choice_is_legal_and_is_the_drop(card, expected):
    s = card_state(card)
    assert s.phase is Phase.CARD_CHOICE
    bot = HeuristicBot(RS)
    for seat in ("p1", "p2"):
        legal = legal_actions(s, RS, seat)
        assert bot.choose(s, seat, legal) == expected
        assert expected in legal


def test_restart_is_taken_when_the_bot_would_stop_and_moved_little():
    s = restart_state({"white_3": 10}, 5, moved=RESTART_BELOW - 1)  # 5 + 3 > 7: always explodes
    legal = legal_actions(s, RS, "p1")
    assert HeuristicBot(RS, 20).choose(s, "p1", legal) == RESTART
    step(s, RS, {"p1": RESTART, "p2": RESTART}, ScriptedChance([]))  # legal for the engine


@pytest.mark.parametrize(
    ("bag", "white_total", "moved"),
    [
        ({"white_1": 10}, 5, RESTART_BELOW - 1),  # a safe next draw: continue
        ({"white_3": 10}, 5, RESTART_BELOW),  # would stop, but the pot moved far: continue
    ],
)
def test_restart_is_declined_otherwise(bag, white_total, moved):
    s = restart_state(bag, white_total, moved)
    legal = legal_actions(s, RS, "p1")
    assert HeuristicBot(RS, 20).choose(s, "p1", legal) == CONTINUE
    step(s, RS, {"p1": CONTINUE, "p2": CONTINUE}, ScriptedChance([]))


# --- explosion look-ahead with card 4 ----------------------------------------------------


def test_brew_look_ahead_uses_the_limit_of_card_4():
    # white total 5, bag of white_3: 5 + 3 = 8 explodes at limit 7, not at limit 9 (card 4)
    plain, plus = card_state("card_8_to_12"), card_state("card_4")
    assert explosion_limit(plain, RS) == RS.explosion_limit
    assert explosion_limit(plus, RS) == RS.explosion_limit + 2
    for s in (plain, plus):
        for p in s.players.values():
            p.bag, p.placed, p.white_total = {"white_3": 10}, ["white_1"], 5
    assert RS.explosion_limit == 7
    bot = HeuristicBot(RS, draw_limit=20)
    assert bot.choose(plain, "p1", [DRAW, STOP]) == STOP
    assert bot.choose(plus, "p1", [DRAW, STOP]) == DRAW
    assert explosion_chance({"white_3": 10}, 5, RS, limit=9) == 0.0


def test_restart_look_ahead_uses_the_limit_of_card_4():
    s = restart_state({"white_3": 10}, 5, moved=3)
    s.card = "card_4"  # the same pot is safe at limit 9
    legal = legal_actions(s, RS, "p1")
    assert HeuristicBot(RS, 20).choose(s, "p1", legal) == CONTINUE


# --- report ----------------------------------------------------------------------------------


def test_round_limits_follow_the_deck():
    assert _round_limits(RS) == [(7, Fraction(11, 12)), (9, Fraction(1, 12))]
    assert _round_limits(load_ruleset("v1.10")) == [(7, Fraction(1))]


def test_brew_outcomes_use_the_limit_of_the_round():
    bag = (("white_3", 3),)  # three chips of weight 3: 9 explodes at limit 7, not at 9
    assert sum(p for (_, boom, _, _), p in _brew_outcomes(RS, bag, 100, limit=7).items() if boom) == 1.0
    assert sum(p for (_, boom, _, _), p in _brew_outcomes(RS, bag, 100, limit=9).items() if boom) == 0.0
    assert _brew_outcomes(RS, bag, 100) == _brew_outcomes(RS, bag, 100, limit=7)


def test_realistic_maximum_on_v1_11_is_not_below_the_one_without_cards():
    # 3 rounds instead of 9: the calculation is far cheaper and the property is the same
    rs = with_rounds(RS, 3)
    no_cards = rs.model_copy(update={"cards": []})
    # card 4 only raises the limit, so the maximum cannot fall (up to float noise)
    assert realistic_baseline_maximum(rs) >= realistic_baseline_maximum(no_cards) - 1e-9


def test_report_numbers_equal_the_record_with_card_4_and_restarts(tmp_path):
    config = TournamentConfig(
        bots=("bot:draw20-pts1-points", "bot:draw50-pts1-blue", "bot:random"),
        games=6,
        seed=11,
        rules="v1.11",
        rounds=4,  # the report's calculated maximum grows with the rounds; 4 keep it cheap
        keep_records=True,
        sample_size=0,
    )
    folder, rows = write_run(config, tmp_path)
    games = [g for s in sorted((folder / "records").glob("*.gz")) for g in read_games(s)]
    assert len(games) == len(rows) == 18
    card_4_games = restarts = 0
    for row, game in zip(rows, games, strict=True):
        events = [e for step_ in game.steps for e in step_.events]
        card_4_games += any(e["kind"] == "card_draw" and e["card"] == "card_4" for e in events)
        restarts += sum(e["kind"] == "restart" for e in events)
        for seat in ("p1", "p2"):
            placed = sum(e["kind"] == "place" and e["seat"] == seat for e in events)
            boom = sum(e["kind"] == "explode" and e["seat"] == seat for e in events)
            assert int(row[f"{seat}_draws"]) == placed
            assert int(row[f"{seat}_explosions"]) == boom
    assert card_4_games > 0 and restarts > 0
    # the report reads the same rows: the explosion share is the share counted from the records
    text = build_report(folder)
    exploded = sum(int(r["p1_explosions"]) + int(r["p2_explosions"]) for r in rows)
    potions = 2 * len(rows) * config.rounds
    assert f"overall   {100 * exploded / potions:.1f}%" in text
    draws = sum(int(r["p1_draws"]) + int(r["p2_draws"]) for r in rows)
    assert f"{draws / len(rows):.2f}" in text
    assert "Cards: only the explosion limit of card 4" in text


def test_no_card_note_in_the_report_of_an_older_ruleset(tmp_path):
    config = TournamentConfig(
        bots=("bot:draw20-pts1-points", "bot:random"),
        games=2,
        seed=1,
        rules="v1.10",
        rounds=3,  # the report's calculated maximum grows with the rounds; 3 are enough here
        sample_size=0,
    )
    folder, _ = write_run(config, tmp_path)
    assert "Cards:" not in build_report(folder)


# --- tournament ------------------------------------------------------------------------------


def test_tournament_on_v1_11_writes_config_and_results(tmp_path):
    config = TournamentConfig(
        bots=("bot:draw20-pts1-points", "bot:draw30-pts3-blue", "bot:random"),
        games=4,
        seed=5,
        rules="v1.11",
        name="cards",
    )
    folder, rows = write_run(config, tmp_path)
    assert json.loads((folder / "config.json").read_text(encoding="utf-8"))["rules"] == "v1.11"
    assert len(rows) == 3 * 4
    with (folder / "results.csv").open(encoding="utf-8", newline="") as f:
        written = list(csv.DictReader(f))
    assert list(written[0]) == csv_columns(RS)
    assert {r["winner"] for r in written} <= {"p1", "p2", "draw"}
