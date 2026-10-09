"""Regenerate the golden record. Only run this on purpose: the golden file pins rules v1 behavior.

uv run python tests/fixtures/make_golden.py
"""

from pathlib import Path

from quack_rl import __version__
from quack_rl.bots import RandomBot
from quack_rl.engine import RngChance
from quack_rl.record import GameRecorder, HeaderLine, SeatInfo
from quack_rl.rules import load_ruleset
from quack_rl.runner import play_game

OUT = Path(__file__).parent / "golden" / "v1_random_seed7.jsonl"


def main() -> None:
    rs = load_ruleset("v1")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    header = HeaderLine(
        game_id="golden-v1-seed7",
        schema_version=1,
        rules_version="v1",
        seed=7,
        mode="sim",
        seats={
            "p1": SeatInfo(kind="bot", name="random", params={"seed": 15}),
            "p2": SeatInfo(kind="bot", name="random", params={"seed": 16}),
        },
        ui={},
        engine_version=__version__,
        started_at="2026-10-08T12:00:00+02:00",
    )
    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        rec = GameRecorder(f, header)
        final = play_game(rs, {"p1": RandomBot(15), "p2": RandomBot(16)}, RngChance(7), rec.on_step)
        rec.close(final)


if __name__ == "__main__":
    main()
