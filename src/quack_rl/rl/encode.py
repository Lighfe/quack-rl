"""Observation of one seat: a readable dict, a flat float32 vector and an action mask.

The view holds only what the seat may know: no draw order, no opponent bag, no simultaneous
choice of the opponent. The one observation layout is number 9 (`BOARD_LAYOUT`): a look-ahead
window of the fields from the own scoring field on (money, points, ruby), a board map of the
placed chips (no static field table), both bags (remaining and complete), the rule scalars,
derived features with the field and points gaps, the hand, the shop, the card block and the point
board block (`docs/specs/2026-10-23-ruleset-v2-1-design.md`). Layout 9 is layout 8 with the
droplet in whole steps (`droplet` for `droplet_halves`, `docs/specs/2026-10-27-game-parts-and-ruleset-v2-3.md`).
The layouts 2 to 6 are archived in `archive/src/quack_rl/rl/encode.py`, layout 7 in
`archive/src/quack_rl/rl/encode_layout7.py`.
"""

from typing import Any

import numpy as np

from quack_rl.components import get_component
from quack_rl.engine import (
    MAX_HAND,
    SEATS,
    GameState,
    Phase,
    Status,
    action_names,
    card_effect,
    explosion_limit,
    has_hand,
    legal_actions,
)
from quack_rl.engine.board import board_position, has_50pts
from quack_rl.engine.state import PlayerState, scoring_field
from quack_rl.rl.derive import derived, derived_names
from quack_rl.rules import Ruleset

BOARD_LAYOUT = 9
LOOKAHEAD = 10  # default K: the window holds the fields k = 0 ... K
PHASES = [p.value for p in Phase]
RESTART_EFFECT = "restart_after_5"
LIMIT_PLUS_2_EFFECT = "explosion_limit_plus_2"
STATUSES = [s.value for s in Status]
_SCALARS = (
    "money",
    "rubies",
    "flask_full",
    "white_total",
    "points",
    "droplet",
    "purchases",
    "chip_purchases",
    "shop_done",
)
# Map channels per field, for own and opponent: colour flags, value, order.
MAP_COLOURS = 8  # colour flags per chip in the map: the eight colours of the ruleset


def observation_layout(rs: Ruleset) -> int:
    """The layout number of a ruleset: always 9, the only layout. The version name is not read."""
    return BOARD_LAYOUT


def _ruleset_colours(rs: Ruleset) -> list[str]:
    return list(dict.fromkeys(c.colour for c in rs.chips))


def map_colours(rs: Ruleset) -> int:
    return MAP_COLOURS


def map_channels(rs: Ruleset) -> int:
    """Map channels per field, for own and opponent: colour flags, value, order."""
    return 2 * (map_colours(rs) + 2)


def phases(rs: Ruleset) -> list[str]:
    return PHASES


def _card_kinds(rs: Ruleset) -> list[str]:
    """One kind per card effect name (no effect included), in the order of the ruleset."""
    return list(dict.fromkeys(c.effect for c in rs.cards))


def _deck_counts(state: GameState, rs: Ruleset) -> dict[str, int]:
    counts = dict.fromkeys(_card_kinds(rs), 0)
    for card_id in state.deck:
        counts[rs.card(card_id).effect] += 1
    return counts


def _max_limit(rs: Ruleset) -> float:
    """The largest explosion limit of a round: the ruleset limit, plus 2 with the limit card."""
    plus = any(c.effect == LIMIT_PLUS_2_EFFECT for c in rs.cards)
    return float(rs.explosion_limit + (2 if plus else 0))


def _restart_available(state: GameState, rs: Ruleset, seat: str) -> bool:
    """The seat can still be offered the restart this round, or has the offer open now."""
    p = state.players[seat]
    if card_effect(state, rs) != RESTART_EFFECT:
        return False
    return p.restart_pending or (not p.restart_offered and p.status is Status.BREWING)


def _colours(rs: Ruleset) -> list[str]:
    colours = _ruleset_colours(rs)
    if len(colours) != map_colours(rs):
        raise ValueError(
            f"observation layout {observation_layout(rs)} has {map_colours(rs)} colour flags per chip "
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


def _ahead(p: PlayerState, rs: Ruleset, k_max: int) -> list[dict[str, int]]:
    """The window of the player: the fields `scoring field + k` for k = 0 ... k_max. Past
    `track_end` the last field repeats."""
    start = scoring_field(p.field, rs)
    cells = (rs.fields[min(start + k, rs.track_end)] for k in range(k_max + 1))
    return [{"money": f.money, "points": f.points, "ruby": int(f.ruby)} for f in cells]


def _public(p: PlayerState, rs: Ruleset) -> dict[str, Any]:
    return {
        "money": p.money,
        "rubies": p.rubies,
        "flask_full": p.flask_full,
        "white_total": p.white_total,
        "points": p.points,
        "status": p.status.value,
        "droplet": p.droplet,
        "purchases": p.purchases,
        "chip_purchases": p.chip_purchases,
        "chip_colours": {c: p.chip_colours.count(c) for c in _colours(rs)},
        "shop_done": p.shop_done,
        "bag_remaining": {c.id: p.bag.get(c.id, 0) for c in rs.chips},
        "bag_owned": {c.id: p.owned(c.id) for c in rs.chips},
        "board": _board(p),
    }


def observe(state: GameState, rs: Ruleset, seat: str, k_max: int = LOOKAHEAD) -> dict[str, Any]:
    """The view of `seat`. The draw order of the bags and the opponent's pending choice are
    not part of it; both bags and the placed chips are public. `ahead` is the look-ahead window
    of `seat` with `k_max + 1` cells; the opponent has none (`field_gap` covers it)."""
    own = _public(state.players[seat], rs)
    opponent = _public(state.players[other_seat(seat)], rs)
    if has_hand(rs):
        own["hand"] = list(state.players[seat].hand)
    obs: dict[str, Any] = {
        "round": state.round,
        "rounds": rs.rounds,
        "explosion_limit": explosion_limit(state, rs),
        "phase": state.phase.value,
        "own": own,
        "opponent": opponent,
        "derived": derived(state, rs, seat),
        "ahead": _ahead(state.players[seat], rs, k_max),
    }
    # the card and the deck are open
    obs["card"] = card_effect(state, rs)
    obs["deck"] = _deck_counts(state, rs)
    obs["restart_available"] = _restart_available(state, rs, seat)
    # the point board is open information: both markers, both flags, both bonuses
    board = rs.point_board
    obs["board"] = {
        "own": _board_view(state.players[seat], rs),
        "opponent": _board_view(state.players[other_seat(seat)], rs),
        "tails": [int(f in board.rat_tails) for f in range(board.fields)],
    }
    return obs


def _hand_names(rs: Ruleset) -> list[str]:
    """Per hand slot a presence flag, the value and the colour flags; then the size."""
    if not has_hand(rs):
        return []
    names = []
    for i in range(MAX_HAND):
        names += [f"own.hand.{i}.present", f"own.hand.{i}.value"]
        names += [f"own.hand.{i}.colour.{c}" for c in _colours(rs)]
    return [*names, "own.hand_size"]


def _hand_values(obs: dict[str, Any], rs: Ruleset) -> list[float]:
    if not has_hand(rs):
        return []
    colours = _colours(rs)
    hand = obs["own"]["hand"]
    values: list[float] = []
    for i in range(MAX_HAND):
        if i >= len(hand):
            values += [0.0] * (2 + len(colours))
            continue
        chip = rs.chip(hand[i])
        values += [1.0, chip.value, *(chip.colour == c for c in colours)]
    return [*values, len(hand)]


def _shop_names(rs: Ruleset) -> list[str]:
    """Per shop item its minimum round and whether the round has reached it."""
    return [n for i in rs.shop for n in (f"shop.{i.id}.min_round", f"shop.{i.id}.open")]


def _shop_values(obs: dict[str, Any], rs: Ruleset) -> list[float]:
    values: list[float] = []
    for i in rs.shop:
        values += [i.min_round, obs["round"] >= i.min_round]
    return values


def _card_names(rs: Ruleset) -> list[str]:
    """The card of the round and the cards left in the deck (one entry per card
    kind), whether the restart is available to the seat, and the resolved round-end drops."""
    kinds = _card_kinds(rs)
    return [
        *(f"card.{k}" for k in kinds),
        *(f"deck.{k}" for k in kinds),
        "restart.available",
    ]


def _card_values(obs: dict[str, Any], rs: Ruleset) -> list[float]:
    kinds = _card_kinds(rs)
    return [
        *(obs["card"] == k for k in kinds),
        *(obs["deck"][k] for k in kinds),
        obs["restart_available"],
    ]


def _board_view(p: PlayerState, rs: Ruleset) -> dict[str, Any]:
    return {
        "position": board_position(p.points, rs),
        "has_50pts": has_50pts(p.points, rs),
        "rat_tail": p.rat_tail,
    }


def _board_names(rs: Ruleset) -> list[str]:
    """Per seat the one-hot marker field, the flag and the rat tail bonus; then the
    tail locations (a tail after field f)."""
    fields = rs.point_board.fields
    names: list[str] = []
    for who in ("own", "opponent"):
        names += [f"{who}.board.marker.{k}" for k in range(fields + 1)]
        names += [f"{who}.board.has_50pts", f"{who}.rat_tail"]
    return [*names, *(f"board.tail.{f}" for f in range(fields))]


def _board_values(obs: dict[str, Any], rs: Ruleset) -> list[float]:
    values: list[float] = []
    for who in ("own", "opponent"):
        view = obs["board"][who]
        values += [view["position"] == k for k in range(rs.point_board.fields + 1)]
        values += [view["has_50pts"], view["rat_tail"]]
    return [*values, *obs["board"]["tails"]]


def _ahead_names(k_max: int) -> list[str]:
    return [f"ahead.{k}.{c}" for k in range(k_max + 1) for c in ("money", "points", "ruby")]


def _ahead_values(obs: dict[str, Any]) -> list[float]:
    return [cell[c] for cell in obs["ahead"] for c in ("money", "points", "ruby")]


def _map_names(rs: Ruleset) -> list[str]:
    colours = _colours(rs)
    names = []
    for f in range(rs.track_end + 1):
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


def vector_names(rs: Ruleset, k_max: int = LOOKAHEAD) -> list[str]:
    """One name per entry of the vector. Depends only on the ruleset and `k_max`. The window
    block comes before the map block, which is last."""
    return [
        "round",
        "rounds",
        "explosion_limit",
        *(f"phase.{p}" for p in phases(rs)),
        *_player_names("own", rs),
        *_player_names("opponent", rs),
        *derived_names(),
        *_hand_names(rs),
        *_shop_names(rs),
        *_card_names(rs),
        *_board_names(rs),
        *_ahead_names(k_max),
        *_map_names(rs),
    ]


def map_slice(rs: Ruleset, k_max: int = LOOKAHEAD) -> slice:
    """The map block: `vec[map_slice(rs)].reshape(rs.track_end + 1, map_channels(rs))`."""
    n = (rs.track_end + 1) * map_channels(rs)
    total = len(vector_names(rs, k_max))
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
        *(obs["derived"][n] for n in derived_names()),
        *_hand_values(obs, rs),
        *_shop_values(obs, rs),
        *_card_values(obs, rs),
        *_board_values(obs, rs),
        *_ahead_values(obs),
        *_map_values(obs, rs),
    ]
    return np.asarray(values, dtype=np.float32)


def observation_bounds(rs: Ruleset, k_max: int = LOOKAHEAD) -> tuple[np.ndarray, np.ndarray]:
    """(low, high) per vector entry, `float32`. Finite where the bound is real (flags, fields,
    ruleset constants, counts the ruleset limits), `inf` where it is not (points, bag counts:
    shops can add chips)."""
    inf = np.inf
    chip_cap = float(rs.max_chip_purchases) if rs.max_chip_purchases is not None else inf
    max_points = float(rs.point_board.max_points)
    scalar_high = {
        "money": inf,
        "rubies": inf,
        "flask_full": 1.0,
        "white_total": inf,
        "points": max_points,
        "droplet": inf,
        "purchases": inf,
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
    cell: list[float] = []
    for _ in range(2):
        cell += [1.0] * len(_colours(rs)) + [max_value, inf]
    ahead_high = [
        float(max(f.money for f in rs.fields)),
        float(max(f.points for f in rs.fields)),
        1.0,
    ] * (k_max + 1)
    # A seat explodes on the draw that passes the limit, so its white total ends below
    # limit + the largest explosion weight of a chip.
    max_weight = max(get_component(rs.component_name(c)).explosion_weight(c) for c in rs.chips)
    # Derived entries. `limit_distance` is negative after an explosion; `points_gap` and `field_gap` have no bound.
    derived_bounds = {
        "scoring_field": (0.0, float(rs.track_end)),
        "ruby_at_scoring_field": (0.0, 1.0),
        "money_if_stop": (0.0, float(max(f.money for f in rs.fields))),
        "limit_distance": (float(-max_weight), _max_limit(rs)),
        "explosion_chance": (0.0, 1.0),
        "rolls_die": (0.0, 1.0),
        "chips_placed": (0.0, inf),
        "field_gap": (-float(rs.track_end), float(rs.track_end)),
        "points_gap": (-inf, inf),
        "field_points": (0.0, float(max(f.points for f in rs.fields))),
        "last_round": (0.0, 1.0),
    }
    hand_high: list[float] = []
    if has_hand(rs):
        slot = [1.0, max_value] + [1.0] * len(_colours(rs))
        hand_high = [*slot * MAX_HAND, float(MAX_HAND)]
    shop_high = [float(rs.rounds), 1.0] * len(rs.shop)
    kinds = _card_kinds(rs)
    per_kind = [sum(c.count for c in rs.cards if c.effect == k) for k in kinds]
    card_high = [*[1.0] * len(kinds), *map(float, per_kind), 1.0]
    pb = rs.point_board
    one_side = [*[1.0] * (pb.fields + 1), 1.0, float(pb.laps * len(pb.rat_tails))]
    board_high = [*one_side, *one_side, *[1.0] * pb.fields]
    derived_low = [derived_bounds[n.split(".")[-1]][0] for n in derived_names()]
    derived_high = [derived_bounds[n.split(".")[-1]][1] for n in derived_names()]
    high = [
        float(rs.rounds),
        float(rs.rounds),
        _max_limit(rs),
        *[1.0] * len(phases(rs)),
        *player,
        *player,
        *derived_high,
        *hand_high,
        *shop_high,
        *card_high,
        *board_high,
        *ahead_high,
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
