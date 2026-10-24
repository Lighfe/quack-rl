"""The calculated points of the field table, checked by simulation.

`realistic_baseline_maximum` (src/quack_rl/report.py) is "points of the field table, without
chip purchases and cards", calculated from the ruleset only. This file plays many games of the
`points` strategy (points round 1) on v2.1 with 9 rounds and an empty shop (so nobody buys
chips), one draw limit after the other, and compares the averages with it:

- (a) the best simulated average over the draw limits is at least the calculation minus 3
  standard errors
- (b) the best simulated average is at most the calculation times (1 + CARD_MARGIN)

The calculation has no card effects (only the explosion limit of card 4), and cards cannot be
removed from the deck, so the simulation is above it. One measurement gave about 22% more; the
margin is CARD_MARGIN. Since the bots spend rubies on droplets (issue #190) the simulation is
about 43% above it. The number is not an upper bound of the real baseline bot.

The opponent is `draw100-pts9-points`: it draws until it explodes, so it never rolls the bonus
die and the bot under test always rolls it when it does not explode, as the calculation assumes.
"""

import math
import multiprocessing
import os
import statistics
from concurrent.futures import ProcessPoolExecutor

import pytest

from quack_rl.bots.heuristic import HeuristicBot
from quack_rl.engine import RngChance
from quack_rl.report import baseline_maximum, realistic_baseline_maximum
from quack_rl.rules import load_ruleset, with_rounds
from quack_rl.runner import play_game

CARD_MARGIN = 0.50
GAMES = 1000
DRAW_LIMITS = (0, 10, 20, 30, 40, 50)
OPPONENT = dict(draw_limit=100, points_round=9, strategy="points")

RS = with_rounds(load_ruleset("v2.1"), 9).model_copy(update={"shop": []})


CHUNK = 125  # games per task, so the pool (at most 4 workers) keeps its workers busy


def play_chunk(draw_limit: int, first: int) -> list[int]:
    """Final points of the bot under test in games `first` to `first + CHUNK - 1`."""
    points = []
    for game in range(first, first + CHUNK):
        seats = {
            "p1": HeuristicBot(RS, draw_limit, 1, "points", seed=2 * game + 1),
            "p2": HeuristicBot(RS, seed=2 * game + 2, **OPPONENT),
        }
        final = play_game(RS, seats, RngChance(game))
        points.append(final.players["p1"].points)
    return points


def simulate_all(also=None):
    """Average final points and its standard error over GAMES games with a fixed seed.

    The games run in a process pool; each game has its own seeds, so the numbers are the same as
    in one loop. `also` is a function that the main process calls while the pool works; the
    result is returned as the second value.
    """
    tasks = [(limit, first) for limit in DRAW_LIMITS for first in range(0, GAMES, CHUNK)]
    with ProcessPoolExecutor(
        max_workers=min(4, os.cpu_count() or 1),
        mp_context=multiprocessing.get_context("spawn"),
    ) as pool:
        futures = [pool.submit(play_chunk, *task) for task in tasks]
        extra = also() if also else None
        chunks = [future.result() for future in futures]
    results = {}
    for limit in DRAW_LIMITS:
        points = []
        for (lim, _), chunk in zip(tasks, chunks, strict=True):
            if lim == limit:
                points += chunk
        results[limit] = (statistics.fmean(points), statistics.stdev(points) / math.sqrt(GAMES))
    return results, extra


@pytest.mark.slow
def test_simulation_matches_the_calculated_field_table_points():
    results, calculated = simulate_all(lambda: realistic_baseline_maximum(RS))
    best, best_stderr = max(results.values())
    print(f"calculated {calculated:.2f}, best simulated {best:.2f}, ratio {best / calculated:.3f}")
    assert best >= calculated - 3 * best_stderr, (best, best_stderr, calculated)
    assert best <= calculated * (1 + CARD_MARGIN), (best, calculated)
    # the loose bound (the cap) is not below the calculated number
    assert baseline_maximum(RS) >= calculated
