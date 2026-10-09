from typing import Any

from quack_rl.components import get_component
from quack_rl.engine.actions import DRAW, STOP
from quack_rl.engine.chance import ChanceLog
from quack_rl.engine.state import SEATS, GameState, Phase, PlayerState, Status
from quack_rl.rules import Ruleset


def _draw(
    p: PlayerState, seat: str, rs: Ruleset, chance: ChanceLog, events: list[dict[str, Any]]
) -> None:
    chip_id = chance.draw_chip(p, seat)
    chip = rs.chip(chip_id)
    component = get_component(chip.component)
    previous = rs.chip(p.placed[-1]) if p.placed else None
    bonus = component.place_bonus(chip, previous)
    p.bag[chip_id] -= 1
    if p.bag[chip_id] == 0:
        del p.bag[chip_id]
    start = p.field
    p.field = min(start + chip.value + bonus, rs.track_end)
    p.white_total += component.explosion_weight(chip)
    p.placed.append(chip_id)
    events.append(
        {
            "seat": seat,
            "kind": "place",
            "chip": chip_id,
            "from": start,
            "to": p.field,
            "bonus": bonus,
        }
    )
    if p.white_total > rs.explosion_limit:
        p.status = Status.EXPLODED
        events.append({"seat": seat, "kind": "explode", "white_total": p.white_total})
    elif sum(p.bag.values()) == 0:
        p.status = Status.STOPPED
        events.append({"seat": seat, "kind": "bag_empty"})


def apply_brew(
    state: GameState,
    rs: Ruleset,
    actions: dict[str, str],
    chance: ChanceLog,
    events: list[dict[str, Any]],
) -> None:
    for seat in SEATS:
        p = state.players[seat]
        if actions[seat] == DRAW:
            _draw(p, seat, rs, chance, events)
        elif actions[seat] == STOP:
            p.status = Status.STOPPED
            events.append({"seat": seat, "kind": "stop", "field": p.field})
    if all(p.status is not Status.BREWING for p in state.players.values()):
        for p in state.players.values():
            p.final_field = p.field
        state.phase = Phase.RESOLVE
