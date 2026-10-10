"""One bot-vs-bot game, shared by `simulate` and `tournament`."""

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TextIO

from quack_rl import __version__
from quack_rl.cli.seats import parse_seat, seat_info
from quack_rl.engine import SEATS, GameState, RngChance, StepResult
from quack_rl.record import (
    RECORD_SCHEMA_VERSION,
    GameRecorder,
    HeaderLine,
    berlin_iso,
    new_game_id,
)
from quack_rl.rules import Ruleset
from quack_rl.runner import play_game


@dataclass
class GameStats:
    """Counts and per-round values taken from the game steps while the game is played.

    `money[seat][k]` is the amount of the seat's `money` event in round k (its money when the
    shop phase of round k starts), `points[seat][k]` its points total at the end of round k
    (after the shop).
    """

    draws: dict[str, int] = field(default_factory=lambda: dict.fromkeys(SEATS, 0))
    buys: dict[str, Counter[str]] = field(default_factory=lambda: {s: Counter() for s in SEATS})
    money: dict[str, dict[int, int]] = field(default_factory=lambda: {s: {} for s in SEATS})
    points: dict[str, dict[int, int]] = field(default_factory=lambda: {s: {} for s in SEATS})


def play_sim_game(
    rs: Ruleset,
    *,
    rules: str,
    rounds: int,
    overrides: Mapping[str, str],
    p1: str,
    p2: str,
    game_seed: int,
    stream: TextIO | None = None,
) -> tuple[GameState, dict[str, int], GameStats]:
    """Play one game of two bot seats with chance seed `game_seed`.

    The bot seats get the seeds 2 * game_seed + 1 and + 2. With a `stream` the game is recorded
    in it. Returns the final state, the number of explosions of each seat, and the draw and
    purchase counts, the money and points per round of each seat.
    """
    seats = {
        "p1": parse_seat(p1, 2 * game_seed + 1, rs=rs),
        "p2": parse_seat(p2, 2 * game_seed + 2, rs=rs),
    }
    recorder: GameRecorder | None = None
    if stream is not None:
        header = HeaderLine(
            game_id=new_game_id(),
            schema_version=RECORD_SCHEMA_VERSION,
            rules_version=rules,
            rounds=rounds,
            overrides=dict[str, int | bool | str](overrides),
            seed=game_seed,
            mode="sim",
            seats={s: seat_info(x) for s, x in seats.items()},
            ui={},
            engine_version=__version__,
            started_at=berlin_iso(),
        )
        recorder = GameRecorder(stream, header)
    explosions = dict.fromkeys(SEATS, 0)
    stats = GameStats()

    def on_step(result: StepResult, decision_ms: dict[str, int]) -> None:
        for event in result.events:
            if event.get("kind") == "explode":
                explosions[event["seat"]] += 1
            elif event.get("kind") == "place":
                stats.draws[event["seat"]] += 1
            elif event.get("kind") == "buy":
                stats.buys[event["seat"]][event["item"]] += 1
            elif event.get("kind") == "money":
                stats.money[event["seat"]][result.round] = event["amount"]
            elif event.get("kind") in ("round_end", "game_end"):
                for seat in SEATS:
                    stats.points[seat][result.round] = result.state.players[seat].points
        if recorder is not None:
            recorder.on_step(result, decision_ms)

    final = play_game(rs, seats, RngChance(game_seed), on_step)
    if recorder is not None:
        recorder.close(final)
    return final, explosions, stats
