"""Observation of one seat: a readable dict, a flat float32 vector and an action mask.

The view holds only what the seat may know: no draw order, no opponent bag, no simultaneous
choice of the opponent. The remaining bag of the own seat is a count per chip id.
"""

from typing import Any

import numpy as np

from quack_rl.engine import SEATS, GameState, Phase, Status, action_names, legal_actions
from quack_rl.engine.state import PlayerState, scoring_field
from quack_rl.rules import Ruleset

PHASES = [p.value for p in Phase]
STATUSES = [s.value for s in Status]
_SCALARS = (
    "field",
    "money",
    "white_total",
    "ruby_fields_ahead",
    "points",
    "droplet_halves",
    "purchases",
    "chip_purchases",
    "shop_done",
)


def _colours(rs: Ruleset) -> list[str]:
    return list(dict.fromkeys(c.colour for c in rs.chips))


def other_seat(seat: str) -> str:
    return SEATS[1] if seat == SEATS[0] else SEATS[0]


def _public(p: PlayerState, rs: Ruleset) -> dict[str, Any]:
    ahead = sum(1 for r in rs.rubies if r >= scoring_field(p.field, rs))
    return {
        "placed": {c.id: p.placed.count(c.id) for c in rs.chips},
        "field": p.field,
        "money": p.money,
        "white_total": p.white_total,
        "ruby_fields_ahead": ahead,
        "points": p.points,
        "status": p.status.value,
        "droplet_halves": p.droplet_halves,
        "purchases": p.purchases,
        "chip_purchases": p.chip_purchases,
        "chip_colours": {c: p.chip_colours.count(c) for c in _colours(rs)},
        "shop_done": p.shop_done,
    }


def observe(state: GameState, rs: Ruleset, seat: str) -> dict[str, Any]:
    """The view of `seat`. The opponent's bag and the draw order are not part of it."""
    own = state.players[seat]
    return {
        "round": state.round,
        "phase": state.phase.value,
        "own": _public(own, rs),
        "opponent": _public(state.players[other_seat(seat)], rs),
        "own_bag": {c.id: own.bag.get(c.id, 0) for c in rs.chips},
    }


def _player_names(prefix: str, rs: Ruleset) -> list[str]:
    return [
        *(f"{prefix}.placed.{c.id}" for c in rs.chips),
        *(f"{prefix}.status.{s}" for s in STATUSES),
        *(f"{prefix}.chip_colours.{c}" for c in _colours(rs)),
        *(f"{prefix}.{k}" for k in _SCALARS),
    ]


def vector_names(rs: Ruleset) -> list[str]:
    """One name per entry of the vector. Depends only on the ruleset."""
    return [
        "round",
        *(f"phase.{p}" for p in PHASES),
        *_player_names("own", rs),
        *_player_names("opponent", rs),
        *(f"own_bag.{c.id}" for c in rs.chips),
    ]


def _player_values(view: dict[str, Any], rs: Ruleset) -> list[float]:
    return [
        *(view["placed"][c.id] for c in rs.chips),
        *(view["status"] == s for s in STATUSES),
        *(view["chip_colours"][c] for c in _colours(rs)),
        *(view[k] for k in _SCALARS),
    ]


def vectorize(obs: dict[str, Any], rs: Ruleset) -> np.ndarray:
    values = [
        obs["round"],
        *(obs["phase"] == p for p in PHASES),
        *_player_values(obs["own"], rs),
        *_player_values(obs["opponent"], rs),
        *(obs["own_bag"][c.id] for c in rs.chips),
    ]
    return np.asarray(values, dtype=np.float32)


def action_mask(state: GameState, rs: Ruleset, seat: str) -> np.ndarray:
    legal = set(legal_actions(state, rs, seat))
    return np.asarray([name in legal for name in action_names(rs)], dtype=np.int8)
