"""Round cards (v2.1): the draw and the effects. A card is an extra on top of the standard rules.

The round start has a fixed order: (1) the round chips, (2) the card is drawn and its effect and
choices are resolved, (3) the rat tail bonus is calculated once (`set_rat_tails`) and the pots move
to their start fields. No card has a special order.

The effects that matter later in the round are hooks that the standard rule calls and that read
the card here: `explosion_limit` (card 4), `card_ruby_field_extras` (cards 1 and 15, the ruby step),
`card_rolls_twice` (card 9, the bonus die in Resolve) and `card_round_end` (card 16). Cards 5 and 6
open `Phase.CARD_CHOICE` (one joint choice, `apply_card_choice`); card 2 opens `Phase.RESTART` in
the brew (`apply_restart`, triggered in `brew.py`).
"""

from typing import Any

from quack_rl.engine.actions import (
    CARD_BLACK,
    CARD_CHIP4_PREFIX,
    CARD_CHIP_PREFIX,
    CARD_DRAW_COUNT,
    CARD_DROP_2,
    CARD_POINTS,
    CARD_POINTS_AMOUNT,
    CARD_PURPLE,
    CARD_REMOVE_WHITE,
    CARD_RUBIES,
    CARD_SWAP_PREFIX,
    CARD_TAIL_POINTS,
    CARD_TAILS_PREFIX,
    CARD_UPGRADE_PREFIX,
    RESTART,
    WAIT,
    late_card_choice,
    upgrade_target,
    white_one,
)
from quack_rl.engine.board import add_points, apply_die_face, calculate_rat_tails, set_rat_tails
from quack_rl.engine.chance import ChanceLog
from quack_rl.engine.state import SEATS, GameState, Phase, PlayerState, refill_all_flasks, start_field
from quack_rl.rules import Ruleset


def card_effect(state: GameState, rs: Ruleset) -> str | None:
    """The effect name of the card of this round; None when no card is drawn (no cards)."""
    return rs.card(state.card).effect if state.card is not None else None


def explosion_limit(state: GameState, rs: Ruleset) -> int:
    """The explosion limit of this round: the ruleset limit, plus 2 with card 4."""
    return rs.explosion_limit + (2 if card_effect(state, rs) == "explosion_limit_plus_2" else 0)


def card_ruby_field_extras(state: GameState, rs: Ruleset) -> tuple[int, int]:
    """What the card adds to a scoring ruby field: (extra rubies, extra points).

    Card 1: 1 ruby more. Card 15: +2 points on top of the ruby."""
    effect = card_effect(state, rs)
    return (1 if effect == "ruby_extra" else 0, 2 if effect == "ruby_field_points" else 0)


def card_rolls_twice(state: GameState, rs: Ruleset) -> bool:
    """Card 9: a player who rolls the bonus die in Resolve rolls it a second time."""
    return card_effect(state, rs) == "die_twice"


def card_round_end(state: GameState, rs: Ruleset, events: list[dict[str, Any]]) -> None:
    """Card 16: at the end of the round (after the Resolve step, before the shop) all flasks are
    refilled."""
    if card_effect(state, rs) == "refill_flasks":
        refill_all_flasks(state)
        events.append({"seat": None, "kind": "card_refill_flasks"})


def _give_rubies(p: PlayerState, seat: str, amount: int, events: list[dict[str, Any]]) -> None:
    p.rubies += amount
    events.append({"seat": seat, "kind": "ruby", "rubies": amount, "total": p.rubies})


def _chip_of(rs: Ruleset, colour: str, value: int) -> str:
    for chip in rs.chips:
        if chip.colour == colour and chip.value == value:
            return chip.id
    raise ValueError(f"the cards need a {colour} chip of value {value} in the ruleset")


def _green_one(rs: Ruleset) -> str:
    return _chip_of(rs, "green", 1)


_CHOICE_EFFECTS = ("choice_drop2_or_purple", "choice_black_or_value2_or_rubies")
CARD_RUBIES_AMOUNT = 3  # card 5, option C
_LATE_CHOICE_EFFECTS = (
    "rat_tails_for_rubies",
    "ruby_for_chip",
    "points_or_remove_white",
    "chip4_or_tail_points",
    "draw4_upgrade",
)  # cards 8, 11, 12, 14, 19: a seat that is not asked gets WAIT


CARD_LOWEST_DRAW = 5  # card 20: chips drawn by each player
CARD_LOWEST_CHIP = ("blue", 2)  # card 20: the reward of the lowest sum


def _draw_chips(
    p: PlayerState, seat: str, n: int, chance: ChanceLog
) -> list[str]:
    """Draw `n` chips from the bag of one player without replacement. Each chip is one `draw_chip`
    outcome, checked against the bag minus the chips already drawn in this draw. The chips go back
    into the bag at the end, so the bag is unchanged."""
    drawn: list[str] = []
    try:
        for _ in range(n):
            chip_id = chance.draw_chip(p, seat)
            p.bag[chip_id] -= 1
            drawn.append(chip_id)
    finally:
        for chip_id in drawn:
            p.bag[chip_id] += 1
    return drawn


def _card_20(state: GameState, rs: Ruleset, chance: ChanceLog, events: list[dict[str, Any]]) -> None:
    """Card 20: both players draw 5 chips (p1, then p2) and add the values; the lowest sum (all
    tied players) gets a blue 2 chip, every other player 1 ruby. The draws are done before any
    reward."""
    sums = {
        seat: sum(rs.chip(c).value for c in _draw_chips(state.players[seat], seat, CARD_LOWEST_DRAW, chance))
        for seat in SEATS
    }
    lowest = min(sums.values())
    chip_id = _chip_of(rs, *CARD_LOWEST_CHIP)
    for seat in SEATS:
        p = state.players[seat]
        if sums[seat] == lowest:
            p.bag[chip_id] = p.bag.get(chip_id, 0) + 1
            events.append({"seat": seat, "kind": "card_chip", "chip": chip_id})
        else:
            _give_rubies(p, seat, 1, events)


def apply_card(
    state: GameState, rs: Ruleset, chance: ChanceLog, events: list[dict[str, Any]]
) -> None:
    """Give the round chips, draw one card from the cards not drawn yet, resolve its immediate
    effects, start the brew."""
    for rc in rs.round_chips:
        if rc.round == state.round:
            for seat in SEATS:
                p = state.players[seat]
                p.bag[rc.chip] = p.bag.get(rc.chip, 0) + 1
                events.append({"seat": seat, "kind": "round_chip", "chip": rc.chip})
    card_id = chance.draw_card(state.deck)
    state.deck.remove(card_id)
    state.card = card_id
    effect = rs.card(card_id).effect
    events.append({"seat": None, "kind": "card_draw", "card": card_id, "effect": effect})
    if effect == "drop_all_1":
        for seat in SEATS:
            p = state.players[seat]
            p.droplet_halves += 2
            p.field = start_field(p, rs)
            events.append({"seat": seat, "kind": "card_drop", "halves": 2})
    elif effect == "fewest_rubies_ruby":
        fewest = min(state.players[s].rubies for s in SEATS)
        for seat in SEATS:
            p = state.players[seat]
            if p.rubies == fewest:
                _give_rubies(p, seat, 1, events)
    elif effect == "everyone_rolls":
        for seat in SEATS:
            face = chance.roll_die(seat)
            apply_die_face(state.players[seat], face, rs)
            events.append({"seat": seat, "kind": "die", "face": face.id})
    elif effect == "fewest_points_green":
        fewest = min(state.players[s].points for s in SEATS)
        chip_id = _green_one(rs)
        for seat in SEATS:
            p = state.players[seat]
            if p.points == fewest:
                p.bag[chip_id] = p.bag.get(chip_id, 0) + 1
                events.append({"seat": seat, "kind": "card_chip", "chip": chip_id})
    elif effect == "draw5_lowest":
        _card_20(state, rs, chance, events)
    elif effect == "draw4_upgrade":
        for seat in SEATS:
            state.players[seat].card_draw = _draw_chips(state.players[seat], seat, CARD_DRAW_COUNT, chance)
    if effect in _CHOICE_EFFECTS:
        state.phase = Phase.CARD_CHOICE
    elif effect in _LATE_CHOICE_EFFECTS:
        if any(late_card_choice(state, rs, seat) != [WAIT] for seat in SEATS):
            state.phase = Phase.CARD_CHOICE
        else:  # nobody has a decision: the step needs no action (card 14 still pays the points)
            apply_card_choice(state, rs, dict.fromkeys(SEATS, WAIT), events)
    else:
        state.phase = Phase.BREW
        set_rat_tails(state, rs, events)


def apply_card_choice(
    state: GameState, rs: Ruleset, actions: dict[str, str], events: list[dict[str, Any]]
) -> None:
    """Cards 5 and 6: both players choose at the same moment; the choices resolve together.

    A chip goes into the bag at once, a drop (card 6) or the rubies (card 5) at once."""
    if state.card is not None and rs.card(state.card).effect in _LATE_CHOICE_EFFECTS:
        _apply_late_choice(state, rs, actions, events)
        return
    for seat in SEATS:
        p = state.players[seat]
        action = actions[seat]
        events.append({"seat": seat, "kind": "card_choice", "action": action})
        chip_id: str | None = None
        if action == CARD_DROP_2:
            p.droplet_halves += 4
            p.field = start_field(p, rs)
            events.append({"seat": seat, "kind": "card_drop", "halves": 4})
        elif action == CARD_PURPLE:
            chip_id = _chip_of(rs, "purple", 1)
        elif action == CARD_BLACK:
            chip_id = _chip_of(rs, "black", 1)
        elif action.startswith(CARD_CHIP_PREFIX):
            chip_id = action.removeprefix(CARD_CHIP_PREFIX)
        elif action == CARD_RUBIES:
            _give_rubies(p, seat, CARD_RUBIES_AMOUNT, events)
        if chip_id is not None:
            p.bag[chip_id] = p.bag.get(chip_id, 0) + 1
            events.append({"seat": seat, "kind": "card_chip", "chip": chip_id})
    state.phase = Phase.BREW
    set_rat_tails(state, rs, events)


def _apply_late_choice(
    state: GameState, rs: Ruleset, actions: dict[str, str], events: list[dict[str, Any]]
) -> None:
    """Cards 8, 12, 14 and 19. Two passes: first the choices of all players are recorded (and the
    entitlements read from the points before any reward), then the rewards are paid, so one
    player's reward never changes another player's entitlement. The rat tail bonus is calculated
    once afterwards, on the new points."""
    assert state.card is not None
    effect = rs.card(state.card).effect
    entitlement = calculate_rat_tails({s: state.players[s].points for s in SEATS}, rs)
    for seat in SEATS:
        events.append({"seat": seat, "kind": "card_choice", "action": actions[seat]})
    for seat in SEATS:
        p = state.players[seat]
        action = actions[seat]
        if effect == "draw4_upgrade":
            if action.startswith(CARD_UPGRADE_PREFIX):
                chip_id = action.removeprefix(CARD_UPGRADE_PREFIX)
                upgraded = upgrade_target(rs, chip_id)
                assert upgraded is not None
                p.bag[chip_id] -= 1
                if p.bag[chip_id] == 0:
                    del p.bag[chip_id]
                p.bag[upgraded] = p.bag.get(upgraded, 0) + 1
                events.append({"seat": seat, "kind": "card_remove_chip", "chip": chip_id})
                events.append({"seat": seat, "kind": "card_chip", "chip": upgraded})
            else:  # WAIT: no drawn chip can be upgraded
                chip_id = _green_one(rs)
                p.bag[chip_id] = p.bag.get(chip_id, 0) + 1
                events.append({"seat": seat, "kind": "card_chip", "chip": chip_id})
            p.card_draw = []
        elif effect == "rat_tails_for_rubies" and action.startswith(CARD_TAILS_PREFIX):
            given = int(action.removeprefix(CARD_TAILS_PREFIX))
            if given:
                p.rat_tail_adjust += given
                _give_rubies(p, seat, given, events)
        elif effect == "ruby_for_chip" and action.startswith(CARD_SWAP_PREFIX):
            chip_id = action.removeprefix(CARD_SWAP_PREFIX)
            p.rubies -= 1
            p.bag[chip_id] = p.bag.get(chip_id, 0) + 1
            events.append({"seat": seat, "kind": "card_swap", "chip": chip_id, "total": p.rubies})
        elif effect == "points_or_remove_white":
            if action == CARD_REMOVE_WHITE:
                chip_id = white_one(rs)
                p.bag[chip_id] -= 1
                events.append({"seat": seat, "kind": "card_remove_chip", "chip": chip_id})
            else:  # CARD_POINTS, or WAIT because the bag has no white 1
                added = add_points(p, CARD_POINTS_AMOUNT, rs)
                events.append({"seat": seat, "kind": "card_points", "points": added})
        elif effect == "chip4_or_tail_points":
            if action == CARD_TAIL_POINTS:
                added = add_points(p, entitlement[seat], rs)
                events.append({"seat": seat, "kind": "card_points", "points": added})
            elif action.startswith(CARD_CHIP4_PREFIX):
                chip_id = action.removeprefix(CARD_CHIP4_PREFIX)
                p.bag[chip_id] = p.bag.get(chip_id, 0) + 1
                events.append({"seat": seat, "kind": "card_chip", "chip": chip_id})
    state.phase = Phase.BREW
    set_rat_tails(state, rs, events)


def apply_restart(
    state: GameState, rs: Ruleset, actions: dict[str, str], events: list[dict[str, Any]]
) -> None:
    """Card 2: a player who restarts puts the pot and the hand back into the bag and starts over.

    The bag is a multiset and every draw is random from it, so the reshuffle needs no extra
    chance outcome. Nothing of the pot is kept; the explosion total and the field go back."""
    for seat in SEATS:
        p = state.players[seat]
        if not p.restart_pending:
            continue
        p.restart_pending = False
        if actions[seat] == RESTART:
            for chip_id in [*p.placed, *p.hand]:
                p.bag[chip_id] = p.bag.get(chip_id, 0) + 1
            events.append({"seat": seat, "kind": "restart", "chips": list(p.placed)})
            p.placed = []
            p.placed_fields = []
            p.hand = []
            p.white_total = 0
            p.field = start_field(p, rs)
        else:
            events.append({"seat": seat, "kind": "restart_continue"})
    state.phase = Phase.BREW
