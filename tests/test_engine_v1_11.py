"""Engine under ruleset v1.11: the round-start card draw and cards 1, 3, 4, 7 (issue #143)."""

import copy
import io

import pytest
from typer.testing import CliRunner

from quack_rl.bots.random_bot import RandomBot
from quack_rl.cli.main import app
from quack_rl.engine import (
    DONE,
    DRAW,
    SEATS,
    STOP,
    IllegalAction,
    IllegalChance,
    Phase,
    RngChance,
    ScriptedChance,
    Status,
    explosion_limit,
    new_game,
    state_from_dict,
    state_to_dict,
    step,
)
from quack_rl.record import GameRecorder, HeaderLine, SeatInfo, read_games, verify_game, verify_seed
from quack_rl.record.replay import RecordedChance
from quack_rl.rules import load_ruleset
from quack_rl.runner import play_game

RS = load_ruleset("v1.11")
ALL_CARDS = ["card_1", "card_2", "card_3", "card_4", "card_5", "card_6", "card_7", "card_8_to_12"]


def card_step(card, state=None, rs=RS):
    state = state or new_game(rs)
    assert state.phase is Phase.CARD
    return step(state, rs, None, ScriptedChance([card]))


def brewing(card, rs=RS):
    """A state in the brew phase of a round whose card is `card`."""
    state = card_step(card).state
    assert state.phase is Phase.BREW and state.card == card
    return state


# --- state and the draw ------------------------------------------------------------------


def test_new_game_has_the_full_deck_and_starts_at_the_card_phase():
    s = new_game(RS)
    assert s.phase is Phase.CARD and s.card is None
    assert len(s.deck) == 12
    assert s.deck.count("card_8_to_12") == 5 and s.deck.count("card_7") == 1


def test_state_round_trip_with_deck_and_card():
    s = card_step("card_4").state
    assert s.card == "card_4" and len(s.deck) == 11 and "card_4" not in s.deck
    data = state_to_dict(s)
    assert data["card"] == "card_4" and data["deck"] == s.deck
    assert state_from_dict(copy.deepcopy(data)) == s
    fresh = new_game(RS)
    assert state_from_dict(state_to_dict(fresh)) == fresh


@pytest.mark.parametrize("version", ["v1", "v1.1", "v1.8", "v1.9", "v1.10"])
def test_rulesets_without_cards_have_no_draw_step(version):
    rs = load_ruleset(version)
    s = new_game(rs)
    assert s.phase is Phase.BREW and s.deck == [] and s.card is None
    assert state_to_dict(s)["deck"] == []


def test_draw_takes_no_action_and_logs_the_card():
    s = new_game(RS)
    with pytest.raises(IllegalAction):
        step(s, RS, {"p1": DRAW, "p2": DRAW}, ScriptedChance(["card_1"]))
    r = card_step("card_8_to_12")
    assert r.legal is None and r.actions is None
    assert r.chance == [{"seat": "table", "kind": "card", "value": "card_8_to_12"}]
    assert r.events == [
        {"seat": None, "kind": "card_draw", "card": "card_8_to_12", "effect": "no_effect"}
    ]
    assert r.state.deck.count("card_8_to_12") == 4


def test_a_card_not_in_the_deck_is_refused():
    s = card_step("card_7").state
    s.phase = Phase.CARD
    with pytest.raises(IllegalChance):
        step(s, RS, None, ScriptedChance(["card_7"]))


class CardScript(RngChance):
    """Seeded chance for chips and die, but the cards come from a list."""

    def __init__(self, seed, cards):
        super().__init__(seed)
        self.cards = iter(cards)

    def draw_card(self, deck):
        return next(self.cards)


class DrawOnceBot:
    kind = "bot"
    name = "draw-once"
    params: dict = {}

    def choose(self, state, seat, legal):
        if state.phase is Phase.SHOP:
            return DONE
        return STOP if STOP in legal else DRAW


def test_nine_rounds_draw_nine_distinct_cards_and_leave_three():
    order = ["card_3", "card_7", "card_1", "card_4", "card_2", "card_5", "card_6", "card_8_to_12"]
    order = [*order, "card_8_to_12"]  # the no-effect entry has 5 copies
    seen = []
    state = play_game(
        RS,
        {s: DrawOnceBot() for s in SEATS},
        CardScript(1, order),
        lambda r, _: seen.extend(e["card"] for e in r.events if e["kind"] == "card_draw"),
    )
    assert seen == order
    assert len(state.deck) == 3
    named = [c for c in seen if c != "card_8_to_12"]
    assert len(named) == len(set(named))


def test_rng_games_never_draw_a_card_twice():
    for seed in range(20):
        cards: list[str] = []
        state = play_game(
            RS,
            {s: RandomBot(seed + i) for i, s in enumerate(SEATS)},
            RngChance(seed),
            lambda r, _, out=cards: out.extend(
                e["card"] for e in r.events if e["kind"] == "card_draw"
            ),
        )
        assert len(cards) == 9 and len(state.deck) == 3
        named = [c for c in cards if c != "card_8_to_12"]
        assert len(named) == len(set(named))
        assert cards.count("card_8_to_12") <= 5


def test_draw_is_uniform_over_the_cards_left():
    counts = {}
    for seed in range(600):
        card = RngChance(seed).draw_card(new_game(RS).deck)
        counts[card] = counts.get(card, 0) + 1
    assert counts["card_8_to_12"] > counts["card_1"] * 2  # 5 copies against 1


def test_a_game_without_cards_draws_nothing_from_the_chance_source():
    rs = load_ruleset("v1.10")
    state = new_game(rs)
    r = step(state, rs, {"p1": DRAW, "p2": DRAW}, ScriptedChance(["white_1", "white_1"]))
    assert [c["kind"] for c in r.chance] == ["draw_chip", "draw_chip"]


# --- card 3: drop +1 ---------------------------------------------------------------------


def test_card_3_moves_every_drop_one_step_at_once():
    s = new_game(RS)
    s.players["p2"].droplet_halves = 3
    s.players["p2"].field = 1
    r = card_step("card_3", s)
    assert [p.droplet_halves for p in r.state.players.values()] == [2, 5]
    assert [p.field for p in r.state.players.values()] == [1, 2]  # the start field follows
    assert [e["kind"] for e in r.events] == ["card_draw", "card_drop", "card_drop"]
    assert r.state.phase is Phase.BREW


# --- card 7: fewest points ---------------------------------------------------------------


def chips_of(state, seat):
    return state.players[seat].bag.get("green_1", 0)


def test_card_7_round_1_tie_gives_both_players_a_green_1():
    r = card_step("card_7")
    assert [chips_of(r.state, s) for s in SEATS] == [2, 2]
    assert [e["kind"] for e in r.events] == ["card_draw", "card_chip", "card_chip"]
    assert r.events[1] == {"seat": "p1", "kind": "card_chip", "chip": "green_1"}


def test_card_7_only_the_player_behind_gets_the_chip():
    s = new_game(RS)
    s.round, s.players["p1"].points, s.players["p2"].points = 4, 5, 2
    r = card_step("card_7", s)
    assert [chips_of(r.state, x) for x in SEATS] == [1, 2]


def test_card_7_tie_later_in_the_game_gives_both():
    s = new_game(RS)
    s.round, s.players["p1"].points, s.players["p2"].points = 6, 4, 4
    r = card_step("card_7", s)
    assert [chips_of(r.state, x) for x in SEATS] == [2, 2]


def test_card_7_chip_can_be_drawn_in_the_same_round():
    s = brewing("card_7")
    for p in s.players.values():
        p.bag = {"green_1": 1}
    r = step(s, RS, {"p1": DRAW, "p2": DRAW}, ScriptedChance(["green_1", "green_1"]))
    assert [p.placed for p in r.state.players.values()] == [["green_1"], ["green_1"]]


# --- card 4: explosion limit -------------------------------------------------------------


def draw_white_1(state, total):
    for p in state.players.values():
        p.bag, p.white_total = {"white_1": 3}, total
    return step(state, RS, {"p1": DRAW, "p2": DRAW}, ScriptedChance(["white_1", "white_1"])).state


def test_card_4_limit_is_9_for_both_players():
    s = brewing("card_4")
    assert explosion_limit(s, RS) == RS.explosion_limit + 2 == 9
    after9 = draw_white_1(copy.deepcopy(s), 8)  # total 9
    assert all(p.status is Status.BREWING for p in after9.players.values())
    after10 = draw_white_1(copy.deepcopy(s), 9)  # total 10
    assert all(p.status is Status.EXPLODED for p in after10.players.values())


def test_limit_is_back_to_normal_in_the_next_round():
    s = brewing("card_4")
    s.phase, s.round = Phase.SHOP, 1
    for p in s.players.values():
        p.status, p.final_field = Status.STOPPED, 3
    s = step(s, RS, {"p1": DONE, "p2": DONE}, ScriptedChance([])).state
    assert s.phase is Phase.CARD and s.card is None and s.round == 2
    s = card_step("card_8_to_12", s).state
    assert explosion_limit(s, RS) == 7
    after = draw_white_1(s, 7)  # total 8 explodes again
    assert all(p.status is Status.EXPLODED for p in after.players.values())


# --- card 1: ruby ------------------------------------------------------------------------


def resolve_state(card, fields):
    s = brewing(card)
    s.phase = Phase.RESOLVE
    for seat, f in zip(SEATS, fields, strict=True):
        p = s.players[seat]
        p.status, p.final_field, p.field = Status.STOPPED, f, f
    return s


def resolve(s):
    dice = [f.id for f in RS.die if f.kind == "money"][:1] * 2
    return step(s, RS, None, ScriptedChance(dice))


def test_card_1_ruby_step_is_two_half_steps_for_a_ruby_player_only():
    assert 5 in RS.rubies and 6 not in RS.rubies
    # scoring field = final field + 1: p1 stops on 4 (scores on ruby 5), p2 on 5 (scores on 6)
    r = resolve(resolve_state("card_1", (4, 5)))
    assert r.state.players["p1"].droplet_halves == 2
    assert r.state.players["p2"].droplet_halves == 0
    assert [e for e in r.events if e["kind"] == "ruby"] == [
        {"seat": "p1", "kind": "ruby", "halves": 2}
    ]


def test_without_card_1_the_ruby_step_is_one_half_step():
    r = resolve(resolve_state("card_8_to_12", (4, 5)))
    assert r.state.players["p1"].droplet_halves == 1
    assert r.state.players["p2"].droplet_halves == 0


# --- cards 2, 5, 6: drawn and recorded, no effect for now --------------------------------


@pytest.mark.parametrize("card", ["card_2", "card_5", "card_6"])
def test_cards_2_5_6_act_like_no_effect_for_now(card):
    plain, special = card_step("card_8_to_12"), card_step(card)
    assert [e["kind"] for e in special.events] == ["card_draw"]
    assert special.events[0]["card"] == card
    a, b = copy.deepcopy(plain.state), copy.deepcopy(special.state)
    a.deck, b.deck, a.card, b.card = [], [], None, None
    assert a == b
    assert explosion_limit(special.state, RS) == 7
    resolved = resolve(resolve_state(card, (4, 5)))
    assert resolved.state.players["p1"].droplet_halves == 1  # the normal ruby step


# --- record, replay, seed check ----------------------------------------------------------


def record_game(seed, cards=None):
    header = HeaderLine(
        game_id=f"g-v1.11-{seed}",
        schema_version=1,
        rules_version="v1.11",
        rounds=RS.rounds,
        seed=seed,
        mode="sim",
        seats={s: SeatInfo(kind="bot", name="random") for s in SEATS},
        ui={},
        engine_version="0.1.0",
        started_at="2026-10-20T10:00:00+02:00",
    )
    stream = io.StringIO()
    rec = GameRecorder(stream, header)
    chance = CardScript(seed, cards) if cards else RngChance(seed)
    seats = {"p1": RandomBot(seed), "p2": RandomBot(seed + 1000)}
    final = play_game(RS, seats, chance, rec.on_step)
    rec.close(final)
    return stream.getvalue(), final


def test_scripted_game_writes_reads_and_replays_to_the_same_state(tmp_path):
    cards = ["card_7", "card_3", "card_4", "card_1", "card_2", "card_5", "card_6", "card_8_to_12"]
    text, final = record_game(5, [*cards, "card_8_to_12"])
    path = tmp_path / "scripted.jsonl"
    path.write_text(text, encoding="utf-8")
    (game,) = read_games(path)
    assert verify_game(game) == []
    state = new_game(RS)
    for line in game.steps:
        state = step(state, RS, line.actions, RecordedChance(line.chance)).state
    assert state == final
    kinds = {e["kind"] for s in game.steps for e in s.events}
    assert {"card_draw", "card_drop", "card_chip"} <= kinds


def test_cli_verify_with_seed_check_passes_on_a_v1_11_record(tmp_path):
    text, _ = record_game(7)
    path = tmp_path / "game.jsonl"
    path.write_text(text, encoding="utf-8")
    (game,) = read_games(path)
    assert verify_game(game) == [] and verify_seed(game) == []
    result = CliRunner().invoke(app, ["verify", str(path), "--seed-check"])
    assert result.exit_code == 0, result.output
    assert "1 games ok" in result.output


def test_tampered_card_in_a_record_is_a_problem(tmp_path):
    text, _ = record_game(7)
    path = tmp_path / "game.jsonl"
    path.write_text(text, encoding="utf-8")
    (game,) = read_games(path)
    g = copy.deepcopy(game)
    first = next(s for s in g.steps if s.phase == "card")
    first.chance[0]["value"] = "card_7" if first.chance[0]["value"] != "card_7" else "card_1"
    assert verify_game(g) != [] or verify_seed(g) != []
