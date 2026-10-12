from quack_rl.engine import GameState


def reward(final_state: GameState, seat: str) -> float:
    """+1 for more points than the other seat, -1 for fewer, 0 for equal points."""
    own = final_state.players[seat].points
    other = max(p.points for s, p in final_state.players.items() if s != seat)
    return float((own > other) - (own < other))
