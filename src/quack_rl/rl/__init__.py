"""RL interface of the engine: encoder, reward and envs. The engine does not import this package."""

from quack_rl.rl.encode import (
    MAP_CHANNELS,
    OBSERVATION_LAYOUT,
    action_mask,
    map_channels,
    map_slice,
    observation_bounds,
    observation_layout,
    observe,
    vector_names,
    vectorize,
)
from quack_rl.rl.opponents import make_opponent
from quack_rl.rl.parallel_env import QuackParallelEnv
from quack_rl.rl.reward import reward
from quack_rl.rl.single_env import QuackEnv

__all__ = [
    "MAP_CHANNELS",
    "OBSERVATION_LAYOUT",
    "QuackEnv",
    "QuackParallelEnv",
    "action_mask",
    "make_opponent",
    "map_channels",
    "map_slice",
    "observation_bounds",
    "observation_layout",
    "observe",
    "reward",
    "vector_names",
    "vectorize",
]
