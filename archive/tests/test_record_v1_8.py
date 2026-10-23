"""Game record and replay under ruleset v1.8 (explosion choice) and older rulesets."""

import copy
import io
from pathlib import Path

import pytest
from typer.testing import CliRunner

from quack_rl.bots import RandomBot
from quack_rl.cli.main import app
from quack_rl.engine import RngChance
from quack_rl.record import (
    GameRecorder,
    HeaderLine,
    SeatInfo,
    read_games,
    verify_game,
    verify_seed,
)
from quack_rl.rules import load_ruleset
from quack_rl.runner import play_game

GOLDEN = Path(__file__).parent / "fixtures" / "golden" / "v1_random_seed7.jsonl"
CHOICES = ("take_money", "take_points")
runner = CliRunner()


class ForcedChoiceBot:
    """A random bot that always answers the explosion choice with the given action."""

    kind = "bot"
    params: dict = {}

    def __init__(self, seed: int, choice: str | None):
        self.name = "random"
        self._inner = RandomBot(seed)
        self._choice = choice

    def choose(self, state, seat, legal):
        if self._choice in legal:
            return self._choice
        return self._inner.choose(state, seat, legal)


def record_text(version: str, seed: int, choice: str | None = None) -> str:
    rs = load_ruleset(version)
    header = HeaderLine(
        game_id=f"g-{version}-{seed}",
        schema_version=1,
        rules_version=version,
        rounds=rs.rounds,
        seed=seed,
        mode="sim",
        seats={s: SeatInfo(kind="bot", name="random") for s in ("p1", "p2")},
        ui={},
        engine_version="0.1.0",
        started_at="2026-10-08T21:15:03+02:00",
    )
    stream = io.StringIO()
    rec = GameRecorder(stream, header)
    seats = {"p1": ForcedChoiceBot(seed, choice), "p2": ForcedChoiceBot(seed + 1000, choice)}
    final = play_game(rs, seats, RngChance(seed), rec.on_step)
    rec.close(final)
    return stream.getvalue()


def load_game(text: str, tmp_path: Path, name: str = "game.jsonl"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    (game,) = read_games(path)
    return game, path


def choice_steps(game):
    return [s for s in game.steps if s.phase == "choice"]


def explosion_rounds(game) -> set[int]:
    return {s.round for s in choice_steps(game)}


@pytest.fixture(scope="module")
def v18_games():
    """Played v1.8 games: one with a round 9 explosion, one with an earlier one, one with both."""
    rounds = load_ruleset("v1.8").rounds
    found = {}
    for seed in range(1, 400):
        game = read_text_game(record_text("v1.8", seed))
        rs = explosion_rounds(game)
        if rounds in rs and "last" not in found:
            found["last"] = (seed, game)
        if any(r < rounds for r in rs) and "early" not in found:
            found["early"] = (seed, game)
        if len(found) == 2:
            break
    assert set(found) == {"last", "early"}, "no seed gave both a round 9 and an earlier explosion"
    return found


def read_text_game(text: str):
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        game, _ = load_game(text, Path(d))
    return game


def test_v1_8_games_with_explosions_verify(v18_games):
    rounds = load_ruleset("v1.8").rounds
    assert rounds in explosion_rounds(v18_games["last"][1])
    assert any(r < rounds for r in explosion_rounds(v18_games["early"][1]))
    for _, game in v18_games.values():
        assert game.header.rules_version == "v1.8"
        assert game.footer is not None
        assert verify_game(game) == []
        assert verify_seed(game) == []


def test_v1_8_choice_step_has_the_recorded_shape(v18_games):
    _, game = v18_games["early"]
    step = choice_steps(game)[0]
    assert step.phase == "choice"
    assert step.actions is not None
    assert any(a in CHOICES for a in step.actions.values())
    chosen = [e for e in step.events if e["kind"] in CHOICES]
    assert chosen
    for e in chosen:
        assert set(e) == {"seat", "kind", "amount"}


def test_v1_8_replayed_final_state_equals_footer(v18_games):
    for _, game in v18_games.values():
        assert game.footer is not None
        assert verify_game(game) == []  # compares points, final fields and winner to the footer
        tampered = copy.deepcopy(game)
        seat = "p1"
        tampered.footer.points[seat] += 1
        assert any("footer" in p for p in verify_game(tampered))


@pytest.mark.parametrize("choice", CHOICES)
def test_both_choices_are_recorded_and_verify(choice, tmp_path):
    for seed in range(1, 100):
        game, _ = load_game(record_text("v1.8", seed, choice), tmp_path)
        events = [e for s in choice_steps(game) for e in s.events if e["kind"] == choice]
        if events:
            assert verify_game(game) == []
            assert verify_seed(game) == []
            return
    pytest.fail(f"no game with a {choice} step in 99 seeds")


def test_bad_choice_action_is_a_problem(v18_games):
    game = copy.deepcopy(v18_games["early"][1])
    step = choice_steps(game)[0]
    seat = next(s for s, a in step.actions.items() if a in CHOICES)
    step.actions[seat] = "draw"
    problems = verify_game(game)
    assert problems and problems[0].startswith(f"step {step.n}:")


def test_golden_v1_record_still_loads_and_verifies():
    (game,) = read_games(GOLDEN)
    assert game.header.rules_version == "v1"
    assert verify_game(game) == []
    assert verify_seed(game) == []


def test_v1_1_game_written_by_the_runner_reads_back_and_verifies(tmp_path):
    game, _ = load_game(record_text("v1.1", 3), tmp_path)
    assert game.header.rules_version == "v1.1"
    assert choice_steps(game) == []
    assert verify_game(game) == []
    assert verify_seed(game) == []


def test_cli_verify_accepts_v1_8_record(v18_games, tmp_path):
    seed, _ = v18_games["early"]
    _, path = load_game(record_text("v1.8", seed), tmp_path)
    result = runner.invoke(app, ["verify", str(path)])
    assert result.exit_code == 0, result.output


def test_cli_verify_reports_changed_take_points_amount(tmp_path):
    for seed in range(1, 100):
        text = record_text("v1.8", seed, "take_points")
        if '"take_points"' in text:
            break
    else:
        pytest.fail("no take_points event in 99 seeds")
    import json

    lines = []
    changed = False
    for line in text.splitlines():
        obj = json.loads(line)
        if obj.get("type") == "step" and not changed:
            for e in obj["events"]:
                if e["kind"] == "take_points":
                    e["amount"] += 1
                    changed = True
        lines.append(json.dumps(obj))
    assert changed
    path = tmp_path / "tampered.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = runner.invoke(app, ["verify", str(path)])
    assert result.exit_code != 0
    assert "events differ" in result.output
