"""Tests for training games stored as chance seed and actions (`quack_rl.rl.game_log`)."""

import json

import numpy as np
import pytest

from quack_rl.engine import action_names, legal_actions
from quack_rl.rl.dataset import ARRAYS, Dataset
from quack_rl.rl.game_log import rebuild_dataset
from quack_rl.rl.opponents import make_opponent
from quack_rl.rl.reward import REWARDS
from quack_rl.rl.single_env import QuackEnv


def play_live(seats, reward="win_loss", seed=0, agent="topchip-draw20-pts6", opponent="random"):
    """Play one game per seat with `QuackEnv`; return the rows collected as `build_dataset` does
    and the `games.jsonl` lines of these games."""
    chunks, lines = [], []
    for i, seat in enumerate(seats):
        env = QuackEnv(
            seat=seat,
            opponent=make_opponent(opponent, seed + i),
            reward_fn=REWARDS[reward],
        )
        names = action_names(env.rs)
        bot = make_opponent(agent, seed + i)
        obs, _ = env.reset(seed=seed + i)
        mask = env.action_masks()
        rows = {name: [] for name in ARRAYS}
        done = False
        while not done:
            legal = legal_actions(env.state, env.rs, env.agent_seat)
            action = names.index(bot.choose(env.state, env.agent_seat, legal))
            next_obs, rew, done, _, info = env.step(action)
            assert not info["illegal_action"]
            for name, value in (
                ("obs", obs),
                ("action", action),
                ("reward", rew),
                ("next_obs", next_obs),
                ("terminated", done),
                ("mask", mask),
                ("next_mask", info["action_mask"]),
                ("episode", i),
            ):
                rows[name].append(value)
            obs, mask = next_obs, info["action_mask"]
        chunks.append(rows)
        lines.append(
            {
                "step": 100 * (i + 1),
                "chance_seed": env.chance_seed,
                "agent_seat": env.agent_seat,
                "opponent": f"bot:{opponent}",
                "actions": env.joint_actions,
            }
        )
    dtypes = {
        "obs": np.float32,
        "action": np.int64,
        "reward": np.float32,
        "next_obs": np.float32,
        "terminated": bool,
        "mask": np.int8,
        "next_mask": np.int8,
        "episode": np.int32,
    }
    live = Dataset(
        **{
            name: np.asarray([v for c in chunks for v in c[name]], dtype=dtypes[name])
            for name in ARRAYS
        }
    )
    return live, lines


def write_lines(path, lines):
    path.write_text("".join(json.dumps(line) + "\n" for line in lines))
    return path


def assert_same(a: Dataset, b: Dataset):
    for name in ARRAYS:
        x, y = getattr(a, name), getattr(b, name)
        assert x.dtype == y.dtype, name
        assert x.shape == y.shape, name
        assert np.array_equal(x, y), name


# --- QuackEnv exposes the game ------------------------------------------------------------------


def test_env_exposes_chance_seed_and_joint_actions():
    env = QuackEnv(seat="p2")
    assert env.chance_seed is None and env.joint_actions == []
    env.reset(seed=5)
    seed = env.chance_seed
    assert isinstance(seed, int)
    before = len(env.trace)
    assert len(env.joint_actions) == sum(1 for r in env.trace if r.actions) <= before
    done = False
    while not done:
        _, _, done, _, _ = env.step(int(np.flatnonzero(env.action_masks())[0]))
    actions = env.joint_actions
    assert actions and all(
        len(pair) == 2 and all(isinstance(a, int) for a in pair) for pair in actions
    )
    names = action_names(env.rs)
    # every engine step that took a joint action is one pair, in order
    joints = [r.actions for r in env.trace if r.actions]
    assert [[names[p1], names[p2]] for p1, p2 in actions] == [[j["p1"], j["p2"]] for j in joints]
    # a copy: changing it does not change the env
    actions.append([0, 0])
    assert len(env.joint_actions) == len(actions) - 1
    # same reset seed, same chance seed; the next reset clears the actions
    env.reset(seed=5)
    assert env.chance_seed == seed
    assert len(env.joint_actions) < len(actions) - 1


def test_env_records_the_action_played_for_an_illegal_one():
    env = QuackEnv(seat="p1")
    env.reset(seed=1)
    mask = env.action_masks()
    illegal = int(np.flatnonzero(mask == 0)[0])
    played = int(np.flatnonzero(mask)[0])
    n = len(env.joint_actions)
    _, _, _, _, info = env.step(illegal)
    assert info["illegal_action"]
    assert env.joint_actions[n][0] == played


# --- rebuild_dataset ----------------------------------------------------------------------------


def test_rebuild_matches_live_games_both_seats(tmp_path):
    live, lines = play_live(["p1", "p2", "p2", "p1"])
    assert {line["agent_seat"] for line in lines} == {"p1", "p2"}
    rebuilt = rebuild_dataset(write_lines(tmp_path / "games.jsonl", lines))
    assert_same(rebuilt, live)
    assert rebuilt.terminated.sum() == 4
    assert set(np.unique(rebuilt.episode)) == {0, 1, 2, 3}


def test_rebuild_matches_live_games_margin_reward(tmp_path):
    live, lines = play_live(["p1", "p2"], reward="margin", seed=7)
    rebuilt = rebuild_dataset(write_lines(tmp_path / "games.jsonl", lines), reward="margin")
    assert_same(rebuilt, live)
    win_loss = rebuild_dataset(tmp_path / "games.jsonl")
    assert not np.array_equal(win_loss.reward, rebuilt.reward)


def test_rebuild_unknown_reward_raises(tmp_path):
    _, lines = play_live(["p1"])
    with pytest.raises(ValueError, match="nope"):
        rebuild_dataset(write_lines(tmp_path / "games.jsonl", lines), reward="nope")


def test_rebuild_illegal_action_names_the_line(tmp_path):
    _, lines = play_live(["p1", "p2"])
    env = QuackEnv()
    env.reset(seed=0)
    illegal = int(np.flatnonzero(env.action_masks() == 0)[0])
    lines[1]["actions"][0] = [illegal, illegal]
    with pytest.raises(ValueError, match=r"line 2\b.*not legal"):
        rebuild_dataset(write_lines(tmp_path / "games.jsonl", lines))


def test_rebuild_actions_end_before_game_over_names_the_line(tmp_path):
    _, lines = play_live(["p1", "p2"])
    lines[0]["actions"] = lines[0]["actions"][:-1]
    with pytest.raises(ValueError, match=r"line 1\b.*before the game is over"):
        rebuild_dataset(write_lines(tmp_path / "games.jsonl", lines))


def test_rebuild_actions_left_after_game_over_names_the_line(tmp_path):
    _, lines = play_live(["p1", "p2"])
    lines[1]["actions"].append(lines[1]["actions"][-1])
    with pytest.raises(ValueError, match=r"line 2\b.*after the game is over"):
        rebuild_dataset(write_lines(tmp_path / "games.jsonl", lines))
