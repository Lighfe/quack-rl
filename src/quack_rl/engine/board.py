"""The points board of ruleset v2 (pure helpers): position, flag and rat tail bonus."""

from quack_rl.engine.state import PlayerState
from quack_rl.rules import Ruleset


def _board(rs: Ruleset):
    board = rs.point_board
    if board is None:
        raise ValueError("this ruleset has no point_board")
    return board


def add_points(p: PlayerState, amount: int, rs: Ruleset) -> int:
    """Add points; with a point board the total stops at `max_points`. Return the amount added.

    Points over the cap are lost. A ruleset without a board does not clamp.
    """
    total = p.points + amount
    if rs.point_board is not None:
        total = min(total, rs.point_board.max_points)
    added = total - p.points
    p.points = total
    return added


def board_position(points: int, rs: Ruleset) -> int:
    """The field 0..fields: a total up to `fields` is the field, a higher total wraps."""
    fields = _board(rs).fields
    return points if points <= fields else points - fields


def has_50pts(points: int, rs: Ruleset) -> bool:
    """True when the total is past the first lap (`points > fields`)."""
    return points > _board(rs).fields


def tails_between(low: int, high: int, rs: Ruleset) -> int:
    """Number of rat tails at a total `p` with `low <= p < high`, over all laps."""
    board = _board(rs)
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
