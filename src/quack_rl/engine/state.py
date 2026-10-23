import dataclasses
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from quack_rl.rules import Ruleset

SEATS: tuple[str, str] = ("p1", "p2")


class Phase(StrEnum):
    CARD = "card"  # v1.11: the round-start card is drawn (no action)
    CARD_CHOICE = "card_choice"  # v1.11: cards 5 and 6, one joint choice
    RESTART = "restart"  # v1.11: card 2, continue or restart after the 5th chip
    BREW = "brew"
    RESOLVE = "resolve"
    CHOICE = "choice"
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
    placed_fields: list[int] = field(default_factory=list)  # landing field of each placed chip
    field: int = 0
    white_total: int = 0
    status: Status = Status.BREWING
    droplet_halves: int = 0
    points: int = 0
    money: int = 0
    purchases: int = 0
    chip_purchases: int = 0  # shop items of kind chip bought this round
    chip_colours: list[str] = dataclasses.field(default_factory=list)  # their colours, in buy order
    shop_done: bool = False
    hand: list[str] = dataclasses.field(default_factory=list)  # blue chip hand: out of the bag, hidden
    final_field: int | None = None
    # v1.11: card 2 (restart offered this round, waiting for the answer), card 5 (drop at round end)
    restart_offered: bool = False
    restart_pending: bool = False
    round_end_halves: int = 0
    rat_tail: int = 0  # v2.1: pot fields gained at the round start (the rat tail bonus)

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
    # v1.11: the card ids still in the deck (one entry per copy), and the card of this round.
    deck: list[str] = field(default_factory=list)
    card: str | None = None


def scoring_field(landing_field: int, rs: Ruleset) -> int:
    """The first free field after the last chip: ruby and money come from here."""
    return min(landing_field + 1, rs.track_end)


def start_field(p: PlayerState, rs: Ruleset) -> int:
    return min(p.droplet_halves // 2 + p.rat_tail, rs.track_end)


def new_game(rs: Ruleset) -> GameState:
    return GameState(
        rules_version=rs.version,
        round=1,
        phase=Phase.CARD,
        step=0,
        players={seat: PlayerState(bag=dict(rs.start_bag)) for seat in SEATS},
        deck=[c.id for c in rs.cards for _ in range(c.count)],
    )


def state_to_dict(state: GameState) -> dict[str, Any]:
    return asdict(state)


def state_from_dict(data: dict[str, Any]) -> GameState:
    players = {
        seat: PlayerState(**{**p, "status": Status(p["status"])})
        for seat, p in data["players"].items()
    }
    return GameState(**{**data, "phase": Phase(data["phase"]), "players": players})
