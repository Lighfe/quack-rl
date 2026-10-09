"""Balance report: reads `results.csv` and `config.json` of a tournament run, nothing else."""

import csv
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from quack_rl.bots import parse_bot_name
from quack_rl.bots.heuristic import BASELINE_NAME
from quack_rl.rules import Ruleset
from quack_rl.tournament import BASE_COLUMNS, SEAT_CHECK_PREFIX, Sweep, TournamentConfig, _rules_for

Z95 = 1.959964  # two-sided 95% normal quantile
SWEEP_STRATEGIES = ("blue", "green", "cleaner", "balanced")
NEEDED_COLUMNS = [*BASE_COLUMNS, "p1_draws", "p2_draws"]
_BUY = re.compile(r"p1_buy_(.+)")


class ReportError(ValueError):
    """The run folder cannot be reported."""


def wilson(wins: float, n: int) -> tuple[float, float]:
    """95% Wilson score interval of `wins` out of `n`, as fractions. `wins` may be a half."""
    if n <= 0:
        return 0.0, 1.0
    p = wins / n
    z2 = Z95 * Z95
    centre = (p + z2 / (2 * n)) / (1 + z2 / n)
    half = Z95 * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / (1 + z2 / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def baseline_maximum(rs: Ruleset) -> float:
    """Upper bound of the final points of a bot that buys only points items.

    Assumptions (a bound, not a number a 30% draw limit can reach):
    - in every round the bot ends on the best money field of the track and rolls the best
      money die face, so its money is `max(money) + max money face`; the last round is
      multiplied by `last_round_money_percent // 100`, as the rules do;
    - in every round it also rolls the best points die face (no money from that roll then, which
      the bound ignores: both are added, so the bound stays an upper bound);
    - money does not carry over (it resets every round), so each round is independent: with
      that money and at most `max_purchases` purchases it buys the points items that give the
      most points (a knapsack over the points items of the shop, items may repeat).
    The maximum is the sum over all rounds of (best purchase points + best die points).
    """
    items = [(i.price, i.points) for i in rs.shop if i.kind == "points"]
    money_faces = [f.amount for f in rs.die if f.kind == "money"]
    point_faces = [f.points for f in rs.die if f.kind == "points"]
    base_money = max(rs.money) + max(money_faces, default=0)
    die_points = max(point_faces, default=0)
    total = 0
    for round_no in range(1, rs.rounds + 1):
        money = base_money
        if round_no == rs.rounds:
            money = money * rs.last_round_money_percent // 100
        # best[k][m]: most points with k purchases and at most m money
        best = [[0] * (money + 1) for _ in range(rs.max_purchases + 1)]
        for k in range(1, rs.max_purchases + 1):
            for m in range(money + 1):
                best[k][m] = best[k - 1][m]
                for price, points in items:
                    if price <= m:
                        best[k][m] = max(best[k][m], best[k - 1][m - price] + points)
        total += best[rs.max_purchases][money] + die_points
    return float(total)


@dataclass
class Agg:
    """Sums over seat-games: wins are counted in halves, so a draw is one half-win."""

    games: int = 0
    halves: int = 0  # 2 per win, 1 per draw
    points: int = 0
    explosions: int = 0
    potions: int = 0

    def add(self, win_halves: int, points: int, explosions: int, rounds: int) -> None:
        self.games += 1
        self.halves += win_halves
        self.points += points
        self.explosions += explosions
        self.potions += rounds

    def merge(self, other: "Agg") -> None:
        self.games += other.games
        self.halves += other.halves
        self.points += other.points
        self.explosions += other.explosions
        self.potions += other.potions

    @property
    def rate(self) -> float:
        return self.halves / 2 / self.games if self.games else 0.0

    @property
    def avg_points(self) -> float:
        return self.points / self.games if self.games else 0.0


def fmt_rate(halves: int, n: int) -> str:
    """Win rate with interval and number of games, in percent."""
    if n == 0:
        return "-"
    lo, hi = wilson(halves / 2, n)
    return f"{100 * halves / 2 / n:.1f}% [{100 * lo:.1f}-{100 * hi:.1f}%] n={n}"


def fmt_share(part: int, whole: int) -> str:
    return f"{100 * part / whole:.1f}%" if whole else "-"


def fmt_cell(a: Agg | None) -> str:
    if a is None or a.games == 0:
        return "-"
    return (
        f"{fmt_rate(a.halves, a.games)} | expl {fmt_share(a.explosions, a.potions)}"
        f" | pts {a.avg_points:.1f}"
    )


def table(headers: list[str], rows: list[list[str]]) -> list[str]:
    widths = [max(len(r[i]) for r in [headers, *rows]) for i in range(len(headers))]

    def line(cells: list[str]) -> str:
        return "  ".join(c.ljust(w) for c, w in zip(cells, widths, strict=True)).rstrip()

    return [line(headers), *(line(r) for r in rows)]


@dataclass
class Data:
    """What the report needs from one run, in plain numbers."""

    rounds: int
    buy_items: list[str]
    bots: dict[str, Agg] = field(default_factory=dict)
    games: int = 0
    seat: Agg = field(default_factory=Agg)  # p1 view of the seat check rows
    seat_draws: int = 0
    # strategy label -> item -> purchases in won seat-games, and the number of won seat-games
    won_buys: dict[str, dict[str, int]] = field(default_factory=dict)
    won_games: dict[str, int] = field(default_factory=dict)
    # strategy label -> (games with the strategy, draws summed over both seats)
    length: dict[str, list[int]] = field(default_factory=dict)
    all_length: list[int] = field(default_factory=lambda: [0, 0])
    baseline_rows: dict[str, int] = field(default_factory=dict)  # sweep_value -> games
    baseline_points: int = 0


def label_of(bot: str) -> str:
    """Strategy of a bot name, `random` for the random bot."""
    try:
        return parse_bot_name(bot)[2]
    except ValueError:
        return bot


def _int(row: dict[str, str], column: str, line: int) -> int:
    try:
        return int(row[column])
    except ValueError:
        raise ReportError(f"results.csv line {line}: {column!r} is not a whole number") from None


def load(folder: Path) -> tuple[Data, dict[str, Any]]:
    """Read results.csv and config.json of a run folder."""
    results = folder / "results.csv"
    if not results.is_file():
        raise ReportError(f"no results.csv in {folder}")
    config_path = folder / "config.json"
    if not config_path.is_file():
        raise ReportError(f"no config.json in {folder}")
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        rounds = int(config["rounds"])
    except (ValueError, KeyError, TypeError):
        raise ReportError(f"config.json in {folder} has no valid 'rounds'") from None
    with results.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames or []
        for column in NEEDED_COLUMNS:
            if column not in columns:
                raise ReportError(f"results.csv in {folder} lacks the column {column!r}")
        buy_items = [m[1] for c in columns if (m := _BUY.fullmatch(c))]
        if not buy_items:
            raise ReportError(f"results.csv in {folder} lacks the columns 'p1_buy_<item>'")
        for item in buy_items:
            if f"p2_buy_{item}" not in columns:
                raise ReportError(f"results.csv in {folder} lacks the column 'p2_buy_{item}'")
        rows = list(reader)
    if not rows:
        raise ReportError(f"results.csv in {folder} has no games")

    data = Data(rounds=rounds, buy_items=buy_items)
    for n, row in enumerate(rows, start=2):
        winner = row["winner"]
        points = {s: _int(row, f"{s}_points", n) for s in ("p1", "p2")}
        expl = {s: _int(row, f"{s}_explosions", n) for s in ("p1", "p2")}
        draws = {s: _int(row, f"{s}_draws", n) for s in ("p1", "p2")}
        halves = {s: 2 if winner == s else 1 if winner == "draw" else 0 for s in ("p1", "p2")}
        if row["pairing"].startswith(SEAT_CHECK_PREFIX):
            data.seat.add(halves["p1"], points["p1"], expl["p1"], rounds)
            data.seat_draws += winner == "draw"
            continue
        data.games += 1
        bots = {"p1": row["p1"], "p2": row["p2"]}
        for seat, bot in bots.items():
            data.bots.setdefault(bot, Agg()).add(halves[seat], points[seat], expl[seat], rounds)
            label = label_of(bot)
            if winner == seat:
                data.won_games[label] = data.won_games.get(label, 0) + 1
                bucket = data.won_buys.setdefault(label, dict.fromkeys(buy_items, 0))
                for item in buy_items:
                    bucket[item] += _int(row, f"{seat}_buy_{item}", n)
            if bot == BASELINE_NAME:
                data.baseline_rows[row["sweep_value"]] = (
                    data.baseline_rows.get(row["sweep_value"], 0) + 1
                )
                data.baseline_points += points[seat]
        total = draws["p1"] + draws["p2"]
        for label in {label_of(b) for b in bots.values()}:
            entry = data.length.setdefault(label, [0, 0])
            entry[0] += 1
            entry[1] += total
        data.all_length[0] += 1
        data.all_length[1] += total
    return data, config


def _by_params(data: Data, strategy: str) -> dict[tuple[int, int], Agg]:
    """Per (draw limit, points round): the sum over the bots of one strategy."""
    out: dict[tuple[int, int], Agg] = {}
    for bot, agg in data.bots.items():
        try:
            draw_limit, points_round, strat = parse_bot_name(bot)
        except ValueError:
            continue
        if strat == strategy:
            out.setdefault((draw_limit, points_round), Agg()).merge(agg)
    return out


def section_ranking(data: Data) -> list[str]:
    ranked = sorted(data.bots.items(), key=lambda kv: (-kv[1].rate, -kv[1].avg_points, kv[0]))
    rows = [
        [bot, str(a.games), fmt_rate(a.halves, a.games), f"{a.avg_points:.1f}"] for bot, a in ranked
    ]
    out = ["== Ranking ==", "Sorted by win rate, then average final points (a draw is half a win)."]
    if not rows:
        return [*out, "No games."]
    return [*out, *table(["bot", "games", "win rate", "avg points"], rows)]


def section_sweeps(data: Data) -> list[str]:
    out: list[str] = []
    for strategy in SWEEP_STRATEGIES:
        cells = _by_params(data, strategy)
        if not cells:
            continue
        out += [f"== Sweeps: {strategy} =="]
        for title, index in (("by draw limit", 0), ("by points round", 1)):
            grouped: dict[int, Agg] = {}
            for key, agg in cells.items():
                grouped.setdefault(key[index], Agg()).merge(agg)
            out += [
                f"-- {strategy}: {title} --",
                *table(
                    ["draw limit" if index == 0 else "points round", "cell"],
                    [[str(k), fmt_cell(grouped[k])] for k in sorted(grouped)],
                ),
            ]
        limits = sorted({k[0] for k in cells})
        rounds = sorted({k[1] for k in cells})
        out += [
            f"-- {strategy}: draw limit (rows) x points round (columns) --",
            *table(
                ["draw limit", *[f"pts {r}" for r in rounds]],
                [[str(d), *[fmt_cell(cells.get((d, r))) for r in rounds]] for d in limits],
            ),
        ]
    if not out:
        return ["== Sweeps ==", "No heuristic bot of the four strategies in this run."]
    return out


def section_items(data: Data) -> list[str]:
    present = sorted({label_of(b) for b in data.bots}, key=_label_key)
    out = [
        "== Item usage of winning bots ==",
        "Average purchases per game by item, only in games the bot seat won.",
    ]
    if not present:
        return [*out, "No games."]
    rows = [
        [
            item,
            *[
                f"{data.won_buys[s][item] / data.won_games[s]:.2f}"
                if data.won_games.get(s)
                else "-"
                for s in present
            ],
        ]
        for item in data.buy_items
    ]
    rows.append(["won games", *[str(data.won_games.get(s, 0)) for s in present]])
    return [*out, *table(["item", *present], rows)]


def _label_key(label: str) -> tuple[int, str]:
    order = [*SWEEP_STRATEGIES, "points", "random"]
    return (order.index(label) if label in order else len(order), label)


def section_explosions(data: Data) -> list[str]:
    expl = sum(a.explosions for a in data.bots.values())
    potions = sum(a.potions for a in data.bots.values())
    by_label: dict[str, Agg] = {}
    for bot, agg in data.bots.items():
        by_label.setdefault(label_of(bot), Agg()).merge(agg)
    out = [
        "== Explosion share and game length ==",
        "Explosion share: exploded potions / potions played. Game length: draws of both seats"
        " summed, averaged over the games the strategy played in.",
    ]
    rows = [
        [
            s,
            fmt_share(by_label[s].explosions, by_label[s].potions),
            f"{data.length[s][1] / data.length[s][0]:.2f}",
        ]
        for s in sorted(by_label, key=_label_key)
    ]
    n, total = data.all_length
    rows.append(
        ["overall", fmt_share(expl, potions), f"{total / n:.2f}" if n else "-"],
    )
    return [*out, *table(["strategy", "explosion share", "draws per game"], rows)]


def section_seat(data: Data) -> list[str]:
    out = ["== Seat check =="]
    n = data.seat.games
    if n == 0:
        return [*out, "Seat check: no seatcheck run in this folder"]
    h1 = data.seat.halves
    lo, hi = wilson(h1 / 2, n)
    verdict = "OK" if lo <= 0.5 <= hi else "DEVIATION"
    return [
        *out,
        f"p1 win rate: {fmt_rate(h1, n)}",
        f"p2 win rate: {fmt_rate(2 * n - h1, n)}",
        f"draw share: {fmt_share(data.seat_draws, n)} of {n} games",
        f"Seat check: {verdict} (50% {'inside' if verdict == 'OK' else 'outside'} the interval"
        " of the p1 win rate)",
    ]


def section_baseline(data: Data, config: dict[str, Any]) -> list[str]:
    out = ["== Baseline =="]
    n = sum(data.baseline_rows.values())
    if n == 0:
        return [*out, f"Baseline {BASELINE_NAME} is not in this run."]
    sweep = config.get("sweep")
    cfg = TournamentConfig(
        bots=(),
        games=1,
        seed=0,
        rules=config.get("rules", "v1"),
        rounds=data.rounds,
        overrides=dict(config.get("overrides") or {}),
        sweep=Sweep(sweep["param"], tuple(sweep["values"])) if sweep else None,
    )
    try:
        maximum = (
            sum(baseline_maximum(_rules_for(cfg, v)) * g for v, g in data.baseline_rows.items()) / n
        )
    except (ValueError, KeyError, TypeError) as e:
        raise ReportError(f"config.json cannot be turned into a ruleset: {e}") from None
    simulated = data.baseline_points / n
    return [
        *out,
        f"Baseline {BASELINE_NAME}: {n} games",
        f"Simulated average final points: {simulated:.1f}",
        f"Calculated maximum (upper bound, see baseline_maximum): {maximum:.1f}",
        f"Difference (maximum - simulated): {maximum - simulated:.1f}",
    ]


def build_report(folder: Path) -> str:
    """The report text of a run folder. Raises ReportError."""
    data, config = load(folder)
    head = [
        f"Balance report: {folder.resolve().name}",
        f"Games: {data.games} (seat check games: {data.seat.games}), "
        f"rounds per game: {data.rounds}",
    ]
    sections = [
        head,
        section_ranking(data),
        section_sweeps(data),
        section_items(data),
        section_explosions(data),
        section_seat(data),
        section_baseline(data, config),
    ]
    return "\n\n".join("\n".join(s) for s in sections) + "\n"


def write_report(folder: Path) -> str:
    """Build the report, write it to `<folder>/report.txt` and return it."""
    text = build_report(folder)
    (folder / "report.txt").write_text(text, encoding="utf-8", newline="")
    return text


__all__ = ["ReportError", "build_report", "write_report", "wilson", "baseline_maximum"]
