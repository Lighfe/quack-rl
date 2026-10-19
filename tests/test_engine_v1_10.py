"""Engine under ruleset v1.10: minimum buy round, round-end order, black, purple, yellow."""

import io
import random

import pytest
from typer.testing import CliRunner

from quack_rl.cli.main import app
from quack_rl.engine import (
    DONE,
    SEATS,
    Phase,
    RngChance,
    ScriptedChance,
    Status,
    buy,
    legal_actions,
    new_game,
    state_from_dict,
    state_to_dict,
    step,
)
from quack_rl.engine.brew import _draw
from quack_rl.engine.chance import ChanceLog
from quack_rl.record import GameRecorder, HeaderLine, SeatInfo, read_games, verify_game, verify_seed
from quack_rl.rules import load_ruleset
from quack_rl.runner import play_game

RS = load_ruleset("v1.10")


# --- minimum buy round -------------------------------------------------------------------


def shop_state(round_, money=30, rs=RS):
    s = new_game(rs)
    s.phase, s.round = Phase.SHOP, round_
    for p in s.players.values():
        p.money, p.status = money, Status.STOPPED
        p.field = p.final_field = 3
    return s


@pytest.mark.parametrize(
    "item,min_round", [("black_1", 1), ("yellow_1", 2), ("yellow_4", 2), ("purple_1", 3)]
)
def test_item_is_legal_only_from_its_minimum_round(item, min_round):
    for round_ in range(1, 10):
        legal = legal_actions(shop_state(round_), RS, "p1")
        assert (buy(item) in legal) == (round_ >= min_round), (item, round_)


def test_buy_below_minimum_round_is_refused_in_a_step():
    from quack_rl.engine import IllegalAction

    with pytest.raises(IllegalAction):
        step(shop_state(1), RS, {"p1": buy("yellow_1"), "p2": DONE}, ScriptedChance([]))
    r = step(shop_state(2), RS, {"p1": buy("yellow_1"), "p2": DONE}, ScriptedChance([]))
    assert r.state.players["p1"].bag["yellow_1"] == 1


def test_older_versions_ignore_the_minimum_round():
    for version in ("v1", "v1.1", "v1.8", "v1.9"):
        rs = load_ruleset(version)
        legal = legal_actions(shop_state(1, rs=rs), rs, "p1")
        assert all(buy(i.id) in legal for i in rs.shop if i.price <= 30 and i.kind == "chip"), (
            version
        )


# --- round end ---------------------------------------------------------------------------


def resolve_state(p1_placed, p2_placed, exploded=(), f1=3, f2=2):
    """Start of Resolve; p1 is the only one to roll the die (it is further)."""
    s = new_game(RS)
    s.phase = Phase.RESOLVE
    for seat, fld, placed in (("p1", f1, p1_placed), ("p2", f2, p2_placed)):
        p = s.players[seat]
        p.field = p.final_field = fld
        p.placed = list(placed)
        p.status = Status.EXPLODED if seat in exploded else Status.STOPPED
    return s


def resolve(p1_placed, p2_placed, exploded=(), **kw):
    s = resolve_state(p1_placed, p2_placed, exploded, **kw)
    chance = ["money_1"] if len(exploded) < 2 else []
    r = step(s, RS, None, ScriptedChance(chance))
    return r.state.players["p1"], r.state.players["p2"], r.events


def pot_events(events):
    return [
        (e["seat"], e["component"], e["points"], e["halves"])
        for e in events
        if e["kind"] == "pot_round_end"
    ]


@pytest.mark.parametrize(
    "a,b,halves_a,halves_b",
    [
        (0, 0, 0, 0),
        (1, 1, 2, 2),
        (2, 2, 2, 2),
        (1, 0, 3, 0),
        (0, 1, 0, 3),
        (3, 1, 3, 0),
        (2, 3, 0, 3),
    ],
)
def test_black_by_counts(a, b, halves_a, halves_b):
    p1, p2, events = resolve(["black_1"] * a, ["black_1"] * b)
    assert (p1.droplet_halves, p2.droplet_halves) == (halves_a, halves_b)
    assert len(pot_events(events)) == (halves_a > 0) + (halves_b > 0)


def test_black_counts_an_exploded_pot():
    p1, p2, _ = resolve(["white_3", "black_1"], ["black_1"], exploded=("p1",))
    assert (p1.droplet_halves, p2.droplet_halves) == (2, 2)
    p1, p2, _ = resolve(["black_1", "black_1"], ["black_1"], exploded=("p1",))
    assert (p1.droplet_halves, p2.droplet_halves) == (3, 0)


@pytest.mark.parametrize("n,points,halves", [(0, 0, 0), (1, 1, 0), (2, 1, 1), (3, 2, 2), (5, 2, 2)])
def test_purple_by_count(n, points, halves):
    p1, p2, _ = resolve(["purple_1"] * n, [])
    assert (p1.points, p1.droplet_halves) == (points, halves)
    assert (p2.points, p2.droplet_halves) == (0, 0)


def test_purple_on_an_exploded_pot_and_chips_go_back_to_the_bag():
    p1, _, _ = resolve(["white_3", "purple_1"], [], exploded=("p1",))
    assert p1.points == 1
    assert p1.placed == ["white_3", "purple_1"]  # the pot stays; the shop end puts it into the bag


def test_two_green_black_and_purple_in_one_round_end_in_order():
    placed = ["black_1", "purple_1", "green_1", "green_2"]
    # last chip green_2 (+1 half step), second last green_1 (+1): green fires twice
    s = resolve_state(placed, ["black_1"])
    r = step(s, RS, None, ScriptedChance(["money_1"]))
    kinds = [(e["seat"], e["kind"], e.get("chip") or e.get("component")) for e in r.events]
    mine = [k for k in kinds if k[0] == "p1" and k[1] in ("round_end_bonus", "pot_round_end")]
    assert mine == [
        ("p1", "round_end_bonus", "green_2"),
        ("p1", "round_end_bonus", "green_1"),
        ("p1", "pot_round_end", "black@1"),
        ("p1", "pot_round_end", "purple@1"),
    ]
    p1, p2 = r.state.players["p1"], r.state.players["p2"]
    assert p1.droplet_halves == 2 + 2 + 0 + 0  # green x2 = 2 halves, black equal 1:1 = 2 halves
    assert p1.points == 1  # purple, one chip
    assert p2.droplet_halves == 2


def test_ruby_comes_first():
    s = resolve_state(["black_1"], ["black_1"], f1=4, f2=2)  # scoring field 5 is a ruby
    r = step(s, RS, None, ScriptedChance(["money_1"]))
    order = [e["kind"] for e in r.events if e["seat"] == "p1"]
    assert order.index("ruby") < order.index("pot_round_end")


def test_older_rulesets_never_write_the_new_event():
    rs = load_ruleset("v1.9")
    s = new_game(rs)
    s.phase = Phase.RESOLVE
    for p in s.players.values():
        p.field = p.final_field = 3
        p.placed = ["white_1"]
        p.status = Status.STOPPED
    r = step(s, rs, None, ScriptedChance(["money_1", "money_1"]))
    assert not [e for e in r.events if e["kind"] in ("pot_round_end", "pot_put_back")]


# --- yellow --------------------------------------------------------------------------------


def draw_all(chips, bag=None, field=0):
    s = new_game(RS)
    p = s.players["p1"]
    p.bag = dict(bag) if bag is not None else {}
    if bag is None:
        for c in chips:
            p.bag[c] = p.bag.get(c, 0) + 1
    p.field = field
    events = []
    log = ChanceLog(ScriptedChance(chips), RS)
    for _ in chips:
        _draw(p, "p1", RS, log, events)
        if p.status is Status.EXPLODED:
            break
    return s, p, events


def test_yellow_after_white_puts_the_white_back_without_taking_back_the_move():
    _, p, events = draw_all(["white_2", "yellow_1"])
    assert p.placed == ["yellow_1"] and p.placed_fields == [3]
    assert p.field == 3  # 2 + 1, the droplet of white is kept
    assert p.white_total == 0
    assert p.bag == {"white_2": 1}
    kinds = [e["kind"] for e in events]
    assert kinds == ["place", "place", "pot_put_back"]
    assert events[2] == {"seat": "p1", "kind": "pot_put_back", "chip": "white_2", "white_total": 0}


@pytest.mark.parametrize("yellow", ["yellow_1", "yellow_2", "yellow_4"])
def test_all_values_of_yellow_put_back(yellow):
    _, p, _ = draw_all(["white_1", yellow])
    assert p.placed == [yellow] and p.bag == {"white_1": 1}


def test_yellow_first_in_the_pot_does_nothing():
    _, p, events = draw_all(["yellow_1"])
    assert p.placed == ["yellow_1"] and not [e for e in events if e["kind"] == "pot_put_back"]


@pytest.mark.parametrize("before", ["orange_1", "green_1", "black_1", "purple_1", "yellow_1"])
def test_yellow_after_a_non_white_chip_does_nothing(before):
    _, p, events = draw_all([before, "yellow_2"])
    assert p.placed == [before, "yellow_2"] and not [
        e for e in events if e["kind"] == "pot_put_back"
    ]


def test_yellow_after_a_white_that_was_after_a_pulled_white():
    # white_3, yellow (pulls white_3), white_1, yellow (pulls white_1)
    _, p, _ = draw_all(["white_3", "yellow_1", "white_1", "yellow_1"])
    assert p.placed == ["yellow_1", "yellow_1"] and p.white_total == 0


def test_yellow_after_yellow_does_nothing():
    _, p, _ = draw_all(["white_1", "yellow_1", "yellow_2"])
    assert p.placed == ["yellow_1", "yellow_2"]


def test_yellow_saves_the_pot_from_an_explosion():
    # 3 + 3 + 1 = 7 is still ok (the limit is "more than 7"); yellow_4 then pulls white_1: total 6
    _, p, _ = draw_all(
        ["white_3", "white_3", "white_1", "yellow_4"],
        bag={"white_3": 2, "white_1": 1, "yellow_4": 1},
    )
    assert p.status is Status.BREWING and p.white_total == 6
    assert p.placed == ["white_3", "white_3", "yellow_4"]


def test_yellow_cannot_save_a_pot_that_exploded_before_it():
    _, p, _ = draw_all(
        ["white_3", "white_3", "white_2", "yellow_1"],
        bag={"white_3": 2, "white_2": 1, "yellow_1": 1},
    )
    assert p.status is Status.EXPLODED and p.white_total == 8 and "yellow_1" not in p.placed


def test_put_back_runs_before_the_explosion_check_of_the_same_step():
    # white_3, white_3 = 6; yellow_1 itself weighs 0, so only the pull lowers the total. Start
    # the pot at a total of 9 by hand: the pot would be over the limit, the pull brings it to 6.
    s = new_game(RS)
    p = s.players["p1"]
    p.bag = {"yellow_1": 1}
    p.placed, p.placed_fields, p.white_total, p.field = ["white_3"], [3], 9, 3
    ev: list = []
    _draw(p, "p1", RS, ChanceLog(ScriptedChance(["yellow_1"]), RS), ev)
    assert p.status is Status.BREWING and p.white_total == 6 and p.placed == ["yellow_1"]
    assert [e["kind"] for e in ev] == ["place", "pot_put_back"]


def test_state_round_trip_after_a_put_back():
    s, p, _ = draw_all(["white_2", "yellow_1"])
    again = state_from_dict(state_to_dict(s))
    assert again == s
    assert again.players["p1"].placed == ["yellow_1"] and again.players["p1"].bag == {"white_2": 1}


# --- scripted draws through whole rounds ------------------------------------------------------


def play_brew(bags, draws1, draws2=("white_1",)):
    """Play one brew phase through `step`: seat draws its scripted chips, then stops.

    The bags are set by hand; every chip that is drawn comes from the script. Returns the state
    after the brew phase and all events. Resolve is not run.
    """
    s = new_game(RS)
    s.players["p1"].bag = dict(bags[0])
    s.players["p2"].bag = dict(bags[1])
    queues = {"p1": list(draws1), "p2": list(draws2)}
    events: list = []
    while s.phase is Phase.BREW:
        actions, chance = {}, []
        assert s.step < 40
        for seat in SEATS:
            p = s.players[seat]
            if p.status is not Status.BREWING:
                actions[seat] = legal_actions(s, RS, seat)[0]
            elif queues[seat]:
                actions[seat] = "draw"
                chance.append(queues[seat].pop(0))
            else:
                actions[seat] = "stop"
        r = step(s, RS, actions, ScriptedChance(chance))
        s, events = r.state, events + list(r.events)
    assert not queues["p1"] and not queues["p2"]
    return s, events


def test_yellow_saves_a_pot_that_the_same_draw_would_explode_without_it():
    # white_3 + white_3 + white_1 = 7, still fine. A white_1 next would make 8 and explode.
    bags = [{"white_3": 2, "white_1": 2, "yellow_1": 1, "orange_1": 1}, {"white_1": 1}]
    base = ["white_3", "white_3", "white_1"]
    s, ev = play_brew(bags, base + ["yellow_1", "white_1"])
    p = s.players["p1"]
    assert p.status is Status.STOPPED and p.white_total == 7
    assert p.placed == ["white_3", "white_3", "yellow_1", "white_1"]
    assert p.bag == {"white_1": 1, "orange_1": 1}
    assert [e["kind"] for e in ev if e["seat"] == "p1" and e["kind"] == "pot_put_back"] == [
        "pot_put_back"
    ]
    # control: the same draws with a non-yellow chip in the middle explode the pot
    s, _ = play_brew(bags, base + ["orange_1", "white_1"])
    assert s.players["p1"].status is Status.EXPLODED


def test_put_back_is_recorded_before_the_next_draw_and_the_chip_can_be_drawn_again():
    bags = [{"white_2": 1, "yellow_2": 1}, {"white_1": 1}]
    s, ev = play_brew(bags, ["white_2", "yellow_2", "white_2"])
    p = s.players["p1"]
    kinds = [(e["kind"], e.get("chip")) for e in ev if e["seat"] == "p1" and e["kind"] != "stop"]
    assert kinds[:4] == [
        ("place", "white_2"),
        ("place", "yellow_2"),
        ("pot_put_back", "white_2"),
        ("place", "white_2"),
    ]
    assert p.placed == ["yellow_2", "white_2"] and p.white_total == 2 and p.bag == {}


def test_yellow_after_a_non_white_chip_through_draws():
    bags = [{"orange_1": 1, "yellow_1": 1}, {"white_1": 1}]
    s, ev = play_brew(bags, ["orange_1", "yellow_1"])
    assert s.players["p1"].placed == ["orange_1", "yellow_1"]
    assert not [e for e in ev if e["kind"] == "pot_put_back"]


def test_state_round_trip_after_a_put_back_in_a_played_brew():
    s, _ = play_brew([{"white_2": 1, "yellow_1": 1}, {"white_1": 1}], ["white_2", "yellow_1"])
    assert state_from_dict(state_to_dict(s)) == s


def finish_round(s, die):
    """Resolve (scripted die results) and return the state after it and the events."""
    r = step(s, RS, None, ScriptedChance(die))
    return r.state, list(r.events)


def test_round_end_with_two_green_black_and_purple_through_draws():
    # p1 pot: black, purple, green_1, green_2 (last and second last green). p2 pot: black.
    bags = [
        {"black_1": 1, "purple_1": 1, "green_1": 1, "green_2": 1},
        {"black_1": 1},
    ]
    s, _ = play_brew(bags, ["black_1", "purple_1", "green_1", "green_2"], ["black_1"])
    s, ev = finish_round(s, ["money_1"])
    mine = [(e["kind"], e.get("chip") or e.get("component")) for e in ev if e["seat"] == "p1"]
    ordered = [m for m in mine if m[0] in ("round_end_bonus", "pot_round_end")]
    assert ordered == [
        ("round_end_bonus", "green_2"),
        ("round_end_bonus", "green_1"),
        ("pot_round_end", "black@1"),
        ("pot_round_end", "purple@1"),
    ]
    p1, p2 = s.players["p1"], s.players["p2"]
    assert p1.points == 1 and p1.droplet_halves == 4 and p2.droplet_halves == 2


def test_black_equal_zero_and_exploded_pot_through_draws():
    # nobody has black: nothing happens, no event
    s, _ = play_brew([{"white_1": 1}, {"white_1": 1}], ["white_1"], ["white_1"])
    s, ev = finish_round(s, ["money_1", "money_1"])
    assert not [e for e in ev if e["kind"] == "pot_round_end"]
    # p1 explodes with a black in the pot; p2 has black too: equal 1:1 gives both +1
    bags = [{"black_1": 1, "white_3": 3}, {"black_1": 1}]
    s, _ = play_brew(bags, ["black_1", "white_3", "white_3", "white_3"], ["black_1"])
    assert s.players["p1"].status is Status.EXPLODED
    s, ev = finish_round(s, ["money_1"])
    assert (s.players["p1"].droplet_halves, s.players["p2"].droplet_halves) == (2, 2)
    assert len([e for e in ev if e["kind"] == "pot_round_end"]) == 2


def test_purple_chips_return_to_the_bag_in_the_next_round():
    bags = [{"purple_1": 3}, {"white_1": 1}]
    s, _ = play_brew(bags, ["purple_1"] * 3, ["white_1"])
    s, _ = finish_round(s, ["money_1"])
    p1 = s.players["p1"]
    assert p1.points == 2 and p1.droplet_halves == 2
    for _ in range(4):  # leave the choice and shop phases with the first legal actions
        if s.phase in (Phase.GAME_OVER, Phase.BREW):
            break
        if s.phase is Phase.CHOICE:
            acts = {
                seat: legal_actions(s, RS, seat)[0] for seat in SEATS if legal_actions(s, RS, seat)
            }
        else:
            acts = {seat: DONE for seat in SEATS}
        s = step(s, RS, acts or None, ScriptedChance(["money_1"])).state
    assert s.phase is Phase.BREW and s.round == 2
    assert s.players["p1"].bag.get("purple_1") == 3 and s.players["p1"].placed == []


# --- record, replay, verify ------------------------------------------------------------------


class NewColourBot:
    """Random bot that buys the new colours whenever it can."""

    kind = "bot"
    name = "random"
    params: dict = {}

    def __init__(self, seed: int):
        self._rng = random.Random(seed)

    def choose(self, state, seat, legal):
        new = [a for a in legal if a.split("_")[0] in ("buy:black", "buy:yellow", "buy:purple")]
        if new:
            return self._rng.choice(new)
        return self._rng.choice(legal)


def record_game(seed: int):
    header = HeaderLine(
        game_id=f"g-v1.10-{seed}",
        schema_version=1,
        rules_version="v1.10",
        rounds=RS.rounds,
        seed=seed,
        mode="sim",
        seats={s: SeatInfo(kind="bot", name="random") for s in SEATS},
        ui={},
        engine_version="0.1.0",
        started_at="2026-10-19T10:00:00+02:00",
    )
    stream = io.StringIO()
    rec = GameRecorder(stream, header)
    seats = {"p1": NewColourBot(seed), "p2": NewColourBot(seed + 1000)}
    final = play_game(RS, seats, RngChance(seed), rec.on_step)
    rec.close(final)
    return stream.getvalue(), final


def components_seen(game):
    return {e["component"] for s in game.steps for e in s.events if e["kind"] == "pot_round_end"}


@pytest.fixture(scope="module")
def played(tmp_path_factory):
    for seed in range(1, 200):
        text, final = record_game(seed)
        path = tmp_path_factory.mktemp("rec") / "game.jsonl"
        path.write_text(text, encoding="utf-8")
        (game,) = read_games(path)
        has_put_back = any(e["kind"] == "pot_put_back" for s in game.steps for e in s.events)
        if has_put_back and components_seen(game) == {"black@1", "purple@1"}:
            return game, final, path
    pytest.fail("no seed in 199 gave a put-back, a black and a purple effect")


def test_game_with_all_three_colours_replays_to_the_same_state(played):
    game, final, _ = played
    assert verify_game(game) == []
    assert verify_seed(game) == []
    from quack_rl.engine import new_game as fresh
    from quack_rl.record.replay import RecordedChance

    state = fresh(RS)
    for line in game.steps:
        state = step(state, RS, line.actions, RecordedChance(line.chance)).state
    assert state == final


def test_cli_verify_with_seed_check_passes(played):
    _, _, path = played
    result = CliRunner().invoke(app, ["verify", str(path), "--seed-check"])
    assert result.exit_code == 0, result.output
    assert "1 games ok" in result.output


def test_tampered_put_back_event_is_a_problem(played):
    import copy

    game, _, _ = played
    g = copy.deepcopy(game)
    for s in g.steps:
        for e in s.events:
            if e["kind"] == "pot_put_back":
                e["white_total"] += 1
                assert verify_game(g)
                return
