"""Records and replay with everything new in v2.3 (issue #189)."""

import io
import json
import random
from collections.abc import Sequence

import pytest
from helpers import RS
from hypothesis import given
from hypothesis import strategies as st

from quack_rl.bots import RandomBot
from quack_rl.engine import SEATS, RngChance
from quack_rl.record import (
    RECORD_SCHEMA_VERSION,
    GameRecorder,
    HeaderLine,
    RecordFormatError,
    SeatInfo,
    read_games,
    verify_game,
    verify_seed,
)
from quack_rl.runner import play_game

CARDS = [c.id for c in RS.cards]


class ForcedDeck(RngChance):
    """Seeded chance whose card draws follow a given order (the test helper that sets the deck order)."""

    def __init__(self, seed: int, order: Sequence[str]):
        super().__init__(seed)
        self._order = iter(order)

    def draw_card(self, deck: Sequence[str]) -> str:
        return next(self._order)


def header(seed: int | None, version: int = RECORD_SCHEMA_VERSION) -> HeaderLine:
    return HeaderLine(
        game_id="g1",
        schema_version=version,
        rules_version="v2.3",
        rounds=RS.rounds,
        seed=seed,
        mode="sim",
        seats={
            "p1": SeatInfo(kind="bot", name="random"),
            "p2": SeatInfo(kind="bot", name="random"),
        },
        ui={},
        engine_version="0.1.0",
        started_at="2026-10-08T21:15:03+02:00",
    )


def record(chance, seed: int | None, bot_seed: int, tmp_path):
    path = tmp_path / "g.jsonl"
    with path.open("w", encoding="utf-8") as f:
        rec = GameRecorder(f, header(seed))
        final = play_game(
            RS, {"p1": RandomBot(bot_seed), "p2": RandomBot(bot_seed + 1)}, chance, rec.on_step
        )
        rec.close(final)
    (game,) = read_games(path)
    return game, final


def test_the_schema_version_is_3():
    assert RECORD_SCHEMA_VERSION == 3


@pytest.mark.parametrize("old", [1, 2])
def test_the_reader_refuses_an_old_schema_version_and_names_both_versions(tmp_path, old):
    """Schema version 2 (v2.1 and v2.2 records, droplet in half steps) is refused, not converted."""
    path = tmp_path / "old.jsonl"
    path.write_text(header(5, version=old).model_dump_json() + "\n", encoding="utf-8")
    with pytest.raises(RecordFormatError) as e:
        list(read_games(path))
    assert f"schema_version {old}" in str(e.value) and "schema_version 3" in str(e.value)


@pytest.mark.parametrize("card", CARDS)
@given(data=st.data())
def test_a_game_with_each_card_replays_to_the_played_state(card, data):
    seed = data.draw(st.integers(min_value=0, max_value=2**31 - 1))
    position = data.draw(st.integers(min_value=0, max_value=RS.rounds - 1))
    rest = [c for c in CARDS if c != card]
    random.Random(seed).shuffle(rest)
    order = [*rest[:position], card, *rest[position:]]
    stream = io.StringIO()
    rec = GameRecorder(stream, header(None))
    final = play_game(
        RS, {"p1": RandomBot(seed), "p2": RandomBot(seed + 1)}, ForcedDeck(seed, order), rec.on_step
    )
    rec.close(final)
    stream.seek(0)
    lines = [json.loads(line) for line in stream.getvalue().splitlines()]
    played = [e["card"] for line in lines for e in line.get("events", []) if e["kind"] == "card_draw"]
    assert played[position] == card
    # replay from the record alone: every step, the events and the footer agree with the played game
    path_game = _read(stream.getvalue())
    assert verify_game(path_game) == []
    assert path_game.footer is not None
    assert path_game.footer.points == {s: final.players[s].points for s in SEATS}


def _read(text: str):
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "g.jsonl"
        path.write_text(text, encoding="utf-8")
        (game,) = read_games(path)
    return game


def test_seeded_games_with_all_20_cards_pass_the_seed_check(tmp_path):
    seen: set[str] = set()
    for seed in range(200):
        game, _final = record(RngChance(seed), seed, seed * 2 + 1, tmp_path)
        assert verify_game(game) == [], seed
        assert verify_seed(game) == [], seed
        seen |= {
            o["value"] for s in game.steps for o in s.chance if o["kind"] == "card"
        }
        if seen == set(CARDS):
            return
    raise AssertionError(f"cards never played: {sorted(set(CARDS) - seen)}")


def test_the_record_holds_the_new_event_kinds_and_chance_outcomes(tmp_path):
    kinds: set[str] = set()
    chance_kinds: set[str] = set()
    for seed in range(200):
        game, _ = record(RngChance(seed), seed, seed * 2 + 1, tmp_path)
        for s in game.steps:
            kinds |= {e["kind"] for e in s.events}
            chance_kinds |= {o["kind"] for o in s.chance}
    wanted = {"ruby", "ruby_drop", "refill_flask", "round_chip", "card_choice", "card_draw"}
    assert wanted <= kinds, wanted - kinds
    assert chance_kinds == {"draw_chip", "die", "card"}


def test_a_changed_event_in_a_v2_3_record_is_found(tmp_path):
    game, _ = record(RngChance(3), 3, 7, tmp_path)
    step = next(s for s in game.steps if any(e["kind"] == "ruby" for e in s.events))
    next(e for e in step.events if e["kind"] == "ruby")["total"] += 1
    assert verify_game(game) != []
