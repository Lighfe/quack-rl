# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "marimo",
#     "altair",
#     "polars",
#     "quack-rl",
# ]
#
# [tool.uv.sources]
# quack-rl = { path = "..", editable = true }
# ///

import marimo

__generated_with = "0.25.2"
app = marimo.App(width="full", app_title="RL monitor")

with app.setup:
    # The monitor of one experiment (issue #294): the training numbers of each seed over the
    # steps (PPO) or epochs (BC), and the win rate per opponent over the checkpoints, next to an
    # optional baseline experiment.
    #
    # Live updates: the `refresh` element ticks every 30 s; the cells that list the experiments
    # and load the runs read `refresh.value`, so they run again on each tick without a click.
    # The picked experiments are kept in `mo.state`, so a tick that rebuilds the dropdowns keeps
    # the choice. The data is read only through `quack_rl.rl.monitor`; nothing is written.
    #
    # Start: uv run --group rl --group monitor marimo run notebooks/rl_monitor.py
    # Other choices: ... marimo run notebooks/rl_monitor.py -- --root <folder>
    #     --experiment <id> --baseline <id>   (the defaults of the dropdowns)
    from pathlib import Path

    import altair as alt
    import marimo as mo
    import polars as pl

    from quack_rl.rl.monitor import experiment_dirs, load_experiment

    alt.data_transformers.disable_max_rows()

    PPO_METRICS = ["mean_reward", "entropy", "value_loss", "explained_variance"]
    BC_METRICS = ["loss", "entropy"]
    NO_DATA = "no data yet"
    GROUPS = ["experiment", "baseline"]


@app.cell
def _():
    mo.md("""
    # RL experiment monitor
    """)
    return


@app.cell
def _():
    refresh = mo.ui.refresh(
        options=["10s", "30s", "1m", "5m"], default_interval="30s", label="Reload every"
    )
    root_input = mo.ui.text(
        value=str(mo.cli_args().get("root") or "data/experiments"),
        label="Experiments root",
        full_width=True,
    )
    mo.hstack([root_input, refresh], justify="start", align="end")
    return refresh, root_input


@app.cell
def _():
    get_picked, set_picked = mo.state(mo.cli_args().get("experiment"))
    get_base, set_base = mo.state(mo.cli_args().get("baseline"))
    return get_base, get_picked, set_base, set_picked


@app.cell
def _(refresh, root_input):
    refresh.value  # a tick lists the experiment folders again
    root = Path(root_input.value)
    names = [path.name for path in experiment_dirs(root)]
    return names, root


@app.cell
def _(get_base, get_picked, names, set_base, set_picked):
    picked_now = get_picked() if get_picked() in names else (names[-1] if names else None)
    base_now = get_base() if get_base() in names else None
    exp_dropdown = mo.ui.dropdown(
        options=names, value=picked_now, label="Experiment", on_change=set_picked
    )
    base_dropdown = mo.ui.dropdown(
        options=names, value=base_now, label="Baseline (optional)", on_change=set_base
    )
    mo.hstack([exp_dropdown, base_dropdown], justify="start")
    return base_dropdown, exp_dropdown


@app.cell
def _(base_dropdown, exp_dropdown, refresh, root):
    refresh.value  # a tick reads the run folders again
    picked = {"experiment": exp_dropdown.value, "baseline": base_dropdown.value}
    runs = {group: (load_experiment(root / name) if name else {}) for group, name in picked.items()}
    return picked, runs


@app.cell
def _(picked, runs):
    def status_row(group, seed, run):
        rows = run.train.height + run.evals.height
        last = run.train[run.train.columns[0]].max() if run.train.height else None
        return {
            "group": group,
            "experiment": picked[group],
            "seed": seed,
            "kind": run.kind or "-",
            "done": run.done,
            "training rows": run.train.height,
            "last step / epoch": last,
            "eval rows": run.evals.height,
            "status": "done" if run.done else ("running" if rows else NO_DATA),
        }

    status = [status_row(group, seed, run) for group in GROUPS for seed, run in runs[group].items()]
    status_view = (
        mo.ui.table(status, selection=None, label="Runs")
        if status
        else mo.md(f"**{NO_DATA}** (no experiment with seed folders under the root)")
    )
    status_view
    return


@app.cell
def _(runs):
    def tagged(frame, group, seed):
        return frame.with_columns(pl.lit(group).alias("group"), pl.lit(f"seed{seed}").alias("seed"))

    def long_train(kind):
        metrics, x = (PPO_METRICS, "steps") if kind == "ppo" else (BC_METRICS, "epoch")
        parts = [
            tagged(run.train.select(x, *metrics), group, seed)
            for group in GROUPS
            for seed, run in runs[group].items()
            if run.kind == kind and run.train.height
        ]
        if not parts:
            return pl.DataFrame()
        return pl.concat(parts).unpivot(
            index=[x, "group", "seed"], on=metrics, variable_name="metric", value_name="value"
        )

    train_ppo = long_train("ppo")
    train_bc = long_train("bc")
    evals = pl.concat(
        [
            tagged(run.evals, group, seed)
            for group in GROUPS
            for seed, run in runs[group].items()
            if run.evals.height
        ]
        or [pl.DataFrame()],
        how="diagonal",
    )
    finals = pl.concat(
        [
            tagged(run.final, group, seed)
            for group in GROUPS
            for seed, run in runs[group].items()
            if run.final.height
        ]
        or [pl.DataFrame()],
        how="diagonal",
    )
    return evals, finals, train_bc, train_ppo


@app.cell
def _(train_bc, train_ppo):
    def train_chart(frame, x, title):
        line = (
            alt.Chart(frame)
            .mark_line(point=True)
            .encode(
                x=alt.X(f"{x}:Q", title=x),
                y=alt.Y("value:Q", title=None, scale=alt.Scale(zero=False)),
                color=alt.Color("seed:N"),
                tooltip=[x, "seed", "metric", "value"],
            )
            .properties(width=320, height=150)
        )
        return (
            line.facet(
                row=alt.Row("metric:N", title=None),
                column=alt.Column("group:N", title=None, sort=GROUPS),
            )
            .resolve_scale(y="independent")
            .properties(title=title)
        )

    train_views = []
    if train_ppo.height:
        train_views.append(train_chart(train_ppo, "steps", "PPO training over steps"))
    if train_bc.height:
        train_views.append(train_chart(train_bc, "epoch", "BC loss and entropy per epoch"))
    mo.vstack([mo.md("## Training"), *(train_views or [mo.md(f"**{NO_DATA}**")])])
    return


@app.cell
def _(evals):
    def eval_chart(frame, mode):
        base = alt.Chart(frame).encode(
            x=alt.X("step:Q", title="checkpoint step"),
            color=alt.Color("seed:N"),
        )
        band = base.mark_area(opacity=0.15).encode(
            y=alt.Y("ci_low:Q", title="win rate", scale=alt.Scale(domain=[0, 1])),
            y2="ci_high:Q",
        )
        line = base.mark_line(point=True).encode(
            y=alt.Y("win_rate:Q"),
            tooltip=["step", "seed", "opponent", "games", "win_rate", "ci_low", "ci_high"],
        )
        return (
            alt.layer(band, line, data=frame)
            .properties(width=320, height=150)
            .facet(
                row=alt.Row("opponent:N", title=None),
                column=alt.Column("group:N", title=None, sort=GROUPS),
            )
            .properties(title=f"Win rate per opponent ({mode})")
        )

    eval_views = [
        eval_chart(evals.filter(pl.col("mode") == mode), mode)
        for mode in ["greedy", "sampled"]
        if evals.height and evals.filter(pl.col("mode") == mode).height
    ]
    mo.vstack([mo.md("## Evaluation"), *(eval_views or [mo.md(f"**{NO_DATA}**")])])
    return


@app.cell
def _(finals):
    final_view = (
        mo.ui.table(
            finals.select(
                "group", "seed", "opponent", "mode", "games", "win_rate", "ci_low", "ci_high"
            ).sort("group", "seed", "opponent", "mode"),
            selection=None,
        )
        if finals.height
        else mo.md(f"**{NO_DATA}**")
    )
    mo.vstack([mo.md("## Final evaluation"), final_view])
    return


if __name__ == "__main__":
    app.run()
