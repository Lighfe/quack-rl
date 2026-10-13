import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full", app_title="RL environment")

with app.setup:
    # The Gymnasium env QuackEnv against RandomBot, and a MaskablePPO training against an opponent
    # of your choice with an honest evaluation. Sections 1 and 2 need only the default install;
    # section 3 needs the `train` group: `uv sync --group train`. Nothing is written to disk
    # unless you press "Save this run".
    import importlib.util
    from pathlib import Path

    import altair as alt
    import marimo as mo
    import numpy as np
    import polars as pl

    from quack_rl.engine import action_names
    from quack_rl.rl import QuackEnv, make_opponent, vector_names
    from quack_rl.rl.runs import eval_dict, load_run, run_path, save_run

    RULES = "v1.1"
    EVAL_GAMES = 500  # games per row of the table
    DEFAULT_STEPS = 2048
    INSTALL_COMMAND = "uv sync --group train"
    RUNS_DIR = Path("data/runs")
    OPPONENT_OPTIONS = ["random", "draw20-pts4-blue", "other (type a name below)"]
    OTHER_OPTION = OPPONENT_OPTIONS[-1]
    ROLLING_WINDOW = 50  # games
    EVAL_ROWS = (
        ("random agent (uniform)", "baseline_random"),
        ("untrained policy (sampled)", "baseline_untrained"),
        ("trained policy (sampled)", "trained_sampled"),
        ("trained policy (greedy)", "trained_greedy"),
    )


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
def resolve_opponent(choice: str | None, typed: str) -> tuple[str | None, str | None]:
    """(opponent name, None) for the dropdown choice and the free text, or (None, message)."""
    name = typed.strip() if choice == OTHER_OPTION else choice
    if not name:
        return None, "Type a bot name, for example `draw20-pts4-blue`, or pick one from the list."
    try:
        make_opponent(name, rules=RULES)
    except ValueError as err:
        return None, f"Not a known opponent: {err}"
    return name, None


@app.function
def run_training(steps: int, opponent: str, eval_games: int, seed: int = 0):
    """Train without `run=` (nothing is written). Returns (TrainResult, config of the run)."""
    from quack_rl.rl.train import train

    result = train(steps, rules=RULES, opponent=opponent, seed=seed, eval_games=eval_games)
    config = {
        "steps": steps,
        "rules": RULES,
        "opponent": opponent,
        "seed": seed,
        "eval_games": eval_games,
    }
    return result, config


@app.function
def eval_rows(evals: dict[str, dict], opponent: str) -> list[dict]:
    """Table rows (wins, draws, losses) from `eval_dict(result)` or the `eval.json` of a run.

    The rows against `RandomBot` exist only when the opponent is not `random`: then the
    `*_vs_random` entries are in `evals`, otherwise there is no second block.
    """
    rows = []
    for suffix, against in (("", opponent), ("_vs_random", "RandomBot")):
        for label, key in EVAL_ROWS:
            r = evals.get(key + suffix)
            if r is not None:
                rows.append(
                    {
                        "agent": label,
                        "against": against,
                        "games": r["games"],
                        "wins": r["wins"],
                        "draws": r["draws"],
                        "losses": r["losses"],
                    }
                )
    return rows


@app.function
def curve_frames(
    episodes: list[dict], metrics: list[dict], window: int = ROLLING_WINDOW
) -> dict[str, pl.DataFrame]:
    """The data of the four plots: rolling means over `window` games, and the loss rows."""
    ep = pl.DataFrame(
        episodes,
        schema={
            "episode": pl.Int64,
            "result": pl.String,
            "points_own": pl.Float64,
            "points_opponent": pl.Float64,
            "explosions_own": pl.Float64,
        },
    ).select(
        "episode",
        win_rate=(pl.col("result") == "win").cast(pl.Float64),
        points_own=pl.col("points_own"),
        points_opponent=pl.col("points_opponent"),
        explosions_own=pl.col("explosions_own"),
    )
    roll = ep.select(
        "episode", pl.exclude("episode").rolling_mean(window_size=window, min_samples=1)
    )
    loss_names = ["policy_gradient_loss", "value_loss", "entropy_loss"]
    met = pl.DataFrame(
        metrics, schema={"timestep": pl.Int64, **{n: pl.Float64 for n in loss_names}}
    )
    return {
        "win_rate": roll.select("episode", "win_rate"),
        "points": roll.select("episode", "points_own", "points_opponent").unpivot(
            index="episode", variable_name="who", value_name="points"
        ),
        "explosions": roll.select("episode", "explosions_own"),
        "losses": met.unpivot(index="timestep", variable_name="loss", value_name="value"),
    }


@app.function
def curve_charts(frames: dict[str, pl.DataFrame]) -> list[alt.Chart]:
    """Four altair line charts for `curve_frames`."""
    return [
        alt.Chart(frames["win_rate"], title="Rolling win rate")
        .mark_line()
        .encode(x="episode:Q", y=alt.Y("win_rate:Q", scale=alt.Scale(domain=[0, 1]))),
        alt.Chart(frames["points"], title="Average points per game (rolling)")
        .mark_line()
        .encode(x="episode:Q", y="points:Q", color="who:N"),
        alt.Chart(frames["explosions"], title="Explosions per game (rolling)")
        .mark_line()
        .encode(x="episode:Q", y="explosions_own:Q"),
        alt.Chart(frames["losses"], title="Loss curves over training")
        .mark_line()
        .encode(x="timestep:Q", y="value:Q", color="loss:N"),
    ]


@app.function
def save_trained(runs_dir: Path, name: str, result, config: dict) -> tuple[bool, str]:
    """Write the run to `runs_dir / name` through `save_run`; (ok, message) for the notebook.

    A bad name (empty, a path separator, `..`) or a name that exists writes nothing.
    """
    try:
        path = run_path(runs_dir, name.strip())
        save_run(path, result, config)
    except (ValueError, FileExistsError) as err:
        return False, str(err)
    return True, f"Saved the run to `{path}`."


@app.function
def saved_runs(runs_dir: Path) -> list[str]:
    """The names of the folders in `runs_dir` (none when it does not exist)."""
    if not runs_dir.is_dir():
        return []
    return sorted(p.name for p in runs_dir.iterdir() if p.is_dir())


@app.function
def load_saved(runs_dir: Path, name: str):
    """(config, frames, table rows, None) of a saved run, or (None, None, None, message)."""
    try:
        config, episodes, metrics, evaluation = load_run(run_path(runs_dir, name))
        frames = curve_frames(episodes, metrics)
        rows = eval_rows(evaluation, config["opponent"])
    except (OSError, ValueError, KeyError, TypeError) as err:
        return None, None, None, f"Cannot load the run `{name}`: {type(err).__name__}: {err}"
    return config, frames, rows, None


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
    opponent_picker = mo.ui.dropdown(
        options=OPPONENT_OPTIONS, value="random", label="Training opponent"
    )
    other_opponent = mo.ui.text(placeholder="draw20-pts4-blue", label="Other bot name")
    steps_input = mo.ui.number(
        start=64, stop=1_000_000, step=64, value=DEFAULT_STEPS, label="Training steps"
    )
    games_input = mo.ui.number(
        start=10, stop=10_000, step=10, value=EVAL_GAMES, label="Games per table row"
    )
    train_button = mo.ui.run_button(label="Train")
    mo.vstack(
        [
            mo.md(
                "## 3. Training and an honest evaluation\n\n`MaskablePPO` (sb3-contrib) on the CPU."
            ),
            mo.hstack([opponent_picker, other_opponent], justify="start"),
            mo.hstack([steps_input, games_input, train_button], justify="start"),
        ]
    )
    return games_input, opponent_picker, other_opponent, steps_input, train_button


@app.cell
def _(opponent_picker, other_opponent):
    opponent_name, opponent_error = resolve_opponent(opponent_picker.value, other_opponent.value)
    mo.callout(mo.md(opponent_error), kind="warn") if opponent_error else mo.md(
        f"Training opponent: `{opponent_name}`"
    )
    return (opponent_name,)


@app.cell
def _(games_input, opponent_name, steps_input, train_button):
    trained = None
    if not train_installed():
        training_output = mo.callout(
            mo.md(f"The `train` group is not installed. Run `{INSTALL_COMMAND}` and reopen."),
            kind="warn",
        )
    elif opponent_name is None:
        training_output = mo.md("Fix the opponent above, then press **Train**.")
    elif not train_button.value:
        training_output = mo.md(
            f"Press **Train** to train {int(steps_input.value)} steps against `{opponent_name}`."
        )
    else:
        with mo.status.spinner(title="Training and evaluating (this takes a while)"):
            trained = run_training(int(steps_input.value), opponent_name, int(games_input.value))
        training_output = mo.md(
            f"""
            One training step is **one decision of the agent** (about 42 per game), not one game.
            Trained {int(steps_input.value)} steps against `{opponent_name}`:
            **{trained[0].games_played} games** were played in training.
            """
        )
    training_output  # noqa: B018 (marimo shows the last expression)
    return (trained,)


@app.cell
def _(opponent_name, trained):
    if trained is None:
        table_output = mo.md("No trained policy yet.")
    else:
        table_output = mo.vstack(
            [
                mo.md(
                    "### Wins, draws and losses\n\nA draw is no win. Every row is "
                    f"{trained[1]['eval_games']} games; the noise is a few points of win rate."
                ),
                mo.ui.table(
                    eval_rows(eval_dict(trained[0]), trained[1]["opponent"]),
                    selection=None,
                    page_size=10,
                ),
            ]
        )
    table_output  # noqa: B018
    return


@app.cell
def _(trained):
    if trained is None:
        curves_output = mo.md("No curves yet.")
    else:
        log = trained[0].log
        curves_output = mo.vstack(
            [
                mo.md("### Curves of this training"),
                *curve_charts(curve_frames(log.episodes, log.metrics)),
            ]
        )
    curves_output  # noqa: B018
    return


@app.cell
def _(trained):
    run_name = mo.ui.text(placeholder="my-first-run", label="Run name")
    save_button = mo.ui.run_button(label="Save this run")
    mo.vstack(
        [
            mo.md(
                "### Save this run\n\nWrites the run to `data/runs/<name>`. "
                "Nothing is written before you press the button."
            ),
            mo.hstack([run_name, save_button], justify="start"),
        ]
    )
    return run_name, save_button


@app.cell
def _(run_name, save_button, trained):
    save_ok = False
    if trained is None:
        save_output = mo.md("Train first, then save.")
    elif not save_button.value:
        save_output = mo.md("Not saved.")
    else:
        save_ok, save_message = save_trained(RUNS_DIR, run_name.value, *trained)
        save_output = mo.callout(mo.md(save_message), kind="success" if save_ok else "danger")
    save_output  # noqa: B018
    return (save_ok,)


@app.cell
def _(save_ok):
    save_ok  # noqa: B018 (read, so that the list of runs is made again after a save)
    runs = saved_runs(RUNS_DIR)
    run_picker = mo.ui.dropdown(options=runs, value=runs[-1] if runs else None, label="Saved run")
    mo.vstack(
        [
            mo.md("## 4. Load a saved run"),
            run_picker if runs else mo.md(f"No saved runs in `{RUNS_DIR}`."),
        ]
    )
    return (run_picker,)


@app.cell
def _(run_picker):
    if run_picker.value is None:
        loaded_output = mo.md("Nothing to load.")
    else:
        loaded_config, loaded_frames, loaded_rows, loaded_error = load_saved(
            RUNS_DIR, run_picker.value
        )
        if loaded_error:
            loaded_output = mo.callout(mo.md(loaded_error), kind="danger")
        else:
            loaded_output = mo.vstack(
                [
                    mo.md(
                        f"Run `{run_picker.value}`: `{loaded_config['opponent']}`, "
                        f"{loaded_config['steps']} steps."
                    ),
                    mo.ui.table(loaded_rows, selection=None, page_size=10),
                    *curve_charts(loaded_frames),
                ]
            )
    loaded_output  # noqa: B018
    return


if __name__ == "__main__":
    app.run()
