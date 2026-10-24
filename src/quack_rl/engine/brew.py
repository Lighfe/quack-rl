from typing import Any

from quack_rl.components import get_component
from quack_rl.engine.actions import (
    CARD_PLACE_DRAW,
    CARD_PLACE_PREFIX,
    DRAW,
    PLAY_PREFIX,
    PUT_BACK_DRAW,
    PUT_BACK_STOP,
    STOP,
    USE_CARD_17,
    USE_FLASK,
)
from quack_rl.engine.cards import card_effect, draw_chips, explosion_limit
from quack_rl.engine.chance import ChanceLog
from quack_rl.engine.state import SEATS, GameState, Phase, PlayerState, Status, start_field
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


def _take_back_last(
    p: PlayerState, seat: str, rs: Ruleset, events: list[dict[str, Any]], kind: str
) -> None:
    """The last (white) chip leaves the pot and goes back into the bag.

    The field goes back to the landing field of the chip before it (the start field when it was
    the first chip) and the white total goes down by the chip's weight. The flask (`use_flask`)
    and card 17 (`use_card_17`) both use this."""
    chip_id = p.placed.pop()
    p.placed_fields.pop()
    chip = rs.chip(chip_id)
    p.field = p.placed_fields[-1] if p.placed_fields else start_field(p, rs)
    p.white_total -= get_component(rs.component_name(chip)).explosion_weight(chip)
    p.bag[chip_id] = p.bag.get(chip_id, 0) + 1
    p.first_white_open = False
    events.append(
        {
            "seat": seat,
            "kind": kind,
            "chip": chip_id,
            "field": p.field,
            "white_total": p.white_total,
        }
    )


def _use_flask(p: PlayerState, seat: str, rs: Ruleset, events: list[dict[str, Any]]) -> None:
    """The flask puts the last white chip back into the bag; the flask is empty."""
    _take_back_last(p, seat, rs, events, "use_flask")
    p.flask_full = False


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
    p.first_white_open = False
    if chip.colour == "white" and not p.first_white_placed:
        p.first_white_placed = p.first_white_open = True
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


def _end_brew(
    state: GameState, rs: Ruleset, chance: ChanceLog, events: list[dict[str, Any]]
) -> None:
    """Nobody is brewing any more. Card 10: each player who stopped without exploding draws 5
    chips (all that are left; nothing for an empty bag), p1 then p2, and the players choose one
    to place (`Phase.CARD_CHOICE`). Otherwise the brew is over: Resolve."""
    if card_effect(state, rs) == "draw5_choose_place":
        asked = False
        for seat in SEATS:
            p = state.players[seat]
            if p.status is Status.STOPPED and not p.card_place_done:
                p.card_place_done = True
                n = min(CARD_PLACE_DRAW, sum(p.bag.values()))
                p.card_draw = draw_chips(p, seat, n, chance)
                asked = asked or n > 0
        if asked:
            state.phase = Phase.CARD_CHOICE
            return
    for p in state.players.values():
        p.final_field = p.field
    state.phase = Phase.RESOLVE


def apply_card_place(
    state: GameState,
    rs: Ruleset,
    actions: dict[str, str],
    chance: ChanceLog,
    events: list[dict[str, Any]],
) -> None:
    """Card 10: the chosen chip is placed as a normal placement. The other drawn chips are still
    in the bag, so a blue chip draws its hand from a bag that holds them. A player who gets a
    hand is brewing again (pick or stop as usual); the placement can make the player explode."""
    limit = explosion_limit(state, rs)
    for seat in SEATS:
        p = state.players[seat]
        action = actions[seat]
        p.card_draw = []
        if not action.startswith(CARD_PLACE_PREFIX):
            continue
        chip_id = action.removeprefix(CARD_PLACE_PREFIX)
        p.bag[chip_id] -= 1
        if p.bag[chip_id] == 0:
            del p.bag[chip_id]
        events.append({"seat": seat, "kind": "card_place", "chip": chip_id})
        _place(p, seat, chip_id, rs, chance, events, limit)
        if p.status is Status.STOPPED and p.hand:
            p.status = Status.BREWING
    if any(p.status is Status.BREWING for p in state.players.values()):
        state.phase = Phase.BREW
    else:
        _end_brew(state, rs, chance, events)


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
        elif action == USE_FLASK:
            _use_flask(p, seat, rs, events)
        elif action == USE_CARD_17:
            _take_back_last(p, seat, rs, events, "use_card_17")
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
        _end_brew(state, rs, chance, events)
    elif card_effect(state, rs) == "restart_after_5":
        for p in state.players.values():
            if p.status is Status.BREWING and len(p.placed) >= 5 and not p.restart_offered:
                p.restart_offered = p.restart_pending = True
                state.phase = Phase.RESTART
