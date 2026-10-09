from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text

from quack_rl.engine import SEATS, GameState, StepResult, start_field
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
        table.add_column(column, no_wrap=True)
    for seat in SEATS:
        p = state.players[seat]
        next_ruby = next((str(f) for f in rs.rubies if f > p.field), "-")
        field_text = f"{p.field} (money {rs.money[p.field]}, next ruby {next_ruby})"
        table.add_row(
            seat,
            p.status.value,
            f"{p.droplet_halves / 2:g} → start {start_field(p, rs)}",
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


def render_step(result: StepResult) -> str:
    lines = []
    for seat in SEATS:
        action = (result.actions or {}).get(seat, "-")
        events = [e for e in result.events if e.get("seat") == seat]
        summary = ", ".join(_fields(e) for e in events)
        lines.append(f"{seat}: {action}  {summary}".rstrip())
    for e in result.events:
        if e.get("seat") is None:
            lines.append(_fields(e))
    return "\n".join(lines)
