import random
from collections import Counter
from typing import Any

import pytest
from helpers import RS
from hypothesis import given
from hypothesis import strategies as st

from quack_rl.bots import RandomBot
from quack_rl.engine import SEATS, WAIT, IllegalAction, Phase, RngChance
from quack_rl.runner import play_game


def run(seed):
    results = []
    final = play_game(
        RS,
        {"p1": RandomBot(seed * 2 + 1), "p2": RandomBot(seed * 2 + 2)},
        RngChance(seed),
        on_step=lambda r, ms: results.append(r),
    )
    return final, results


def test_a_seeded_game_is_reproducible():
    a, ra = run(7)
    b, rb = run(7)
    assert a == b and [r.events for r in ra] == [r.events for r in rb]


def test_a_game_ends_after_nine_rounds_with_a_winner():
    final, results = run(3)
    assert final.phase is Phase.GAME_OVER and final.round == RS.rounds
    assert final.winner in ("p1", "p2", "draw")
    assert [r.n for r in results] == list(range(1, len(results) + 1))


@given(seed=st.integers(min_value=0, max_value=2**31 - 1))
def test_invariants_hold_in_random_games(seed):
    final, results = run(seed)
    acquired = {s: Counter(RS.start_bag) for s in SEATS}
    for r in results:
        for e in r.events:
            if e["kind"] == "buy":
                item = RS.shop_item(e["item"])
                if item.kind == "chip":
                    acquired[e["seat"]][item.chip] += 1
                elif item.kind == "remove_chip":
                    acquired[e["seat"]][item.chip] -= 1
            if e["kind"] == "die":
                face = next(f for f in RS.die if f.id == e["face"])
                if face.kind == "chip":
                    acquired[e["seat"]][face.chip] += 1
        for seat in SEATS:
            p = r.state.players[seat]
            # chip accounting per chip type: owned = start + bought + die - removed = bag + placed
            owned = Counter(p.bag) + Counter(p.placed)
            assert +acquired[seat] == owned
            assert p.money >= 0
            assert 0 <= p.field <= RS.track_end
            assert all(n > 0 for n in p.bag.values())
            if r.actions is not None:
                assert r.actions[seat] in r.legal[seat]
        if any(e["kind"] == "round_end" for e in r.events):
            assert all(not p.placed for p in r.state.players.values())
    assert final.phase is Phase.GAME_OVER


# --- RandomBot ---


def test_random_bot_attributes():
    bot = RandomBot(42)
    assert bot.kind == "bot"
    assert bot.name == "random"
    assert bot.params == {"seed": 42}
    unseeded = RandomBot()
    assert unseeded.kind == "bot"
    assert unseeded.name == "random"
    assert unseeded.params == {"seed": None}


def test_random_bot_is_reproducible_per_seed():
    state = None  # choose does not read the state
    legal_lists = [["a", "b", "c", "d"][: 1 + i % 4] for i in range(50)]
    a, b = RandomBot(5), RandomBot(5)
    seq_a = [a.choose(state, "p1", legal) for legal in legal_lists]  # type: ignore[arg-type]
    seq_b = [b.choose(state, "p1", legal) for legal in legal_lists]  # type: ignore[arg-type]
    assert seq_a == seq_b
    assert all(choice in legal for choice, legal in zip(seq_a, legal_lists, strict=True))
    expected_rng = random.Random(5)
    assert seq_a == [expected_rng.choice(legal) for legal in legal_lists]


def test_random_bot_chooses_uniformly():
    bot = RandomBot(123)
    legal = ["x", "y", "z"]
    counts = Counter(bot.choose(None, "p1", legal) for _ in range(3000))  # type: ignore[arg-type]
    assert set(counts) == set(legal)
    assert all(counts[name] >= 800 for name in legal)


# --- Runner ---


class RecordingSeat:
    """Chooses randomly and records every legal list it is given."""

    kind = "bot"
    name = "recording"

    def __init__(self, seed: int):
        self._rng = random.Random(seed)
        self.params: dict[str, Any] = {"seed": seed}
        self.asked: list[list[str]] = []

    def choose(self, state, seat, legal):
        self.asked.append(list(legal))
        return self._rng.choice(legal)


class ScriptedHumanSeat:
    """A test seat of kind "human": no keyboard input, it picks the first legal action."""

    kind = "human"
    name = "scripted-human"

    def __init__(self):
        self.params: dict[str, Any] = {}

    def choose(self, state, seat, legal):
        return legal[0]


class IllegalSeat:
    kind = "bot"
    name = "illegal"

    def __init__(self):
        self.params: dict[str, Any] = {}

    def choose(self, state, seat, legal):
        return "not-an-action"


def test_a_wait_only_seat_is_not_asked():
    recorder = RecordingSeat(11)
    results = []
    play_game(
        RS,
        {"p1": recorder, "p2": RandomBot(12)},
        RngChance(13),
        on_step=lambda r, ms: results.append(r),
    )
    assert recorder.asked, "the recording seat was never asked"
    assert all(legal != [WAIT] for legal in recorder.asked)
    wait_steps = [r for r in results if r.legal is not None and r.legal["p1"] == [WAIT]]
    assert wait_steps, "the game had no step where p1 could only wait"
    for r in wait_steps:
        assert r.actions is not None and r.actions["p1"] == WAIT


def test_on_step_gets_decision_ms_only_for_asked_human_seats():
    human = ScriptedHumanSeat()
    calls: list[tuple[Any, dict[str, int]]] = []
    final = play_game(
        RS,
        {"p1": human, "p2": RandomBot(21)},
        RngChance(22),
        on_step=lambda r, ms: calls.append((r, dict(ms))),
    )
    assert final.phase is Phase.GAME_OVER
    assert [r.n for r, _ in calls] == list(range(1, len(calls) + 1))
    saw_no_action_step = False
    saw_human_timing = False
    for r, ms in calls:
        assert "p2" not in ms
        if r.actions is None:
            saw_no_action_step = True
            assert ms == {}
            continue
        for seat, value in ms.items():
            assert seat == "p1"
            # asked: the human seat had more than the single wait action
            assert r.legal[seat] != [WAIT]
            assert isinstance(value, int) and value >= 0
            saw_human_timing = True
        if r.legal["p1"] != [WAIT]:
            assert "p1" in ms
    assert saw_no_action_step and saw_human_timing


def test_an_illegal_action_from_a_seat_raises():
    with pytest.raises(IllegalAction):
        play_game(RS, {"p1": IllegalSeat(), "p2": RandomBot(1)}, RngChance(1))
