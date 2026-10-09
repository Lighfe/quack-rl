from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

RECORD_SCHEMA_VERSION = 1


class _Line(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SeatInfo(_Line):
    kind: Literal["human", "bot"]
    name: str
    params: dict[str, Any] = {}


class HeaderLine(_Line):
    type: Literal["header"] = "header"
    game_id: str
    schema_version: int
    rules_version: str
    seed: int | None
    mode: Literal["play", "sim"]
    seats: dict[str, SeatInfo]
    ui: dict[str, Any]
    engine_version: str
    started_at: str


class StepLine(_Line):
    type: Literal["step"] = "step"
    game_id: str
    n: int
    round: int
    phase: str
    legal: dict[str, list[str]] | None
    actions: dict[str, str] | None
    chance: list[dict[str, Any]]
    events: list[dict[str, Any]]
    decision_ms: dict[str, int] | None = None


class FooterLine(_Line):
    type: Literal["footer"] = "footer"
    game_id: str
    points: dict[str, int]
    final_fields: dict[str, int | None]
    winner: str


Line = Annotated[HeaderLine | StepLine | FooterLine, Field(discriminator="type")]
LINE_ADAPTER: TypeAdapter[HeaderLine | StepLine | FooterLine] = TypeAdapter(Line)


def record_json_schema() -> dict[str, Any]:
    return LINE_ADAPTER.json_schema()
