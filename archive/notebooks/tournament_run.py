import marimo

__generated_with = "0.25.1"
app = marimo.App(width="medium", app_title="Tournament run")

with app.setup:
    # Reads only config.json, results.csv and seats.parquet of one run folder (see README.md,
    # sections "Tournament run folder" and "`seats.parquet`"). No game records.
    import json
    import re
    from pathlib import Path

    import altair as alt
    import marimo as mo
    import polars as pl

    from quack_rl.report import wilson
    from quack_rl.tournament import SEAT_CHECK_PREFIX

    # resolved from the notebook file, not from the working directory
    RUNS_DIR = Path(__file__).resolve().parent.parent / "data" / "tournaments"
    NEEDED_FILES = ("config.json", "results.csv", "seats.parquet")


@app.function
def missing_files(folder: Path) -> list[str]:
    """The files of NEEDED_FILES that `folder` lacks, in that order."""
    return [name for name in NEEDED_FILES if not (folder / name).is_file()]


@app.function
def run_folders(root: Path) -> list[Path]:
    """Subfolders of `root` that hold all of NEEDED_FILES, sorted by name (oldest first)."""
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir() and not missing_files(p))


@app.function
def no_folder_message(root: Path) -> str:
    """Markdown text for the case that no run folder qualifies."""
    files = ", ".join(NEEDED_FILES)
    if not root.is_dir():
        lines = [
            f"**No run folder to show.** The folder `{root}` does not exist "
            f"(`data/` is not committed), so a run folder with {files} is missing.",
            f"\nMissing files: {files}.",
        ]
    else:
        lines = [f"**No run folder to show.** No subfolder of `{root}` holds {files}."]
        subfolders = sorted(q for q in root.iterdir() if q.is_dir())
        if not subfolders:
            lines.append(f"\nMissing files: {files}.")
        for p in subfolders:
            lines.append(f"- `{p.name}` lacks {', '.join(missing_files(p))}")
    lines.append("\nRun folders from before the `seats.parquet` file (issue #43) do not show up.")
    return "\n".join(lines)


@app.function
def read_results(path: Path) -> pl.DataFrame:
    """results.csv with the name columns read as text."""
    text = ("pairing", "p1", "p2", "winner", "sweep_value")
    return pl.read_csv(path, schema_overrides={c: pl.String for c in text})


@app.function
def without_seat_checks(rows: pl.DataFrame) -> pl.DataFrame:
    """Leave out the seat check rows, unless every row is one (the rule of `quack-rl report`)."""
    is_check = pl.col("pairing").cast(pl.String).str.starts_with(SEAT_CHECK_PREFIX)
    rest = rows.filter(~is_check)
    return rows if rest.height == 0 else rest


@app.function
def ranking(results: pl.DataFrame) -> pl.DataFrame:
    """[bot, win_rate, low, high, avg_points, games] from results.csv rows.

    Each row gives one seat-game to the p1 bot and one to the p2 bot; a draw counts as half
    a win. Sweep values are pooled. Sorted like `quack-rl report`.
    """
    rows = without_seat_checks(results)
    seat_games = pl.concat(
        [
            rows.select(
                bot=pl.col(seat).cast(pl.String),
                score=pl.when(pl.col("winner") == seat)
                .then(1.0)
                .when(pl.col("winner") == "draw")
                .then(0.5)
                .otherwise(0.0),
                points=pl.col(f"{seat}_points").cast(pl.Float64),
            )
            for seat in ("p1", "p2")
        ]
    )
    per_bot = seat_games.group_by("bot").agg(
        score=pl.col("score").sum(), avg_points=pl.col("points").mean(), games=pl.len()
    )
    out = []
    for r in per_bot.iter_rows(named=True):
        low, high = wilson(r["score"], r["games"])
        out.append(
            {
                "bot": r["bot"],
                "win_rate": r["score"] / r["games"],
                "low": low,
                "high": high,
                "avg_points": r["avg_points"],
                "games": r["games"],
            }
        )
    out.sort(key=lambda r: (-r["win_rate"], -r["avg_points"], r["bot"]))
    schema = {
        "bot": pl.String,
        "win_rate": pl.Float64,
        "low": pl.Float64,
        "high": pl.Float64,
        "avg_points": pl.Float64,
        "games": pl.Int64,
    }
    return pl.DataFrame(out, schema=schema)


@app.function
def end_bags(seats: pl.DataFrame) -> pl.DataFrame:
    """[bot, <chip ids>..., games]: mean end count of each chip per bot, chip ids in file order."""
    bag_columns = [c for c in seats.columns if c.startswith("bag_")]
    rows = without_seat_checks(seats)
    return (
        rows.group_by("bot")
        .agg(
            *(pl.col(c).cast(pl.Float64).mean().alias(c.removeprefix("bag_")) for c in bag_columns),
            games=pl.len().cast(pl.Int64),
        )
        .sort("bot")
    )


@app.function
def per_bot_rounds(seats: pl.DataFrame) -> pl.DataFrame:
    """[bot, round, money, points, games], one row per bot and round: means over seat-games."""
    rounds = sorted(int(m[1]) for c in seats.columns if (m := re.fullmatch(r"money_r(\d+)", c)))
    schema = {
        "bot": pl.String,
        "round": pl.Int64,
        "money": pl.Float64,
        "points": pl.Float64,
        "games": pl.Int64,
    }
    if not rounds:
        return pl.DataFrame(schema=schema)
    rows = without_seat_checks(seats)
    long = pl.concat(
        [
            rows.select(
                bot=pl.col("bot").cast(pl.String),
                round=pl.lit(k, pl.Int64),
                money=pl.col(f"money_r{k}").cast(pl.Float64),
                points=pl.col(f"points_r{k}").cast(pl.Float64),
            )
            for k in rounds
        ]
    )
    return (
        long.group_by("bot", "round")
        .agg(
            money=pl.col("money").mean(),
            points=pl.col("points").mean(),
            games=pl.len().cast(pl.Int64),
        )
        .sort("bot", "round")
        .select(list(schema))
    )


@app.function
def round_chart(rounds: pl.DataFrame, bots: list[str], column: str, title: str) -> alt.Chart:
    """Line chart of `column` of per_bot_rounds over the rounds, one line per selected bot."""
    data = rounds.filter(pl.col("bot").is_in(pl.Series(list(bots), dtype=pl.String).implode()))
    return (
        alt.Chart(data, title=title)
        .mark_line(point=True)
        .encode(
            x=alt.X("round:O", title="round"),
            y=alt.Y(f"{column}:Q", title=title),
            color=alt.Color("bot:N", title="bot"),
            tooltip=[
                alt.Tooltip("bot:N"),
                alt.Tooltip("round:O"),
                alt.Tooltip(f"{column}:Q", format=".2f"),
                alt.Tooltip("games:Q"),
            ],
        )
        .properties(width="container", height=320)
    )


@app.cell(hide_code=True)
def _():
    mo.md("""
    # Tournament run

    Ranking, end bags, and money and points per round of one run folder. Seat check games are
    left out unless the run has only those; sweep values are pooled per bot.
    """)
    return


@app.cell(hide_code=True)
def _():
    _cli_folder = mo.cli_args().get("run-folder")
    _found = run_folders(RUNS_DIR)
    _options = {p.name: str(p) for p in _found}
    _default = _found[-1].name if _found else None
    if _cli_folder:
        _path = Path(str(_cli_folder)).expanduser().resolve()
        _default = f"{_path.name} (--run-folder)"
        _options = {_default: str(_path), **_options}
    folder_picker = mo.ui.dropdown(options=_options, value=_default, label="Run folder")
    folder_picker  # noqa: B018 (marimo shows the last expression)
    return (folder_picker,)


@app.cell(hide_code=True)
def _(folder_picker):
    mo.stop(
        not folder_picker.value,
        mo.callout(mo.md(no_folder_message(RUNS_DIR)), kind="warn"),
    )
    folder = Path(folder_picker.value)
    _missing = missing_files(folder)
    _note = "" if folder.is_dir() else " (the folder does not exist)"
    mo.stop(
        bool(_missing),
        mo.callout(
            mo.md(f"Run folder `{folder}` lacks {', '.join(_missing)}{_note}."),
            kind="warn",
        ),
    )
    config = json.loads((folder / "config.json").read_text(encoding="utf-8"))
    results = read_results(folder / "results.csv")
    seats = pl.read_parquet(folder / "seats.parquet")
    return config, folder, results, seats


@app.cell(hide_code=True)
def _(config, folder):
    mo.md(f"""
    ## Run `{config.get("name", folder.name)}`

    Ruleset: `{config.get("rules", "-")}` · games per pairing: {config.get("games", "-")}
    · folder: `{folder.name}`
    """)
    return


@app.cell(hide_code=True)
def _(results):
    rank = ranking(results)
    _rows = [
        {
            "bot": r["bot"],
            "win rate [95% interval]": (
                f"{100 * r['win_rate']:.1f}% [{100 * r['low']:.1f}-{100 * r['high']:.1f}%]"
            ),
            "avg end points": round(r["avg_points"], 1),
            "games": r["games"],
        }
        for r in rank.iter_rows(named=True)
    ]
    mo.vstack(
        [
            mo.md(
                "### Ranking\n\nSorted by win rate (a draw is half a win), then average end points."
            ),
            mo.ui.table(_rows, selection=None, pagination=False) if _rows else mo.md("No games."),
        ]
    )
    return (rank,)


@app.cell(hide_code=True)
def _(rank, seats):
    _order = {bot: i for i, bot in enumerate(rank["bot"].to_list())}
    _bags = end_bags(seats)
    _bags = (
        _bags.with_columns(pl.col(c).round(2) for c in _bags.columns if c not in ("bot", "games"))
        .with_columns(_rank=pl.col("bot").replace_strict(_order, default=len(_order)))
        .sort("_rank", "bot")
        .drop("_rank")
    )
    mo.vstack(
        [
            mo.md("### End bag\n\nAverage count of each chip a bot owns at game end."),
            mo.ui.table(_bags, selection=None, pagination=False),
        ]
    )
    return


@app.cell(hide_code=True)
def _(rank, seats):
    rounds = per_bot_rounds(seats)
    _in_rounds = set(rounds["bot"].to_list())
    _bots = [b for b in rank["bot"].to_list() if b in _in_rounds]
    _bots += sorted(_in_rounds - set(_bots))
    bot_select = mo.ui.multiselect(options=_bots, value=_bots, label="Bots in the charts")
    bot_select  # noqa: B018 (marimo shows the last expression)
    return bot_select, rounds


@app.cell(hide_code=True)
def _(bot_select, rounds):
    mo.vstack(
        [
            round_chart(
                rounds, bot_select.value, "money", "Average money at the start of the shop phase"
            ),
            round_chart(rounds, bot_select.value, "points", "Average points total"),
        ]
    )
    return


if __name__ == "__main__":
    app.run()
