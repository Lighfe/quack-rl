"""Ruleset v2.2: the stored game with a ruby step, and RL on v2.2.

The record is `tests/fixtures/golden/v2_2_random_seed7.jsonl` (regenerate it on purpose with
`uv run python tests/fixtures/make_golden.py v2.2`).
"""

import json
import random
from pathlib import Path

import numpy as np

from quack_rl.engine import Phase, legal_actions
from quack_rl.record import read_games, verify_game, verify_seed
from quack_rl.rl import QuackParallelEnv, vector_names
from quack_rl.rules import load_ruleset

GOLDEN = Path(__file__).parent / "fixtures" / "golden"
RECORD = GOLDEN / "v2_2_random_seed7.jsonl"
RS = load_ruleset("v2.2")


def test_v2_2_record_replays_and_has_a_ruby_step():
    (game,) = read_games(RECORD)
    assert game.header.rules_version == "v2.2"
    assert verify_game(game) == []
    assert verify_seed(game) == []
    ruby = [s for s in game.steps if s.phase == "ruby"]
    assert ruby
    for s in game.steps:
        if s.phase == "shop":
            assert not {"ruby_drop", "refill_flask"} & {a for legal in s.legal.values() for a in legal}
    spent = {e["kind"] for s in ruby for e in s.events}
    assert "ruby_drop" in spent or "refill_flask" in spent


def test_layout8_sample_adds_only_phase_ruby():
    sample = json.loads((GOLDEN / "layout8_sample.json").read_text(encoding="utf-8"))
    v21 = vector_names(load_ruleset("v2.1"))
    assert sample["names"] == v21
    assert vector_names(RS) == v21  # v2.2 has the same layout as v2.1
    phases = [n for n in v21 if n.startswith("phase.")]
    assert phases == [f"phase.{p.value}" for p in Phase]
    assert phases.index("phase.ruby") == phases.index("phase.shop") + 1


def test_masked_random_v2_2_game_stays_in_the_space_and_reaches_the_ruby_step():
    seen = False
    for seed in range(3):
        env = QuackParallelEnv(rules=RS)
        rng = random.Random(seed)
        obs, _ = env.reset(seed=seed)
        space = env.observation_space("p1")
        while env.agents:
            seen = seen or env.state.phase is Phase.RUBY
            for seat in env.agents:
                assert space.contains(obs[seat])
                if env.state.phase is not Phase.GAME_OVER:
                    legal = set(legal_actions(env.state, RS, seat))
                    mask = obs[seat]["action_mask"]
                    assert {env._names[i] for i in np.flatnonzero(mask)} <= legal | {"wait"}
            acts = {
                a: rng.choice(np.flatnonzero(obs[a]["action_mask"]).tolist()) for a in env.agents
            }
            obs, *_ = env.step(acts)
    assert seen
