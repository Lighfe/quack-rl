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
    CARD_CHIP_PREFIX,
    CARD_DROP_2,
    CARD_PURPLE,
    CARD_RUBIES,
    RESTART,
)
from quack_rl.engine.board import apply_die_face, set_rat_tails
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
    if effect in _CHOICE_EFFECTS:
        state.phase = Phase.CARD_CHOICE
    else:
        state.phase = Phase.BREW
        set_rat_tails(state, rs, events)


def apply_card_choice(
    state: GameState, rs: Ruleset, actions: dict[str, str], events: list[dict[str, Any]]
) -> None:
    """Cards 5 and 6: both players choose at the same moment; the choices resolve together.

    A chip goes into the bag at once, a drop (card 6) or the rubies (card 5) at once."""
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
