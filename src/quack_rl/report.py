"""Balance report: reads `results.csv` and `config.json` of a tournament run, nothing else."""

import csv
import json
import math
from dataclasses import dataclass, field
from fractions import Fraction
from functools import lru_cache
from pathlib import Path
from typing import Any

from quack_rl.bots import parse_bot_name
from quack_rl.bots.heuristic import BASELINE_NAME
from quack_rl.components import Component, get_component, pot_effects
from quack_rl.rules import Ruleset, load_ruleset
from quack_rl.tournament import BASE_COLUMNS, SEAT_CHECK_PREFIX, Sweep, TournamentConfig, _rules_for

Z95 = 1.959964  # two-sided 95% normal quantile
SWEEP_STRATEGIES = ("blue", "green", "cleaner", "balanced")
NEEDED_COLUMNS = [*BASE_COLUMNS, "p1_draws", "p2_draws"]


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
    """Loose upper bound of the final points of any bot: the `max_points` cap of the board.

    This is a loose bound that no bot reaches. The number of the field table for the baseline
    is `realistic_baseline_maximum`.
    """
    return float(rs.point_board.max_points)


CONFIRM_TEST = "tests/test_baseline_maximum.py"

_Bag = tuple[tuple[str, int], ...]


def _round_limits(rs: Ruleset) -> list[tuple[int, Fraction]]:
    """The explosion limits a round can have, with their chance (card 4).

    One card is drawn per round without replacement, so each round has the same chance for a
    card: its share of the deck. Only the limit of card 4 is part of the calculated maximum;
    the other card effects are not."""
    total = sum(c.count for c in rs.cards)
    plus = sum(c.count for c in rs.cards if c.effect == "explosion_limit_plus_2")
    limits = [(rs.explosion_limit, Fraction(total - plus, total))]
    if plus:
        limits.append((rs.explosion_limit + 2, Fraction(plus, total)))
    return [(limit, chance) for limit, chance in limits if chance]


def _brew_outcomes(
    rs: Ruleset,
    bag: _Bag,
    draw_limit: int,
    fractions: set[Fraction] | None = None,
    limit: int | None = None,
) -> dict[tuple[int, bool, int, int], float]:
    """Chance of each end of a brew for a bot with `draw_limit`.

    The key is (advance, exploded, droplet halves, points). The bot rule of `HeuristicBot`: the
    first chip is always drawn; then it stops when the chance to explode is more than the draw
    limit. A brew also ends on an explosion or an empty bag. The advance is the sum of the chip
    advances (blue bonus included), so the final field is `min(start field + advance, track_end)`.
    The halves are the droplet halves of the pot effects (black, purple); the points are the pot
    effects' points. Rubies (green, black, purple) do not move the droplet, so the chain ignores
    them.

    The hooks get the inputs the engine gives them: `puts_back_previous(chip, previous)` at each
    placement (a put-back chip returns to the bag and its explosion weight leaves the total, as
    in `engine/brew.py`) and `pot_effects` at the end (same function as `apply_resolve`). The
    odds are for one player, so the other pot is empty (a black chip then counts as the larger
    pot). When no chip of the bag has such a hook, only the last two chips are tracked.

    `limit` is the explosion limit of the round (card 4); the ruleset limit when None.
    """
    limit = rs.explosion_limit if limit is None else limit
    # With `fractions`, the explosion chances (in percent) met at the stop decisions are added.
    memo: dict[tuple, dict[tuple[int, bool, int, int], float]] = {}
    chips = {chip.id: chip for chip in rs.chips}
    parts = {i: get_component(rs.component_name(c)) for i, c in chips.items()}
    weight = {i: parts[i].explosion_weight(c) for i, c in chips.items()}
    tracked = any(
        type(parts[i]).puts_back_previous is not Component.puts_back_previous
        or type(parts[i]).pot_round_end is not Component.pot_round_end
        for i, _ in bag
    )

    def end_bonus(pot: tuple[str, ...]) -> tuple[int, int]:
        halves = points = 0
        if tracked:
            for _, effect in pot_effects(rs, pot, ()):
                halves += effect.droplet_halves
                points += effect.points
        return halves, points

    def place(chip_id: str, white: int, pot: tuple[str, ...]) -> tuple[int, tuple[str, ...], bool]:
        """(white total, pot, put back?) after placing the chip, as the engine does."""
        previous = chips[pot[-1]] if pot else None
        new_white = white + weight[chip_id]
        put_back = parts[chip_id].puts_back_previous(chips[chip_id], previous)
        if put_back:
            new_white -= weight[pot[-1]]
            new_pot = (*pot[:-1], chip_id)
        else:
            new_pot = (*pot, chip_id)
        return new_white, new_pot if tracked else new_pot[-2:], put_back

    def go(
        remaining: _Bag, white: int, pot: tuple[str, ...]
    ) -> dict[tuple[int, bool, int, int], float]:
        """Outcomes from this state on; the advance counts from now."""
        key = (remaining, white, pot)
        if key in memo:
            return memo[key]
        size = sum(n for _, n in remaining)
        out: dict[tuple[int, bool, int, int], float] = {}
        if pot:
            bad = sum(n for i, n in remaining if place(i, white, pot)[0] > limit)
            if fractions is not None:
                fractions.add(Fraction(100 * bad, size))
            if bad * 100 > draw_limit * size:
                out[(0, False, *end_bonus(pot))] = 1.0
                memo[key] = out
                return out
        previous = chips[pot[-1]] if pot else None
        for chip_id, count in remaining:
            chip = chips[chip_id]
            if tracked:
                gain = chip.value + parts[chip_id].place_bonus(
                    chip, previous, [chips[c] for c in pot]
                )
            else:
                gain = chip.value + parts[chip_id].place_bonus(chip, previous)
            new_white, new_pot, put_back = place(chip_id, white, pot)
            chance = count / size
            if new_white > limit:
                results = {(0, True, *end_bonus(new_pot)): 1.0}
            else:
                left = dict(remaining)
                left[chip_id] -= 1
                if put_back:
                    left[pot[-1]] = left.get(pot[-1], 0) + 1
                new_remaining = tuple(sorted((i, n) for i, n in left.items() if n > 0))
                if new_remaining:
                    results = go(new_remaining, new_white, new_pot)
                else:
                    results = {(0, False, *end_bonus(new_pot)): 1.0}
            for (advance, exploded, halves, points), p in results.items():
                outcome = (advance + gain, exploded, halves, points)
                out[outcome] = out.get(outcome, 0.0) + chance * p
        memo[key] = out
        return out

    return go(bag, 0, ())


def _bags(rs: Ruleset) -> list[_Bag]:
    """Every bag a player can start a round with: the start bag plus chips of the die faces."""
    gifts = sorted({f.chip for f in rs.die if f.kind == "chip" and f.chip is not None})
    seen = {tuple(sorted(rs.start_bag.items()))}
    frontier = set(seen)
    for _ in range(rs.rounds - 1):
        step: set[_Bag] = set()
        for bag in frontier:
            for gift in gifts:
                counts = dict(bag)
                counts[gift] = counts.get(gift, 0) + 1
                step.add(tuple(sorted(counts.items())))
        frontier = step - seen
        seen |= step
    return sorted(seen)


def _draw_limit_classes(rs: Ruleset) -> list[int]:
    """One draw limit (0 to 100 percent) for each way the limit can change the bot's choices.

    The bot stops when the explosion chance in percent is more than the limit, so two limits
    act the same when the same chances lie above both.
    """
    chances: set[Fraction] = set()
    for bag in _bags(rs):
        for limit, _ in _round_limits(rs):
            # at 100 the bot never stops: all states are met
            _brew_outcomes(rs, bag, 100, chances, limit)
    reps: dict[int, int] = {}
    for limit in range(101):
        reps.setdefault(sum(1 for c in chances if c <= limit), limit)
    return sorted(reps.values())


def _expected_points(rs: Ruleset, draw_limit: int) -> float:
    """Average final points of the `points` bot (points round 1) with one draw limit.

    The chain state is (droplet halves, bag, points). The points follow the engine order of a
    round: pot effects, the bonus die face, the points of the scoring field, and in the last
    round money // `last_round_money_divisor` (an exploded potion takes the points of the field
    instead of the money). The total stops at `max_points` after every step. The bot buys no
    chips, so the bag only grows by die chip faces.
    """
    start = tuple(sorted(rs.start_bag.items()))
    die_total = sum(f.weight for f in rs.die)
    cap = rs.point_board.max_points
    brews: dict[tuple[_Bag, int], dict[tuple[int, bool, int, int], float]] = {}
    # (droplet halves, bag, points) -> chance
    states: dict[tuple[int, _Bag, int], float] = {(0, start, 0): 1.0}
    for round_number in range(1, rs.rounds + 1):
        nxt: dict[tuple[int, _Bag, int], float] = {}
        for (halves, bag, points), p_state in states.items():
            begin = min(halves // 2, rs.track_end)
            for limit, p_limit in _round_limits(rs):
                if (bag, limit) not in brews:
                    brews[bag, limit] = _brew_outcomes(rs, bag, draw_limit, None, limit)
                for (advance, exploded, green, pot_points), p_brew in brews[bag, limit].items():
                    p = p_state * p_brew * float(p_limit)
                    scoring = min(min(begin + advance, rs.track_end) + 1, rs.track_end)
                    field = rs.fields[scoring]
                    base_halves = halves + green
                    after_pot = min(points + pot_points, cap)
                    faces = [None] if exploded else rs.die  # an exploded potion never rolls
                    for face in faces:
                        chance = p if face is None else p * face.weight / die_total
                        new_halves, new_bag, total = base_halves, bag, after_pot
                        if face is not None:
                            if face.kind == "droplet":
                                new_halves += face.halves
                            elif face.kind == "chip" and face.chip is not None:
                                counts = dict(bag)
                                counts[face.chip] = counts.get(face.chip, 0) + 1
                                new_bag = tuple(sorted(counts.items()))
                            elif face.kind == "points":
                                total = min(total + face.points, cap)
                        total = min(total + field.points, cap)
                        if round_number == rs.rounds and not exploded:
                            total = min(total + field.money // rs.last_round_money_divisor, cap)
                        key = (new_halves, new_bag, total)
                        nxt[key] = nxt.get(key, 0.0) + chance
        states = nxt
    return sum(chance * points for (_, _, points), chance in states.items())


def realistic_baseline_maximum(rs: Ruleset) -> float:
    """Points of the field table, without chip purchases and cards.

    The best average final points of a bot with strategy `points` that plays alone and buys no
    chips. The bot has any draw limit (0 to 100 percent) and points round 1. The number is
    calculated from the ruleset only, no simulation: for each draw limit, the chance of every
    end of a brew is summed over all draw orders of the bag, and the rounds are followed as a
    chain over (droplet position, bag, points); the result is the best draw limit.

    It is not an upper bound of the real baseline bot: that bot buys chips, and cards add points
    that this number does not have. `tests/test_baseline_maximum.py` compares it with a
    simulation without chip purchases and allows a margin for the cards.

    Assumptions:
    - the bot plays alone: it always rolls the bonus die when its potion did not explode;
    - an exploded potion does not roll the die and takes the points of its field;
    - points: pot effects, die points, field points, and in the last round money divided by
      `last_round_money_divisor`; the total stops at `max_points`;
    - the droplet moves by the pot effects (black, purple) and die faces; rubies are not
      spent (no ruby drop, no flask refill); the die chip faces add chips
      to the bag;
    - the explosion limit of a round is the ruleset limit, or +2 with card 4, weighted by
      the share of card 4 in the deck. The other card effects are not in the number.
    """
    return _realistic_cached(rs.model_dump_json())


@lru_cache(maxsize=32)
def _realistic_cached(ruleset_json: str) -> float:
    rs = Ruleset.model_validate_json(ruleset_json)
    return max(_expected_points(rs, limit) for limit in _draw_limit_classes(rs))


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
        try:
            buy_items = [item.id for item in load_ruleset(config.get("rules", "v2.1")).shop]
        except (ValueError, KeyError, TypeError, OSError) as e:
            raise ReportError(f"config.json in {folder} names no usable ruleset: {e}") from None
        for item in buy_items:
            for seat in ("p1", "p2"):
                if f"{seat}_buy_{item}" not in columns:
                    raise ReportError(
                        f"results.csv in {folder} lacks the column '{seat}_buy_{item}'"
                    )
        rows = list(reader)
    if not rows:
        raise ReportError(f"results.csv in {folder} has no games")

    data = Data(rounds=rounds, buy_items=buy_items)
    seat_data = Data(rounds=rounds, buy_items=buy_items)  # bot view of the seat check rows
    for n, row in enumerate(rows, start=2):
        winner = row["winner"]
        points = {s: _int(row, f"{s}_points", n) for s in ("p1", "p2")}
        expl = {s: _int(row, f"{s}_explosions", n) for s in ("p1", "p2")}
        draws = {s: _int(row, f"{s}_draws", n) for s in ("p1", "p2")}
        halves = {s: 2 if winner == s else 1 if winner == "draw" else 0 for s in ("p1", "p2")}
        target = data
        if row["pairing"].startswith(SEAT_CHECK_PREFIX):
            data.seat.add(halves["p1"], points["p1"], expl["p1"], rounds)
            data.seat_draws += winner == "draw"
            target = seat_data
        target.games += 1
        bots = {"p1": row["p1"], "p2": row["p2"]}
        for seat, bot in bots.items():
            target.bots.setdefault(bot, Agg()).add(halves[seat], points[seat], expl[seat], rounds)
            label = label_of(bot)
            if winner == seat:
                target.won_games[label] = target.won_games.get(label, 0) + 1
                bucket = target.won_buys.setdefault(label, dict.fromkeys(buy_items, 0))
                for item in buy_items:
                    bucket[item] += _int(row, f"{seat}_buy_{item}", n)
            if bot == BASELINE_NAME:
                target.baseline_rows[row["sweep_value"]] = (
                    target.baseline_rows.get(row["sweep_value"], 0) + 1
                )
                target.baseline_points += points[seat]
        total = draws["p1"] + draws["p2"]
        for label in {label_of(b) for b in bots.values()}:
            entry = target.length.setdefault(label, [0, 0])
            entry[0] += 1
            entry[1] += total
        target.all_length[0] += 1
        target.all_length[1] += total
    if data.games == 0:
        # a pure seat check run: the bot sections read its rows
        seat_data.seat, seat_data.seat_draws = data.seat, data.seat_draws
        data = seat_data
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
        rules=config.get("rules", "v2.1"),
        rounds=data.rounds,
        overrides=dict(config.get("overrides") or {}),
        sweep=Sweep(sweep["param"], tuple(sweep["values"])) if sweep else None,
    )
    try:
        rulesets = {v: _rules_for(cfg, v) for v in data.baseline_rows}
        maximum = (
            sum(realistic_baseline_maximum(rulesets[v]) * g for v, g in data.baseline_rows.items())
            / n
        )
        loose = sum(baseline_maximum(rulesets[v]) * g for v, g in data.baseline_rows.items()) / n
    except (ValueError, KeyError, TypeError) as e:
        raise ReportError(f"config.json cannot be turned into a ruleset: {e}") from None
    simulated = data.baseline_points / n
    cards = [
        "Cards: only the explosion limit of card 4 is in the calculated numbers;"
        " other card effects are not."
    ]
    return [
        *out,
        f"Baseline {BASELINE_NAME}: {n} games",
        f"Simulated average final points: {simulated:.1f}",
        f"Calculated points of the field table, without chip purchases and cards: {maximum:.1f}",
        "This is not an upper bound of the baseline bot, because the baseline buys chips and"
        f" cards add points; {CONFIRM_TEST} checks it against a simulation without chip purchases.",
        f"Calculated maximum (loose upper bound, see baseline_maximum): {loose:.1f}",
        *cards,
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


__all__ = [
    "ReportError",
    "build_report",
    "write_report",
    "wilson",
    "baseline_maximum",
    "realistic_baseline_maximum",
]
