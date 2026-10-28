"""The view of one seat: JSON content for the browser. Field names are fixed (the frontend uses
them). Another seat's hand, card draw and pending action are never part of it."""

from typing import Any

from quack_rl.engine import SEATS, explosion_limit, start_field
from quack_rl.engine.state import scoring_field
from quack_rl.labels import action_label
from quack_rl.rl.encode import observe
from quack_rl.rules import Ruleset
from quack_rl.rules.cards import get_card_effect
from quack_rl.rules.model import DieFace
from quack_rl.rules.spellbook import colour_effect
from quack_rl.web.session import GameSession


def event_text(event: dict[str, Any]) -> str:
    """One log line of an engine event: the seat (when it has one), the kind, then the fields."""
    fields = " ".join(f"{k}={v}" for k, v in event.items() if k not in ("seat", "kind"))
    seat = event.get("seat")
    head = f"{seat}: {event['kind']}" if seat is not None else event["kind"]
    return f"{head} {fields}".rstrip()


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
        "log": {"lines": [event_text(e) for e in events], "events": events},
        "ingredients": _ingredients(session),
        "board": _board(session),
    }
