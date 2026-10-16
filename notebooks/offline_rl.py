# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "marimo",
#     "altair",
#     "polars",
#     "pyarrow",
#     "torch>=2.2",
#     "sb3-contrib>=2.3",
#     "quack-rl",
# ]
#
# [tool.uv.sources]
# quack-rl = { path = "..", editable = true }
# ///

import marimo

__generated_with = "0.25.1"
app = marimo.App(width="medium", app_title="Offline RL")

with app.setup:
    # The offline RL path in one notebook: bot games as a dataset (issue #89), masked behaviour
    # cloning on it (issue #90), and the win rate of the trained policy against bots.
    #
    # Reactivity: every UI element lives in its own cell, every output cell reads `.value` of the
    # elements it needs, nothing is mutated and no state is kept between cells. Light outputs
    # update on every change. The heavy steps (build, train, live games) run behind a run button.
    # Nothing is written to `data/`: a build and a trained run go to a temporary folder.
    import csv
    import tempfile
    from pathlib import Path

    import altair as alt
    import marimo as mo
    import polars as pl

    from quack_rl.engine import action_names
    from quack_rl.rl import PolicyBot, evaluate, vector_names
    from quack_rl.rl.dataset import DEFAULT_BOTS, write_dataset
    from quack_rl.rl.finetune import finetune_online
    from quack_rl.rl.offline import load_offline_data, train_offline_run
    from quack_rl.rl.replay_dqn import train_dqn
    from quack_rl.rules import load_ruleset

    ROOT = Path(__file__).resolve().parent.parent
    SAMPLE = ROOT / "tests" / "fixtures" / "dataset" / "sample.parquet"
    ANALYSIS = ROOT / "docs" / "analysis" / "2026-10-offline-rl-first-run"
    RULES = "v1.1"
    OBS_DIM = len(vector_names(load_ruleset(RULES)))
    ACTIONS = action_names(load_ruleset(RULES))
    BUILD_LIVE = "build live"
    LOAD_SAMPLE = "load the committed sample"
    BOT_CHOICES = (*DEFAULT_BOTS, "draw20-pts1-points", "draw10-pts4-blue", "draw20-pts6-green")
    OPPONENTS = ("draw20-pts4-green", "random", "draw20-pts1-points")
    COMMITTED_POLICY = "offline-bc-1"
    COLUMNS = ["episode", "step", "action", "reward", "bot", "opponent", "seat"]


@app.function
def load_dataset(source: str, bots: list[str], games: int, seed: int, clicked: bool) -> dict:
    """Build a dataset (source `build live`, only after a click) or take the committed sample.

    Return {"path", "frame", "message"}. `path` and `frame` are None and `message` says why
    when there is nothing to show yet or the data is not usable."""
    import pyarrow.parquet as pq

    none = {"path": None, "frame": None}
    if source == BUILD_LIVE:
        if not bots:
            return {**none, "message": "Select at least one bot to build a dataset."}
        if not clicked:
            return {
                **none,
                "message": f"Press **Build dataset** to play {games} games with "
                f"{len(bots)} bot(s) (seed {seed}).",
            }
        path = Path(tempfile.mkdtemp(prefix="quack-offline-dataset-")) / "dataset.parquet"
        try:
            write_dataset(path, bots, games, seed, RULES)
        except ValueError as err:
            return {**none, "message": f"The dataset could not be built: {err}"}
    else:
        path = SAMPLE
        if not path.is_file():
            return {**none, "message": f"The committed sample `{path.name}` is missing."}
    try:
        load_offline_data(path, OBS_DIM)  # the check of the layout: obs has OBS_DIM values
    except (ValueError, FileNotFoundError) as err:
        return {**none, "message": f"This dataset cannot be used for training: {err}"}
    frame = pl.from_arrow(pq.read_table(path, columns=COLUMNS))
    return {"path": path, "frame": frame, "message": ""}


@app.function
def bot_shares(frame: pl.DataFrame | None) -> pl.DataFrame:
    """Games and share of games per recorded bot (a game counts for the bot of its seat)."""
    if frame is None:
        return pl.DataFrame({"bot": [], "games": [], "share": []})
    per_bot = frame.group_by("bot").agg(pl.col("episode").n_unique().alias("games"))
    total = frame["episode"].n_unique()
    return per_bot.with_columns((pl.col("games") / total).round(3).alias("share")).sort(
        ["games", "bot"], descending=[True, False]
    )


@app.function
def episode_table(frame: pl.DataFrame | None, number: int) -> pl.DataFrame:
    """The decisions of game `number`: decision number, action name, reward."""
    columns = {"decision": [], "action": [], "reward": []}
    if frame is None:
        return pl.DataFrame(columns)
    rows = frame.filter(pl.col("episode") == number).sort("step")
    if rows.is_empty():
        return pl.DataFrame(columns)
    return pl.DataFrame(
        {
            "decision": (rows["step"] + 1).to_list(),
            "action": [ACTIONS[a] for a in rows["action"].to_list()],
            "reward": rows["reward"].to_list(),
        }
    )


@app.function
def dataset_numbers(frame: pl.DataFrame | None) -> tuple[int, int]:
    """(games, steps) of a dataset frame."""
    if frame is None:
        return 0, 0
    return frame["episode"].n_unique(), frame.height


@app.function
def run_training(dataset: dict, steps: int, seed: int, clicked: bool) -> dict:
    """Train on the dataset after a click. Return {"status", "run_dir", "metrics", "message"}.

    status is `idle` (no click), `nodata` (click, but no dataset yet) or `done`."""
    result = {"status": "idle", "run_dir": None, "metrics": None, "message": ""}
    if not clicked:
        return {**result, "message": f"Press **Train** to train for {steps} gradient steps."}
    if dataset["path"] is None:
        return {
            **result,
            "status": "nodata",
            "message": "There is no dataset yet. Build or load one in section 1 first.",
        }
    runs_dir = Path(tempfile.mkdtemp(prefix="quack-offline-run-"))
    train_offline_run(
        dataset["path"], "notebook-run", runs_dir, seed=seed, steps=steps, rules=RULES,
        log_every=max(1, steps // 20),
    )  # fmt: skip
    run_dir = runs_dir / "notebook-run"
    with (run_dir / "metrics.csv").open() as f:
        rows = [{k: float(v) for k, v in row.items()} for row in csv.DictReader(f)]
    return {**result, "status": "done", "run_dir": run_dir, "metrics": pl.DataFrame(rows)}


@app.function
def committed_result() -> dict:
    """The committed 500-game result of the first run: {"rows", "headline", "message"}."""
    summary = ANALYSIS / "tournament-p1-summary.csv"
    result = ANALYSIS / "result.json"
    if not summary.is_file() or not result.is_file():
        return {
            "rows": None,
            "message": f"The committed result is missing: expected `{summary.name}` and "
            f"`{result.name}` in `{ANALYSIS.relative_to(ROOT)}`.",
        }
    import json

    with summary.open() as f:
        rows = [
            {
                "opponent": r["p2"],
                "games": int(r["games"]),
                "wins": int(r["p1_wins"]),
                "draws": int(r["draws"]),
                "losses": int(r["p1_losses"]),
                "win_rate": float(r["p1_win_rate"]),
            }
            for r in csv.DictReader(f)
            if r["p1"] == COMMITTED_POLICY
        ]
    headline = json.loads(result.read_text())["policy_p1"]["win_rate"]
    return {"rows": rows, "headline": headline, "message": ""}


@app.function
def run_live(training: dict, games: int, seed: int, clicked: bool) -> dict:
    """Play the trained policy against the three opponents after a click.

    Return {"status", "table", "message"}; status is `idle`, `notrained` or `done`."""
    if not clicked:
        return {
            "status": "idle",
            "table": None,
            "message": f"Press **Play** to play {games} games against each opponent.",
        }
    if training["run_dir"] is None:
        return {
            "status": "notrained",
            "table": None,
            "message": "There is no trained policy yet. Train one in section 2 first.",
        }
    bot = PolicyBot.from_run(training["run_dir"], RULES)
    rows = []
    for name in OPPONENTS:
        r = evaluate(bot.policy, name, RULES, games, seed)
        rows.append(
            {
                "opponent": name,
                "games": r.games,
                "wins": r.wins,
                "draws": r.draws,
                "losses": r.losses,
                "win_rate": round(r.win_rate, 3),
            }
        )
    return {"status": "done", "table": pl.DataFrame(rows), "message": ""}


@app.function
def run_finetune(
    training: dict, steps: int, opponent: str, games: int, seed: int, clicked: bool
) -> dict:
    """Continue the section 2 policy online with PPO after a click; play it before and after.

    Return {"status", "table", "message"}; status is `idle`, `notrained` or `done`. The
    fine-tuned run goes to a temporary folder. Both policies play `games` games against the
    chosen opponent with the same seed."""
    if not clicked:
        return {
            "status": "idle",
            "table": None,
            "message": f"Press **Fine-tune** to train {steps} steps against `{opponent}`, then "
            f"play {games} games before and after.",
        }
    if training["run_dir"] is None:
        return {
            "status": "notrained",
            "table": None,
            "message": "There is no trained policy yet. Train one in section 2 first.",
        }
    out_dir = Path(tempfile.mkdtemp(prefix="quack-finetune-")) / "run"
    finetune_online(training["run_dir"], out_dir, steps, opponent, seed=seed, rules=RULES)
    rows = []
    for label, folder in (("before", training["run_dir"]), ("after", out_dir)):
        r = evaluate(PolicyBot.from_run(folder, RULES).policy, opponent, RULES, games, seed)
        rows.append(
            {
                "policy": label,
                "opponent": opponent,
                "games": r.games,
                "wins": r.wins,
                "draws": r.draws,
                "losses": r.losses,
                "win_rate": round(r.win_rate, 3),
            }
        )
    return {"status": "done", "table": pl.DataFrame(rows), "message": ""}


@app.function
def run_dqn(
    dataset: dict, offline_steps: int, online_steps: int, opponent: str, games: int, seed: int,
    clicked: bool,
) -> dict:  # fmt: skip
    """Train the replay-buffer DQN on the section 1 dataset after a click; play it twice.

    Return {"status", "losses", "counts", "table", "message"}; status is `idle` (no click),
    `nodata` (click, but no usable dataset) or `done`. The table has one row per phase
    (`after offline`, `after online`) and opponent, played with `evaluate`."""
    result = {"status": "idle", "losses": None, "counts": None, "table": None, "message": ""}
    if not clicked:
        return {
            **result,
            "message": f"Press **Train DQN** to take {offline_steps} offline and {online_steps} "
            f"online steps (online games against `{opponent}`), then play {games} games per "
            "opponent after each phase.",
        }
    if dataset["path"] is None:
        return {
            **result,
            "status": "nodata",
            "message": "There is no dataset yet. Build or load one in section 1 first.",
        }
    snapshots = {}

    def play(policy) -> list[dict]:
        rows = []
        for name in OPPONENTS:
            r = evaluate(policy, name, RULES, games, seed)
            rows.append(
                {
                    "opponent": name,
                    "games": r.games,
                    "wins": r.wins,
                    "draws": r.draws,
                    "losses": r.losses,
                    "win_rate": round(r.win_rate, 3),
                }
            )
        return rows

    try:
        _, rows, policy = train_dqn(
            dataset["path"], opponent, offline_steps, online_steps, seed, RULES,
            after_offline=lambda p: snapshots.update(offline=play(p)),
        )  # fmt: skip
    except ValueError as err:
        return {**result, "status": "nodata", "message": f"This dataset cannot be used: {err}"}
    table = [
        {"phase": label, **row}
        for label, played in (
            ("after offline", snapshots["offline"]),
            ("after online", play(policy)),
        )
        for row in played
    ]
    last = rows[-1] if rows else {"offline_count": 0, "online_count": 0}
    return {
        **result,
        "status": "done",
        "losses": pl.DataFrame(rows),
        "counts": {"offline": last["offline_count"], "online": last["online_count"]},
        "table": pl.DataFrame(table),
    }


@app.cell
def _():
    mo.md("""
    # Offline RL: from bot games to a policy

    Section 1 builds or loads a dataset of bot games, section 2 trains a policy on it, section 3
    plays that policy against bots. Every control updates what depends on it by itself.
    """)
    return


@app.cell
def _():
    mo.md("""
    ## 1. Dataset
    """)
    return


@app.cell
def _():
    mo.md("""
    A dataset is a list of games that bots played. One **step** is one decision of one bot: the
    state it saw, the action it chose and the reward. The **share per bot** is the share of the
    games in which that bot was the recorded seat. The source "build live" plays new games (press
    the button); "load the committed sample" reads a small ready-made file. The bot choice, the
    games and the seed only apply to "build live".
    """)
    return


@app.cell
def _():
    source = mo.ui.dropdown([LOAD_SAMPLE, BUILD_LIVE], value=LOAD_SAMPLE, label="Source")
    return (source,)


@app.cell
def _():
    bots = mo.ui.multiselect(list(BOT_CHOICES), value=list(DEFAULT_BOTS), label="Bots (build live)")
    return (bots,)


@app.cell
def _():
    games = mo.ui.slider(1, 50, 1, value=20, label="Games (build live)")
    return (games,)


@app.cell
def _():
    seed = mo.ui.number(0, 10_000, 1, value=0, label="Seed")
    return (seed,)


@app.cell
def _():
    build_button = mo.ui.run_button(label="Build dataset")
    return (build_button,)


@app.cell
def _(bots, build_button, games, seed, source):
    mo.vstack([mo.hstack([source, seed, games], justify="start"), bots, build_button])
    return


@app.cell
def _(bots, build_button, games, seed, source):
    dataset = load_dataset(
        source.value, list(bots.value), int(games.value), int(seed.value), build_button.value
    )
    return (dataset,)


@app.cell
def _(dataset):
    shares = bot_shares(dataset["frame"])
    n_games, n_steps = dataset_numbers(dataset["frame"])
    note = mo.callout(mo.md(dataset["message"]), kind="info") if dataset["message"] else None
    mo.vstack(
        [
            note,
            mo.hstack(
                [mo.stat(n_games, label="Games"), mo.stat(n_steps, label="Steps (rows)")],
                justify="start",
            ),
            mo.md("Share of games per bot"),
            shares,
        ]
    )
    return


@app.cell
def _():
    episode_pick = mo.ui.number(0, 49, 1, value=0, label="Example game (0-based)")
    episode_pick
    return (episode_pick,)


@app.cell
def _(dataset, episode_pick):
    episode = episode_table(dataset["frame"], int(episode_pick.value))
    mo.vstack(
        [
            mo.md(
                f"Game {int(episode_pick.value)}: {episode.height} decisions"
                if episode.height
                else f"No game number {int(episode_pick.value)} in this dataset."
            ),
            episode,
        ]
    )
    return


@app.cell
def _():
    mo.md("""
    ## 2. Training
    """)
    return


@app.cell
def _():
    mo.md("""
    The policy learns to copy the bots: for each state it is shown the action the bot chose, and
    the **loss** says how far its choice is from the bot's (lower is closer; it counts only the
    legal actions). One gradient step looks at a batch of 256 steps. The curve is the mean loss
    over each short stretch of training. The trained run goes to a temporary folder, not to
    `data/runs/`. After you change a setting above, press **Train** again.
    """)
    return


@app.cell
def _():
    steps = mo.ui.slider(50, 2000, 50, value=300, label="Gradient steps")
    return (steps,)


@app.cell
def _():
    train_button = mo.ui.run_button(label="Train")
    return (train_button,)


@app.cell
def _(steps, train_button):
    mo.hstack([steps, train_button], justify="start")
    return


@app.cell
def _(steps):
    budget_shown = int(steps.value)
    mo.md(f"Step budget: **{budget_shown}** gradient steps")
    return


@app.cell
def _(dataset, seed, steps, train_button):
    training = run_training(dataset, int(steps.value), int(seed.value), train_button.value)
    return (training,)


@app.cell
def _(training):
    mo.stop(training["status"] != "done", mo.callout(mo.md(training["message"]), kind="info"))
    loss_chart = (
        alt.Chart(training["metrics"])
        .mark_line(point=True)
        .encode(x=alt.X("step:Q", title="gradient step"), y=alt.Y("loss:Q", title="loss"))
        .properties(title="Loss per logged step", height=240)
    )
    loss_chart
    return


@app.cell
def _():
    mo.md("""
    ## 3. Tournament
    """)
    return


@app.cell
def _():
    mo.md("""
    The **win rate** is wins divided by games; a draw is not a win. Part (a) is the result that
    is committed in the repo: the policy of the first full run, 500 games per opponent, playing
    first. Part (b) plays the policy you trained above. 20 to 50 games is a rough number
    (a small sample, the win rate can be off by 10 points or more); 500 games is the committed
    result.
    """)
    return


@app.cell
def _():
    committed = committed_result()
    if committed["message"]:
        committed_view = mo.callout(mo.md(committed["message"]), kind="warn")
    else:
        committed_view = mo.vstack(
            [
                mo.md(
                    f"(a) Committed result of `{COMMITTED_POLICY}`, 500 games per opponent, "
                    "policy first"
                ),
                pl.DataFrame(committed["rows"]),
            ]
        )
    committed_view
    return


@app.cell
def _():
    live_games = mo.ui.slider(1, 50, 1, value=20, label="Games per opponent")
    return (live_games,)


@app.cell
def _():
    live_button = mo.ui.run_button(label="Play")
    return (live_button,)


@app.cell
def _(live_button, live_games):
    mo.vstack(
        [
            mo.md("(b) Live games with your trained policy"),
            mo.hstack([live_games, live_button], justify="start"),
        ]
    )
    return


@app.cell
def _(live_button, live_games, seed, training):
    live = run_live(training, int(live_games.value), int(seed.value), live_button.value)
    return (live,)


@app.cell
def _(live):
    mo.stop(live["status"] != "done", mo.callout(mo.md(live["message"]), kind="info"))
    live["table"]
    return


@app.cell
def _():
    mo.md("""
    ## 4. Online fine-tuning
    """)
    return


@app.cell
def _():
    mo.md("""
    Behaviour cloning trained only the actor (the part that picks actions). The value head, the
    critic that PPO needs to judge states, is still untrained, so the first PPO updates can make
    the policy worse before they make it better. A few thousand steps is a rough check, not a
    training run: the result may be better, equal or worse, and it is shown either way. The
    fine-tuned run goes to a temporary folder, not to `data/runs/`.
    """)
    return


@app.cell
def _():
    ft_steps = mo.ui.slider(128, 5000, 128, value=512, label="PPO steps")
    return (ft_steps,)


@app.cell
def _():
    ft_opponent = mo.ui.dropdown(list(OPPONENTS), value=OPPONENTS[0], label="Opponent")
    return (ft_opponent,)


@app.cell
def _():
    ft_games = mo.ui.slider(1, 50, 1, value=20, label="Games")
    return (ft_games,)


@app.cell
def _():
    ft_button = mo.ui.run_button(label="Fine-tune")
    return (ft_button,)


@app.cell
def _(ft_button, ft_games, ft_opponent, ft_steps):
    mo.hstack([ft_steps, ft_opponent, ft_games, ft_button], justify="start")
    return


@app.cell
def _(ft_steps):
    ft_budget_shown = int(ft_steps.value)
    mo.md(f"PPO step budget: **{ft_budget_shown}** steps")
    return


@app.cell
def _(ft_button, ft_games, ft_opponent, ft_steps, seed, training):
    finetune = run_finetune(
        training,
        int(ft_steps.value),
        str(ft_opponent.value),
        int(ft_games.value),
        int(seed.value),
        ft_button.value,
    )
    return (finetune,)


@app.cell
def _(finetune):
    mo.stop(finetune["status"] != "done", mo.callout(mo.md(finetune["message"]), kind="info"))
    finetune["table"]
    return


@app.cell
def _():
    mo.md("""
    ## 5. Replay buffer and DQN
    """)
    return


@app.cell
def _():
    mo.md("""
    A **replay buffer** is a store of past steps (state, action, reward, next state) that the
    learner draws random batches from. Here it starts with the dataset of section 1 (the
    **offline part**, never overwritten) and gets new games against a bot (the **online part**).
    Phase 1 learns from the offline part only; phase 2 plays games, adds each step to the online
    part and learns from the whole buffer. The **Q-value** is the agent's estimate of the total
    reward it still gets after an action; the **loss** is how far that estimate is from reward
    plus the discounted estimate of the next state (lower is closer). Plain Q-learning on bot
    data can overrate actions the bots never took, and no conservative penalty is used here, so
    a weak result is an expected finding, and it is shown as it is.
    """)
    return


@app.cell
def _():
    dq_offline = mo.ui.slider(50, 2000, 50, value=300, label="Offline steps")
    return (dq_offline,)


@app.cell
def _():
    dq_online = mo.ui.slider(50, 2000, 50, value=300, label="Online steps")
    return (dq_online,)


@app.cell
def _():
    dq_opponent = mo.ui.dropdown(list(OPPONENTS), value=OPPONENTS[0], label="Opponent (online)")
    return (dq_opponent,)


@app.cell
def _():
    dq_games = mo.ui.slider(1, 50, 1, value=20, label="Games")
    return (dq_games,)


@app.cell
def _():
    dq_button = mo.ui.run_button(label="Train DQN")
    return (dq_button,)


@app.cell
def _(dq_button, dq_games, dq_offline, dq_online, dq_opponent):
    mo.hstack([dq_offline, dq_online, dq_opponent, dq_games, dq_button], justify="start")
    return


@app.cell
def _(dq_offline, dq_online):
    dq_budget_shown = (int(dq_offline.value), int(dq_online.value))
    mo.md(f"Budget: **{dq_budget_shown[0]}** offline and **{dq_budget_shown[1]}** online steps")
    return (dq_budget_shown,)


@app.cell
def _(dataset, dq_button, dq_games, dq_offline, dq_online, dq_opponent, seed):
    dqn = run_dqn(
        dataset,
        int(dq_offline.value),
        int(dq_online.value),
        str(dq_opponent.value),
        int(dq_games.value),
        int(seed.value),
        dq_button.value,
    )
    return (dqn,)


@app.cell
def _(dqn):
    mo.stop(dqn["status"] != "done", mo.callout(mo.md(dqn["message"]), kind="info"))
    dq_chart = (
        alt.Chart(dqn["losses"])
        .mark_line()
        .encode(
            x=alt.X("step:Q", title="gradient step"),
            y=alt.Y("loss:Q", title="loss"),
            color=alt.Color("phase:N", title="phase"),
        )
        .properties(title="Loss per gradient step", height=240)
    )
    mo.vstack(
        [
            mo.hstack(
                [
                    mo.stat(dqn["counts"]["offline"], label="Buffer: offline part"),
                    mo.stat(dqn["counts"]["online"], label="Buffer: online part"),
                ],
                justify="start",
            ),
            dq_chart,
            mo.md("Games per opponent after phase 1 (offline) and after phase 2 (online)"),
            dqn["table"],
        ]
    )
    return (dq_chart,)


if __name__ == "__main__":
    app.run()
