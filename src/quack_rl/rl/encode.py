"""Observation of one seat: a readable dict, a flat float32 vector and an action mask.

The view holds only what the seat may know: no draw order, no opponent bag, no simultaneous
choice of the opponent. Observation layout 2 (rules v1, v1.1): a board map of the placed
chips, both bags (remaining and complete), the rule scalars and derived features of the
generic rules.
Observation layout 3 (rulesets with `explosion_choice`, v1.8): layout 2 plus the phase
`choice`, the points of the own scoring field and a last-round flag
(`docs/specs/2026-10-16-observation-layout-3.md`).
"""

from typing import Any

import numpy as np

from quack_rl.components import get_component
from quack_rl.engine import SEATS, GameState, Phase, Status, action_names, legal_actions
from quack_rl.engine.state import PlayerState, scoring_field
from quack_rl.rl.derive import derived, derived_names
from quack_rl.rules import Ruleset

OBSERVATION_LAYOUT = 2  # the layout of v1 and v1.1; see `observation_layout` for a ruleset
CHOICE_LAYOUT = 3
# layout 2 has no choice phase; layout 3 has it
PHASES = [p.value for p in Phase if p is not Phase.CHOICE]
PHASES_CHOICE = [p.value for p in Phase]
STATUSES = [s.value for s in Status]
_SCALARS = (
    "money",
    "white_total",
    "ruby_fields_ahead",
    "points",
    "droplet_halves",
    "purchases",
    "chip_purchases",
    "shop_done",
)
# Map channels per field: money, ruby, then own and opponent: colour flags, value, order.
MAP_COLOURS = 4
MAP_CHANNELS = 2 + 2 * (MAP_COLOURS + 2)


def observation_layout(rs: Ruleset) -> int:
    """The layout number of a ruleset: 3 with the explosion choice, else 2."""
    return CHOICE_LAYOUT if rs.explosion_choice else OBSERVATION_LAYOUT


def phases(rs: Ruleset) -> list[str]:
    return PHASES_CHOICE if rs.explosion_choice else PHASES


def _colours(rs: Ruleset) -> list[str]:
    colours = list(dict.fromkeys(c.colour for c in rs.chips))
    if len(colours) != MAP_COLOURS:
        raise ValueError(
            f"observation layout {observation_layout(rs)} has {MAP_COLOURS} colour flags per chip "
            f"in the map; the ruleset has {len(colours)} colours"
        )
    return colours


def other_seat(seat: str) -> str:
    return SEATS[1] if seat == SEATS[0] else SEATS[0]


def _board(p: PlayerState) -> dict[int, dict[str, Any]]:
    """Landing field -> chip id and placement order (1 first). A later chip on the same
    field (the cap at `track_end`) replaces the earlier one."""
    board: dict[int, dict[str, Any]] = {}
    for order, (chip_id, landing) in enumerate(
        zip(p.placed, p.placed_fields, strict=True), start=1
    ):
        board[landing] = {"chip": chip_id, "order": order}
    return board


def _public(p: PlayerState, rs: Ruleset) -> dict[str, Any]:
    ahead = sum(1 for r in rs.rubies if r >= scoring_field(p.field, rs))
    return {
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
        "bag_remaining": {c.id: p.bag.get(c.id, 0) for c in rs.chips},
        "bag_owned": {c.id: p.owned(c.id) for c in rs.chips},
        "board": _board(p),
    }


def observe(state: GameState, rs: Ruleset, seat: str) -> dict[str, Any]:
    """The view of `seat`. The draw order of the bags and the opponent's pending choice are
    not part of it; both bags and the placed chips are public."""
    return {
        "round": state.round,
        "rounds": rs.rounds,
        "explosion_limit": rs.explosion_limit,
        "phase": state.phase.value,
        "own": _public(state.players[seat], rs),
        "opponent": _public(state.players[other_seat(seat)], rs),
        "derived": derived(state, rs, seat),
    }


def _map_names(rs: Ruleset) -> list[str]:
    colours = _colours(rs)
    names = []
    for f in range(rs.track_end + 1):
        names += [f"map.{f}.money", f"map.{f}.ruby"]
        for who in ("own", "opponent"):
            names += [f"map.{f}.{who}.colour.{c}" for c in colours]
            names += [f"map.{f}.{who}.value", f"map.{f}.{who}.order"]
    return names


def _player_names(prefix: str, rs: Ruleset) -> list[str]:
    return [
        *(f"{prefix}.status.{s}" for s in STATUSES),
        *(f"{prefix}.chip_colours.{c}" for c in _colours(rs)),
        *(f"{prefix}.{k}" for k in _SCALARS),
        *(f"{prefix}.bag.remaining.{c.id}" for c in rs.chips),
        *(f"{prefix}.bag.owned.{c.id}" for c in rs.chips),
    ]


def vector_names(rs: Ruleset) -> list[str]:
    """One name per entry of the vector. Depends only on the ruleset. The map block is last."""
    return [
        "round",
        "rounds",
        "explosion_limit",
        *(f"phase.{p}" for p in phases(rs)),
        *_player_names("own", rs),
        *_player_names("opponent", rs),
        *derived_names(rs),
        *_map_names(rs),
    ]


def map_slice(rs: Ruleset) -> slice:
    """The map block: `vec[map_slice(rs)].reshape(rs.track_end + 1, MAP_CHANNELS)`."""
    n = (rs.track_end + 1) * MAP_CHANNELS
    total = len(vector_names(rs))
    return slice(total - n, total)


def _player_values(view: dict[str, Any], rs: Ruleset) -> list[float]:
    return [
        *(view["status"] == s for s in STATUSES),
        *(view["chip_colours"][c] for c in _colours(rs)),
        *(view[k] for k in _SCALARS),
        *(view["bag_remaining"][c.id] for c in rs.chips),
        *(view["bag_owned"][c.id] for c in rs.chips),
    ]


def _map_values(obs: dict[str, Any], rs: Ruleset) -> list[float]:
    colours = _colours(rs)
    values: list[float] = []
    for f in range(rs.track_end + 1):
        values += [rs.money[f], f in rs.rubies]
        for who in ("own", "opponent"):
            slot = obs[who]["board"].get(f)
            if slot is None:
                values += [0.0] * (len(colours) + 2)
                continue
            chip = rs.chip(slot["chip"])
            values += [chip.colour == c for c in colours]
            values += [chip.value, slot["order"]]
    return values


def vectorize(obs: dict[str, Any], rs: Ruleset) -> np.ndarray:
    values = [
        obs["round"],
        obs["rounds"],
        obs["explosion_limit"],
        *(obs["phase"] == p for p in phases(rs)),
        *_player_values(obs["own"], rs),
        *_player_values(obs["opponent"], rs),
        *(obs["derived"][n] for n in derived_names(rs)),
        *_map_values(obs, rs),
    ]
    return np.asarray(values, dtype=np.float32)


def observation_bounds(rs: Ruleset) -> tuple[np.ndarray, np.ndarray]:
    """(low, high) per vector entry, `float32`. Finite where the bound is real (flags, fields,
    ruleset constants, counts the ruleset limits), `inf` where it is not (points, bag counts:
    shops can add chips)."""
    inf = np.inf
    chip_cap = float(rs.max_chip_purchases) if rs.max_chip_purchases is not None else inf
    purchase_cap = float(rs.max_purchases) if rs.max_purchases is not None else inf
    chip_cap = min(chip_cap, purchase_cap)
    scalar_high = {
        "money": inf,
        "white_total": inf,
        "ruby_fields_ahead": float(len(rs.rubies)),
        "points": inf,
        "droplet_halves": inf,
        "purchases": purchase_cap,
        "chip_purchases": chip_cap,
        "shop_done": 1.0,
    }
    player = [
        *[1.0] * len(STATUSES),
        *[chip_cap] * len(_colours(rs)),
        *(scalar_high[k] for k in _SCALARS),
        *[inf] * (2 * len(rs.chips)),
    ]
    max_value = float(max(c.value for c in rs.chips))
    cell = [float(max(rs.money)), 1.0]
    for _ in range(2):
        cell += [1.0] * len(_colours(rs)) + [max_value, inf]
    # A seat explodes on the draw that passes the limit, so its white total ends below
    # limit + the largest explosion weight of a chip.
    max_weight = max(get_component(c.component).explosion_weight(c) for c in rs.chips)
    money_cap = float(max(rs.money) * rs.last_round_money_percent // 100)
    # Derived entries. `limit_distance` is negative after an explosion; `point_delta` has no bound.
    derived_bounds = {
        "scoring_field": (0.0, float(rs.track_end)),
        "ruby_at_scoring_field": (0.0, 1.0),
        "money_if_stop": (0.0, max(money_cap, float(max(rs.money)))),
        "limit_distance": (float(-max_weight), float(rs.explosion_limit)),
        "explosion_chance": (0.0, 1.0),
        "rolls_die": (0.0, 1.0),
        "chips_placed": (0.0, inf),
        "point_delta": (-inf, inf),
        "field_points": (0.0, float(max(rs.points)) if rs.points is not None else 0.0),
        "last_round": (0.0, 1.0),
    }
    derived_low = [derived_bounds[n.split(".")[-1]][0] for n in derived_names(rs)]
    derived_high = [derived_bounds[n.split(".")[-1]][1] for n in derived_names(rs)]
    high = [
        float(rs.rounds),
        float(rs.rounds),
        float(rs.explosion_limit),
        *[1.0] * len(phases(rs)),
        *player,
        *player,
        *derived_high,
        *cell * (rs.track_end + 1),
    ]
    n_before = 3 + len(phases(rs)) + 2 * len(player)
    low = [
        1.0,
        1.0,
        1.0,
        *[0.0] * (n_before - 3),
        *derived_low,
        *[0.0] * (len(high) - n_before - len(derived_low)),
    ]
    return np.asarray(low, dtype=np.float32), np.asarray(high, dtype=np.float32)


def action_mask(state: GameState, rs: Ruleset, seat: str) -> np.ndarray:
    legal = set(legal_actions(state, rs, seat))
    return np.asarray([name in legal for name in action_names(rs)], dtype=np.int8)
