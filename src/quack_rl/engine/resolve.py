from typing import Any

from quack_rl.components import get_component, pot_effects
from quack_rl.engine.board import add_points, apply_die_face
from quack_rl.engine.cards import card_rolls_twice, card_ruby_field_extras, card_round_end
from quack_rl.engine.chance import ChanceLog
from quack_rl.engine.state import SEATS, GameState, Phase, Status, scoring_field
from quack_rl.rules import Ruleset


def _apply_pot_effects(
    state: GameState, rs: Ruleset, seat: str, events: list[dict[str, Any]]
) -> None:
    """Round-end effects that see the whole pot (black, purple), in component order."""
    p = state.players[seat]
    other = state.players[SEATS[1] if seat == SEATS[0] else SEATS[0]]
    for component, effect in pot_effects(rs, p.placed, other.placed):
        if effect.points or effect.droplet_halves:
            add_points(p, effect.points, rs)
            p.droplet_halves += effect.droplet_halves
            events.append(
                {
                    "seat": seat,
                    "kind": "pot_round_end",
                    "component": component.name,
                    "points": effect.points,
                    "halves": effect.droplet_halves,
                }
            )


def apply_resolve(
    state: GameState, rs: Ruleset, chance: ChanceLog, events: list[dict[str, Any]]
) -> None:
    """Rules 4.3: ruby (scoring field: 1 ruby), green bonus, bonus die, then money (seats p1, p2).

    The field gives money and points. An exploded potion waits for the CHOICE phase. In the last
    round the money becomes points (money // last_round_money_divisor).
    """
    for seat in SEATS:
        p = state.players[seat]
        assert p.final_field is not None
        if rs.fields[scoring_field(p.final_field, rs)].ruby:
            extra_rubies, extra_points = card_ruby_field_extras(state, rs)
            gained = 1 + extra_rubies
            p.rubies += gained
            events.append({"seat": seat, "kind": "ruby", "rubies": gained, "total": p.rubies})
            if extra_points:
                added = add_points(p, extra_points, rs)
                events.append({"seat": seat, "kind": "card_points", "points": added})
        for position_from_end, chip_id in enumerate(reversed(p.placed[-2:])):
            chip = rs.chip(chip_id)
            halves = get_component(rs.component_name(chip)).round_end_droplet_halves(
                chip, position_from_end
            )
            if halves:
                p.droplet_halves += halves
                events.append(
                    {"seat": seat, "kind": "round_end_bonus", "chip": chip_id, "halves": halves}
                )
        _apply_pot_effects(state, rs, seat, events)
        if p.round_end_halves:
            p.droplet_halves += p.round_end_halves
            events.append(
                {"seat": seat, "kind": "card_round_end_drop", "halves": p.round_end_halves}
            )
            p.round_end_halves = 0
    eligible = [s for s in SEATS if state.players[s].status is not Status.EXPLODED]
    if eligible:
        best = max(scoring_field(state.players[s].final_field or 0, rs) for s in eligible)
        for seat in eligible:
            p = state.players[seat]
            if scoring_field(p.final_field or 0, rs) == best:
                for _ in range(2 if card_rolls_twice(state, rs) else 1):
                    face = chance.roll_die(seat)
                    apply_die_face(p, face, rs)
                    events.append({"seat": seat, "kind": "die", "face": face.id})
    choosing = False
    for seat in SEATS:
        p = state.players[seat]
        assert p.final_field is not None
        fld = scoring_field(p.final_field, rs)
        p.purchases = 0
        p.chip_purchases = 0
        p.chip_colours = []
        p.shop_done = False
        p.money = 0
        if p.status is Status.EXPLODED:
            choosing = True
            continue
        money = rs.fields[fld].money
        add_points(p, rs.fields[fld].points, rs)
        if state.round == rs.rounds:
            add_points(p, money // rs.last_round_money_divisor, rs)
            money = 0
        p.money = money
        events.append({"seat": seat, "kind": "money", "amount": p.money})
    card_round_end(state, rs, events)
    state.phase = Phase.CHOICE if choosing else Phase.SHOP
