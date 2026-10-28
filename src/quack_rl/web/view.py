"""The view of one seat: JSON content for the browser. Field names are fixed (the frontend uses
them). Another seat's hand, card draw and pending action are never part of it."""

from typing import Any

from quack_rl.engine import SEATS, explosion_limit, start_field
from quack_rl.engine.actions import (
    CARD_BLACK,
    CARD_CHIP4_PREFIX,
    CARD_CHIP_PREFIX,
    CARD_DROP_2,
    CARD_POINTS,
    CARD_POINTS_AMOUNT,
    CARD_PURPLE,
    CARD_REMOVE_WHITE,
    CARD_RUBIES,
    CARD_SWAP_NO,
    CARD_SWAP_PREFIX,
    CARD_TAIL_POINTS,
    CARD_TAILS_PREFIX,
    CARD_UPGRADE_PREFIX,
    WAIT,
)
from quack_rl.engine.state import scoring_field
from quack_rl.labels import action_label
from quack_rl.rl.encode import observe
from quack_rl.rules import Ruleset
from quack_rl.rules.cards import get_card_effect
from quack_rl.rules.model import DieFace
from quack_rl.rules.spellbook import colour_effect
from quack_rl.web.session import GameSession


def _plural(n: int, word: str, plural: str) -> str:
    return f"+{n} {word if n == 1 else plural}"


def die_text(face: DieFace, rs: Ruleset) -> str:
    """The text of a bonus die face, from its kind and numbers (one rule per kind, no face ids)."""
    if face.kind == "chip":
        assert face.chip is not None
        chip = rs.chip(face.chip)
        return f"{chip.colour.capitalize()} {chip.value} into the bag"
    if face.kind == "droplet":
        return f"Droplet +{face.droplet}"
    if face.kind == "rubies":
        return _plural(face.rubies, "ruby", "rubies")
    return _plural(face.points, "point", "points")


def _words(value: Any) -> str:
    """An id or name as words: underscores and `@` become spaces."""
    return " ".join(str(value).replace("_", " ").replace("@", " ").split())


def _chip_name(chip_id: str, rs: Ruleset) -> str:
    """A chip in words, from the ruleset: its colour and value ("Orange 1")."""
    chip = rs.chip(chip_id)
    return f"{chip.colour.capitalize()} {chip.value}"


def _chip_of(colour: str, value: int, rs: Ruleset) -> str:
    return next(_chip_name(c.id, rs) for c in rs.chips if c.colour == colour and c.value == value)


def _chip_list(chip_ids: list[str], rs: Ruleset) -> str:
    return _and([_chip_name(c, rs) for c in chip_ids])


def _count(n: int, word: str, plural: str) -> str:
    return f"{n} {word if n == 1 else plural}"


def _and(parts: list[str]) -> str:
    return parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])} and {parts[-1]}"


def _gains(event: dict[str, Any]) -> list[str]:
    """The points, droplet and rubies of an event, each only when it is not 0."""
    parts = []
    if event.get("points"):
        parts.append(_count(event["points"], "point", "points"))
    if event.get("drop"):
        parts.append(f"droplet +{event['drop']}")
    if event.get("rubies"):
        parts.append(_count(event["rubies"], "ruby", "rubies"))
    return parts


def _choice_text(action: str, rs: Ruleset) -> str:
    """The card choice of a seat in words (follows "chose")."""
    if action.startswith((CARD_CHIP_PREFIX, CARD_CHIP4_PREFIX)):
        return f"a {_chip_name(action.split(':', 1)[1], rs)} chip"
    if action.startswith(CARD_SWAP_PREFIX):
        return f"to swap a ruby for a {_chip_name(action.removeprefix(CARD_SWAP_PREFIX), rs)} chip"
    if action.startswith(CARD_UPGRADE_PREFIX):
        return f"to upgrade {_chip_name(action.removeprefix(CARD_UPGRADE_PREFIX), rs)}"
    if action.startswith(CARD_TAILS_PREFIX):
        n = int(action.removeprefix(CARD_TAILS_PREFIX))
        if n:
            return f"to give up {_count(n, 'rat tail', 'rat tails')} for rubies"
        return "to keep the rat tails"
    fixed = {
        CARD_DROP_2: "droplet +2",
        CARD_PURPLE: f"a {_chip_of('purple', 1, rs)} chip",
        CARD_BLACK: f"a {_chip_of('black', 1, rs)} chip",
        CARD_RUBIES: "3 rubies",
        CARD_SWAP_NO: "not to swap",
        CARD_POINTS: f"{CARD_POINTS_AMOUNT} points",
        CARD_REMOVE_WHITE: "to remove a white 1 chip from the bag",
        CARD_TAIL_POINTS: "points for the rat tails",
    }
    return fixed.get(action, _words(action))


def _game_end(event: dict[str, Any]) -> str:
    winner = event.get("winner")
    head = "Game over: a draw" if winner == "draw" else f"Game over: {winner} wins"
    points = event.get("points") or {}
    scores = ", ".join(f"{seat} {n}" for seat, n in points.items())
    return f"{head} with points {scores}." if scores else f"{head}."


def _unknown(event: dict[str, Any]) -> str:
    """A kind without a sentence: its words, then its non-zero fields as words."""
    fields = [
        f"{_words(k)} {_words(v)}"
        for k, v in event.items()
        if k not in ("seat", "kind") and v not in (0, None, [], {}, "")
    ]
    seat = event.get("seat")
    head = f"{seat}: {_words(event['kind'])}" if seat is not None else _words(event["kind"])
    return f"{', '.join([head, *fields])}."


def _sentence(e: dict[str, Any], rs: Ruleset) -> str | None:
    """The sentence of a known kind, or None."""
    s, kind = e.get("seat"), e["kind"]
    chip = _chip_name(e["chip"], rs) if isinstance(e.get("chip"), str) else ""
    chips = e.get("chips") or []
    gains = _gains(e)
    if kind == "bag_empty":
        return f"{s}'s bag is empty."
    if kind == "buy":
        name = _chip_name(rs.shop_item(e["item"]).chip, rs)
        price = e.get("price")
        return f"{s} bought {name} for {price} coins." if price else f"{s} bought {name}."
    if kind == "card_chip":
        return f"{s} got a {chip} chip from the card."
    if kind == "card_choice":
        if e["action"] == WAIT:
            return f"{s} had nothing to choose for the card."
        return f"{s} chose {_choice_text(e['action'], rs)}."
    if kind == "card_draw":
        card = _words(e["card"]).capitalize()
        return f"{card} drawn: {get_card_effect(e['effect']).description}."
    if kind == "card_drop":
        return f"{s} got droplet +{e['drop']} from the card." if e.get("drop") else None
    if kind == "card_place":
        return f"{s} placed {chip} from the card draw."
    if kind == "card_points":
        return (
            f"{s} got {_and(gains)} from the card." if gains else f"{s} got nothing from the card."
        )
    if kind == "card_refill_flasks":
        return "The card refills every flask."
    if kind == "card_remove_chip":
        return f"{s} removed a {chip} chip from the bag."
    if kind == "card_swap":
        return f"{s} swapped a ruby for a {chip} chip."
    if kind == "die":
        faces = {face.id: face for face in rs.die}
        face = faces.get(e.get("face", ""))
        return f"{s} rolled the bonus die: {die_text(face, rs)}." if face else None
    if kind == "done":
        return f"{s} had nothing to choose." if e.get("auto") else f"{s} is done."
    if kind == "explode":
        return f"{s}'s pot exploded."
    if kind == "game_end":
        return _game_end(e)
    if kind == "hand":
        return f"{s} drew {_chip_list(chips, rs)}." if chips else f"{s} drew nothing."
    if kind == "money":
        amount = e.get("amount")
        return f"{s} has {amount} coins to spend." if amount else f"{s} has no coins to spend."
    if kind == "place":
        bonus = f" (bonus +{e['bonus']})" if e.get("bonus") else ""
        return f"{s} placed {chip} on field {e['to']}{bonus}."
    if kind == "pot_put_back":
        return f"{s}'s {chip} went from the pot back into the bag."
    if kind == "pot_round_end":
        colour = str(e.get("component", "")).split("@")[0]
        what = _words(colour)
        return f"{s}: {what} chips, {_and(gains)}." if gains else f"{s}: {what} chips."
    if kind == "put_back":
        return f"{s} put {_chip_list(chips, rs)} back into the bag." if chips else None
    if kind == "rat_tail":
        n = e.get("bonus")
        return f"{s} gets a rat tail bonus of {_count(n, 'field', 'fields')}." if n else None
    if kind == "refill_flask":
        paid = _count(e["rubies"], "ruby", "rubies") if e.get("rubies") else ""
        return f"{s} paid {paid} to refill the flask." if paid else f"{s} refilled the flask."
    if kind == "restart":
        if chips:
            return f"{s} restarted: {_chip_list(chips, rs)} went back into the bag."
        return f"{s} restarted."
    if kind == "restart_continue":
        return f"{s} brews on."
    if kind == "round_chip":
        return f"{s} got a {chip} chip for the new round."
    if kind == "round_end":
        return f"Round {e['next_round']} begins."
    if kind == "round_end_bonus":
        got = f", {_and(gains)}" if gains else ""
        return f"{s}: {chip} at the end of the pot{got}."
    if kind == "ruby":
        return f"{s} got {_and(gains)}." if gains else None
    if kind == "ruby_drop":
        paid = _count(e["rubies"], "ruby", "rubies") if e.get("rubies") else "rubies"
        return f"{s} paid {paid} for droplet +{e['drop']}." if e.get("drop") else None
    if kind == "ruby_points":
        rubies, points = e.get("rubies"), e.get("points")
        if not rubies:
            return f"{s} had no rubies left."
        r = _count(rubies, "ruby", "rubies")
        if not points:
            return f"{s} kept {r}, too few for a point."
        return f"{s} traded {r} for {_count(points, 'point', 'points')}."
    if kind == "stop":
        return f"{s} stopped on field {e['field']}."
    if kind == "take_money":
        amount = e.get("amount")
        return f"{s} took {amount} coins." if amount else f"{s} chose the money."
    if kind == "take_points":
        amount = e.get("amount")
        got = _count(amount, "point", "points") if amount else ""
        return f"{s} took {got}." if got else f"{s} chose the points."
    if kind in ("use_card_17", "use_flask"):
        how = "the flask" if kind == "use_flask" else "card 17"
        return f"{s} used {how}: {chip} went back into the bag, the pot is on field {e['field']}."
    return None


def event_text(event: dict[str, Any], rs: Ruleset) -> str:
    """One log line of an engine event: a plain sentence with chip names from the ruleset. Count
    fields that are 0 and empty lists are left out (the final scores of `game_end` excepted). A
    kind without a sentence gives its words and its non-zero fields, never `key=value`."""
    return _sentence(event, rs) or _unknown(event)


def _last_roll(session: GameSession) -> dict[str, Any] | None:
    """The bonus die of the newest resolve, each roll with the text of its face."""
    if session.last_roll is None:
        return None
    faces = {face.id: face for face in session.rs.die}
    rolls = [
        {**roll, "text": die_text(faces[roll["face"]], session.rs)}
        for roll in session.last_roll["rolls"]
    ]
    return {"round": session.last_roll["round"], "rolls": rolls}


def _board(session: GameSession) -> dict[str, Any]:
    board = session.rs.point_board
    return {"fields": board.fields, "laps": board.laps, "rat_tails": list(board.rat_tails)}


def _card(session: GameSession) -> dict[str, str] | None:
    if session.state.card is None:
        return None
    card = session.rs.card(session.state.card)
    return {"id": card.id, "effect": card.effect, "text": get_card_effect(card.effect).description}


def _game(session: GameSession) -> dict[str, Any]:
    state = session.state
    return {
        "round": state.round,
        "rounds": session.rs.rounds,
        "phase": state.phase.value,
        "revision": session.revision,
        "explosion_limit": explosion_limit(state, session.rs),
        "card": _card(session),
        "winner": state.winner,
        "last_roll": _last_roll(session),
    }


def _bag(session: GameSession, seat: str, viewer: str) -> dict[str, int]:
    """The bag counts per chip id. For another seat the hand counts as in the bag: it is hidden."""
    p = session.state.players[seat]
    counts = dict(p.bag)
    if seat != viewer:
        for chip_id in p.hand:
            counts[chip_id] = counts.get(chip_id, 0) + 1
    return {c.id: counts[c.id] for c in session.rs.chips if counts.get(c.id, 0) > 0}


def _pot(session: GameSession, seat: str) -> list[dict[str, Any]]:
    p = session.state.players[seat]
    froms = session.pot_froms(seat)
    entries = []
    for i, (chip_id, landing) in enumerate(zip(p.placed, p.placed_fields, strict=True)):
        chip = session.rs.chip(chip_id)
        entries.append(
            {
                "order": i + 1,
                "chip": chip_id,
                "colour": chip.colour,
                "value": chip.value,
                "from": froms[i],
                "landing": landing,
            }
        )
    return entries


def _seat(session: GameSession, seat: str, viewer: str) -> dict[str, Any]:
    p = session.state.players[seat]
    return {
        "id": seat,
        "kind": session.kind(seat),
        "status": p.status.value,
        "points": p.points,
        "money": p.money,
        "rubies": p.rubies,
        "flask_full": p.flask_full,
        "white_total": p.white_total,
        "droplet": p.droplet,
        "start_field": start_field(p, session.rs),
        "rat_tail": p.rat_tail,
        "bag": _bag(session, seat, viewer),
        "pot": _pot(session, seat),
    }


def _window(session: GameSession, seat: str) -> list[dict[str, int]]:
    rs = session.rs
    ahead = observe(session.state, rs, seat)["ahead"]
    start = scoring_field(session.state.players[seat].field, rs)
    return [{"field": min(start + k, rs.track_end), **cell} for k, cell in enumerate(ahead)]


def _ingredients(session: GameSession) -> list[dict[str, Any]]:
    """The shop catalogue: per colour, its chips with price, minimum round and availability this
    round (a catalogue fact: it does not depend on money, phase or seat)."""
    rs, rnd = session.rs, session.state.round
    items = {item.chip: item for item in rs.shop}
    colours = list(dict.fromkeys(c.colour for c in rs.chips))
    entries = []
    for colour in colours:
        chips = []
        for c in rs.chips:
            if c.colour != colour:
                continue
            item = items.get(c.id)
            chips.append(
                {
                    "chip": c.id,
                    "value": c.value,
                    "price": item.price if item else None,
                    "min_round": item.min_round if item else None,
                    "available": item is not None and rnd >= item.min_round,
                }
            )
        entries.append(
            {"colour": colour, "effect": colour_effect(rs.spellbook, colour), "chips": chips}
        )
    return entries


def seat_view(session: GameSession, seat: str) -> dict[str, Any]:
    state, rs = session.state, session.rs
    to_act = session.to_act()
    legal = session.legal(seat) if seat in to_act else []
    events = session.events_for(seat)
    p = state.players[seat]
    return {
        "game": _game(session),
        "you": seat,
        "to_act": to_act,
        "seats": [_seat(session, s, seat) for s in SEATS],
        "window": _window(session, seat),
        "chips": [{"id": c.id, "colour": c.colour, "value": c.value} for c in rs.chips],
        "legal": [{"id": a, "label": action_label(a, rs, state, seat)} for a in legal],
        "hand": list(p.hand),
        "card_draw": list(p.card_draw),
        "log": {"lines": [event_text(e, rs) for e in events], "events": events},
        "ingredients": _ingredients(session),
        "board": _board(session),
    }
