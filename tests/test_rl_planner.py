"""The planner: determinization, flat Monte Carlo search and the agent folder of kind `planner`.

Every agent is written under `tmp_path`. All tests but the `slow` one use a small
`simulations`, so the fast subset stays fast.
"""

import copy
import io
import json
import random
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import pytest

from quack_rl.bots import RandomBot
from quack_rl.engine import (
    SEATS,
    WAIT,
    GameState,
    Phase,
    RngChance,
    legal_actions,
    needs_actions,
    new_game,
    state_to_dict,
    step,
)
from quack_rl.rl import agents
from quack_rl.rl.agents import AgentManifest, load_agent, save_agent
from quack_rl.rl.determinize import determinize
from quack_rl.rl.encode import BOARD_LAYOUT
from quack_rl.rl.planner import (
    DEFAULT_MAX_SECONDS,
    DEFAULT_ROLLOUT,
    DEFAULT_SIMULATIONS,
    PlannerBot,
)
from quack_rl.rules import load_ruleset
from quack_rl.runner import play_game
from quack_rl.simgame import play_sim_game

RS = load_ruleset("v2.3")
REPO = Path(__file__).resolve().parents[1]
SMALL = 4  # simulations per decision in the fast tests


def advance(seed: int, until) -> GameState:
    """Play random bots from a new game until `until(state)` holds at a decision."""
    bots = {s: RandomBot(seed + i) for i, s in enumerate(SEATS)}
    chance = RngChance(seed)
    state = new_game(RS)
    while state.phase is not Phase.GAME_OVER:
        if needs_actions(state) and until(state):
            return state
        actions = None
        if needs_actions(state):
            actions = {}
            for s in SEATS:
                legal = legal_actions(state, RS, s)
                actions[s] = WAIT if legal == [WAIT] else bots[s].choose(state, s, legal)
        state = step(state, RS, actions, chance).state
    raise AssertionError("the game ended before the wanted state")


def with_hidden(state: GameState, seat: str, hand: list[str], card_draw: list[str]) -> GameState:
    """A copy where `seat` holds `hand` (taken out of its bag) and has `card_draw`."""
    out = copy.deepcopy(state)
    p = out.players[seat]
    for chip_id in hand:
        assert p.bag.get(chip_id, 0) > 0
        p.bag[chip_id] -= 1
        if p.bag[chip_id] == 0:
            del p.bag[chip_id]
    p.hand = list(hand)
    p.card_draw = list(card_draw)
    return out


def brew_state() -> GameState:
    """A brew decision where p1 has more than one legal action."""
    return advance(3, lambda s: len(legal_actions(s, RS, "p1")) > 1 and s.phase is Phase.BREW)


def shop_state() -> GameState:
    """A shop decision of p1 (many legal actions)."""
    return advance(5, lambda s: s.phase is Phase.SHOP and len(legal_actions(s, RS, "p1")) > 2)


# --- determinize --------------------------------------------------------------------------------


def test_determinize_hides_the_opponent_hand():
    base = brew_state()
    opp_bag = base.players["p2"].bag
    hand = sorted(opp_bag)[:2]
    state = with_hidden(base, "p2", hand, [sorted(opp_bag)[0]] * 3)
    own_bag = sorted(base.players["p1"].bag)
    state = with_hidden(state, "p1", own_bag[:1], own_bag[-1:])
    before = state_to_dict(state)

    world = determinize(state, RS, "p1", random.Random(0))

    assert state_to_dict(state) == before  # the input is not changed
    opp, orig = world.players["p2"], state.players["p2"]
    assert opp.hand == []
    returned = Counter(orig.hand)
    for chip_id in set(orig.bag) | set(returned) | set(opp.bag):
        assert opp.bag.get(chip_id, 0) == orig.bag.get(chip_id, 0) + returned[chip_id]
    assert len(opp.card_draw) == len(orig.card_draw) == 3
    assert not Counter(opp.card_draw) - Counter(opp.bag)  # drawn from the bag
    me, mine = world.players["p1"], state.players["p1"]
    assert me.hand == mine.hand and me.card_draw == mine.card_draw and me.bag == mine.bag
    assert sorted(world.deck) == sorted(state.deck)


def test_determinize_gives_the_same_world_for_the_same_public_state():
    base = brew_state()
    opp = sorted(base.players["p2"].bag)
    a = with_hidden(base, "p2", opp[:1], opp[:2])
    b = with_hidden(base, "p2", opp[-1:], opp[-2:])
    wa = determinize(a, RS, "p1", random.Random(9))
    wb = determinize(b, RS, "p1", random.Random(9))
    assert state_to_dict(wa) == state_to_dict(wb)
    assert list(wa.players["p2"].bag) == list(wb.players["p2"].bag)  # same key order too


# --- choose -------------------------------------------------------------------------------------


def test_choice_ignores_hidden_information():
    base = shop_state()
    opp = sorted(base.players["p2"].bag)
    a = with_hidden(base, "p2", opp[:2], opp[:1] * 2)
    b = with_hidden(base, "p2", opp[-2:], opp[-1:] * 2)
    legal = legal_actions(base, RS, "p1")
    assert legal == legal_actions(a, RS, "p1") == legal_actions(b, RS, "p1")
    for seed in range(3):
        pa = PlannerBot(RS, simulations=2 * len(legal), seed=seed, max_seconds=600)
        pb = PlannerBot(RS, simulations=2 * len(legal), seed=seed, max_seconds=600)
        assert pa.choose(a, "p1", legal) == pb.choose(b, "p1", legal)
        assert pa.time_capped == pb.time_capped == 0


def test_single_legal_action_returns_it_without_simulating(monkeypatch):
    planner = PlannerBot(RS, simulations=SMALL, seed=0)

    def no_simulation(*args, **kwargs):
        raise AssertionError("simulated")

    monkeypatch.setattr(planner, "_simulate", no_simulation)
    monkeypatch.setattr("quack_rl.rl.planner.determinize", no_simulation)
    state = brew_state()
    assert planner.choose(state, "p1", ["stop"]) == "stop"


def test_choose_leaves_the_state_unchanged():
    state = shop_state()
    before = state_to_dict(state)
    planner = PlannerBot(RS, simulations=SMALL, seed=1)
    planner.choose(state, "p1", legal_actions(state, RS, "p1"))
    assert state_to_dict(state) == before


def test_planner_never_touches_the_real_chance_rng():
    chance = RngChance(11)
    state = new_game(RS)
    state = step(state, RS, None, chance).state  # the first card
    while not (needs_actions(state) and len(legal_actions(state, RS, "p1")) > 1):
        actions = None
        if needs_actions(state):
            actions = {s: legal_actions(state, RS, s)[0] for s in SEATS}
        state = step(state, RS, actions, chance).state
    planner = PlannerBot(RS, simulations=SMALL, seed=2)
    random.seed(123)
    global_before = random.getstate()
    chance_before = chance._rng.getstate()
    planner.choose(state, "p1", legal_actions(state, RS, "p1"))
    assert random.getstate() == global_before
    assert chance._rng.getstate() == chance_before


def test_the_best_mean_wins_and_a_tie_goes_to_the_first_action(monkeypatch):
    planner = PlannerBot(RS, simulations=6, seed=0)
    results = {"a": 0.5, "b": 1.0, "c": 1.0}
    monkeypatch.setattr(planner, "_simulate", lambda world, seat, action, seeds: results[action])
    state = brew_state()
    assert planner.choose(state, "p1", ["a", "b", "c"]) == "b"


def test_the_clock_cap_stops_a_decision_and_counts_it():
    state = shop_state()
    planner = PlannerBot(RS, simulations=10_000, seed=0, max_seconds=0.05)
    legal = legal_actions(state, RS, "p1")
    assert planner.choose(state, "p1", legal) in legal
    assert planner.time_capped == 1


# --- full games ---------------------------------------------------------------------------------


def planner_manifest(name: str, simulations: int = SMALL, rollout: str = DEFAULT_ROLLOUT):
    return AgentManifest(
        name=name,
        kind="planner",
        rules=RS.version,
        layout=BOARD_LAYOUT,
        settings={"simulations": simulations, "rollout": rollout},
        created_at="2026-11-05T00:00:00+00:00",
    )


def comparable(text: str) -> list[dict]:
    lines = [json.loads(line) for line in text.splitlines()]
    for line in lines:
        for key in ("game_id", "started_at", "finished_at"):
            line.pop(key, None)
    return lines


def test_planner_plays_full_games_legally(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    save_agent(tmp_path / "data" / "agents" / "plan", planner_manifest("plan", simulations=2))

    def records() -> list[list[dict]]:
        out = []
        for game in range(4):
            p1, p2 = ("agent:plan", "bot:random") if game % 2 == 0 else ("bot:random", "agent:plan")
            stream = io.StringIO()
            final, _, _ = play_sim_game(
                RS,
                rules="v2.3",
                rounds=RS.rounds,
                overrides={},
                p1=p1,
                p2=p2,
                game_seed=40 + game,
                stream=stream,
            )  # raises IllegalAction on an illegal choice
            assert final.phase is Phase.GAME_OVER
            out.append(comparable(stream.getvalue()))
        return out

    first = records()
    assert first[0][0]["seats"]["p1"]["name"] == "planner"
    assert first == records()


@pytest.mark.slow
def test_decision_time_stays_under_budget():
    planner = PlannerBot(RS, seed=0)  # the defaults of scripts/make_planner_agent.py
    assert planner.simulations == DEFAULT_SIMULATIONS
    assert planner.max_seconds == DEFAULT_MAX_SECONDS
    times: list[float] = []
    choose = planner.choose

    def timed(state, seat, legal):
        started = time.perf_counter()
        action = choose(state, seat, legal)
        times.append(time.perf_counter() - started)
        return action

    planner.choose = timed  # type: ignore[method-assign]
    final = play_game(RS, {"p1": planner, "p2": RandomBot(1)}, RngChance(7))
    assert final.phase is Phase.GAME_OVER
    assert times, "the planner made no decision"
    assert max(times) <= DEFAULT_MAX_SECONDS + 0.5, f"slowest decision {max(times):.2f} s"


# --- the agent folder ---------------------------------------------------------------------------


def test_planner_agent_loads_in_a_fresh_process(tmp_path):
    save_agent(tmp_path / "plan", planner_manifest("plan"))
    code = (
        "import sys\n"
        "from pathlib import Path\n"
        "from quack_rl.rl.agents import load_agent\n"
        "from quack_rl.rules import load_ruleset\n"
        "bot = load_agent('plan', load_ruleset('v2.3'), 3, root=Path(sys.argv[1]))\n"
        "print(type(bot).__module__, type(bot).__name__, bot.simulations)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path)],
        capture_output=True,
        text=True,
        cwd=REPO,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["quack_rl.rl.planner", "PlannerBot", str(SMALL)]


def test_load_agent_builds_the_planner_from_the_settings(tmp_path):
    save_agent(tmp_path / "plan", planner_manifest("plan", simulations=7, rollout="bot:random"))
    bot = load_agent("plan", RS, 5, root=tmp_path)
    assert isinstance(bot, PlannerBot)
    assert (bot.simulations, bot.rollout, bot.params["seed"]) == (7, "bot:random", 5)
    assert agents.PLANNER_FACTORY is not None


def test_bad_planner_settings_are_an_agent_error(tmp_path):
    save_agent(tmp_path / "plan", planner_manifest("plan", rollout="human"))
    with pytest.raises(agents.AgentError, match="planner settings"):
        load_agent("plan", RS, root=tmp_path)


def test_make_planner_agent_writes_the_folder(tmp_path):
    script = REPO / "scripts" / "make_planner_agent.py"
    args = [sys.executable, str(script), "--name", "plan", "--root", str(tmp_path)]
    result = subprocess.run([*args, "--simulations", "20"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    data = json.loads((tmp_path / "plan" / "agent.json").read_text())
    assert data["kind"] == "planner" and data["weights"] is None
    assert data["settings"] == {
        "simulations": 20,
        "rollout": DEFAULT_ROLLOUT,
        "max_seconds": DEFAULT_MAX_SECONDS,
    }
    again = subprocess.run(args, capture_output=True, text=True)
    assert again.returncode != 0 and "already exists" in again.stderr
