from typing import Any

from quack_rl.components import get_component
from quack_rl.engine.actions import DRAW, PLAY_PREFIX, PUT_BACK_DRAW, PUT_BACK_STOP, STOP
from quack_rl.engine.cards import explosion_limit
from quack_rl.engine.chance import ChanceLog
from quack_rl.engine.state import SEATS, GameState, Phase, PlayerState, Status
from quack_rl.rules import Ruleset


def _put_back(p: PlayerState, seat: str, events: list[dict[str, Any]]) -> None:
    """The whole hand goes back into the bag."""
    if not p.hand:
        return
    events.append({"seat": seat, "kind": "put_back", "chips": list(p.hand)})
    for chip_id in p.hand:
        p.bag[chip_id] = p.bag.get(chip_id, 0) + 1
    p.hand = []


def _put_back_previous(
    p: PlayerState, seat: str, rs: Ruleset, events: list[dict[str, Any]]
) -> None:
    """The chip placed before the one just placed leaves the pot and goes back into the bag.

    The field (droplet) is not taken back; the explosion total goes down by the chip's weight."""
    chip_id = p.placed.pop(-2)
    p.placed_fields.pop(-2)
    chip = rs.chip(chip_id)
    p.white_total -= get_component(rs.component_name(chip)).explosion_weight(chip)
    p.bag[chip_id] = p.bag.get(chip_id, 0) + 1
    events.append(
        {"seat": seat, "kind": "pot_put_back", "chip": chip_id, "white_total": p.white_total}
    )


def _draw_hand(
    p: PlayerState, seat: str, size: int, chance: ChanceLog, events: list[dict[str, Any]]
) -> None:
    """Draw up to `size` chips from the bag into the hand (all that is left if fewer)."""
    for _ in range(min(size, sum(p.bag.values()))):
        chip_id = chance.draw_chip(p, seat)
        p.bag[chip_id] -= 1
        if p.bag[chip_id] == 0:
            del p.bag[chip_id]
        p.hand.append(chip_id)
    if p.hand:
        events.append({"seat": seat, "kind": "hand", "chips": list(p.hand)})


def _place(
    p: PlayerState,
    seat: str,
    chip_id: str,
    rs: Ruleset,
    chance: ChanceLog,
    events: list[dict[str, Any]],
    limit: int | None = None,
) -> None:
    """Place a chip that is already out of the bag (drawn, or played from the hand).

    Order: place (move, explosion total), the rest of the hand back into the bag, then a blue
    chip draws its new hand."""
    chip = rs.chip(chip_id)
    component = get_component(rs.component_name(chip))
    previous = rs.chip(p.placed[-1]) if p.placed else None
    bonus = component.place_bonus(chip, previous, [rs.chip(c) for c in p.placed])
    start = p.field
    p.field = min(start + chip.value + bonus, rs.track_end)
    p.white_total += component.explosion_weight(chip)
    p.placed.append(chip_id)
    p.placed_fields.append(p.field)
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
    if component.puts_back_previous(chip, previous):
        _put_back_previous(p, seat, rs, events)
    _put_back(p, seat, events)
    if p.white_total > (rs.explosion_limit if limit is None else limit):
        p.status = Status.EXPLODED
        events.append({"seat": seat, "kind": "explode", "white_total": p.white_total})
        return
    _draw_hand(p, seat, component.hand_size(chip), chance, events)
    if sum(p.bag.values()) == 0 and not p.hand:
        p.status = Status.STOPPED
        events.append({"seat": seat, "kind": "bag_empty"})


def _draw(
    p: PlayerState,
    seat: str,
    rs: Ruleset,
    chance: ChanceLog,
    events: list[dict[str, Any]],
    limit: int | None = None,
) -> None:
    chip_id = chance.draw_chip(p, seat)
    p.bag[chip_id] -= 1
    if p.bag[chip_id] == 0:
        del p.bag[chip_id]
    _place(p, seat, chip_id, rs, chance, events, limit)


def apply_brew(
    state: GameState,
    rs: Ruleset,
    actions: dict[str, str],
    chance: ChanceLog,
    events: list[dict[str, Any]],
) -> None:
    limit = explosion_limit(state, rs)
    for seat in SEATS:
        p = state.players[seat]
        action = actions[seat]
        if action == DRAW:
            _draw(p, seat, rs, chance, events, limit)
        elif action == STOP:
            p.status = Status.STOPPED
            events.append({"seat": seat, "kind": "stop", "field": p.field})
        elif action.startswith(PLAY_PREFIX):
            chip_id = p.hand.pop(int(action[len(PLAY_PREFIX) :]))
            _place(p, seat, chip_id, rs, chance, events, limit)
        elif action == PUT_BACK_DRAW:
            _put_back(p, seat, events)
            _draw(p, seat, rs, chance, events, limit)
        elif action == PUT_BACK_STOP:
            _put_back(p, seat, events)
            p.status = Status.STOPPED
            events.append({"seat": seat, "kind": "stop", "field": p.field})
    if all(p.status is not Status.BREWING for p in state.players.values()):
        for p in state.players.values():
            p.final_field = p.field
        state.phase = Phase.RESOLVE
