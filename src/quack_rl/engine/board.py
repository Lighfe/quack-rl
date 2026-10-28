"""The points board (pure helpers): position, flag and rat tail bonus."""

from typing import Any

from quack_rl.engine.state import SEATS, GameState, PlayerState, start_field
from quack_rl.rules import DieFace, Ruleset


def add_points(p: PlayerState, amount: int, rs: Ruleset) -> int:
    """Add points; the total stops at `max_points` of the point board. Return the amount added.

    Points over the cap are lost.
    """
    total = min(p.points + amount, rs.point_board.max_points)
    added = total - p.points
    p.points = total
    return added


def die_events(seat: str, p: PlayerState, face: DieFace) -> list[dict[str, Any]]:
    """The events of a rolled face, after `apply_die_face`: the `die` event, and for a ruby face
    a `ruby` event with the balance."""
    events: list[dict[str, Any]] = [{"seat": seat, "kind": "die", "face": face.id}]
    if face.kind == "rubies":
        events.append({"seat": seat, "kind": "ruby", "rubies": face.rubies, "total": p.rubies})
    return events


def apply_die_face(p: PlayerState, face: DieFace, rs: Ruleset) -> None:
    """Apply a bonus die face to a player."""
    if face.kind == "droplet":
        p.droplet += face.droplet
    elif face.kind == "rubies":
        p.rubies += face.rubies
    elif face.kind == "chip" and face.chip is not None:
        p.bag[face.chip] = p.bag.get(face.chip, 0) + 1
    elif face.kind == "points":
        add_points(p, face.points, rs)


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


def calculate_rat_tails(points: dict[str, int], rs: Ruleset) -> dict[str, int]:
    """Rat tails per seat: 0 for the leader, else the tails between the seat and the leader.

    Not capped. A card changes the bonus with `PlayerState.rat_tail_adjust`, not here."""
    lead = max(points.values())
    return {
        seat: 0 if total == lead else tails_between(total, lead, rs)
        for seat, total in points.items()
    }


def set_rat_tails(state: GameState, rs: Ruleset, events: list[dict[str, Any]]) -> None:
    """Round start, once and after the card: set `rat_tail` from the points (less the card
    adjustment, never below 0) and move each pot to its boosted start field."""
    bonus = calculate_rat_tails({seat: state.players[seat].points for seat in SEATS}, rs)
    for seat in SEATS:
        p = state.players[seat]
        p.rat_tail = max(0, bonus[seat] - p.rat_tail_adjust)
        p.field = start_field(p, rs)
        if p.rat_tail > 0:
            events.append({"seat": seat, "kind": "rat_tail", "bonus": p.rat_tail})
