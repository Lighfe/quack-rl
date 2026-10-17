"""Game record and replay under ruleset v1.9 (blue hand and pick step)."""

import io
import random

import pytest

from quack_rl.engine import SEATS, RngChance, new_game, step
from quack_rl.record import GameRecorder, HeaderLine, SeatInfo, read_games, verify_game, verify_seed
from quack_rl.record.replay import RecordedChance, _header_ruleset
from quack_rl.rules import load_ruleset
from quack_rl.runner import play_game

PICK_ACTIONS = ("put_back_draw", "put_back_stop")


class PickBot:
    """Random bot that buys blue chips whenever it can, so hands and picks happen."""

    kind = "bot"
    name = "random"
    params: dict = {}

    def __init__(self, seed: int):
        self._rng = random.Random(seed)

    def choose(self, state, seat, legal):
        blue = [a for a in legal if a.startswith("buy:blue")]
        if blue:
            return self._rng.choice(blue)
        return self._rng.choice(legal)


def record_game(seed: int):
    rs = load_ruleset("v1.9")
    header = HeaderLine(
        game_id=f"g-v1.9-{seed}",
        schema_version=1,
        rules_version="v1.9",
        rounds=rs.rounds,
        seed=seed,
        mode="sim",
        seats={s: SeatInfo(kind="bot", name="random") for s in SEATS},
        ui={},
        engine_version="0.1.0",
        started_at="2026-10-17T10:00:00+02:00",
    )
    stream = io.StringIO()
    rec = GameRecorder(stream, header)
    seats = {"p1": PickBot(seed), "p2": PickBot(seed + 1000)}
    final = play_game(rs, seats, RngChance(seed), rec.on_step)
    rec.close(final)
    return stream.getvalue(), final


def actions_of(game):
    return [a for s in game.steps if s.actions for a in s.actions.values()]


def events_of(game, kind):
    return [e for s in game.steps for e in s.events if e["kind"] == kind]


def covers_all(game) -> bool:
    acts = actions_of(game)
    plays = [a for a in acts if a.startswith("play:")]
    chain = any(
        e["kind"] == "place" and e.get("chip", "").startswith("blue")
        for s in game.steps
        if s.actions and any(a.startswith("play:") for a in s.actions.values())
        for e in s.events
    )
    return bool(plays) and all(p in acts for p in PICK_ACTIONS) and chain


@pytest.fixture(scope="module")
def played(tmp_path_factory):
    for seed in range(1, 300):
        text, final = record_game(seed)
        path = tmp_path_factory.mktemp("rec") / "game.jsonl"
        path.write_text(text, encoding="utf-8")
        (game,) = read_games(path)
        if covers_all(game):
            return game, final, path
    pytest.fail("no seed in 299 gave a play, a chain, put_back_draw and put_back_stop")


def test_record_holds_pick_actions_and_hand_events(played):
    game, _, path = played
    raw = path.read_text(encoding="utf-8")
    for token in (
        '"play:',
        '"put_back_draw"',
        '"put_back_stop"',
        '"kind":"hand"',
        '"kind":"put_back"',
    ):
        assert token in raw
    acts = actions_of(game)
    assert any(a.startswith("play:") for a in acts)
    assert all(p in acts for p in PICK_ACTIONS)
    hands = events_of(game, "hand")
    puts = events_of(game, "put_back")
    assert hands and puts
    assert all(isinstance(e["chips"], list) and e["chips"] for e in hands)
    assert all(isinstance(e["chips"], list) for e in puts)


def test_replayed_final_state_equals_live_final_state(played):
    game, final, _ = played
    assert verify_game(game) == []
    assert verify_seed(game) == []
    rs = _header_ruleset(game)
    state = new_game(rs)
    for line in game.steps:
        chance = RecordedChance(line.chance)
        state = step(state, rs, line.actions, chance).state
    assert state == final
    for seat in SEATS:
        a, b = state.players[seat], final.players[seat]
        assert (a.status, a.bag, a.hand, a.placed, a.money, a.points) == (
            b.status,
            b.bag,
            b.hand,
            b.placed,
            b.money,
            b.points,
        )


def test_tampered_hand_event_is_a_problem(played):
    game, _, _ = played
    import copy

    g = copy.deepcopy(game)
    for s in g.steps:
        for e in s.events:
            if e["kind"] == "hand":
                e["chips"] = list(reversed(e["chips"])) + ["white_1"]
                assert verify_game(g)
                return
    pytest.fail("no hand event")
