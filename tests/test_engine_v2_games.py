"""Ruleset v2 end to end: bots, records, tournament and environments (issue #160)."""

import csv
import random

import numpy as np
from gymnasium.utils.env_checker import check_env
from pettingzoo.test import parallel_api_test
from typer.testing import CliRunner

from quack_rl.cli.main import app
from quack_rl.record import read_games, verify_game
from quack_rl.rl import QuackEnv, QuackParallelEnv
from quack_rl.rules import load_ruleset
from quack_rl.simgame import play_sim_game

RS = load_ruleset("v2")
runner = CliRunner()
HEURISTIC = "bot:draw20-pts1-points"


def play(p1, p2, seed, stream=None):
    return play_sim_game(
        RS, rules="v2", rounds=RS.rounds, overrides={}, p1=p1, p2=p2, game_seed=seed, stream=stream
    )[0]


def check_end(final):
    assert all(p.points <= 100 for p in final.players.values())
    assert final.winner in ("p1", "p2", "draw")


def test_heuristic_vs_heuristic_games_end_within_100_points():
    for seed in range(4):
        check_end(play(HEURISTIC, HEURISTIC, seed))


def test_random_vs_random_games_end_within_100_points():
    for seed in range(4):
        check_end(play("bot:random", "bot:random", seed))


def test_masked_random_game_stays_in_the_observation_space():
    env = QuackParallelEnv(rules="v2")
    space = env.observation_space("p1")
    rng = random.Random(1)
    obs, _ = env.reset(seed=7)
    steps = 0
    while env.agents:
        for agent in env.agents:
            assert space["observation"].contains(obs[agent]["observation"])
            assert space["action_mask"].contains(obs[agent]["action_mask"])
        acts = {a: rng.choice(np.flatnonzero(obs[a]["action_mask"]).tolist()) for a in env.agents}
        obs, _, _, _, _ = env.step(acts)
        steps += 1
    assert steps > 0


def test_recorded_v2_game_reads_back_and_verifies(tmp_path):
    path = tmp_path / "game.jsonl"
    with path.open("w", encoding="utf-8") as f:
        final = play(HEURISTIC, "bot:random", 3, stream=f)
    (game,) = read_games(path)
    assert verify_game(game) == []
    assert '"rat_tail"' in path.read_text(encoding="utf-8")
    check_end(final)


def test_tournament_on_v2_writes_its_result_table(tmp_path):
    result = runner.invoke(
        app,
        ["tournament", "--rules", "v2", "--bots", f"{HEURISTIC},bot:random", "--games", "2",
         "--seed", "5", "--out", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    (run,) = [p for p in tmp_path.glob("*") if p.is_dir()]
    with (run / "results.csv").open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert {r["winner"] for r in rows} <= {"p1", "p2", "draw"}


def test_parallel_api_on_v2():
    parallel_api_test(QuackParallelEnv(rules="v2"), num_cycles=1000)


def test_check_env_on_v2():
    check_env(QuackEnv(rules="v2"), skip_render_check=True)
