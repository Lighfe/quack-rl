"""Tests for the live and final evaluator (`quack_rl.rl.live_eval`) and the greedy and sampled
play modes of `PolicyBot` and `OfflinePolicy`."""

import csv
import json
import os
import subprocess
import sys
import threading

import numpy as np
import pytest

from quack_rl.rl.experiment import EVAL_OPPONENTS
from quack_rl.rl.live_eval import EVAL_COLUMNS, complete_checkpoints

JOIN_TIMEOUT = 300.0
POLL = 0.05


# --- no rl group ------------------------------------------------------------------------------


def test_module_imports_without_torch():
    code = (
        "import sys, quack_rl.rl.live_eval; "
        "assert 'torch' not in sys.modules and 'sb3_contrib' not in sys.modules"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_help_names_all_options():
    done = subprocess.run(
        [sys.executable, "-m", "quack_rl.rl.live_eval", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0
    for option in ("--games", "--seed", "--modes", "--final", "--poll"):
        assert option in done.stdout, option


def test_complete_checkpoints_skip_temp_files(tmp_path):
    assert complete_checkpoints(tmp_path) == []
    folder = tmp_path / "checkpoints"
    folder.mkdir()
    for name in ("step_2048.zip", "step_1024.zip", "step_3072.tmp.zip", "epoch_2.tmp.pt", "x.pt"):
        (folder / name).write_bytes(b"")
    assert [n for n, _ in complete_checkpoints(tmp_path)] == [1024, 2048]


def test_watch_run_unknown_mode_raises(tmp_path):
    from quack_rl.rl.live_eval import watch_run

    with pytest.raises(ValueError, match="mode"):
        watch_run(tmp_path, games=1, seed=0, modes=("best",))


def test_watch_run_with_done_and_no_checkpoint_returns_without_rows(tmp_path):
    from quack_rl.rl.live_eval import watch_run

    (tmp_path / "config.json").write_text(json.dumps({"rules": "v2.3"}))
    (tmp_path / "done.json").write_text("{}")
    watch_run(tmp_path, games=1, seed=0, modes=("greedy",), poll_seconds=POLL)
    assert not (tmp_path / "eval.csv").exists()


def test_watch_run_waits_on_an_empty_folder(tmp_path):
    from quack_rl.rl.live_eval import watch_run

    run = tmp_path / "run"  # not there yet
    errors: list[BaseException] = []
    thread = start(watch_run, errors, run, games=1, seed=0, modes=("greedy",), poll_seconds=POLL)
    thread.join(0.5)
    assert thread.is_alive() and not errors  # waiting, no error
    run.mkdir()
    (run / "checkpoints").mkdir()
    thread.join(0.3)
    assert thread.is_alive() and not errors
    (run / "config.json").write_text(json.dumps({"rules": "v2.3"}))
    (run / "done.json").write_text("{}")
    thread.join(JOIN_TIMEOUT)
    assert not thread.is_alive() and not errors
    assert not (run / "eval.csv").exists()


def test_final_eval_without_checkpoint_raises(tmp_path):
    from quack_rl.rl.live_eval import final_eval

    (tmp_path / "checkpoints").mkdir()
    (tmp_path / "checkpoints" / "step_1024.tmp.zip").write_bytes(b"")
    with pytest.raises(FileNotFoundError):
        final_eval(tmp_path, games=1)


# --- helpers ------------------------------------------------------------------------------------


def start(target, errors, *args, **kwargs) -> threading.Thread:
    def run() -> None:
        try:
            target(*args, **kwargs)
        except BaseException as err:  # noqa: BLE001 - reported to the test
            errors.append(err)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


def read_rows(path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        assert tuple(reader.fieldnames or ()) == EVAL_COLUMNS
        return list(reader)


def keys(rows) -> list[tuple[int, str, str]]:
    return [(int(r["step"]), r["opponent"], r["mode"]) for r in rows]


def wait_for(predicate, thread, errors, timeout: float = JOIN_TIMEOUT) -> None:
    import time

    end = time.monotonic() + timeout
    while time.monotonic() < end:
        assert not errors, errors
        if predicate():
            return
        assert thread.is_alive()
        time.sleep(POLL)
    raise AssertionError("timed out")


def env_states(n: int):
    """`n` (state, seat, legal) triples from random games."""
    from quack_rl.bots import RandomBot
    from quack_rl.engine import action_names, legal_actions
    from quack_rl.rl import QuackEnv

    out = []
    rng = np.random.default_rng(0)
    seed = 0
    while len(out) < n:
        env = QuackEnv(opponent=RandomBot(seed))
        env.reset(seed=seed)
        names = action_names(env.rs)
        done = False
        while not done and len(out) < n:
            legal = legal_actions(env.state, env.rs, env.agent_seat)
            out.append((env.state, env.agent_seat, legal))
            _, _, done, _, _ = env.step(names.index(str(rng.choice(legal))))
        seed += 1
    return out


# --- PPO ----------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ppo_models():
    pytest.importorskip("sb3_contrib")
    from sb3_contrib import MaskablePPO

    from quack_rl.rl import QuackEnv

    return [
        MaskablePPO("MlpPolicy", QuackEnv(), device="cpu", seed=s, policy_kwargs={"net_arch": [8]})
        for s in range(3)
    ]


def save_ppo(model, path) -> None:
    """Save like `ppo_run`: into a temporary file, then rename, so a matching file is complete."""
    tmp = path.with_name(path.name.replace(".zip", ".tmp.zip"))
    model.save(str(tmp))
    os.replace(tmp, path)


def save_bc(net, path) -> None:
    import torch

    tmp = path.with_name(path.name.replace(".pt", ".tmp.pt"))
    torch.save(net.state_dict(), tmp)
    os.replace(tmp, path)


def ppo_run(folder, models, names) -> None:
    (folder / "checkpoints").mkdir(parents=True, exist_ok=True)
    (folder / "config.json").write_text(json.dumps({"rules": "v2.3"}))
    for model, name in zip(models, names, strict=True):
        save_ppo(model, folder / "checkpoints" / name)


def test_policy_bot_greedy_matches_predict(ppo_models):
    from quack_rl.engine import action_names
    from quack_rl.rl.encode import action_mask, observe, vectorize
    from quack_rl.rl.policy_bot import PolicyBot
    from quack_rl.rules import load_ruleset

    rs = load_ruleset("v2.3")
    names = action_names(rs)
    model = ppo_models[0]
    bot = PolicyBot(model, rs)
    assert bot.params == {"deterministic": True}
    for state, seat, legal in env_states(40):
        obs = vectorize(observe(state, rs, seat), rs)
        mask = np.asarray(action_mask(state, rs, seat), dtype=bool)
        action, _ = model.predict(obs, action_masks=mask, deterministic=True)
        assert bot.choose(state, seat, legal) == names[int(action)]


def test_policy_bot_modes(ppo_models):
    from quack_rl.rl.policy_bot import PolicyBot

    with pytest.raises(ValueError, match="mode"):
        PolicyBot(ppo_models[0], "v2.3", mode="best")
    bot = PolicyBot(ppo_models[0], "v2.3", mode="sampled", seed=7)
    assert bot.params == {"deterministic": False, "seed": 7}
    states = env_states(60)
    first = [bot.choose(*s) for s in states]
    again = PolicyBot(ppo_models[0], "v2.3", mode="sampled", seed=7)
    assert [again.choose(*s) for s in states] == first
    assert all(choice in legal for choice, (_, _, legal) in zip(first, states, strict=True))
    greedy = PolicyBot(ppo_models[0], "v2.3")
    assert first != [greedy.choose(*s) for s in states]  # sampling does not always pick the top


@pytest.mark.slow
def test_watch_run_ppo_follows_the_run(tmp_path, ppo_models):
    from quack_rl.rl.live_eval import watch_run

    ppo_run(tmp_path, ppo_models[:2], ["step_1024.zip", "step_2048.zip"])
    (tmp_path / "checkpoints" / "step_4096.tmp.zip").write_bytes(b"not a model")
    errors: list[BaseException] = []
    thread = start(
        watch_run, errors, tmp_path, games=1, seed=0, modes=("greedy",), poll_seconds=POLL
    )
    csv_path = tmp_path / "eval.csv"
    n = len(EVAL_OPPONENTS)
    wait_for(lambda: csv_path.is_file() and len(read_rows(csv_path)) == 2 * n, thread, errors)
    thread.join(0.3)
    assert thread.is_alive()  # no done.json: it keeps watching
    save_ppo(ppo_models[2], tmp_path / "checkpoints" / "step_3072.zip")
    (tmp_path / "done.json").write_text("{}")
    thread.join(JOIN_TIMEOUT)
    assert not thread.is_alive() and not errors, errors
    rows = read_rows(csv_path)
    assert keys(rows) == [
        (step, opp, "greedy") for step in (1024, 2048, 3072) for opp in EVAL_OPPONENTS
    ]
    for row in rows:
        assert int(row["games"]) == 1
        assert int(row["wins"]) + int(row["draws"]) + int(row["losses"]) == 1
        assert 0.0 <= float(row["ci_low"]) <= float(row["win_rate"]) <= float(row["ci_high"])

    # a restart writes no duplicate rows (and a lost row set of a checkpoint is made again)
    lines = csv_path.read_text().splitlines()
    csv_path.write_text("\n".join(lines[: 1 + 2 * n]) + "\n")  # as if step 3072 never got rows
    watch_run(tmp_path, games=1, seed=0, modes=("greedy",), poll_seconds=POLL)
    assert keys(read_rows(csv_path)) == keys(rows)
    watch_run(tmp_path, games=1, seed=0, modes=("greedy",), poll_seconds=POLL)
    assert keys(read_rows(csv_path)) == keys(rows)
    assert len(set(keys(rows))) == len(rows)


@pytest.mark.slow
def test_sampled_mode_same_seed_same_counts(tmp_path, ppo_models):
    from quack_rl.rl.live_eval import watch_run

    counts = []
    for name in ("a", "b"):
        run = tmp_path / name
        ppo_run(run, ppo_models[:1], ["step_1024.zip"])
        (run / "done.json").write_text("{}")
        watch_run(run, games=2, seed=5, modes=("sampled",), poll_seconds=POLL)
        rows = read_rows(run / "eval.csv")
        assert keys(rows) == [(1024, opp, "sampled") for opp in EVAL_OPPONENTS]
        counts.append([(r["wins"], r["draws"], r["losses"]) for r in rows])
    assert counts[0] == counts[1]


@pytest.mark.slow
def test_final_eval_one_row_per_opponent_and_mode(tmp_path, ppo_models):
    from quack_rl.rl.live_eval import final_eval

    ppo_run(tmp_path, ppo_models[:2], ["step_1024.zip", "step_2048.zip"])
    (tmp_path / "checkpoints" / "step_9999.tmp.zip").write_bytes(b"not a model")
    (tmp_path / "final_eval.csv").write_text("old\n")
    path = final_eval(tmp_path, games=1, seed=3)
    assert path == tmp_path / "final_eval.csv"
    rows = read_rows(path)
    assert keys(rows) == [
        (2048, opp, mode) for opp in EVAL_OPPONENTS for mode in ("greedy", "sampled")
    ]
    assert not (tmp_path / "eval.csv").exists()


# --- BC -----------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def bc_nets():
    torch = pytest.importorskip("torch")
    from quack_rl.rl import QuackEnv
    from quack_rl.rl.offline import make_mlp

    env = QuackEnv()
    obs_dim, n_actions = env.observation_space.shape[0], int(env.action_space.n)
    nets = []
    for s in range(2):
        torch.manual_seed(s)
        nets.append(make_mlp(obs_dim, n_actions, 8))
    return obs_dim, n_actions, nets


def test_offline_policy_greedy_matches_argmax_and_modes(bc_nets):
    import torch

    from quack_rl.engine import action_names
    from quack_rl.rl.encode import action_mask, observe, vectorize
    from quack_rl.rl.offline import OfflinePolicy, masked
    from quack_rl.rules import load_ruleset

    rs = load_ruleset("v2.3")
    names = action_names(rs)
    net = bc_nets[2][0]
    policy = OfflinePolicy(net, rs)
    assert policy.params == {"deterministic": True}
    states = env_states(60)
    for state, seat, legal in states:
        obs = vectorize(observe(state, rs, seat), rs)
        mask = torch.as_tensor(np.asarray(action_mask(state, rs, seat), dtype=np.float32))
        with torch.no_grad():
            scores = net(torch.as_tensor(np.asarray(obs, dtype=np.float32))[None])[0]
        assert policy.choose(state, seat, legal) == names[int(masked(scores, mask).argmax())]
    with pytest.raises(ValueError, match="mode"):
        OfflinePolicy(net, rs, mode="best")
    sampled = OfflinePolicy(net, rs, mode="sampled", seed=4)
    assert sampled.params == {"deterministic": False, "seed": 4}
    first = [sampled.choose(*s) for s in states]
    again = OfflinePolicy(net, rs, mode="sampled", seed=4)
    assert [again.choose(*s) for s in states] == first
    assert all(choice in legal for choice, (_, _, legal) in zip(first, states, strict=True))
    assert first != [policy.choose(*s) for s in states]  # sampling does not always pick the top


@pytest.mark.slow
def test_watch_run_bc_folder(tmp_path, bc_nets):

    from quack_rl.rl.live_eval import watch_run

    obs_dim, n_actions, nets = bc_nets
    folder = tmp_path / "checkpoints"
    folder.mkdir()
    config = {"rules": "v2.3", "obs_dim": obs_dim, "n_actions": n_actions, "config": {"hidden": 8}}
    (tmp_path / "config.json").write_text(json.dumps(config))
    save_bc(nets[0], folder / "epoch_1.pt")
    (folder / "epoch_2.tmp.pt").write_bytes(b"not a state dict")
    errors: list[BaseException] = []
    thread = start(
        watch_run, errors, tmp_path, games=1, seed=0, modes=("greedy",), poll_seconds=POLL
    )
    csv_path = tmp_path / "eval.csv"
    n = len(EVAL_OPPONENTS)
    wait_for(lambda: csv_path.is_file() and len(read_rows(csv_path)) == n, thread, errors)
    save_bc(nets[1], folder / "epoch_2.pt")
    (tmp_path / "done.json").write_text("{}")
    thread.join(JOIN_TIMEOUT)
    assert not thread.is_alive() and not errors, errors
    assert keys(read_rows(csv_path)) == [
        (step, opp, "greedy") for step in (1, 2) for opp in EVAL_OPPONENTS
    ]
    watch_run(tmp_path, games=1, seed=0, modes=("greedy",), poll_seconds=POLL)  # restart
    assert len(read_rows(csv_path)) == 2 * n
