"""Tests for the logic of the marimo notebook notebooks/rl_env.py (issue #53)."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from quack_rl.cli.render import render_step
from quack_rl.engine import Phase, StepResult, action_names
from quack_rl.record import SeatInfo, read_games, verify_game, verify_seed
from quack_rl.rl import vector_names
from quack_rl.rules import load_ruleset

NOTEBOOK = Path(__file__).resolve().parent.parent / "notebooks" / "rl_env.py"


@pytest.fixture(scope="module")
def nb():
    spec = importlib.util.spec_from_file_location("rl_env_notebook", NOTEBOOK)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cells_1_and_2_create_reset_and_step(nb):
    env = nb.make_env()
    obs, info = env.reset(seed=0)

    named = nb.named_observation(env, obs)
    assert list(named) == vector_names(env.rs)
    assert set(nb.legal_names(env, info["action_mask"])) <= set(action_names(env.rs))
    legal = nb.legal_names(env, info["action_mask"])
    assert legal

    obs2, reward, done, mask = nb.step_named(env, legal[0])
    assert list(nb.named_observation(env, obs2)) == vector_names(env.rs)
    assert reward in (0.0, 1.0, -1.0)
    assert done is False
    assert mask.shape == info["action_mask"].shape
    assert nb.legal_names(env, mask)  # a real decision follows


def test_random_steps_reach_the_end_with_a_zero_mask(nb):
    env = nb.make_env()
    _, info = env.reset(seed=1)
    mask, done, reward = info["action_mask"], False, 0.0
    while not done:
        _, reward, done, mask = nb.step_named(env, nb.legal_names(env, mask)[0])
    assert reward in (-1.0, 0.0, 1.0)
    assert nb.legal_names(env, mask) == []


def test_train_installed_is_a_bool(nb):
    assert isinstance(nb.train_installed(), bool)


def _fake_evals(with_random: bool) -> dict[str, dict]:
    def one(wins, draws, losses):
        return {"games": wins + draws + losses, "wins": wins, "draws": draws, "losses": losses}

    out = {
        "baseline_random": one(1, 0, 3),
        "baseline_untrained": one(2, 0, 2),
        "trained_sampled": one(3, 0, 1),
        "trained_greedy": one(4, 0, 0),
    }
    if with_random:
        out.update({k + "_vs_random": v for k, v in list(out.items())})
    return out


def test_resolve_opponent_accepts_the_two_presets_and_a_typed_name(nb):
    assert nb.resolve_opponent("random", "") == ("random", None)
    assert nb.resolve_opponent("draw20-pts4-blue", "") == ("draw20-pts4-blue", None)
    assert nb.resolve_opponent(nb.OTHER_OPTION, " draw10-pts6-green ") == (
        "draw10-pts6-green",
        None,
    )


@pytest.mark.parametrize(
    "choice,typed",
    [(None, ""), ("nonsense", ""), ("other (type a name below)", "nonsense"),
     ("other (type a name below)", ""), ("other (type a name below)", "   ")],
)  # fmt: skip
def test_resolve_opponent_bad_names_give_a_message(nb, choice, typed):
    name, message = nb.resolve_opponent(choice, typed)
    assert name is None
    assert message


def test_eval_rows_show_wins_draws_losses_against_both_opponents(nb):
    rows = nb.eval_rows(_fake_evals(True), "draw20-pts4-blue")
    assert len(rows) == 8
    assert {r["against"] for r in rows} == {"draw20-pts4-blue", "RandomBot"}
    first = rows[0]
    assert (first["wins"], first["draws"], first["losses"]) == (1, 0, 3)
    assert {"agent", "against", "games", "wins", "draws", "losses"} == set(first)


def test_eval_rows_do_not_repeat_randombot_when_the_opponent_is_random(nb):
    rows = nb.eval_rows(_fake_evals(False), "random")
    assert len(rows) == 4
    assert {r["against"] for r in rows} == {"random"}


def _episodes(n: int) -> list[dict]:
    return [
        {
            "episode": i + 1,
            "timestep": 40 * (i + 1),
            "result": "win" if i % 2 == 0 else "loss",
            "points_own": 10.0,
            "points_opponent": 5.0,
            "explosions_own": i % 3,
            "decisions": 40,
        }
        for i in range(n)
    ]


def test_curve_frames_have_the_four_curves(nb):
    metrics = [
        {"timestep": 128, "policy_gradient_loss": -0.1, "value_loss": 0.5, "entropy_loss": -1.0}
    ]
    frames = nb.curve_frames(_episodes(6), metrics, window=2)
    assert set(frames) == {"win_rate", "points", "explosions", "losses"}
    assert frames["win_rate"]["win_rate"].to_list() == [1.0, 0.5, 0.5, 0.5, 0.5, 0.5]
    assert set(frames["points"]["who"]) == {"points_own", "points_opponent"}
    assert frames["explosions"].height == 6
    assert set(frames["losses"]["loss"]) == {
        "policy_gradient_loss",
        "value_loss",
        "entropy_loss",
    }
    assert len(nb.curve_charts(frames)) == 4


def test_curve_frames_work_without_rows(nb):
    frames = nb.curve_frames([], [])
    assert all(f.height == 0 for f in frames.values())
    assert len(nb.curve_charts(frames)) == 4


def test_saved_runs_and_load_saved_without_a_runs_folder(nb, tmp_path):
    runs = tmp_path / "runs"
    assert nb.saved_runs(runs) == []
    config, frames, rows, message = nb.load_saved(runs, "nope")
    assert config is frames is rows is None
    assert "nope" in message
    assert not runs.exists()


def test_load_saved_reports_a_broken_run(nb, tmp_path):
    (tmp_path / "bad").mkdir()
    (tmp_path / "bad" / "config.json").write_text("{not json")
    assert nb.saved_runs(tmp_path) == ["bad"]
    *_, message = nb.load_saved(tmp_path, "bad")
    assert message and "bad" in message
    *_, message = nb.load_saved(tmp_path, "../x")
    assert message


def test_save_trained_refuses_bad_names_and_writes_nothing(nb, tmp_path):
    runs = tmp_path / "runs"
    for name in ("", "  ", "../x", "a/b", "a\\b"):
        ok, message = nb.save_trained(runs, name, object(), {})
        assert ok is False and message
    assert not runs.exists()


def test_opening_the_notebook_writes_no_file(nb, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    nb.app.run()
    assert list(tmp_path.iterdir()) == []


def test_training_install_message_is_the_uv_command(nb):
    assert nb.INSTALL_COMMAND == "uv sync --group train"


@pytest.fixture(scope="module")
def trained(nb):
    pytest.importorskip("sb3_contrib", reason="needs the train group: uv sync --group train")
    return nb.run_training(256, "random", eval_games=4)


def test_training_writes_nothing_and_saving_round_trips(nb, trained, tmp_path):
    result, config = trained
    runs = tmp_path / "runs"
    assert result.games_played >= 1
    assert not runs.exists()  # training itself wrote nothing

    ok, message = nb.save_trained(runs, "first", result, config)
    assert ok, message
    assert nb.saved_runs(runs) == ["first"]
    before = (runs / "first" / "config.json").read_text()

    ok, message = nb.save_trained(runs, "first", result, {**config, "steps": 1})
    assert ok is False and "exists" in message
    assert (runs / "first" / "config.json").read_text() == before

    loaded_config, frames, rows, error = nb.load_saved(runs, "first")
    assert error is None
    assert loaded_config["opponent"] == "random"
    assert len(rows) == 4  # the opponent is random: no RandomBot block
    assert frames["win_rate"].height == result.games_played


def test_load_saved_reports_malformed_csv_values(nb, trained, tmp_path):
    result, config = trained
    ok, message = nb.save_trained(tmp_path, "garbled", result, config)
    assert ok, message
    episodes = tmp_path / "garbled" / "episodes.csv"
    header, *lines = episodes.read_text().splitlines()
    assert "points_own" in header.split(",")
    column = header.split(",").index("points_own")
    cells = lines[0].split(",")
    cells[column] = "garbage"
    episodes.write_text("\n".join([header, ",".join(cells), *lines[1:]]) + "\n")
    config_, frames, rows, message = nb.load_saved(tmp_path, "garbled")
    assert config_ is frames is rows is None
    assert message and "garbled" in message


def test_training_against_a_bot_has_the_randombot_rows(nb):
    pytest.importorskip("sb3_contrib", reason="needs the train group: uv sync --group train")
    from quack_rl.rl.runs import eval_dict

    result, config = nb.run_training(128, "draw20-pts4-blue", eval_games=2)
    assert len(nb.eval_rows(eval_dict(result), config["opponent"])) == 8


class FakeModel:
    """Stands in for a MaskablePPO model: `predict` takes the first (or last) legal action."""

    def predict(self, observation, action_masks, deterministic):
        legal = np.flatnonzero(action_masks)
        return (legal[0] if deterministic else legal[-1]), None


@pytest.mark.parametrize("deterministic", [True, False])
def test_play_traced_game_returns_a_whole_game_and_writes_nothing(
    nb, tmp_path, monkeypatch, deterministic
):
    monkeypatch.chdir(tmp_path)
    trace = nb.play_traced_game(FakeModel(), "random", "v1.1", 3, deterministic)
    assert trace and all(isinstance(r, StepResult) for r in trace)
    assert [r.n for r in trace] == list(range(1, len(trace) + 1))
    assert trace[-1].state.phase is Phase.GAME_OVER
    assert list(tmp_path.iterdir()) == []


def test_play_traced_game_is_reproducible_by_seed(nb):
    one = nb.play_traced_game(FakeModel(), "random", "v1.1", 5, True)
    two = nb.play_traced_game(FakeModel(), "random", "v1.1", 5, True)
    other = nb.play_traced_game(FakeModel(), "random", "v1.1", 6, True)
    assert [r.chance for r in one] == [r.chance for r in two]
    assert [r.chance for r in one] != [r.chance for r in other]


def test_trace_text_uses_render_step_for_every_step(nb):
    trace = nb.play_traced_game(FakeModel(), "random", "v1.1", 1, True)
    rs = load_ruleset("v1.1")
    text = nb.trace_text(trace, rs)
    assert text.count("p1:") >= len(trace)
    assert render_step(trace[0], rs) in text


@pytest.mark.parametrize("opponent", ["random", "draw20-pts4-blue"])
def test_exported_game_reads_back_and_verifies(nb, tmp_path, opponent):
    trace = nb.play_traced_game(FakeModel(), opponent, "v1.1", 11, False)
    path = tmp_path / "game.jsonl"
    nb.export_game(trace, path, "v1.1", 11, "my-run", opponent=opponent)
    (game,) = list(read_games(path))
    assert game.header.mode == "sim"
    assert game.header.seed == 11
    assert game.header.seats["p1"] == SeatInfo(kind="bot", name="my-run")
    assert game.header.seats["p2"].name == opponent
    assert len(game.steps) == len(trace)
    assert game.footer is not None
    assert verify_game(game) == []
    assert verify_seed(game) == []


def test_export_to_folder_writes_exactly_one_file_and_refuses_an_empty_folder(nb, tmp_path):
    trace = nb.play_traced_game(FakeModel(), "random", "v1.1", 2, True)
    folder = tmp_path / "out"
    ok, message = nb.export_to_folder("  ", trace, "v1.1", 2, "r")
    assert ok is False and message
    ok, message = nb.export_to_folder(str(folder), trace, "v1.1", 2, "r")
    assert ok, message
    assert len(list(folder.iterdir())) == 1
    assert str(next(folder.iterdir())) in message


def test_playing_games_without_export_writes_no_file(nb, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for seed in range(3):
        nb.play_traced_game(FakeModel(), "random", "v1.1", seed, True)
    assert list(tmp_path.iterdir()) == []


def test_replay_source_without_a_trained_model_or_run(nb, tmp_path):
    model, opponent, message = nb.replay_source(None, tmp_path, None)
    assert model is None and opponent is None and message
    model, opponent, message = nb.replay_source(None, tmp_path, "missing")
    assert model is None and message and "missing" in message


def test_agent_name_prefers_the_typed_name(nb):
    assert nb.agent_name(" mine ", None) == "mine"
    assert nb.agent_name("", "saved-run") == "saved-run"
    assert nb.agent_name("", None) == "trained"
