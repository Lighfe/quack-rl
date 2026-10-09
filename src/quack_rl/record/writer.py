from typing import TextIO

from pydantic import BaseModel

from quack_rl.engine import SEATS, GameState, StepResult
from quack_rl.record.schema import FooterLine, HeaderLine, StepLine


class GameRecorder:
    """Writes one game as JSON Lines, one line at a time (flushed after each line)."""

    def __init__(self, stream: TextIO, header: HeaderLine):
        self._stream = stream
        self.game_id = header.game_id
        self._write(header)

    def _write(self, line: BaseModel) -> None:
        self._stream.write(line.model_dump_json(exclude_none=False) + "\n")
        self._stream.flush()

    def on_step(self, result: StepResult, decision_ms: dict[str, int]) -> None:
        self._write(
            StepLine(
                game_id=self.game_id,
                n=result.n,
                round=result.round,
                phase=result.phase.value,
                legal=result.legal,
                actions=result.actions,
                chance=result.chance,
                events=result.events,
                decision_ms=decision_ms or None,
            )
        )

    def close(self, state: GameState) -> None:
        self._write(
            FooterLine(
                game_id=self.game_id,
                points={s: state.players[s].points for s in SEATS},
                final_fields={s: state.players[s].final_field for s in SEATS},
                winner=state.winner or "",
            )
        )
