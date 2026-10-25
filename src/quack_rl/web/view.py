"""The view of one seat: JSON content for the browser. Field names are fixed (the frontend uses
them). Another seat's hand, card draw and pending action are never part of it."""

from typing import Any

from quack_rl.engine import SEATS, explosion_limit, start_field
from quack_rl.engine.state import scoring_field
from quack_rl.labels import action_label
from quack_rl.rl.encode import observe
from quack_rl.rules.cards import get_card_effect
from quack_rl.web.session import GameSession


def event_text(event: dict[str, Any]) -> str:
    """One log line of an engine event: the seat (when it has one), the kind, then the fields."""
    fields = " ".join(f"{k}={v}" for k, v in event.items() if k not in ("seat", "kind"))
    seat = event.get("seat")
    head = f"{seat}: {event['kind']}" if seat is not None else event["kind"]
    return f"{head} {fields}".rstrip()


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
        "droplet": p.droplet_halves // 2,
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
    }
