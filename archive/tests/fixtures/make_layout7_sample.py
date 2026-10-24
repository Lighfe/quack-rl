"""Make the stored sample of observation layout 7 (rules v2.1): one game through the environment.

Run only on purpose: the file pins v2.1 behaviour (issue #167). Do not regenerate it unless
layout 7 is changed on purpose.

uv run python tests/fixtures/make_layout7_sample.py
"""

import random
from pathlib import Path

import numpy as np

from quack_rl.rl import QuackParallelEnv, vector_names
from quack_rl.rules import load_ruleset

OUT = Path(__file__).parent / "layout7" / "sample.npz"


def play_sample() -> dict[str, np.ndarray]:
    """Play one game: reset(seed=7), each seat draws its action from its mask with Random(7)."""
    rs = load_ruleset("v2.1")
    env = QuackParallelEnv(rules="v2.1")
    rng = random.Random(7)
    obs, _ = env.reset(seed=7)
    vecs, masks = [], []
    done = False
    while not done:
        actions = {}
        for seat in ("p1", "p2"):
            vecs.append(obs[seat]["observation"])
            masks.append(obs[seat]["action_mask"])
            actions[seat] = rng.choice(np.flatnonzero(obs[seat]["action_mask"]).tolist())
        obs, _, terminated, _, _ = env.step(actions)
        done = all(terminated.values())
    for seat in ("p1", "p2"):  # the last observation
        vecs.append(obs[seat]["observation"])
        masks.append(obs[seat]["action_mask"])
    assert env.state.round >= 3, "fewer than three rounds played"
    return {
        "observations": np.stack(vecs),
        "masks": np.stack(masks),
        "vector_names": np.array(vector_names(rs)),
    }


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(OUT, **play_sample())


if __name__ == "__main__":
    main()
