"""Golden replay of a stored v2.3 game, the layout 9 sample and RL on v2.3.

The files are `tests/fixtures/golden/v2_3_random_seed7.jsonl` and `layout9_sample.json`
(regenerate them on purpose with `uv run python tests/fixtures/make_golden.py`). A rule number or
an engine step that changes the outcome fails here.
"""

import json
import random
from pathlib import Path

import numpy as np

from quack_rl.engine import Phase, legal_actions, new_game, step
from quack_rl.record import RecordedChance, read_games, verify_game, verify_seed
from quack_rl.rl import BOARD_LAYOUT, QuackParallelEnv, observe, vector_names, vectorize
from quack_rl.rules import load_ruleset

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "fixtures" / "golden"
RECORD = GOLDEN / "v2_3_random_seed7.jsonl"
SAMPLE = GOLDEN / "layout9_sample.json"
LAYOUT8_SAMPLE = ROOT / "archive" / "tests" / "fixtures" / "golden" / "layout8_sample.json"
RS = load_ruleset("v2.3")

# Stored result of the game (the footer of the record)
FINAL_POINTS = {"p1": 11, "p2": 15}
FINAL_FIELDS = {"p1": 11, "p2": 11}


def golden():
    (game,) = read_games(RECORD)
    return game


def test_stored_game_replays_to_the_stored_final_state():
    game = golden()
    assert game.header.rules_version == "v2.3"
    assert verify_game(game) == []  # every event and legal set equals the replay, footer too
    assert verify_seed(game) == []  # the chance outcomes equal what the seed gives
    end = [e for s in game.steps for e in s.events if e["kind"] == "game_end"]
    assert len(end) == 1
    assert end[0]["points"] == FINAL_POINTS and end[0]["final_fields"] == FINAL_FIELDS
    assert end[0]["winner"] == "p2"


def test_stored_game_has_a_ruby_step_and_the_shop_offers_no_ruby_spend():
    game = golden()
    ruby = [s for s in game.steps if s.phase == "ruby"]
    assert ruby
    for s in game.steps:
        if s.phase == "shop":
            offered = {a for legal in s.legal.values() for a in legal}
            assert not {"ruby_drop", "refill_flask"} & offered
    spent = {e["kind"] for s in ruby for e in s.events}
    assert "ruby_drop" in spent


def test_droplet_events_carry_whole_steps_and_no_halves():
    game = golden()
    events = [e for s in game.steps for e in s.events]
    assert not [e for e in events if "halves" in e]
    drops = [e for e in events if e["kind"] in ("ruby_drop", "card_drop")]
    assert drops and all(e["drop"] in (1, 2) for e in drops)


def test_a_changed_rule_number_changes_the_outcome():
    game = golden()
    game.header.overrides = {"explosion_limit": "5"}
    assert verify_game(game)


# --- the stored layout 9 sample ----------------------------------------------------------


def test_layout9_names_are_the_layout8_names_with_whole_step_droplets():
    sample = json.loads(SAMPLE.read_text(encoding="utf-8"))
    old = json.loads(LAYOUT8_SAMPLE.read_text(encoding="utf-8"))
    assert sample["layout"] == BOARD_LAYOUT == 9
    assert sample["record"] == RECORD.name
    renamed = {"own.droplet_halves": "own.droplet", "opponent.droplet_halves": "opponent.droplet"}
    assert sample["names"] == [renamed.get(n, n) for n in old["names"]]
    assert vector_names(RS) == sample["names"]


def test_layout9_sample_matches_the_encoder_value_for_value():
    sample = json.loads(SAMPLE.read_text(encoding="utf-8"))
    state = new_game(RS)
    for line in golden().steps[: sample["after_step"]]:
        state = step(state, RS, line.actions, RecordedChance(line.chance)).state
    names = vector_names(RS)
    vector = vectorize(observe(state, RS, sample["seat"]), RS)
    assert len(vector) == len(sample["values"]) == len(names)
    wrong = [
        (n, got, want)
        for n, got, want in zip(names, vector.tolist(), sample["values"], strict=True)
        if got != want
    ]
    assert wrong == []
    own = sample["names"].index("own.droplet")
    assert sample["values"][own] == state.players[sample["seat"]].droplet


def test_masked_random_v2_3_game_stays_in_the_space_and_reaches_the_ruby_step():
    seen = False
    for seed in range(3):
        env = QuackParallelEnv(rules=RS)
        rng = random.Random(seed)
        obs, _ = env.reset(seed=seed)
        space = env.observation_space("p1")
        while env.agents:
            seen = seen or env.state.phase is Phase.RUBY
            for seat in env.agents:
                assert space.contains(obs[seat])
                if env.state.phase is not Phase.GAME_OVER:
                    legal = set(legal_actions(env.state, RS, seat))
                    mask = obs[seat]["action_mask"]
                    assert {env._names[i] for i in np.flatnonzero(mask)} <= legal | {"wait"}
            acts = {
                a: rng.choice(np.flatnonzero(obs[a]["action_mask"]).tolist()) for a in env.agents
            }
            obs, *_ = env.step(acts)
    assert seen
