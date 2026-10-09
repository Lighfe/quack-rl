from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text

from quack_rl.engine import SEATS, GameState, StepResult, start_field
from quack_rl.engine.state import scoring_field
from quack_rl.rules import Ruleset

CHIP_STYLE = {
    "white": "bold white",
    "orange": "bold dark_orange",
    "blue": "bold blue",
    "green": "bold green",
}


def chip_text(chip_id: str, rs: Ruleset) -> Text:
    chip = rs.chip(chip_id)
    return Text(f"{chip.colour[0].upper()}{chip.value}", style=CHIP_STYLE.get(chip.colour, ""))


def _chips(chip_ids: list[str], rs: Ruleset) -> Text:
    return Text(" ").join(chip_text(c, rs) for c in chip_ids) if chip_ids else Text("-")


def render_board(state: GameState, rs: Ruleset, bag_assist: bool) -> RenderableType:
    title = f"Round {state.round}/{rs.rounds} · {state.phase.value} · step {state.step}"
    table = Table(title=title, show_lines=True)
    for column in ("seat", "status", "droplet", "field", "white", "points", "money", "chips"):
        table.add_column(column)
    for seat in SEATS:
        p = state.players[seat]
        scoring = scoring_field(p.field, rs)
        ruby = "yes" if scoring in rs.rubies else "no"
        field_text = f"field {p.field}\nscore {scoring} · ${rs.money[scoring]}\nruby: {ruby}"
        table.add_row(
            seat,
            p.status.value,
            f"droplet {p.droplet_halves / 2:g}\nstart {start_field(p, rs)}",
            field_text,
            f"{p.white_total}/{rs.explosion_limit}",
            str(p.points),
            str(p.money),
            _chips(p.placed, rs),
        )
    parts: list[RenderableType] = [table]
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
        case "money":
            return f"+{face.amount} money"
        case "points":
            return f"+{face.points} point" + ("s" if face.points != 1 else "")
        case "droplet":
            return f"+{face.halves / 2:g} droplet"
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
