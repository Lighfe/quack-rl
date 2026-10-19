"""Make the stored sample of layouts 2, 3 and 4 (v1, v1.1, v1.8, v1.9): vectors and masks of random games.

The v1 and v1.1 part was made from the code before layout 3 was added, the v1.8 and v1.9 part
from the code before layout 5 (issue #137). Do not regenerate it unless these layouts are
changed on purpose.

uv run python tests/fixtures/make_layout2_sample.py
"""

import random
from pathlib import Path

import numpy as np

from quack_rl.engine import RngChance, legal_actions, needs_actions, new_game, step
from quack_rl.engine.state import Phase
from quack_rl.rl import action_mask, observe, vectorize
from quack_rl.rules import load_ruleset

OUT = Path(__file__).parent / "layout2" / "sample.npz"
VERSIONS = ["v1", "v1.1", "v1.8", "v1.9"]
SEEDS = [1, 2, 3]


def states(rs, seed):
    rng = random.Random(seed)
    chance = RngChance(seed)
    state = new_game(rs)
    yield state
    while state.phase is not Phase.GAME_OVER:
        actions = (
            {s: rng.choice(legal_actions(state, rs, s)) for s in ("p1", "p2")}
            if needs_actions(state)
            else None
        )
        state = step(state, rs, actions, chance).state
        yield state


def main() -> None:
    arrays = {}
    for version in VERSIONS:
        rs = load_ruleset(version)
        vecs, masks = [], []
        for seed in SEEDS:
            for state in states(rs, seed):
                for seat in ("p1", "p2"):
                    vecs.append(vectorize(observe(state, rs, seat), rs))
                    masks.append(action_mask(state, rs, seat))
        arrays[f"{version}_vectors"] = np.stack(vecs)
        arrays[f"{version}_masks"] = np.stack(masks)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(OUT, **arrays)


if __name__ == "__main__":
    main()
