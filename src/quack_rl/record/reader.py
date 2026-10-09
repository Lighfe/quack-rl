import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from quack_rl.record.schema import LINE_ADAPTER, FooterLine, HeaderLine, StepLine


class RecordFormatError(ValueError):
    """A record file that does not follow the record format."""


@dataclass
class RecordedGame:
    header: HeaderLine
    steps: list[StepLine] = field(default_factory=list)
    footer: FooterLine | None = None


def _check_header_rounds(path: Path, number: int, text: str) -> None:
    """A header without `rounds` is refused with a message that names the field and the game."""
    try:
        raw = json.loads(text)
    except ValueError:
        return  # the schema check reports it
    if isinstance(raw, dict) and raw.get("type") == "header" and "rounds" not in raw:
        raise RecordFormatError(
            f"{path}:{number}: game {raw.get('game_id')}: header has no field `rounds`"
        )


def read_games(path: Path) -> Iterator[RecordedGame]:
    """Yield each game of a record file. An unfinished game is yielded with footer None."""
    current: RecordedGame | None = None
    with path.open(encoding="utf-8") as f:
        for number, text in enumerate(f, start=1):
            if not text.strip():
                continue
            _check_header_rounds(path, number, text)
            try:
                line = LINE_ADAPTER.validate_json(text)
            except ValidationError as e:
                raise RecordFormatError(f"{path}:{number}: {e}") from e
            if isinstance(line, HeaderLine):
                if current is not None:
                    yield current
                current = RecordedGame(header=line)
                continue
            if current is None or current.footer is not None:
                raise RecordFormatError(f"{path}:{number}: {line.type} line outside a game")
            if line.game_id != current.header.game_id:
                raise RecordFormatError(
                    f"{path}:{number}: game_id {line.game_id} inside game {current.header.game_id}"
                )
            if isinstance(line, StepLine):
                current.steps.append(line)
            else:
                current.footer = line
                yield current
                current = None
    if current is not None:
        yield current
