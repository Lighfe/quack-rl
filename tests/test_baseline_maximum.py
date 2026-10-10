"""The calculated maximum of the baseline bot, confirmed by simulation.

`realistic_baseline_maximum` (src/quack_rl/report.py) is calculated from the ruleset only. This
file plays many games of the `points` strategy (points round 1) on v1 with 9 rounds, one draw
limit after the other, and compares the averages with it:

- (a) no draw limit has a simulated average above the maximum plus 3 standard errors
- (b) the best simulated average over the draw limits is at least the maximum minus TOLERANCE

TOLERANCE is 2% of the maximum (the issue allows at most 5%; the calculation is exact for the
rules, so the gap is mostly the draw limit grid and the simulation noise).

The opponent is `draw100-pts9-points`: it draws until it explodes, so it never rolls the bonus
die and the bot under test always rolls it when it does not explode, as the calculation assumes.
Against a stronger opponent the bot rolls less often and its average is lower than the maximum.
"""

import math
import statistics

from quack_rl.bots.heuristic import HeuristicBot
from quack_rl.engine import RngChance
from quack_rl.report import CONFIRM_TOLERANCE, baseline_maximum, realistic_baseline_maximum
from quack_rl.rules import load_ruleset, with_rounds
from quack_rl.runner import play_game

TOLERANCE = 0.02
GAMES = 2000
DRAW_LIMITS = (0, 10, 20, 30, 40, 50)
OPPONENT = dict(draw_limit=100, points_round=9, strategy="points")

RS = with_rounds(load_ruleset("v1"), 9)


def simulate(draw_limit: int) -> tuple[float, float]:
    """Average final points and its standard error over GAMES games with a fixed seed."""
    points = []
    for game in range(GAMES):
        seats = {
            "p1": HeuristicBot(RS, draw_limit, 1, "points", seed=2 * game + 1),
            "p2": HeuristicBot(RS, seed=2 * game + 2, **OPPONENT),
        }
        final = play_game(RS, seats, RngChance(game))
        points.append(final.players["p1"].points)
    return statistics.fmean(points), statistics.stdev(points) / math.sqrt(GAMES)


def test_simulation_confirms_the_calculated_maximum():
    maximum = realistic_baseline_maximum(RS)
    results = {limit: simulate(limit) for limit in DRAW_LIMITS}
    assert TOLERANCE <= CONFIRM_TOLERANCE <= 0.05
    for limit, (mean, stderr) in results.items():
        assert mean <= maximum + 3 * stderr, (limit, mean, stderr, maximum)
    best = max(mean for mean, _ in results.values())
    assert best >= maximum - TOLERANCE * maximum, (best, maximum)
    # the baseline bot (draw limit 30) is below the maximum, which is below the loose bound
    assert results[30][0] < maximum < baseline_maximum(RS) == 151
