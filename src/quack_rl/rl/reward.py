from collections.abc import Callable

from quack_rl.engine import GameState

MARGIN_SCALE = 40.0
"""Points of margin that give the full reward of `margin_reward` (+1 or -1).

Measured with ruleset v2.3: 800 games, 50 for each ordered pair of the three preset bots
(`PRESET_BOTS`) and `bot:random` (16 pairs, chance seeds 0 to 49, seats alternating). The final
margin (own points minus the other seat's) had mean -0.1 and standard deviation 20.8; its absolute
value had median 12, 90th percentile 35, 95th percentile 39, 99th percentile 46 and maximum 53.
So 40 points is about the 95th percentile: almost all margins stay inside (-1, 1).
"""


def reward(final_state: GameState, seat: str) -> float:
    """+1 for more points than the other seat, -1 for fewer, 0 for equal points."""
    own = final_state.players[seat].points
    other = max(p.points for s, p in final_state.players.items() if s != seat)
    return float((own > other) - (own < other))


def margin_reward(final_state: GameState, seat: str) -> float:
    """Own points minus the best other seat's points, divided by `MARGIN_SCALE`, in [-1, 1]."""
    own = final_state.players[seat].points
    other = max(p.points for s, p in final_state.players.items() if s != seat)
    return max(-1.0, min(1.0, (own - other) / MARGIN_SCALE))


REWARDS: dict[str, Callable[[GameState, str], float]] = {
    "win_loss": reward,
    "margin": margin_reward,
}
