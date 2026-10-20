"""Derived features of one seat for the generic rules of the game.

A derived feature is a function of what the observation already holds. It adds convenience,
not information. Only generic rules are derived (fields, the money table, rubies, the
explosion limit, the die, points); what a single colour or chip does is learned from the
board. The rule code stays in the engine and the bots: this module calls `scoring_field`,
`explosion_chance` and the ruleset tables.
"""

from quack_rl.bots.heuristic import explosion_chance
from quack_rl.engine import SEATS, GameState, Status, explosion_limit
from quack_rl.engine.state import PlayerState, scoring_field
from quack_rl.rules import Ruleset

# Per seat, in vector order.
SEAT_FEATURES = (
    "scoring_field",
    "ruby_at_scoring_field",
    "money_if_stop",
    "limit_distance",
    "explosion_chance",
    "rolls_die",
    "chips_placed",
)
SHARED_FEATURES = ("point_delta",)
# Layout 3 (rulesets with `explosion_choice`) appends these after the layout 2 entries.
CHOICE_FEATURES = ("own.field_points", "last_round")


def derived_names(rs: Ruleset | None = None) -> list[str]:
    """Names of the derived entries, in the order of `derived`. With a ruleset that has the
    explosion choice (layout 3) the entries of `CHOICE_FEATURES` follow; without `rs`, layout 2."""
    names = [
        *(f"{who}.{k}" for who in ("own", "opponent") for k in SEAT_FEATURES),
        *SHARED_FEATURES,
    ]
    if rs is not None and rs.explosion_choice:
        names += CHOICE_FEATURES
    return names


def _money_if_stop(p: PlayerState, state: GameState, rs: Ruleset) -> int:
    """The money table at the scoring field, halved after an explosion, times the last-round
    multiplier. The bonus die and the round-end bonus are not included."""
    money = rs.money[scoring_field(p.field, rs)]
    if p.status is Status.EXPLODED and not rs.explosion_choice:
        money //= 2
    if state.round == rs.rounds:
        if rs.last_round_money_divisor is not None:
            return 0  # v1.8: the last-round money becomes points at once
        money = money * rs.last_round_money_percent // 100
    return money


def derived(state: GameState, rs: Ruleset, seat: str) -> dict[str, float]:
    """Derived features of `seat` ("own.*"), of its opponent ("opponent.*") and "point_delta"
    (own points minus opponent points)."""
    other = SEATS[1] if seat == SEATS[0] else SEATS[0]
    players = {"own": state.players[seat], "opponent": state.players[other]}
    fields = {who: scoring_field(p.field, rs) for who, p in players.items()}
    best = max(
        (fields[who] for who, p in players.items() if p.status is not Status.EXPLODED),
        default=None,
    )
    limit = explosion_limit(state, rs)
    out: dict[str, float] = {}
    for who, p in players.items():
        out[f"{who}.scoring_field"] = fields[who]
        out[f"{who}.ruby_at_scoring_field"] = float(fields[who] in rs.rubies)
        out[f"{who}.money_if_stop"] = _money_if_stop(p, state, rs)
        out[f"{who}.limit_distance"] = limit - p.white_total
        out[f"{who}.explosion_chance"] = explosion_chance(p.bag, p.white_total, rs, limit=limit)
        out[f"{who}.rolls_die"] = float(p.status is not Status.EXPLODED and fields[who] == best)
        out[f"{who}.chips_placed"] = len(p.placed)
    out["point_delta"] = players["own"].points - players["opponent"].points
    if rs.explosion_choice:
        out["own.field_points"] = rs.points[fields["own"]] if rs.points is not None else 0
        out["last_round"] = float(state.round == rs.rounds)
    return out
