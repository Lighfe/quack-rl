"""The opponent mix: `--opponent` with a comma-separated list of bot specs (issue #263).

The tests that train need the `rl` group (`uv run --group rl --with pytest pytest
tests/test_rl_opponent_mix.py`); they skip without it.
"""

import json
import runpy
import sys
from pathlib import Path

import pytest

from quack_rl.bots.presets import PRESET_BOTS
from quack_rl.rl.opponents import OpponentMix, distinct_specs, parse_opponents
from quack_rl.rl.single_env import QuackEnv

REPO = Path(__file__).resolve().parents[1]
TOPCHIP, SPENDMOST, BLACKPURPLE = PRESET_BOTS


def episodes(mix: OpponentMix, n: int) -> list[str]:
    picked = []
    for _ in range(n):
        mix.reset()
        picked.append(mix.current)
    return picked


# --- parsing the list -------------------------------------------------------------------------


def test_a_single_spec_parses_to_itself():
    assert parse_opponents("bot:random") == ["bot:random"]


def test_spaces_around_commas_are_allowed_and_repeats_are_kept():
    text = f"{TOPCHIP} , {SPENDMOST},{TOPCHIP}"
    assert parse_opponents(text) == [TOPCHIP, SPENDMOST, TOPCHIP]


@pytest.mark.parametrize(
    "text, item",
    [(f"{TOPCHIP},bot:nope", "'bot:nope'"), ("bot:random,", "''"), (",bot:random", "''")],
)
def test_an_unknown_or_empty_item_names_the_item(text, item):
    with pytest.raises(ValueError) as err:
        parse_opponents(text)
    assert item in str(err.value)


def test_distinct_specs_keep_the_order_and_add_random_once():
    assert distinct_specs([TOPCHIP, SPENDMOST, TOPCHIP]) == [TOPCHIP, SPENDMOST, "bot:random"]
    assert distinct_specs(["bot:random", TOPCHIP]) == ["bot:random", TOPCHIP]
    assert distinct_specs(["random", TOPCHIP]) == ["random", TOPCHIP]


# --- the mix as an opponent -------------------------------------------------------------------


def test_opponent_mix_same_seed_same_sequence():
    first = episodes(OpponentMix(list(PRESET_BOTS), seed=7), 40)
    again = episodes(OpponentMix(list(PRESET_BOTS), seed=7), 40)
    other = episodes(OpponentMix(list(PRESET_BOTS), seed=8), 40)
    assert first == again
    assert first != other
    assert set(first) == set(PRESET_BOTS)


def test_a_repeated_spec_counts_twice_in_the_sampling():
    picked = episodes(OpponentMix([TOPCHIP, TOPCHIP, SPENDMOST], seed=0), 3000)
    share = picked.count(TOPCHIP) / len(picked)
    assert 0.62 < share < 0.71  # 2/3 expected


def test_the_mix_picks_an_opponent_on_each_env_reset_and_plays_legal_moves():
    import numpy as np

    mix = OpponentMix([TOPCHIP, "bot:random"], seed=1)
    env = QuackEnv(seat="random", opponent=mix)
    rng = np.random.default_rng(0)
    seen = []
    for game in range(6):
        _, info = env.reset(seed=game)
        seen.append(mix.current)
        done = False
        while not done:
            action = int(rng.choice(np.flatnonzero(info["action_mask"])))
            _, _, done, _, info = env.step(action)
            assert not info["illegal_action"]
    assert len(seen) == 6 and set(seen) <= {TOPCHIP, "bot:random"}


def test_the_mix_needs_a_reset_before_it_plays():
    with pytest.raises(RuntimeError, match="reset"):
        OpponentMix([TOPCHIP], seed=0).choose(None, "p1", ["Wait"])


# --- the script -------------------------------------------------------------------------------


def run_script(monkeypatch, argv: list[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["train_ppo.py", *argv])
    runpy.run_path(str(REPO / "scripts" / "train_ppo.py"), run_name="__main__")


@pytest.mark.parametrize("opponent", [f"{TOPCHIP},bot:nope", "bot:random,"])
def test_script_refuses_a_bad_list_before_training(tmp_path, monkeypatch, capsys, opponent):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as stop:
        run_script(monkeypatch, ["--opponent", opponent, "--steps", "1", "--out", "run"])
    assert stop.value.code != 0
    item = opponent.split(",")[1]
    assert repr(item) in capsys.readouterr().err
    assert not (tmp_path / "run").exists()


@pytest.mark.slow
def test_train_ppo_with_an_opponent_mix_writes_an_agent(tmp_path, monkeypatch, capsys):
    pytest.importorskip("sb3_contrib")
    from quack_rl.rl.agents import load_agent
    from quack_rl.rules import load_ruleset

    monkeypatch.chdir(tmp_path)
    opponents = f"{TOPCHIP}, {SPENDMOST}"
    run_script(
        monkeypatch,
        ["--opponent", opponents, "--steps", "1024", "--eval-games", "2", "--seed", "0"]
        + ["--out", "run", "--agent-name", "mix-tiny"],
    )
    printed = capsys.readouterr().out
    for spec in (TOPCHIP, SPENDMOST, "bot:random"):
        assert sum(line.startswith(f"vs {spec}: win rate") for line in printed.splitlines()) == 1
    result = json.loads((tmp_path / "run" / "result.json").read_text())
    assert list(result["evaluations"]) == [TOPCHIP, SPENDMOST, "bot:random"]
    for ev in result["evaluations"].values():
        assert ev["games"] == 2 and 0 <= ev["ci_low"] <= ev["win_rate"] <= ev["ci_high"] <= 1
    config = json.loads((tmp_path / "run" / "config.json").read_text())
    assert config["opponent"] == [TOPCHIP, SPENDMOST]
    seat = load_agent("mix-tiny", load_ruleset("v2.3"), root=tmp_path / "data" / "agents")
    assert seat.name == "agent:mix-tiny"
