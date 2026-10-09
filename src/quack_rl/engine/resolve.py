from typing import Any

from quack_rl.components import get_component
from quack_rl.engine.chance import ChanceLog
from quack_rl.engine.state import SEATS, GameState, Phase, PlayerState, Status, scoring_field
from quack_rl.rules import DieFace, Ruleset


def _apply_face(p: PlayerState, face: DieFace) -> int:
    """Apply a bonus die face; return extra money for this round."""
    if face.kind == "droplet":
        p.droplet_halves += face.halves
    elif face.kind == "chip" and face.chip is not None:
        p.bag[face.chip] = p.bag.get(face.chip, 0) + 1
    elif face.kind == "points":
        p.points += face.points
    elif face.kind == "money":
        return face.amount
    return 0


def apply_resolve(
    state: GameState, rs: Ruleset, chance: ChanceLog, events: list[dict[str, Any]]
) -> None:
    """Rules 4.3: ruby (scoring field), green bonus, bonus die, then money (seats p1, p2).

    In the last round the money is multiplied by last_round_money_percent // 100.
    """
    extra_money = {seat: 0 for seat in SEATS}
    for seat in SEATS:
        p = state.players[seat]
        assert p.final_field is not None
        if scoring_field(p.final_field, rs) in rs.rubies:
            p.droplet_halves += 1
            events.append({"seat": seat, "kind": "ruby", "halves": 1})
        for position_from_end, chip_id in enumerate(reversed(p.placed[-2:])):
            chip = rs.chip(chip_id)
            halves = get_component(chip.component).round_end_droplet_halves(chip, position_from_end)
            if halves:
                p.droplet_halves += halves
                events.append(
                    {"seat": seat, "kind": "round_end_bonus", "chip": chip_id, "halves": halves}
                )
    eligible = [s for s in SEATS if state.players[s].status is not Status.EXPLODED]
    if eligible:
        best = max(scoring_field(state.players[s].final_field or 0, rs) for s in eligible)
        for seat in eligible:
            p = state.players[seat]
            if scoring_field(p.final_field or 0, rs) == best:
                face = chance.roll_die(seat)
                extra_money[seat] += _apply_face(p, face)
                events.append({"seat": seat, "kind": "die", "face": face.id})
    for seat in SEATS:
        p = state.players[seat]
        assert p.final_field is not None
        money = rs.money[scoring_field(p.final_field, rs)]
        if p.status is Status.EXPLODED:
            money //= 2
        money += extra_money[seat]
        if state.round == rs.rounds:
            money = money * rs.last_round_money_percent // 100
        p.money = money
        p.purchases = 0
        p.shop_done = False
        events.append({"seat": seat, "kind": "money", "amount": p.money})
    state.phase = Phase.SHOP
