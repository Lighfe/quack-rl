"""Continue a saved policy online with MaskablePPO against a bot (issue #94).

The run folder of an offline (behaviour cloning) run holds a `MaskablePPO` model whose actor is
trained and whose value head is not. `finetune_online` loads it, attaches a `QuackEnv`, trains
for `steps` timesteps and writes a new run folder that `PolicyBot.from_run` loads. The source
run is never changed. torch and sb3-contrib are imported inside the function (the `train` group).
"""

import json
import shutil
from pathlib import Path

from quack_rl.rl.opponents import make_opponent
from quack_rl.rl.runs import load_model
from quack_rl.rl.single_env import QuackEnv
from quack_rl.rl.train import N_STEPS

BATCH_SIZE = 64


def finetune_online(
    run_dir: Path | str,
    out_dir: Path | str,
    steps: int,
    opponent: str,
    seed: int = 0,
    rules: str = "v1.1",
    learning_rate: float = 1e-4,
) -> Path:
    """Train the model of `run_dir` for `steps` timesteps against `opponent`; write `out_dir`.

    The agent sits at a random seat each game. `out_dir` gets `config.json` (the config of the
    source run plus a `finetune` entry) and `model.zip`. Raise ValueError for an unknown
    opponent or `steps < 1`, FileExistsError for a non-empty `out_dir`, all before training.
    """
    if steps < 1:
        raise ValueError(f"steps must be at least 1, not {steps}")
    make_opponent(opponent, seed=seed, rules=rules)  # ValueError on an unknown name
    run_dir, out_dir = Path(run_dir), Path(out_dir)
    if out_dir.exists() and (not out_dir.is_dir() or any(out_dir.iterdir())):
        raise FileExistsError(f"output folder {out_dir} already exists and is not empty")

    import gymnasium as gym
    from sb3_contrib.common.maskable.buffers import MaskableRolloutBuffer
    from stable_baselines3.common.utils import ConstantSchedule

    model = load_model(run_dir, rules)

    class MaskedEnv(gym.Wrapper):
        def action_masks(self):
            return self.env.action_masks()

    env = MaskedEnv(
        QuackEnv(seat="random", rules=rules, opponent=make_opponent(opponent, seed, rules))
    )
    env.reset(seed=seed)
    # The offline build made the network with an unbounded Box; the env states its real bounds.
    # The network is the same, so take the env's space for the model and the policy.
    model.observation_space = model.policy.observation_space = env.observation_space
    model.set_env(env)
    # The saved model carries the defaults of the offline build (2048 steps per rollout). Use
    # the rollout size of `train`, so a short run is not rounded up to 2048 timesteps.
    model.n_steps = N_STEPS
    model.batch_size = BATCH_SIZE
    model.learning_rate = learning_rate
    model.lr_schedule = ConstantSchedule(learning_rate)
    model.rollout_buffer = MaskableRolloutBuffer(
        N_STEPS,
        model.observation_space,
        model.action_space,
        device=model.device,
        gamma=model.gamma,
        gae_lambda=model.gae_lambda,
        n_envs=1,
    )
    model.set_random_seed(seed)
    model.learn(total_timesteps=steps)

    config = json.loads((run_dir / "config.json").read_text())
    config["finetune"] = {
        "steps": steps,
        "opponent": opponent,
        "seed": seed,
        "learning_rate": learning_rate,
    }
    tmp = out_dir.with_name(f".{out_dir.name}.tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    try:
        (tmp / "config.json").write_text(json.dumps(config, indent=2) + "\n")
        model.save(str(tmp / "model.zip"))
        if out_dir.exists():
            out_dir.rmdir()  # an empty folder is allowed
        tmp.rename(out_dir)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return out_dir
