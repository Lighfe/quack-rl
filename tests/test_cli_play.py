import io
import itertools
import re
from pathlib import Path

import pytest
import typer
from helpers import RS
from rich.console import Console
from typer.testing import CliRunner

from quack_rl.cli import human
from quack_rl.cli.human import HumanSeat
from quack_rl.cli.main import app
from quack_rl.cli.render import chip_text, render_board, render_step
from quack_rl.engine import DRAW, STOP, Phase, StepResult, buy, new_game
from quack_rl.record import read_games, verify_game

runner = CliRunner()
TRACEBACK = "Traceback (most recent call last)"


def text_of(renderable, width: int = 120) -> str:
    console = Console(file=io.StringIO(), width=width, color_system=None)
    console.print(renderable)
    return console.file.getvalue()  # type: ignore[attr-defined]


def board(state=None, bag_assist=True, width: int = 120) -> str:
    return text_of(render_board(state or new_game(RS), RS, bag_assist), width)


def seat_with(keys, label="Player 1"):
    stream = io.StringIO()
    it = iter(keys)
    seat = HumanSeat(label, Console(file=stream, width=120), True, RS, read_key=lambda: next(it))
    return seat, stream


def script(monkeypatch, keys):
    it = itertools.cycle(keys)
    monkeypatch.setattr(human, "default_read_key", lambda: next(it))


def play(tmp_path, *extra, seed="4"):
    return runner.invoke(app, ["play", "--rules", "v2.1", "--seed", seed, "--out", str(tmp_path), *extra])


def play_files(tmp_path: Path) -> list[Path]:
    return sorted((tmp_path / "v2.1" / "play").glob("*.jsonl"))


def only_game(tmp_path: Path):
    (path,) = play_files(tmp_path)
    (game,) = read_games(path)
    return path, game


# --- board -------------------------------------------------------------------


def test_board_new_game_shows_round_phase_seats_and_numbers():
    text = board(width=80)
    for expected in ("Round 1/9", "brew", "p1", "p2", "brewing", "start 0", "0/7"):
        assert expected in text
    assert "next ruby" not in text
    assert "field 0" in text and "score 1 $1" in text
    assert "ruby: no" in text and "points" in text


def test_board_shows_placed_chips_and_dash_when_none():
    s = new_game(RS)
    s.players["p1"].placed = ["white_1", "orange_1"]
    for width in (80, 120):
        text = board(s, width=width)
        assert "W1 O1" in text
        assert re.search(r"│ -\s*│\s*$", text, re.MULTILINE)


def field_cell(landing: int) -> list[str]:
    """The three lines of p1's field cell when p1 is on `landing`."""
    s = new_game(RS)
    s.players["p1"].field = landing
    row = next(line for line in board(s, width=120).splitlines() if line.startswith("│ p1"))
    cells = [c.strip() for c in row.strip("│").split("│")]
    lines = [cells[3]]
    rows = board(s, width=120).splitlines()
    i = rows.index(row)
    for extra in rows[i + 1 : i + 3]:
        lines.append([c.strip() for c in extra.strip("│").split("│")][3])
    return lines


@pytest.mark.parametrize(
    ("landing", "scoring", "ruby"),
    [(4, 5, "yes"), (3, 4, "no"), (0, 1, "no"), (53, 53, "no")],
)
def test_board_field_cell_shows_scoring_field_money_and_ruby(landing, scoring, ruby):
    expected_ruby = "yes" if RS.fields[scoring].ruby else "no"
    assert expected_ruby == ruby or landing == 53
    lines = field_cell(landing)
    assert lines == [
        f"field {landing}",
        f"score {scoring} ${RS.fields[scoring].money} +{RS.fields[scoring].points}pt",
        f"ruby: {ruby}",
    ]


def test_board_past_last_ruby_shows_scoring_field_53_and_money_35():
    s = new_game(RS)
    s.players["p1"].field = 53
    for width in (80, 120):
        text = board(s, width=width)
        assert "None" not in text and "next ruby" not in text
        assert "score 53 $35" in text


def test_board_full_v1_values_fit_in_80_columns():
    s = new_game(RS)
    s.round = 9
    for seat in ("p1", "p2"):
        p = s.players[seat]
        p.field = 53
        p.money = 88
        p.points = 77
        p.droplet_halves = 99
        p.placed = ["orange_1", "blue_1", "green_1", "white_1", "orange_1", "blue_1"]
    text = board(s, width=80)
    assert max(len(line) for line in text.splitlines()) <= 80
    # the field cell stays three lines: nothing wraps
    assert text.count("field 53") == 2
    assert text.count("score 53 $35") == 2
    assert text.count("ruby: no") == 2
    row = text.splitlines()
    first = next(i for i, line in enumerate(row) if "field 53" in line)
    assert "score 53 $35" in row[first + 1] and "ruby: no" in row[first + 2]


def die_result(*events) -> StepResult:
    return StepResult(new_game(RS), 1, 1, Phase.RESOLVE, None, None, [], list(events))


def test_render_step_bonus_die_lines_one_per_roller():
    events = [
        {"seat": "p1", "kind": "die", "face": "point_2"},
        {"seat": "p2", "kind": "die", "face": "point_1"},
    ]
    lines = render_step(die_result(*events), RS).splitlines()
    assert "bonus die p1: +2 points" in lines
    assert "bonus die p2: +1 point" in lines


@pytest.mark.parametrize(
    ("face", "effect"),
    [
        ("droplet_1", "+1 droplet"),
        ("droplet_half", "+0.5 droplet"),
        ("orange_1", "+1 orange_1 chip"),
    ],
)
def test_render_step_bonus_die_effects(face, effect):
    lines = render_step(die_result({"seat": "p1", "kind": "die", "face": face}), RS).splitlines()
    assert f"bonus die p1: {effect}" in lines


def test_render_step_no_die_line_without_roll():
    text = render_step(die_result({"seat": "p1", "kind": "money", "amount": 3}), RS)
    assert "bonus die" not in text


def test_render_step_die_not_joined_with_other_seat_events():
    events = [
        {"seat": "p1", "kind": "money", "amount": 3},
        {"seat": "p1", "kind": "die", "face": "point_2"},
    ]
    lines = render_step(die_result(*events), RS).splitlines()
    assert any(line == "bonus die p1: +2 points" for line in lines)
    assert not any(line.startswith("p1:") and "die" in line for line in lines)


def test_board_bag_lines_only_with_assist():
    s = new_game(RS)
    with_bag = board(s, True)
    assert any(line.startswith("p1 bag:") and "4×W1" in line for line in with_bag.splitlines())
    assert any(line.startswith("p2 bag:") for line in with_bag.splitlines())
    assert "bag" not in board(s, False)


# --- human seat ----------------------------------------------------------------


def test_keys_map_to_legal_actions():
    legal = ["done", buy("orange_1"), buy("blue_1"), buy("green_1")]
    s = new_game(RS)
    s.phase = Phase.SHOP
    assert seat_with("2")[0].choose(s, "p1", legal) == buy("blue_1")
    assert seat_with("0")[0].choose(s, "p1", legal) == "done"
    s.phase = Phase.BREW
    assert seat_with("d")[0].choose(s, "p1", [DRAW, STOP]) == DRAW
    assert seat_with("s")[0].choose(s, "p1", [DRAW, STOP]) == STOP


def test_buy_keys_continue_with_letters():
    legal = ["done", *[buy(i.id) for i in RS.shop]]
    assert len(legal) - 1 >= 10
    seat, _ = seat_with("a")
    assert seat.choose(new_game(RS), "p1", legal) == legal[10]


def test_unknown_and_illegal_keys_try_again():
    s = new_game(RS)
    seat, stream = seat_with(["x", "0", "s", "d"])
    assert seat.choose(s, "p1", [DRAW]) == DRAW
    assert stream.getvalue().count("try again") == 3
    legal = ["done", buy("orange_1"), buy("blue_1"), buy("green_1")]
    seat, stream = seat_with(["4", "3"])
    assert seat.choose(s, "p1", legal) == buy("green_1")
    assert stream.getvalue().count("try again") == 1


def test_default_read_key_is_hidden(monkeypatch):
    seen = {}

    def fake_getchar(echo=True):
        seen["echo"] = echo
        return "d"

    monkeypatch.setattr(typer, "getchar", fake_getchar)
    assert human.default_read_key() == "d"
    assert seen["echo"] is False


def test_choose_prints_nothing_after_a_valid_key():
    stream = io.StringIO()
    it = iter(["d"])

    def read():
        before = stream.getvalue()
        key = next(it)
        read.before = before  # type: ignore[attr-defined]
        return key

    seat = HumanSeat("Player 1", Console(file=stream, width=120), True, RS, read_key=read)
    assert seat.choose(new_game(RS), "p1", [DRAW]) == DRAW
    assert stream.getvalue() == read.before  # type: ignore[attr-defined]


def test_choose_prints_board_and_menu_with_buy_details():
    s = new_game(RS)
    s.phase = Phase.SHOP
    item = RS.shop[0]
    seat, stream = seat_with("0")
    seat.choose(s, "p1", ["done", buy(item.id)])
    out = stream.getvalue()
    assert "Round 1/9" in out and "p1 bag:" in out
    assert "Player 1 (p1)" in out
    assert "[0] done" in out
    assert f"[1] buy {item.id} ({item.price})" in out


# --- play command --------------------------------------------------------------


def test_play_human_vs_bot_records_a_verifiable_game(tmp_path, monkeypatch):
    script(monkeypatch, "ds0m1")
    result = play(tmp_path)
    assert result.exit_code == 0, result.output
    assert TRACEBACK not in result.output
    assert "winner:" in result.output and "points" in result.output
    assert "p1: draw" in result.output and "p2: " in result.output  # step reveals
    assert "game_over" in result.output  # final board
    assert re.search(r"points: p1 \d+, p2 \d+", result.output)
    path, game = only_game(tmp_path)
    assert f"record: {path}" in result.output.replace("\n", "")
    assert game.header.mode == "play" and game.header.ui == {"bag_assist": True}
    assert game.header.seats["p1"].kind == "human"
    assert game.header.seats["p2"].kind == "bot"
    assert game.footer is not None
    assert verify_game(game) == []
    v = runner.invoke(app, ["verify", str(path)])
    assert v.exit_code == 0 and "1 games ok" in v.output


def test_decision_ms_only_for_human_seats(tmp_path, monkeypatch):
    script(monkeypatch, "ds0m1")
    assert play(tmp_path).exit_code == 0
    _, game = only_game(tmp_path)
    assert any("p1" in (s.decision_ms or {}) for s in game.steps)
    assert all("p2" not in (s.decision_ms or {}) for s in game.steps)


def test_no_bag_assist(tmp_path, monkeypatch):
    script(monkeypatch, "ds0m1")
    result = play(tmp_path, "--no-bag-assist")
    assert result.exit_code == 0, result.output
    _, game = only_game(tmp_path)
    assert game.header.ui == {"bag_assist": False}
    assert " bag: " not in result.output


def test_hot_seat(tmp_path, monkeypatch):
    script(monkeypatch, "ds0m1")
    result = play(tmp_path, "--p2", "human")
    assert result.exit_code == 0, result.output
    assert "Player 1 (p1)" in result.output and "Player 2 (p2)" in result.output
    _, game = only_game(tmp_path)
    assert game.header.seats["p1"].kind == "human"
    assert game.header.seats["p2"].kind == "human"
    assert any({"p1", "p2"} <= set(s.decision_ms or {}) for s in game.steps)
    assert verify_game(game) == []


def test_same_seed_and_keys_give_the_same_game(tmp_path, monkeypatch):
    games = []
    for run in ("a", "b"):
        script(monkeypatch, "ds0m1")
        assert play(tmp_path / run).exit_code == 0
        games.append(only_game(tmp_path / run)[1])
    a, b = games
    assert [s.actions for s in a.steps] == [s.actions for s in b.steps]
    assert [s.chance for s in a.steps] == [s.chance for s in b.steps]
    assert a.footer is not None and b.footer is not None
    # the game id is random per game; everything else in the footer must match
    assert a.footer.model_dump(exclude={"game_id"}) == b.footer.model_dump(exclude={"game_id"})
    assert a.footer.winner == b.footer.winner and a.footer.points == b.footer.points


def interrupting(exc, at):
    calls = itertools.count()

    def key():
        if next(calls) == at:
            raise exc
        return "d"

    return key


@pytest.mark.parametrize("exc", [KeyboardInterrupt, EOFError])
def test_abort_keeps_a_partial_record(tmp_path, monkeypatch, exc):
    monkeypatch.setattr(human, "default_read_key", interrupting(exc, 3))
    result = play(tmp_path)
    assert result.exit_code == 130, result.output
    assert TRACEBACK not in result.output
    path, game = only_game(tmp_path)
    assert f"game aborted, partial record: {path}" in result.output.replace("\n", "")
    assert game.footer is None and game.steps
    assert verify_game(game) == ["incomplete game: no footer"]


def test_abort_at_first_key_leaves_header_only(tmp_path, monkeypatch):
    monkeypatch.setattr(human, "default_read_key", interrupting(KeyboardInterrupt, 0))
    result = play(tmp_path)
    assert result.exit_code == 130, result.output
    assert "game aborted, partial record:" in result.output
    path, game = only_game(tmp_path)
    # v2.1 opens with a card step (chance only, no decision): the header and that step are written
    assert [s.actions for s in game.steps] == [None] and game.footer is None
    v = runner.invoke(app, ["verify", str(path)])
    assert v.exit_code == 1 and "incomplete game" in v.output
    assert TRACEBACK not in v.output


def test_unknown_seat_writes_no_file(tmp_path):
    result = play(tmp_path, "--p1", "bot:nope")
    assert result.exit_code != 0
    assert "bot:random" in result.output and "human" in result.output
    assert TRACEBACK not in result.output
    assert play_files(tmp_path) == []


def test_unsupported_rules_writes_no_file(tmp_path):
    result = play(tmp_path, "--rules", "v9")
    assert result.exit_code != 0
    assert "v9" in result.output and TRACEBACK not in result.output
    assert play_files(tmp_path) == []
    assert not (tmp_path / "v9").exists()


def test_simulate_still_refuses_human(tmp_path):
    result = runner.invoke(app, ["simulate", "--p1", "human", "--out", str(tmp_path)])
    assert result.exit_code != 0
    assert "quack-rl play" in result.output


def test_archived_v2_is_refused_and_names_the_known_ruleset(tmp_path):
    result = play(tmp_path, "--rules", "v2")
    assert result.exit_code != 0
    assert "v2" in result.output and "v2.1" in result.output and TRACEBACK not in result.output
    assert play_files(tmp_path) == []


def test_ruby_drop_has_its_own_key_and_no_buy_key_is_used_twice():
    from quack_rl.cli.human import BUY_KEYS, RUBY_DROP_KEY, key_map
    from quack_rl.engine import RUBY_DROP

    assert key_map(["done", RUBY_DROP])[RUBY_DROP_KEY] == RUBY_DROP
    assert RUBY_DROP_KEY not in BUY_KEYS and len(set(BUY_KEYS)) == len(BUY_KEYS)


def test_board_shows_the_ruby_count():
    assert board(width=120).count("rubies 1") == 2


def test_flask_keys_are_their_own_and_the_board_shows_the_flask():
    from quack_rl.cli.human import BUY_KEYS, REFILL_FLASK_KEY, USE_FLASK_KEY, key_map
    from quack_rl.engine import REFILL_FLASK, USE_FLASK

    assert key_map(["draw", "stop", USE_FLASK])[USE_FLASK_KEY] == USE_FLASK
    assert key_map(["done", REFILL_FLASK])[REFILL_FLASK_KEY] == REFILL_FLASK
    assert USE_FLASK_KEY not in BUY_KEYS and REFILL_FLASK_KEY not in BUY_KEYS
    assert board(width=120).count("flask full") == 2


# --- v2.1 actions: keys, texts, scripted games (issue #191) ---------------------


def test_new_actions_get_distinct_keys():
    from quack_rl.cli.human import USE_CARD_17_KEY, key_map
    from quack_rl.engine import REFILL_FLASK, RUBY_DROP, USE_FLASK
    from quack_rl.engine.actions import USE_CARD_17

    legal = [USE_FLASK, USE_CARD_17, RUBY_DROP, REFILL_FLASK]
    keys = key_map(legal)
    assert len(keys) == len(legal)
    assert keys[USE_CARD_17_KEY] == USE_CARD_17
    shop = ["done", RUBY_DROP, REFILL_FLASK, *[buy(i.id) for i in RS.shop]]
    assert len(key_map(shop)) == len(shop)


@pytest.mark.parametrize(
    "action",
    [
        "use_flask", "use_card_17", "ruby_drop", "refill_flask", "card_tails:2", "card_tails:0",
        "card_place:blue_2", "card_upgrade:green_1", "card_swap:green_1", "card_swap_no",
        "card_points", "card_remove_white", "card_chip4:red_4", "card_tail_points",
    ],
)
def test_describe_new_actions_is_short_text(action):
    seat, _ = seat_with("")
    text = seat._describe(action)
    assert text != action and 0 < len(text) <= 45


def test_play_help_names_the_three_seat_forms():
    out = runner.invoke(app, ["play", "--help"]).output
    out = " ".join(out.split())
    assert "human" in out and "bot:random" in out
    assert "bot:draw<percent>-pts<round>-<strategy>" in out


def policy_reader(monkeypatch, prefer, log):
    """Scripted keys: take each action of `prefer` once when it is legal, else a plain choice."""
    last = {}
    original = HumanSeat.choose
    used: set[str] = set()

    def spy(self, state, seat, legal):
        last["legal"] = list(legal)
        return original(self, state, seat, legal)

    def read():
        legal = last["legal"]
        by_action = {a: k for k, a in human.key_map(legal).items()}
        for action in prefer:
            if action in legal and action not in used:
                used.add(action)
                log.append(action)
                return by_action[action]
        for action in ("done", "take_money", "stop"):
            if action in legal:
                return by_action[action]
        return by_action[legal[0]]

    monkeypatch.setattr(HumanSeat, "choose", spy)
    monkeypatch.setattr(human, "default_read_key", read)


def test_scripted_game_with_heuristic_bot_uses_flask_and_ruby_drop(tmp_path, monkeypatch):
    log: list[str] = []
    policy_reader(monkeypatch, ["use_flask", "ruby_drop"], log)
    result = play(tmp_path, "--p2", "bot:draw20-pts1-points", "--rounds", "4", seed="1")
    assert result.exit_code == 0, result.output
    _, game = only_game(tmp_path)
    assert game.footer is not None and verify_game(game) == []
    assert log == ["use_flask", "ruby_drop"]
    recorded = [s.actions["p1"] for s in game.steps if s.actions and "p1" in s.actions]
    assert "use_flask" in recorded and "ruby_drop" in recorded


# --- one round for each card with a question ------------------------------------


def _card_start(card, **setup):
    s = new_game(RS)
    for seat, vals in setup.items():
        for k, v in vals.items():
            setattr(s.players[seat], k, v)
    return s


def _ask(state, expected_text, expected_action, p2=None, chance=()):
    """p1 answers with the key shown for `expected_action`; returns the state after the step."""
    from quack_rl.engine import ScriptedChance, legal_actions, step

    legal = legal_actions(state, RS, "p1")
    key = next(k for k, a in human.key_map(legal).items() if a == expected_action)
    seat, stream = seat_with(key)
    assert seat.choose(state, "p1", legal) == expected_action
    assert f"[{key}] {expected_text}" in " ".join(stream.getvalue().split())
    other = p2 or legal_actions(state, RS, "p2")[0]
    return step(state, RS, {"p1": expected_action, "p2": other}, ScriptedChance(chance)).state


def _after_card(card, bags=None, chance=(), **setup):
    from quack_rl.engine import ScriptedChance, step

    s = _card_start(card, **setup)
    for seat, bag in (bags or {}).items():
        s.players[seat].bag = dict(bag)
    return step(s, RS, None, ScriptedChance([card, *chance]))


def _finish_round(state, start_round):
    """Play the rest of the round with plain choices (stop, done, take_money, else the first legal action)."""
    from quack_rl.engine import RngChance, legal_actions, step

    chance = RngChance(7)
    for _ in range(500):
        if state.round > start_round or state.phase is Phase.GAME_OVER:
            return state
        joint = {}
        for seat in ("p1", "p2"):
            legal = legal_actions(state, RS, seat)
            if legal:
                joint[seat] = next((a for a in ("stop", "done", "take_money") if a in legal), legal[0])
        state = step(state, RS, joint or None, chance).state
    raise AssertionError("the round did not end")


def test_every_card_question_is_shown_and_its_answer_is_applied():
    from quack_rl.engine import DRAW, STOP, ScriptedChance, step

    # card 5: three rubies
    s = _after_card("card_5").state
    done = _ask(s, "3 rubies", "card_rubies")
    assert done.players["p1"].rubies == RS.start_rubies + 3
    assert _finish_round(done, done.round).round == done.round + 1
    # card 8: p1 trails by 13 points, gives up 2 rat tails
    out = _after_card("card_8", p1={"points": 0}, p2={"points": 13})
    done = _ask(out.state, "card 8: 2 rat tails for rubies", "card_tails:2")
    assert done.players["p1"].rubies > RS.start_rubies
    assert _finish_round(done, done.round).round == done.round + 1
    # card 10: both stop after one chip, p1 places one of the 5 drawn chips
    bag = {"white_1": 4, "white_2": 2, "green_1": 2}
    s = _card_start("card_10")
    s.players["p1"].bag, s.players["p2"].bag = dict(bag), dict(bag)
    s = step(s, RS, None, ScriptedChance(["card_10"])).state
    s = step(s, RS, {"p1": DRAW, "p2": DRAW}, ScriptedChance(["white_1", "white_1"])).state
    drawn = ["green_1", "green_1", "white_1", "white_2", "white_2"]
    p2_drawn = ["white_1", "white_1", "white_1", "white_2", "white_2"]
    out = step(s, RS, {"p1": STOP, "p2": STOP}, ScriptedChance([*drawn, *p2_drawn]))
    chip = chip_text("green_1", RS).plain
    done = _ask(out.state, f"card 10: place {chip}", "card_place:green_1")
    assert done.phase is not Phase.CARD_CHOICE
    assert "green_1" in done.players["p1"].placed
    assert _finish_round(done, done.round).round == done.round + 1
    # card 11: upgrade green_1 to green_2
    b11 = {"white_1": 4, "white_2": 1, "yellow_2": 1, "green_1": 1, "white_3": 1}
    out = _after_card("card_11", {"p1": b11}, ["white_1", "white_2", "yellow_2", "green_1"] + ["white_1"] * 4)
    chip = chip_text("green_1", RS).plain
    done = _ask(out.state, f"card 11: upgrade {chip}", "card_upgrade:green_1")
    assert done.players["p1"].bag["green_2"] == 1
    assert _finish_round(done, done.round).round == done.round + 1
    # card 12: a ruby for a white 1
    out = _after_card("card_12", p2={"rubies": 0})
    before = out.state.players["p1"].rubies
    done = _ask(out.state, "card 12: ruby for a white 1", "card_swap:white_1")
    assert done.players["p1"].rubies == before - 1
    assert _finish_round(done, done.round).round == done.round + 1
    # card 14: 4 points
    out = _after_card("card_14")
    done = _ask(out.state, "card 14: 4 points", "card_points")
    assert done.players["p1"].points == 4
    assert _finish_round(done, done.round).round == done.round + 1
    # card 19: a value-4 chip
    out = _after_card("card_19")
    done = _ask(out.state, "card 19: a green 4 into the bag", "card_chip4:green_4")
    assert done.players["p1"].bag["green_4"] == 1
    assert _finish_round(done, done.round).round == done.round + 1


def test_scripted_card_17_decision_puts_the_first_white_chip_back():
    from quack_rl.engine import DRAW, ScriptedChance, legal_actions, step
    from quack_rl.engine.actions import USE_CARD_17

    s = new_game(RS)
    s.players["p1"].bag = s.players["p2"].bag = {"white_1": 4, "white_2": 2, "green_1": 2}
    s = step(s, RS, None, ScriptedChance(["card_17"])).state
    for p in s.players.values():
        p.flask_full = False
    s = step(s, RS, {"p1": DRAW, "p2": DRAW}, ScriptedChance(["white_2", "white_1"])).state
    legal = legal_actions(s, RS, "p1")
    assert USE_CARD_17 in legal
    done = _ask(s, "card 17: first white chip back to bag", USE_CARD_17, p2=DRAW, chance=["white_1"])
    assert done.players["p1"].placed == []


def test_board_shows_rubies_flask_and_the_card_line_but_no_hidden_hand():
    from quack_rl.engine import ScriptedChance, step

    s = step(new_game(RS), RS, None, ScriptedChance(["card_14"])).state
    s.players["p1"].rubies, s.players["p2"].rubies = 3, 0
    s.players["p2"].flask_full = False
    s.players["p2"].hand = ["yellow_2"]
    text = board(s)
    assert "rubies 3" in text and "rubies 0" in text
    assert "flask full" in text and "flask empty" in text
    from quack_rl.rules.cards import get_card_effect

    description = get_card_effect(RS.card("card_14").effect).description
    assert description and f"card: card_14 ({description})" in text and "deck:" in text
    assert "hand" not in text and "Y2" not in text
