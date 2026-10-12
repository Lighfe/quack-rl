import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full", app_title="RL environment")

with app.setup:
    # The Gymnasium env QuackEnv against RandomBot, and a very small MaskablePPO training (a
    # smoke test of the tooling, not an agent that is any good). Cells 1 and 2 need only the
    # default install; cell 3 needs the `train` group: `uv sync --group train`.
    import importlib.util

    import marimo as mo
    import numpy as np

    from quack_rl.engine import action_names
    from quack_rl.rl import QuackEnv, vector_names

    RULES = "v1.1"
    EVAL_GAMES = 100  # games per win rate
    DEFAULT_STEPS = 2048
    INSTALL_COMMAND = "uv sync --group train"


@app.function
def make_env() -> QuackEnv:
    """The single-seat env on v1.1: the agent is p1, RandomBot plays p2."""
    return QuackEnv(seat="p1", opponent=None, rules=RULES)


@app.function
def named_observation(env: QuackEnv, obs: np.ndarray) -> dict[str, float]:
    """The flat observation vector with its entry names (`vector_names`)."""
    return dict(zip(vector_names(env.rs), (float(x) for x in obs), strict=True))


@app.function
def legal_names(env: QuackEnv, mask: np.ndarray) -> list[str]:
    """The names of the actions the mask allows."""
    return [name for name, ok in zip(action_names(env.rs), mask, strict=True) if ok]


@app.function
def step_named(env: QuackEnv, name: str):
    """Play the action called `name`; returns (obs, reward, terminated, mask)."""
    obs, reward, terminated, _, info = env.step(action_names(env.rs).index(name))
    return obs, reward, terminated, info["action_mask"]


@app.function
def train_installed() -> bool:
    return importlib.util.find_spec("sb3_contrib") is not None


@app.function
def win_rate(env: QuackEnv, model, games: int = EVAL_GAMES) -> float:
    """Share of `games` games with a win for the agent (a draw is no win), seeds 0..games-1."""
    wins = 0
    for seed in range(games):
        obs, info = env.reset(seed=seed)
        done = False
        reward = 0.0
        while not done:
            action, _ = model.predict(obs, action_masks=env.action_masks(), deterministic=True)
            obs, reward, done, _, _ = env.step(int(action))
        wins += reward > 0
    return wins / games


@app.function
def train_model(steps: int, seed: int = 0):
    """An untrained MaskablePPO and the same model after `steps` steps, on the CPU."""
    from sb3_contrib import MaskablePPO

    env = make_env()
    model = MaskablePPO("MlpPolicy", env, seed=seed, device="cpu", verbose=0)
    before = win_rate(make_env(), model)
    model.learn(total_timesteps=steps)
    return before, win_rate(make_env(), model)


@app.cell(hide_code=True)
def _():
    mo.md(f"""
    # RL environment

    `QuackEnv`: you play p1 on `{RULES}`, `RandomBot` plays p2. The reward is +1 for a win,
    -1 for a loss and 0 for a draw, given once at the end of the game.
    """)
    return


@app.cell
def _():
    env = make_env()
    first_obs, first_info = env.reset(seed=0)
    first_state = {
        "obs": first_obs,
        "mask": first_info["action_mask"],
        "reward": None,
        "done": False,
    }
    mo.vstack(
        [
            mo.md("## 1. Observation and action mask after `reset`"),
            mo.ui.table(
                [{"entry": k, "value": v} for k, v in named_observation(env, first_obs).items()],
                selection=None,
                page_size=10,
            ),
            mo.md(
                "Legal actions: "
                + ", ".join(f"`{n}`" for n in legal_names(env, first_state["mask"]))
            ),
        ]
    )
    return env, first_state


@app.cell
def _(first_state):
    get_state, set_state = mo.state(first_state)
    return get_state, set_state


@app.cell
def _(env, get_state):
    names = legal_names(env, get_state()["mask"])
    action_picker = mo.ui.dropdown(options=names, value=names[0] if names else None, label="Action")
    action_picker  # noqa: B018 (marimo shows the last expression)
    return (action_picker,)


@app.cell
def _(action_picker, env, first_state, set_state):
    def _play(_):
        obs, reward, done, mask = step_named(env, action_picker.value)
        set_state({"obs": obs, "mask": mask, "reward": reward, "done": done})

    def _random(_):
        name = np.random.default_rng().choice(legal_names(env, env.action_masks()))
        obs, reward, done, mask = step_named(env, str(name))
        set_state({"obs": obs, "mask": mask, "reward": reward, "done": done})

    def _new_game(_):
        obs, info = env.reset()
        set_state({**first_state, "obs": obs, "mask": info["action_mask"]})

    step_button = mo.ui.button(label="Step with the action", on_click=_play)
    random_button = mo.ui.button(label="Random step", on_click=_random)
    new_game_button = mo.ui.button(label="New game", on_click=_new_game)
    mo.hstack([step_button, random_button, new_game_button], justify="start")
    return


@app.cell
def _(env, get_state):
    _state = get_state()
    mo.vstack(
        [
            mo.md(
                "## 2. Steps\n\nReward of the last step: "
                f"`{_state['reward']}` · game over: `{_state['done']}`\n\n"
                "Legal actions: "
                + (", ".join(f"`{n}`" for n in legal_names(env, _state["mask"])) or "none")
            ),
            mo.ui.table(
                [
                    {"entry": k, "value": v}
                    for k, v in named_observation(env, _state["obs"]).items()
                ],
                selection=None,
                page_size=10,
            ),
        ]
    )
    return


@app.cell
def _():
    steps_input = mo.ui.number(
        start=64, stop=100_000, step=64, value=DEFAULT_STEPS, label="Training steps"
    )
    train_button = mo.ui.run_button(label="Train")
    mo.vstack(
        [
            mo.md("## 3. A very simple training\n\n`MaskablePPO` (sb3-contrib) on the CPU."),
            mo.hstack([steps_input, train_button], justify="start"),
        ]
    )
    return steps_input, train_button


@app.cell
def _(steps_input, train_button):
    mo.stop(
        not train_installed(),
        mo.callout(
            mo.md(f"The `train` group is not installed. Run `{INSTALL_COMMAND}` and reopen."),
            kind="warn",
        ),
    )
    mo.stop(
        not (train_button.value or mo.app_meta().mode == "script"),
        mo.md("Press **Train**."),
    )
    before, after = train_model(int(steps_input.value))
    mo.md(f"""
    Win rate against `RandomBot` over {EVAL_GAMES} games after {int(steps_input.value)} steps
    (no tuning, no claim about strength; a draw is no win):

    | | win rate |
    |---|---|
    | before training | {before:.0%} |
    | after training | {after:.0%} |
    """)
    return


if __name__ == "__main__":
    app.run()
