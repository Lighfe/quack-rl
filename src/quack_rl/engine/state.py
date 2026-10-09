from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from quack_rl.rules import Ruleset

SEATS: tuple[str, str] = ("p1", "p2")


class Phase(StrEnum):
    BREW = "brew"
    RESOLVE = "resolve"
    SHOP = "shop"
    GAME_OVER = "game_over"


class Status(StrEnum):
    BREWING = "brewing"
    STOPPED = "stopped"
    EXPLODED = "exploded"


@dataclass
class PlayerState:
    bag: dict[str, int]
    placed: list[str] = field(default_factory=list)
    field: int = 0
    white_total: int = 0
    status: Status = Status.BREWING
    droplet_halves: int = 0
    points: int = 0
    money: int = 0
    purchases: int = 0
    shop_done: bool = False
    final_field: int | None = None

    def owned(self, chip_id: str) -> int:
        return self.bag.get(chip_id, 0) + self.placed.count(chip_id)


@dataclass
class GameState:
    rules_version: str
    round: int
    phase: Phase
    step: int
    players: dict[str, PlayerState]
    winner: str | None = None


def scoring_field(landing_field: int, rs: Ruleset) -> int:
    """The first free field after the last chip: ruby and money come from here."""
    return min(landing_field + 1, rs.track_end)


def start_field(p: PlayerState, rs: Ruleset) -> int:
    return min(p.droplet_halves // 2, rs.track_end)


def new_game(rs: Ruleset) -> GameState:
    return GameState(
        rules_version=rs.version,
        round=1,
        phase=Phase.BREW,
        step=0,
        players={seat: PlayerState(bag=dict(rs.start_bag)) for seat in SEATS},
    )


def state_to_dict(state: GameState) -> dict[str, Any]:
    return asdict(state)


def state_from_dict(data: dict[str, Any]) -> GameState:
    players = {
        seat: PlayerState(**{**p, "status": Status(p["status"])})
        for seat, p in data["players"].items()
    }
    return GameState(**{**data, "phase": Phase(data["phase"]), "players": players})
