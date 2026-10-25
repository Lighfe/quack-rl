from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text

from quack_rl.engine import SEATS, GameState, StepResult, explosion_limit, start_field
from quack_rl.engine.state import scoring_field
from quack_rl.rules import Ruleset
from quack_rl.rules.cards import get_card_effect

CHIP_STYLE = {
    "white": "bold white",
    "orange": "bold dark_orange",
    "blue": "bold blue",
    "green": "bold green",
    "red": "bold red",
    "black": "bold black on white",
    "yellow": "bold yellow",
    "purple": "bold magenta",
}
# First letter of the colour, except black: "B" is blue's.
CHIP_LETTER = {"black": "K"}


def chip_text(chip_id: str, rs: Ruleset) -> Text:
    chip = rs.chip(chip_id)
    return Text(
        f"{CHIP_LETTER.get(chip.colour, chip.colour[0].upper())}{chip.value}",
        style=CHIP_STYLE.get(chip.colour, ""),
    )


def hand_text(chip_ids: list[str], rs: Ruleset) -> Text:
    return Text("hand: ") + _chips(chip_ids, rs)


def draw_text(chip_ids: list[str], rs: Ruleset) -> Text:
    """Card 11: the chips a player drew; only the choosing player is shown this line."""
    return Text("drawn: ") + _chips(chip_ids, rs)


def _chips(chip_ids: list[str], rs: Ruleset) -> Text:
    return Text(" ").join(chip_text(c, rs) for c in chip_ids) if chip_ids else Text("-")


def card_line(state: GameState, rs: Ruleset) -> str:
    """The card of the round and the cards still in the deck."""
    if state.card is None:
        card = "-"
    else:
        spec = rs.card(state.card)
        card = f"{spec.id} ({get_card_effect(spec.effect).description})"
    return f"card: {card}   deck: {len(state.deck)} left"


def render_board(state: GameState, rs: Ruleset, bag_assist: bool) -> RenderableType:
    title = f"Round {state.round}/{rs.rounds} · {state.phase.value} · step {state.step}"
    table = Table(title=title, show_lines=True)
    for column in ("seat", "status", "droplet", "field", "white", "points", "money", "chips"):
        table.add_column(column, no_wrap=column in ("droplet", "field"))
    for seat in SEATS:
        p = state.players[seat]
        scoring = scoring_field(p.field, rs)
        ruby = "yes" if rs.fields[scoring].ruby else "no"
        gain = f" +{rs.fields[scoring].points}pt"
        field_text = (
            f"field {p.field}\nscore {scoring} ${rs.fields[scoring].money}{gain}\nruby: {ruby}"
        )
        tail = f" (rat tail +{p.rat_tail})" if p.rat_tail > 0 else ""
        table.add_row(
            seat,
            p.status.value,
            f"drop {p.droplet_halves / 2:g}\nstart {start_field(p, rs)}{tail}",
            field_text,
            f"{p.white_total}/{explosion_limit(state, rs)}",
            str(p.points),
            f"{p.money}\nrubies {p.rubies}\nflask {'full' if p.flask_full else 'empty'}",
            _chips(p.placed, rs),
        )
    parts: list[RenderableType] = [table]
    parts.append(Text(card_line(state, rs)))
    if state.round == rs.rounds:
        parts.append(
            Text(
                f"Round {rs.rounds}: money becomes points (money // {rs.last_round_money_divisor})"
            )
        )
    if bag_assist:
        for seat in SEATS:
            bag = state.players[seat].bag
            content = Text(" ").join(
                Text(f"{n}×") + chip_text(c, rs) for c, n in sorted(bag.items()) if n > 0
            )
            parts.append(Text(f"{seat} bag: ") + content)
    return Group(*parts)


def _fields(event: dict, skip: tuple[str, ...] = ("seat",)) -> str:
    return " ".join(f"{k}={v}" for k, v in event.items() if k not in skip)


def _die_effect(face_id: str, rs: Ruleset) -> str:
    face = next(f for f in rs.die if f.id == face_id)
    match face.kind:
        case "points":
            return f"+{face.points} point" + ("s" if face.points != 1 else "")
        case "droplet":
            return f"+{face.halves / 2:g} droplet"
        case "rubies":
            return f"+{face.rubies} ruby" + ("s" if face.rubies != 1 else "")
        case _:
            return f"+1 {face.chip} chip"


def render_step(result: StepResult, rs: Ruleset) -> str:
    lines = []
    for seat in SEATS:
        action = (result.actions or {}).get(seat, "-")
        events = [e for e in result.events if e.get("seat") == seat and e.get("kind") != "die"]
        summary = ", ".join(_fields(e) for e in events)
        lines.append(f"{seat}: {action}  {summary}".rstrip())
    for e in result.events:
        if e.get("kind") == "die":
            lines.append(f"bonus die {e['seat']}: {_die_effect(e['face'], rs)}")
    for e in result.events:
        if e.get("seat") is None:
            lines.append(_fields(e))
    return "\n".join(lines)
