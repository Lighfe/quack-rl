"""Tests for the marimo notebook notebooks/offline_rl.py (issue #91).

Headless, through `app.run(defs=...)`: a def given to `app.run` replaces the cell that makes
that variable, so a test hands in a UI element with the value a user would set (a run button
gets its click through `_update(True)`) and reads the outputs of the same run. No second
trigger is needed, which is what a live update means. The tests are light: at most 3 games,
at most 20 training steps, one live game per opponent.
"""

import csv
import importlib.util
import re
from pathlib import Path

import marimo as mo
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

pytest.importorskip("sb3_contrib", reason="needs the train group: uv sync --group train")

ROOT = Path(__file__).resolve().parent.parent
NOTEBOOK = ROOT / "notebooks" / "offline_rl.py"
SUMMARY = ROOT / "docs" / "analysis" / "2026-10-offline-rl-first-run" / "tournament-p1-summary.csv"


@pytest.fixture(scope="module")
def nb():
    spec = importlib.util.spec_from_file_location("offline_rl_notebook", NOTEBOOK)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def click():
    button = mo.ui.run_button()
    button._update(True)
    return button


def build_defs(nb, bots=None, games=3, seed=0):
    """The elements for `build live` after a click on the build button."""
    return {
        "source": mo.ui.dropdown([nb.LOAD_SAMPLE, nb.BUILD_LIVE], value=nb.BUILD_LIVE),
        "bots": mo.ui.multiselect(
            list(nb.BOT_CHOICES), value=list(bots or ["draw20-pts4-blue", "random"])
        ),
        "games": mo.ui.slider(1, 50, 1, value=games),
        "seed": mo.ui.number(0, 10_000, 1, value=seed),
        "build_button": click(),
    }


def steps_element(steps):
    return mo.ui.slider(1, 2000, 1, value=steps)  # the real slider starts at 50


def run(nb, **defs):
    outputs, names = nb.app.run(defs=defs)
    return outputs, names


def test_every_cell_runs_with_the_defaults(nb):
    outputs, d = run(nb)
    assert d["dataset"]["path"] == nb.SAMPLE
    assert d["n_games"] == 20 and d["n_steps"] == 1649
    assert d["budget_shown"] == 300
    # nothing heavy runs before a click: a hint and no result
    assert d["training"]["status"] == "idle" and d["training"]["run_dir"] is None
    assert d["live"]["status"] == "idle" and d["live"]["table"] is None
    assert "Press" in d["training"]["message"] and "Press" in d["live"]["message"]
    assert d["committed"]["message"] == ""


def test_new_bot_selection_changes_the_shares_table(nb):
    _, a = run(nb, **build_defs(nb, bots=["draw20-pts4-blue"]))
    _, b = run(nb, **build_defs(nb, bots=["random", "draw20-pts4-green"]))
    assert a["shares"]["bot"].to_list() == ["draw20-pts4-blue"]
    assert a["shares"]["share"].to_list() == [1.0]
    assert set(b["shares"]["bot"].to_list()) <= {"random", "draw20-pts4-green"}
    assert a["shares"].to_dicts() != b["shares"].to_dicts()


def test_source_games_and_seed_change_the_dataset(nb):
    _, sample = run(nb)
    _, built = run(nb, **build_defs(nb, games=3, seed=0))
    assert built["n_games"] == 3 and sample["n_games"] == 20
    assert built["n_steps"] != sample["n_steps"]
    _, more = run(nb, **build_defs(nb, games=2, seed=0))
    assert more["n_games"] == 2
    _, other_seed = run(nb, **build_defs(nb, games=3, seed=1))
    assert other_seed["n_steps"] != built["n_steps"] or (
        other_seed["episode"].to_dicts() != built["episode"].to_dicts()
    )


def test_build_needs_the_click(nb):
    defs = build_defs(nb)
    defs["build_button"] = mo.ui.run_button()
    _, d = run(nb, **defs)
    assert d["dataset"]["frame"] is None and "Press **Build dataset**" in d["dataset"]["message"]
    assert d["n_games"] == 0


def test_episode_choice_changes_the_episode_table(nb):
    _, first = run(nb, episode_pick=mo.ui.number(0, 49, 1, value=0))
    _, second = run(nb, episode_pick=mo.ui.number(0, 49, 1, value=1))
    assert first["episode"].columns == ["decision", "action", "reward"]
    assert first["episode"].height > 0 and second["episode"].height > 0
    assert first["episode"].to_dicts() != second["episode"].to_dicts()
    assert first["episode"]["decision"].to_list()[0] == 1


def test_new_step_budget_changes_the_shown_budget(nb):
    _, a = run(nb, steps=mo.ui.slider(50, 2000, 50, value=100))
    _, b = run(nb, steps=mo.ui.slider(50, 2000, 50, value=450))
    assert (a["budget_shown"], b["budget_shown"]) == (100, 450)


def test_train_click_gives_the_loss_in_the_same_run(nb):
    _, d = run(nb, steps=steps_element(20), train_button=click())
    training = d["training"]
    assert training["status"] == "done"
    metrics = training["metrics"]
    assert metrics.columns == ["step", "loss", "accuracy"] and metrics.height >= 2
    assert metrics["step"].to_list()[-1] == 20
    run_dir = training["run_dir"]
    assert (run_dir / "model.zip").is_file()
    assert (ROOT / "data" / "runs") not in run_dir.parents
    assert d["loss_chart"] is not None


def test_new_step_budget_changes_the_training(nb):
    _, a = run(nb, steps=steps_element(10), train_button=click())
    _, b = run(nb, steps=steps_element(20), train_button=click())
    assert a["training"]["metrics"]["step"].to_list()[-1] == 10
    assert b["training"]["metrics"]["step"].to_list()[-1] == 20


def test_live_games_click_and_games_slider(nb):
    base = {"steps": steps_element(20), "train_button": click()}
    _, one = run(nb, **base, live_games=mo.ui.slider(1, 50, 1, value=1), live_button=click())
    _, two = run(nb, **base, live_games=mo.ui.slider(1, 50, 1, value=2), live_button=click())
    for d, games in ((one, 1), (two, 2)):
        table = d["live"]["table"]
        assert d["live"]["status"] == "done"
        assert table["opponent"].to_list() == list(nb.OPPONENTS)
        assert table["games"].to_list() == [games] * 3
        for row in table.to_dicts():
            assert row["wins"] + row["draws"] + row["losses"] == games
            assert row["win_rate"] == round(row["wins"] / games, 3)
    assert one["live"]["table"]["games"].to_list() != two["live"]["table"]["games"].to_list()


def test_committed_result_matches_the_csv(nb):
    _, d = run(nb)
    rows = {r["opponent"]: r for r in d["committed"]["rows"]}
    with SUMMARY.open() as f:
        csv_rows = {r["p2"]: r for r in csv.DictReader(f) if r["p1"] == nb.COMMITTED_POLICY}
    assert set(rows) == set(nb.OPPONENTS) == set(csv_rows)
    for name, row in rows.items():
        assert row["win_rate"] == float(csv_rows[name]["p1_win_rate"])
        assert row["wins"] == int(csv_rows[name]["p1_wins"]) and row["games"] == 500
    assert (
        rows["draw20-pts4-green"]["win_rate"] == 0.472 and rows["draw20-pts4-green"]["wins"] == 236
    )
    assert rows["random"]["win_rate"] == 1.0
    assert rows["draw20-pts1-points"]["win_rate"] == 0.894
    assert d["committed"]["headline"] == 0.472


def test_empty_bot_selection_shows_a_message(nb):
    defs = build_defs(nb)
    defs["bots"] = mo.ui.multiselect(list(nb.BOT_CHOICES), value=[])
    _, d = run(nb, **defs)
    assert "at least one bot" in d["dataset"]["message"]
    assert d["dataset"]["path"] is None and d["n_steps"] == 0


def test_missing_committed_result_shows_a_message(nb, monkeypatch, tmp_path):
    # `app.run` builds its own namespace, so the paths are patched on the functions' module
    monkeypatch.setattr(nb, "ANALYSIS", ROOT / "docs" / "analysis" / "does-not-exist")
    result = nb.committed_result()
    assert result["rows"] is None and "missing" in result["message"]


def test_dataset_with_a_wrong_obs_length_shows_a_message(nb, monkeypatch, tmp_path):
    bad = tmp_path / "bad.parquet"
    pq.write_table(
        pa.table(
            {
                "obs": pa.array([[0.0] * 10], pa.list_(pa.float32())),
                "action_mask": pa.array([[1] * 15], pa.list_(pa.int8())),
                "action": pa.array([0], pa.int16()),
            }
        ),
        bad,
    )
    monkeypatch.setattr(nb, "SAMPLE", bad)
    dataset = nb.load_dataset(nb.LOAD_SAMPLE, [], 20, 0, False)
    assert dataset["path"] is None and dataset["frame"] is None
    assert "cannot be used" in dataset["message"] and "848" in dataset["message"]
    training = nb.run_training(dataset, 20, 0, True)
    assert training["status"] == "nodata"
    assert nb.bot_shares(dataset["frame"]).height == 0
    assert nb.episode_table(dataset["frame"], 0).height == 0


def test_missing_sample_shows_a_message(nb, monkeypatch, tmp_path):
    monkeypatch.setattr(nb, "SAMPLE", tmp_path / "none.parquet")
    dataset = nb.load_dataset(nb.LOAD_SAMPLE, [], 20, 0, False)
    assert dataset["path"] is None and "missing" in dataset["message"]


def test_train_before_a_dataset_exists_shows_a_message(nb):
    defs = build_defs(nb)
    defs["build_button"] = mo.ui.run_button()  # the dataset is not built yet
    _, d = run(nb, **defs, train_button=click())
    assert d["training"]["status"] == "nodata"
    assert "no dataset yet" in d["training"]["message"]
    _, e = run(nb, live_button=click())
    assert e["live"]["status"] == "notrained" and "no trained policy" in e["live"]["message"]


def test_every_section_heading_has_a_text_cell(nb):
    outputs, _ = run(nb)
    html = [getattr(o, "text", "") for o in outputs if o is not None]
    headings = [i for i, h in enumerate(html) if "<h2" in h]
    assert len(headings) == 3
    for i in headings:
        nxt = html[i + 1]
        assert "<h2" not in nxt and len(re.sub(r"<[^>]+>", "", nxt).strip()) > 40


def test_design_rules_of_the_source():
    source = NOTEBOOK.read_text()
    assert "mo.state" not in source and "set_state" not in source
    assert "mo.stop(" in source and "mo.ui.run_button(" in source
