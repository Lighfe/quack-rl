"""Gymnasium env: the agent plays one seat, a bot plays the other.

Built on `QuackParallelEnv`, so the engine rules live in one place. The opponent acts inside
`step`. An action outside the mask is replaced by the first legal action and flagged with
`info["illegal_action"]`; use `action_masks()` to avoid it. Steps where the agent can only
`Wait` are skipped, so the agent sees real decisions only. At the terminal step the mask is
all zero, as `legal_actions` is empty when the game is over.
"""

from collections.abc import Callable
from typing import Any

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from quack_rl.bots.random_bot import RandomBot
from quack_rl.engine import SEATS, GameState, Phase, StepResult, legal_actions
from quack_rl.rl.encode import other_seat
from quack_rl.rl.parallel_env import QuackParallelEnv
from quack_rl.rl.reward import reward
from quack_rl.rules import Ruleset


class QuackEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(
        self,
        seat: str = "p1",
        opponent: Any = None,
        rules: str | Ruleset = "v1.1",
        reward_fn: Callable[[GameState, str], float] = reward,
    ):
        """`seat` is "p1", "p2" or "random" (per episode). `opponent` has `choose(state, seat,
        legal)`; None means a `RandomBot`, seeded from the env on each reset."""
        if seat not in (*SEATS, "random"):
            raise ValueError(f"seat must be 'p1', 'p2' or 'random', not {seat!r}")
        self._env = QuackParallelEnv(rules=rules, reward_fn=reward_fn)
        self.rs = self._env.rs
        self.seat = seat
        self._default_opponent = opponent is None
        self.opponent = RandomBot() if opponent is None else opponent
        self.agent_seat = SEATS[0] if seat == "random" else seat
        self.observation_space = spaces.Box(-np.inf, np.inf, (self._env._obs_len,), np.float32)
        self.action_space = self._env.action_space("p1")
        self._wait = self._env._wait
        self._mask = np.zeros(self.action_space.n, dtype=np.int8)
        self._ended = True
        self._decisions = 0

    @property
    def trace(self) -> list[StepResult]:
        """The engine step results of the current game (the list of the parallel env)."""
        return self._env.trace

    @property
    def state(self) -> GameState:
        return self._env.state

    def action_masks(self) -> np.ndarray:
        """The current action mask (for `MaskablePPO`)."""
        return self._mask.copy()

    def _wait_only(self, mask: np.ndarray) -> bool:
        return bool(mask[self._wait]) and int(mask.sum()) == 1

    def _opponent_action(self) -> int:
        opp = other_seat(self.agent_seat)
        legal = legal_actions(self.state, self.rs, opp)
        return self._env._names.index(self.opponent.choose(self.state, opp, legal))

    def _advance(self, action: int | None) -> tuple[float, bool]:
        """Play env steps until the agent has a real decision or the game ends.

        `action` is the agent's first action; later steps are Wait-only for the agent.
        """
        total = 0.0
        done = False
        obs: dict = {}
        while True:
            act = self._wait if action is None else action
            action = None
            _, rewards, terms, _, _ = self._env.step(
                {self.agent_seat: act, other_seat(self.agent_seat): self._opponent_action()}
            )
            total += rewards[self.agent_seat]
            done = terms[self.agent_seat]
            if done:
                break
            obs = self._env._obs()[self.agent_seat]
            if not self._wait_only(obs["action_mask"]):
                break
        return total, done

    def _observation(self) -> np.ndarray:
        obs = self._env._obs()[self.agent_seat]
        self._mask = obs["action_mask"]
        if self.state.phase is Phase.GAME_OVER:  # no legal action at the end: all-zero mask
            self._mask = np.zeros_like(self._mask)
        return obs["observation"]

    def _episode_summary(self) -> dict[str, Any]:
        own_seat = self.agent_seat
        opp_seat = other_seat(own_seat)
        own = self.state.players[own_seat].points
        opp = self.state.players[opp_seat].points
        explosions = {own_seat: 0, opp_seat: 0}
        for result in self.trace:
            for event in result.events:
                if event["kind"] == "explode":
                    explosions[event["seat"]] += 1
        return {
            "result": "win" if own > opp else "loss" if own < opp else "draw",
            "points": {"own": own, "opponent": opp},
            "explosions": {"own": explosions[own_seat], "opponent": explosions[opp_seat]},
            "decisions": self._decisions,
            "seat": own_seat,
        }

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        if self.seat == "random":
            self.agent_seat = SEATS[int(self.np_random.integers(len(SEATS)))]
        if self._default_opponent:
            self.opponent = RandomBot(int(self.np_random.integers(2**32)))
        chance_seed = int(self.np_random.integers(2**32))
        self._env.reset(seed=chance_seed)
        self._ended = False
        self._decisions = 0
        # the first decision point may already be Wait-only for the agent
        while self._wait_only(self._env._obs()[self.agent_seat]["action_mask"]):
            _, done = self._advance(None)
            if done:  # cannot happen in a real game; keep the env consistent
                break
        obs = self._observation()
        return obs, {"action_mask": self.action_masks()}

    def step(self, action: int):
        if self._ended:
            raise RuntimeError("the episode has ended: call reset() before step()")
        action = int(action)
        illegal = not self._mask[action]
        if illegal:  # a plain (unmasked) learner or check_env: play the first legal action
            action = int(np.flatnonzero(self._mask)[0])
        total, done = self._advance(action)
        self._decisions += 1
        if done:
            self._ended = True
        obs = self._observation()
        info: dict[str, Any] = {"action_mask": self.action_masks(), "illegal_action": illegal}
        if done:
            info["episode"] = self._episode_summary()
        return obs, total, done, False, info
