"""The points board of ruleset v2.1 (pure helpers): position, flag and rat tail bonus."""

from typing import Any

from quack_rl.engine.state import SEATS, GameState, PlayerState, start_field
from quack_rl.rules import Ruleset


def add_points(p: PlayerState, amount: int, rs: Ruleset) -> int:
    """Add points; the total stops at `max_points` of the point board. Return the amount added.

    Points over the cap are lost.
    """
    total = min(p.points + amount, rs.point_board.max_points)
    added = total - p.points
    p.points = total
    return added


def board_position(points: int, rs: Ruleset) -> int:
    """The field 0..fields: a total up to `fields` is the field, a higher total wraps."""
    fields = rs.point_board.fields
    return points if points <= fields else points - fields


def has_50pts(points: int, rs: Ruleset) -> bool:
    """True when the total is past the first lap (`points > fields`)."""
    return points > rs.point_board.fields


def tails_between(low: int, high: int, rs: Ruleset) -> int:
    """Number of rat tails at a total `p` with `low <= p < high`, over all laps."""
    board = rs.point_board
    return sum(
        1
        for lap in range(board.laps)
        for f in board.rat_tails
        if low <= f + board.fields * lap < high
    )


def rat_tail_bonus(points: dict[str, int], rs: Ruleset) -> dict[str, int]:
    """Bonus per seat: 0 for every seat with the top total, else the tails up to the leader."""
    lead = max(points.values())
    return {
        seat: 0 if total == lead else tails_between(total, lead, rs)
        for seat, total in points.items()
    }


def set_rat_tails(state: GameState, rs: Ruleset, events: list[dict[str, Any]]) -> None:
    """Round start: set `rat_tail` from the points and move each pot to its boosted start field."""
    bonus = rat_tail_bonus({seat: state.players[seat].points for seat in SEATS}, rs)
    for seat in SEATS:
        p = state.players[seat]
        p.rat_tail = bonus[seat]
        p.field = start_field(p, rs)
        if bonus[seat] > 0:
            events.append({"seat": seat, "kind": "rat_tail", "bonus": bonus[seat]})
