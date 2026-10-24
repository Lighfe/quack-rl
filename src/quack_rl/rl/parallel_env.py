"""PettingZoo ParallelEnv over the engine: both seats act at every step.

One env step goes from one engine decision point (Brew or Shop) to the next. Phases without
decisions (Resolve) are folded into the step whose joint action triggers them. A seat with
nothing to do has only `Wait` in its mask.
"""

import copy
import random
from collections.abc import Callable
from typing import Any

import numpy as np
from gymnasium import spaces
from pettingzoo import ParallelEnv

from quack_rl.engine import (
    SEATS,
    WAIT,
    ChanceSource,
    GameState,
    Phase,
    RngChance,
    StepResult,
    action_names,
    needs_actions,
    new_game,
    step,
)
from quack_rl.rl.encode import action_mask, observation_bounds, observe, vector_names, vectorize
from quack_rl.rl.reward import reward
from quack_rl.rules import Ruleset, load_ruleset


class QuackParallelEnv(ParallelEnv):
    metadata = {"name": "quack_rl_parallel_v0", "render_modes": []}

    def __init__(
        self,
        rules: str | Ruleset = "v2.1",
        reward_fn: Callable[[GameState, str], float] = reward,
        chance: ChanceSource | None = None,
    ):
        """`chance` replaces the seeded chance source (tests with scripted chance)."""
        self.rs = load_ruleset(rules) if isinstance(rules, str) else rules
        self.reward_fn = reward_fn
        self._chance_override = chance
        self.possible_agents = list(SEATS)
        self.agents: list[str] = []
        self._names = action_names(self.rs)
        self._wait = self._names.index(WAIT)
        self._obs_len = len(vector_names(self.rs))
        self._obs_low, self._obs_high = observation_bounds(self.rs)
        self._observation_space = spaces.Dict(
            {
                "observation": spaces.Box(
                    self._obs_low, self._obs_high, (self._obs_len,), np.float32
                ),
                "action_mask": spaces.Box(0, 1, (len(self._names),), np.int8),
            }
        )
        self._action_space = spaces.Discrete(len(self._names))
        self.state: GameState = new_game(self.rs)
        self._chance: ChanceSource = RngChance(0)
        self._ended = True
        self.trace: list[StepResult] = []

    def observation_space(self, agent: str) -> spaces.Space:
        return self._observation_space

    def action_space(self, agent: str) -> spaces.Space:
        return self._action_space

    def _fold(self, chance: ChanceSource) -> None:
        while self.state.phase is not Phase.GAME_OVER and not needs_actions(self.state):
            result = step(self.state, self.rs, None, chance)
            self.trace.append(result)
            self.state = result.state

    def _obs(self) -> dict[str, dict[str, np.ndarray]]:
        out = {}
        for seat in self.agents or self.possible_agents:
            mask = action_mask(self.state, self.rs, seat)
            out[seat] = {
                "observation": vectorize(observe(self.state, self.rs, seat), self.rs),
                "action_mask": mask,
            }
        return out

    def reset(self, seed: int | None = None, options: dict | None = None):
        if self._chance_override is not None:
            self._chance = self._chance_override
        else:
            self._chance = RngChance(random.randrange(2**32) if seed is None else seed)
        self.state = new_game(self.rs)
        self.trace = []
        self.agents = list(self.possible_agents)
        self._ended = False
        self._fold(self._chance)
        return self._obs(), {a: {} for a in self.agents}

    def step(self, actions: dict[str, int]):
        if self._ended:
            raise RuntimeError("the episode has ended: call reset() before step()")
        joint = {seat: self._names[int(actions[seat])] for seat in self.agents}
        result = step(self.state, self.rs, joint, self._chance)
        self.trace.append(result)
        self.state = result.state
        self._fold(self._chance)
        done = self.state.phase is Phase.GAME_OVER
        obs = self._obs()
        rewards = {
            a: float(self.reward_fn(copy.deepcopy(self.state), a)) if done else 0.0
            for a in self.agents
        }
        terminations = {a: done for a in self.agents}
        truncations = {a: False for a in self.agents}
        infos: dict[str, dict[str, Any]] = {a: {} for a in self.agents}
        if done:
            self._ended = True
            self.agents = []
        return obs, rewards, terminations, truncations, infos
