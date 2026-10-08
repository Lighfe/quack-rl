# M1 Terminal Game Implementation Plan

> **Execution:** this plan is executed by the agent-graph-kit loop (`docs/process.md`). Each task below becomes one GitHub issue in `docs/task-template.md` format, a sub-issue of the M1 stage issue. Do not use the superpowers skills subagent-driven-development or executing-plans (`AGENTS.md`). Steps use checkbox (`- [ ]`) syntax.

**Goal:** Play the simplified Quacks game (rules v1) in the terminal — human vs bot, bot vs bot, hot seat — with every game recorded as a replayable, verifiable JSON Lines event log.

**Architecture:** A pure Python rules engine (no I/O) driven by a TOML ruleset and a registry of chip components. Chance comes through a `ChanceSource` interface, so games can be played with a seeded RNG, scripted in tests, or replayed from a record. Adapters around the engine: a game runner with bots, a recorder and record store, replay and verify, and a Typer/Rich command-line interface.

**Tech Stack:** Python 3.12, uv, pydantic 2, Typer, Rich, tzdata; dev: pytest, Hypothesis, Ruff, pyright.

**Spec:** `docs/specs/2026-10-08-quack-rl-design.md` (rules: `docs/rules/rules-v1.md`)

## Global Constraints

- Python 3.12 (`requires-python = ">=3.12"`, `.python-version` = `3.12`), uv, `src/` layout, package `quack_rl`
- Test command: `uv run --with pytest pytest`. The default suite stays under about 30 seconds; Hypothesis example counts are capped by the `default` profile; `HYPOTHESIS_PROFILE=deep` is opt-in
- Ruff for linting and formatting (`uv run ruff check .`, `uv run ruff format --check .`); pyright in basic mode (`uv run pyright`)
- The engine (`src/quack_rl/engine/`, `src/quack_rl/components/`, `src/quack_rl/rules/`) does no I/O except reading the packaged ruleset file, and knows nothing about bots, terminals, files or HTTP
- Every number of the rules lives in the ruleset file `src/quack_rl/rules/v1.toml`, never hard-coded in engine code
- Actions and legal actions are names: `wait`, `draw`, `stop`, `done`, `buy:<item id>`
- Seats are `p1` and `p2`; within one step, seats are processed in this order
- Droplet positions are stored as integer half steps (`droplet_halves`); start field = `droplet_halves // 2`
- Record times are Berlin local time with UTC offset (`Europe/Berlin`): file names `2026-10-08_21-15-03+0200`, headers ISO 8601
- `data/` is gitignored; records go to `data/records/`
- Rules version `v1` is the only supported version; any other version is refused with `UnsupportedRulesVersion`
- Never put secrets in commits, issues or reports (public repo)

## Review Focus

- A player's bag runs empty during brewing without an explosion → the player stops (`bag_empty` event), the game goes on, no crash (test in Task 5)
- A chip would move past field 53, and a player on field 53 draws again → the field stays 53, money is 35 (test in Task 5)
- Both potions explode in the same round → nobody rolls the bonus die, both get half money, the game goes on (test in Task 6)
- A player has too little money for any item, or has used 3 purchases → only `done` (or `wait`) is legal (test in Task 7)
- A human game is aborted (Ctrl+C) → the record file keeps its header and steps without a footer; reading it gives an incomplete game, and `verify` reports "incomplete game" instead of crashing (tests in Tasks 9, 10 and 12)

---

## File structure

```
pyproject.toml                         project, deps, tool config
.python-version
src/quack_rl/__init__.py               __version__
src/quack_rl/rules/__init__.py         re-exports
src/quack_rl/rules/model.py            pydantic Ruleset, ChipSpec, ShopItem, DieFace
src/quack_rl/rules/load.py             load_ruleset, SUPPORTED_RULES_VERSIONS, UnsupportedRulesVersion
src/quack_rl/rules/v1.toml             ruleset data v1
src/quack_rl/components/__init__.py    imports chips (registers them), re-exports
src/quack_rl/components/base.py        Component base class
src/quack_rl/components/registry.py    register, get_component, UnknownComponent
src/quack_rl/components/chips.py       white@1, orange@1, blue@1, green@1
src/quack_rl/engine/__init__.py        re-exports the engine API
src/quack_rl/engine/state.py           Phase, Status, PlayerState, GameState, new_game, (de)serialization
src/quack_rl/engine/actions.py         action names, action_names, legal_actions
src/quack_rl/engine/chance.py          ChanceSource, ChanceLog, RngChance, ScriptedChance, IllegalChance
src/quack_rl/engine/brew.py            apply_brew
src/quack_rl/engine/resolve.py         apply_resolve
src/quack_rl/engine/shop.py            apply_shop, end of round, game end
src/quack_rl/engine/game.py            step, StepResult, needs_actions, IllegalAction, GameOver
src/quack_rl/bots/__init__.py
src/quack_rl/bots/random_bot.py        RandomBot
src/quack_rl/runner.py                 Seat protocol, play_game
src/quack_rl/record/__init__.py
src/quack_rl/record/schema.py          HeaderLine, StepLine, FooterLine, record_json_schema
src/quack_rl/record/writer.py          GameRecorder
src/quack_rl/record/store.py           RecordStore, LocalRecordStore, berlin_stamp
src/quack_rl/record/reader.py          RecordedGame, read_games, RecordFormatError
src/quack_rl/record/replay.py          RecordedChance, verify_game, verify_seed
src/quack_rl/cli/__init__.py
src/quack_rl/cli/main.py               Typer app: version, simulate, verify, replay, play
src/quack_rl/cli/seats.py              parse_seat
src/quack_rl/cli/render.py             Rich board and step rendering
src/quack_rl/cli/human.py              HumanSeat (hidden keypress)
tests/conftest.py                      Hypothesis profiles
tests/helpers.py                       test helpers (ruleset, scripted steps)
tests/fixtures/golden/v1_random_seed7.jsonl
tests/fixtures/make_golden.py
tests/test_*.py
```

---

### Task 1: Python project skeleton and CLI stub

**Files:**
- Create: `pyproject.toml`, `.python-version`, `src/quack_rl/__init__.py`, `src/quack_rl/cli/__init__.py`, `src/quack_rl/cli/main.py`, `tests/conftest.py`, `tests/test_cli_version.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: nothing
- Produces: package `quack_rl` with `__version__: str`; Typer app `quack_rl.cli.main:app` with command `version`; console script `quack-rl`; Hypothesis profiles `default` and `deep`

- [ ] **Step 1: Write `pyproject.toml` and `.python-version`**

```toml
[project]
name = "quack-rl"
version = "0.1.0"
description = "A simplified Quacks of Quedlinburg as a recorded game and RL environment"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.7",
    "typer>=0.12",
    "rich>=13.7",
    "tzdata>=2024.1",
]

[project.scripts]
quack-rl = "quack_rl.cli.main:app"

[dependency-groups]
dev = [
    "pytest>=8.0",
    "hypothesis>=6.100",
    "ruff>=0.6",
    "pyright>=1.1.380",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/quack_rl"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["tests"]
addopts = "-q"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]

[tool.pyright]
include = ["src"]
typeCheckingMode = "basic"
pythonVersion = "3.12"
```

`.python-version`:

```
3.12
```

- [ ] **Step 2: Write the failing test** `tests/test_cli_version.py`

```python
from typer.testing import CliRunner

from quack_rl import __version__
from quack_rl.cli.main import app


def test_version_command_prints_package_version():
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == __version__
```

`tests/conftest.py`:

```python
import os

from hypothesis import settings

settings.register_profile("default", max_examples=30, deadline=None)
settings.register_profile("deep", max_examples=1000, deadline=None)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "default"))
```

- [ ] **Step 3: Run it to verify it fails**

Run: `uv run --with pytest pytest tests/test_cli_version.py`
Expected: FAIL (`ModuleNotFoundError: No module named 'quack_rl'`)

- [ ] **Step 4: Write the minimal implementation**

`src/quack_rl/__init__.py`:

```python
"""Quack RL: a simplified Quacks of Quedlinburg as a recorded game and RL environment."""

__version__ = "0.1.0"
```

`src/quack_rl/cli/__init__.py`: empty file.

`src/quack_rl/cli/main.py`:

```python
import typer

from quack_rl import __version__

app = typer.Typer(no_args_is_help=True, help="Quack RL: play, simulate, replay and verify games.")


@app.callback()
def main() -> None:
    """Quack RL command line."""


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo(__version__)
```

- [ ] **Step 5: Run the tests and the quality tools**

Run: `uv run --with pytest pytest` → PASS (1 test)
Run: `uv run ruff check . && uv run ruff format --check . && uv run pyright` → no errors
Run: `uv run quack-rl version` → prints `0.1.0`

- [ ] **Step 6: Update `README.md`**

```markdown
# Quack RL

A simplified version of The Quacks of Quedlinburg (rules: `docs/rules/rules-v1.md`), built as a recorded game and a reinforcement learning environment. Design: `docs/specs/2026-10-08-quack-rl-design.md`.

## Set-up

Requires [uv](https://docs.astral.sh/uv/).

    uv sync
    uv run quack-rl --help

## Tests

    uv run --with pytest pytest
    HYPOTHESIS_PROFILE=deep uv run --with pytest pytest   # slower, more random games
```

- [ ] **Step 7: Commit** (include `uv.lock`)

```bash
git add pyproject.toml .python-version uv.lock src tests README.md
git commit -m "Add Python project skeleton and quack-rl CLI stub"
```

---

### Task 2: Ruleset v1 data and models

**Files:**
- Create: `src/quack_rl/rules/__init__.py`, `src/quack_rl/rules/model.py`, `src/quack_rl/rules/load.py`, `src/quack_rl/rules/v1.toml`, `tests/test_ruleset.py`

**Interfaces:**
- Consumes: package skeleton (Task 1)
- Produces:
  - `quack_rl.rules.load_ruleset(version: str) -> Ruleset`
  - `quack_rl.rules.SUPPORTED_RULES_VERSIONS: tuple[str, ...]` (= `("v1",)`)
  - `quack_rl.rules.UnsupportedRulesVersion(ValueError)`
  - `Ruleset` fields: `version: str`, `rounds: int`, `explosion_limit: int`, `max_purchases: int`, `track_end: int`, `money: list[int]` (index = field), `rubies: list[int]`, `chips: list[ChipSpec]`, `start_bag: dict[str, int]`, `shop: list[ShopItem]`, `die: list[DieFace]`; methods `chip(chip_id: str) -> ChipSpec`, `shop_item(item_id: str) -> ShopItem`
  - `ChipSpec(id: str, colour: str, value: int, component: str)`
  - `ShopItem(id: str, price: int, kind: Literal["chip", "remove_chip", "droplet", "points"], chip: str | None, halves: int, points: int)`
  - `DieFace(id: str, weight: int, kind: Literal["droplet", "chip", "money", "points"], chip: str | None, halves: int, amount: int, points: int)`

- [ ] **Step 1: Write the failing test** `tests/test_ruleset.py`

```python
import re
from pathlib import Path

import pytest

from quack_rl.rules import SUPPORTED_RULES_VERSIONS, UnsupportedRulesVersion, load_ruleset

RULES_DOC = Path(__file__).resolve().parents[1] / "docs" / "rules" / "rules-v1.md"


def doc_money(field: int) -> int:
    # formula from docs/rules/rules-v1.md, section 1 "Track"
    if field <= 14:
        return field
    if field <= 52:
        return 15 + (field - 15) // 2
    return 35


def test_supported_versions_is_v1_only():
    assert SUPPORTED_RULES_VERSIONS == ("v1",)


def test_unknown_version_is_refused():
    with pytest.raises(UnsupportedRulesVersion):
        load_ruleset("v0")


def test_core_numbers():
    rs = load_ruleset("v1")
    assert rs.version == "v1"
    assert rs.rounds == 9
    assert rs.explosion_limit == 7
    assert rs.max_purchases == 3
    assert rs.track_end == 53


def test_money_track_matches_rules_doc():
    rs = load_ruleset("v1")
    assert len(rs.money) == 54
    assert rs.money == [doc_money(f) for f in range(54)]
    assert rs.money[53] == 35


def test_rubies_match_rules_doc():
    rs = load_ruleset("v1")
    assert rs.rubies == [5, 9, 13, 16, 20, 24, 28, 30, 34, 36, 40, 42, 46, 50, 52]
    line = "Ruby fields: " + ", ".join(str(f) for f in rs.rubies) + "."
    assert line in RULES_DOC.read_text(encoding="utf-8")


def test_start_bag():
    rs = load_ruleset("v1")
    assert rs.start_bag == {"white_1": 4, "white_2": 2, "white_3": 1, "orange_1": 1, "green_1": 1}


SHOP_LABELS = {
    "orange_1": "Orange 1",
    "blue_1": "Blue 1",
    "blue_2": "Blue 2",
    "blue_4": "Blue 4",
    "green_1": "Green 1",
    "green_2": "Green 2",
    "green_4": "Green 4",
    "remove_white_1": "Remove one White 1",
    "droplet_1": "Advance droplet by 1",
    "points_2": "2 victory points",
    "points_5": "5 victory points",
    "points_10": "10 victory points",
}


def test_shop_prices_match_rules_doc():
    rs = load_ruleset("v1")
    doc = RULES_DOC.read_text(encoding="utf-8")
    assert [i.id for i in rs.shop] == list(SHOP_LABELS)
    for item in rs.shop:
        pattern = rf"\|[^|\n]*{re.escape(SHOP_LABELS[item.id])}\s*\|\s*{item.price}\s*\|"
        assert re.search(pattern, doc), item.id


def test_die_faces():
    rs = load_ruleset("v1")
    faces = {f.id: f for f in rs.die}
    assert sum(f.weight for f in rs.die) == 6
    assert (faces["droplet_1"].kind, faces["droplet_1"].halves, faces["droplet_1"].weight) == ("droplet", 2, 1)
    assert (faces["droplet_half"].kind, faces["droplet_half"].halves) == ("droplet", 1)
    assert (faces["orange_1"].kind, faces["orange_1"].chip) == ("chip", "orange_1")
    assert (faces["money_1"].kind, faces["money_1"].amount, faces["money_1"].weight) == ("money", 1, 2)
    assert (faces["point_1"].kind, faces["point_1"].points) == ("points", 1)


def test_lookup_helpers():
    rs = load_ruleset("v1")
    assert rs.chip("blue_2").value == 2
    assert rs.shop_item("points_10").price == 22
    with pytest.raises(KeyError):
        rs.chip("purple_9")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with pytest pytest tests/test_ruleset.py`
Expected: FAIL (`ModuleNotFoundError: No module named 'quack_rl.rules'`)

- [ ] **Step 3: Write the ruleset file** `src/quack_rl/rules/v1.toml`

```toml
# Quack RL ruleset v1. Human-readable rules: docs/rules/rules-v1.md
# Every number here is a tuning default. Never edit a version that has recorded games:
# make a new version file instead (for example v1.1).
version = "v1"
rounds = 9
explosion_limit = 7      # potion explodes when the white total is more than this
max_purchases = 3        # per player per round
track_end = 53

# money per field, index = field 0..53
money = [
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14,
    15, 15, 16, 16, 17, 17, 18, 18, 19, 19, 20, 20, 21, 21, 22, 22, 23, 23, 24, 24,
    25, 25, 26, 26, 27, 27, 28, 28, 29, 29, 30, 30, 31, 31, 32, 32, 33, 33,
    35,
]

rubies = [5, 9, 13, 16, 20, 24, 28, 30, 34, 36, 40, 42, 46, 50, 52]

[start_bag]
white_1 = 4
white_2 = 2
white_3 = 1
orange_1 = 1
green_1 = 1

[[chips]]
id = "white_1"
colour = "white"
value = 1
component = "white@1"

[[chips]]
id = "white_2"
colour = "white"
value = 2
component = "white@1"

[[chips]]
id = "white_3"
colour = "white"
value = 3
component = "white@1"

[[chips]]
id = "orange_1"
colour = "orange"
value = 1
component = "orange@1"

[[chips]]
id = "blue_1"
colour = "blue"
value = 1
component = "blue@1"

[[chips]]
id = "blue_2"
colour = "blue"
value = 2
component = "blue@1"

[[chips]]
id = "blue_4"
colour = "blue"
value = 4
component = "blue@1"

[[chips]]
id = "green_1"
colour = "green"
value = 1
component = "green@1"

[[chips]]
id = "green_2"
colour = "green"
value = 2
component = "green@1"

[[chips]]
id = "green_4"
colour = "green"
value = 4
component = "green@1"

[[shop]]
id = "orange_1"
price = 3
kind = "chip"
chip = "orange_1"

[[shop]]
id = "blue_1"
price = 5
kind = "chip"
chip = "blue_1"

[[shop]]
id = "blue_2"
price = 9
kind = "chip"
chip = "blue_2"

[[shop]]
id = "blue_4"
price = 16
kind = "chip"
chip = "blue_4"

[[shop]]
id = "green_1"
price = 4
kind = "chip"
chip = "green_1"

[[shop]]
id = "green_2"
price = 8
kind = "chip"
chip = "green_2"

[[shop]]
id = "green_4"
price = 14
kind = "chip"
chip = "green_4"

[[shop]]
id = "remove_white_1"
price = 15
kind = "remove_chip"
chip = "white_1"

[[shop]]
id = "droplet_1"
price = 10
kind = "droplet"
halves = 2

[[shop]]
id = "points_2"
price = 6
kind = "points"
points = 2

[[shop]]
id = "points_5"
price = 13
kind = "points"
points = 5

[[shop]]
id = "points_10"
price = 22
kind = "points"
points = 10

[[die]]
id = "droplet_1"
weight = 1
kind = "droplet"
halves = 2

[[die]]
id = "droplet_half"
weight = 1
kind = "droplet"
halves = 1

[[die]]
id = "orange_1"
weight = 1
kind = "chip"
chip = "orange_1"

[[die]]
id = "money_1"
weight = 2
kind = "money"
amount = 1

[[die]]
id = "point_1"
weight = 1
kind = "points"
points = 1
```

- [ ] **Step 4: Write the models** `src/quack_rl/rules/model.py`

```python
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ChipSpec(_Frozen):
    id: str
    colour: str
    value: int
    component: str


class ShopItem(_Frozen):
    id: str
    price: int
    kind: Literal["chip", "remove_chip", "droplet", "points"]
    chip: str | None = None
    halves: int = 0
    points: int = 0


class DieFace(_Frozen):
    id: str
    weight: int
    kind: Literal["droplet", "chip", "money", "points"]
    chip: str | None = None
    halves: int = 0
    amount: int = 0
    points: int = 0


class Ruleset(_Frozen):
    version: str
    rounds: int
    explosion_limit: int
    max_purchases: int
    track_end: int
    money: list[int]
    rubies: list[int]
    start_bag: dict[str, int]
    chips: list[ChipSpec]
    shop: list[ShopItem]
    die: list[DieFace]

    @model_validator(mode="after")
    def _check_references(self) -> "Ruleset":
        chip_ids = {c.id for c in self.chips}
        if len(self.money) != self.track_end + 1:
            raise ValueError("money needs one entry per field 0..track_end")
        if any(not 0 <= f <= self.track_end for f in self.rubies):
            raise ValueError("ruby field outside the track")
        for chip_id in self.start_bag:
            if chip_id not in chip_ids:
                raise ValueError(f"start_bag: unknown chip {chip_id}")
        for entry in [*self.shop, *self.die]:
            if entry.kind in ("chip", "remove_chip") and entry.chip not in chip_ids:
                raise ValueError(f"{entry.id}: unknown chip {entry.chip}")
        return self

    def chip(self, chip_id: str) -> ChipSpec:
        for c in self.chips:
            if c.id == chip_id:
                return c
        raise KeyError(chip_id)

    def shop_item(self, item_id: str) -> ShopItem:
        for item in self.shop:
            if item.id == item_id:
                return item
        raise KeyError(item_id)
```

`src/quack_rl/rules/load.py`:

```python
import tomllib
from importlib import resources

from quack_rl.rules.model import Ruleset

SUPPORTED_RULES_VERSIONS: tuple[str, ...] = ("v1",)


class UnsupportedRulesVersion(ValueError):
    """The rules version is not supported by this engine."""


def load_ruleset(version: str) -> Ruleset:
    if version not in SUPPORTED_RULES_VERSIONS:
        raise UnsupportedRulesVersion(
            f"rules version {version!r} is not supported (supported: {SUPPORTED_RULES_VERSIONS})"
        )
    text = resources.files("quack_rl.rules").joinpath(f"{version}.toml").read_text(encoding="utf-8")
    return Ruleset.model_validate(tomllib.loads(text))
```

`src/quack_rl/rules/__init__.py`:

```python
from quack_rl.rules.load import SUPPORTED_RULES_VERSIONS, UnsupportedRulesVersion, load_ruleset
from quack_rl.rules.model import ChipSpec, DieFace, Ruleset, ShopItem

__all__ = [
    "SUPPORTED_RULES_VERSIONS",
    "ChipSpec",
    "DieFace",
    "Ruleset",
    "ShopItem",
    "UnsupportedRulesVersion",
    "load_ruleset",
]
```

- [ ] **Step 5: Run the tests**

Run: `uv run --with pytest pytest tests/test_ruleset.py` → PASS
Run: `uv run --with pytest pytest && uv run ruff check . && uv run pyright` → no errors

- [ ] **Step 6: Commit**

```bash
git add src/quack_rl/rules tests/test_ruleset.py
git commit -m "Add ruleset v1 data and models"
```

---

### Task 3: Chip components and registry

**Files:**
- Create: `src/quack_rl/components/__init__.py`, `src/quack_rl/components/base.py`, `src/quack_rl/components/registry.py`, `src/quack_rl/components/chips.py`, `tests/test_components.py`

**Interfaces:**
- Consumes: `ChipSpec`, `load_ruleset` (Task 2)
- Produces:
  - `quack_rl.components.Component` with `name: ClassVar[str]` and methods `place_bonus(chip: ChipSpec, previous: ChipSpec | None) -> int`, `explosion_weight(chip: ChipSpec) -> int`, `round_end_droplet_halves(chip: ChipSpec, position_from_end: int) -> int` (0 = last placed chip, 1 = second last), `features(chip: ChipSpec) -> dict[str, float]`
  - `quack_rl.components.get_component(name: str) -> Component`, `quack_rl.components.register` (class decorator), `quack_rl.components.UnknownComponent(KeyError)`
  - Registered names: `white@1`, `orange@1`, `blue@1`, `green@1`

- [ ] **Step 1: Write the failing test** `tests/test_components.py`

```python
import pytest

from quack_rl.components import UnknownComponent, get_component
from quack_rl.rules import load_ruleset

rs = load_ruleset("v1")


def comp(chip_id):
    return get_component(rs.chip(chip_id).component)


def test_every_ruleset_component_is_registered():
    for chip in rs.chips:
        get_component(chip.component)


def test_unknown_component():
    with pytest.raises(UnknownComponent):
        get_component("purple@1")


def test_white_adds_its_value_to_the_explosion_total():
    assert comp("white_3").explosion_weight(rs.chip("white_3")) == 3
    assert comp("orange_1").explosion_weight(rs.chip("orange_1")) == 0


# rules 1 "Chips": blue +1 if the previously placed chip has a value other than 1
@pytest.mark.parametrize(
    ("previous", "bonus"),
    [(None, 0), ("white_1", 0), ("white_2", 1), ("orange_1", 0), ("green_4", 1)],
)
def test_blue_bonus(previous, bonus):
    prev = rs.chip(previous) if previous else None
    assert comp("blue_2").place_bonus(rs.chip("blue_2"), prev) == bonus


def test_only_blue_has_a_place_bonus():
    for chip_id in ("white_2", "orange_1", "green_2"):
        assert comp(chip_id).place_bonus(rs.chip(chip_id), rs.chip("white_2")) == 0


# rules 4.3: each green chip among the last two placed chips: droplet +0.5 (one half step)
@pytest.mark.parametrize(("position_from_end", "halves"), [(0, 1), (1, 1), (2, 0)])
def test_green_round_end_bonus(position_from_end, halves):
    assert comp("green_1").round_end_droplet_halves(rs.chip("green_1"), position_from_end) == halves


def test_non_green_has_no_round_end_bonus():
    assert comp("blue_1").round_end_droplet_halves(rs.chip("blue_1"), 0) == 0


def test_features_describe_the_chip():
    features = comp("white_2").features(rs.chip("white_2"))
    assert features["value"] == 2.0
    assert features["explosion_weight"] == 2.0
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with pytest pytest tests/test_components.py`
Expected: FAIL (`ModuleNotFoundError: No module named 'quack_rl.components'`)

- [ ] **Step 3: Write the implementation**

`src/quack_rl/components/base.py`:

```python
from typing import ClassVar

from quack_rl.rules import ChipSpec


class Component:
    """Behavior of one chip type. Subclasses override only the hooks they use."""

    name: ClassVar[str]

    def place_bonus(self, chip: ChipSpec, previous: ChipSpec | None) -> int:
        """Extra fields to advance when this chip is placed after `previous` (None: first chip)."""
        return 0

    def explosion_weight(self, chip: ChipSpec) -> int:
        """Amount added to the white total when this chip is placed."""
        return 0

    def round_end_droplet_halves(self, chip: ChipSpec, position_from_end: int) -> int:
        """Droplet half steps at round end; position_from_end 0 = last placed chip."""
        return 0

    def features(self, chip: ChipSpec) -> dict[str, float]:
        """Descriptive features for entity encodings (spec 7.4)."""
        return {
            "value": float(chip.value),
            "explosion_weight": float(self.explosion_weight(chip)),
        }
```

`src/quack_rl/components/registry.py`:

```python
from quack_rl.components.base import Component

_REGISTRY: dict[str, Component] = {}


class UnknownComponent(KeyError):
    """No component is registered under this name."""


def register[C: type[Component]](cls: C) -> C:
    if cls.name in _REGISTRY:
        raise ValueError(f"component {cls.name} is already registered")
    _REGISTRY[cls.name] = cls()
    return cls


def get_component(name: str) -> Component:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise UnknownComponent(name) from None
```

`src/quack_rl/components/chips.py`:

```python
from quack_rl.components.base import Component
from quack_rl.components.registry import register
from quack_rl.rules import ChipSpec


@register
class White(Component):
    name = "white@1"

    def explosion_weight(self, chip: ChipSpec) -> int:
        return chip.value


@register
class Orange(Component):
    name = "orange@1"


@register
class Blue(Component):
    name = "blue@1"

    def place_bonus(self, chip: ChipSpec, previous: ChipSpec | None) -> int:
        return 1 if previous is not None and previous.value != 1 else 0


@register
class Green(Component):
    name = "green@1"

    def round_end_droplet_halves(self, chip: ChipSpec, position_from_end: int) -> int:
        return 1 if position_from_end in (0, 1) else 0
```

`src/quack_rl/components/__init__.py`:

```python
from quack_rl.components import chips as _chips  # noqa: F401  (registers the v1 components)
from quack_rl.components.base import Component
from quack_rl.components.registry import UnknownComponent, get_component, register

__all__ = ["Component", "UnknownComponent", "get_component", "register"]
```

- [ ] **Step 4: Run the tests**

Run: `uv run --with pytest pytest tests/test_components.py` → PASS
Run: `uv run --with pytest pytest && uv run ruff check . && uv run pyright` → no errors

- [ ] **Step 5: Commit**

```bash
git add src/quack_rl/components tests/test_components.py
git commit -m "Add chip components and registry"
```

---

### Task 4: Game state, actions and legal actions

**Files:**
- Create: `src/quack_rl/engine/__init__.py`, `src/quack_rl/engine/state.py`, `src/quack_rl/engine/actions.py`, `tests/helpers.py`, `tests/test_state_actions.py`

**Interfaces:**
- Consumes: `Ruleset`, `load_ruleset` (Task 2)
- Produces (all re-exported from `quack_rl.engine`):
  - `SEATS: tuple[str, str] = ("p1", "p2")`
  - `Phase(StrEnum)`: `BREW="brew"`, `RESOLVE="resolve"`, `SHOP="shop"`, `GAME_OVER="game_over"`
  - `Status(StrEnum)`: `BREWING="brewing"`, `STOPPED="stopped"`, `EXPLODED="exploded"`
  - `PlayerState` (mutable dataclass): `bag: dict[str, int]`, `placed: list[str]`, `field: int`, `white_total: int`, `status: Status`, `droplet_halves: int`, `points: int`, `money: int`, `purchases: int`, `shop_done: bool`, `final_field: int | None`; method `owned(chip_id: str) -> int`
  - `GameState` (mutable dataclass): `rules_version: str`, `round: int`, `phase: Phase`, `step: int`, `players: dict[str, PlayerState]`, `winner: str | None` (`"p1"`, `"p2"` or `"draw"`)
  - `new_game(rs: Ruleset) -> GameState`, `start_field(p: PlayerState, rs: Ruleset) -> int`
  - `state_to_dict(state: GameState) -> dict`, `state_from_dict(data: dict) -> GameState`
  - `WAIT`, `DRAW`, `STOP`, `DONE` (str constants), `buy(item_id: str) -> str`, `action_names(rs: Ruleset) -> list[str]`, `legal_actions(state: GameState, rs: Ruleset, seat: str) -> list[str]`

- [ ] **Step 1: Write the failing test** `tests/test_state_actions.py` and the helper `tests/helpers.py`

`tests/helpers.py`:

```python
from quack_rl.rules import load_ruleset

RS = load_ruleset("v1")
```

`tests/test_state_actions.py`:

```python
import json

from helpers import RS
from quack_rl.engine import (
    DONE,
    DRAW,
    STOP,
    WAIT,
    Phase,
    Status,
    action_names,
    buy,
    legal_actions,
    new_game,
    state_from_dict,
    state_to_dict,
)


def test_new_game_setup():
    s = new_game(RS)
    assert (s.rules_version, s.round, s.phase, s.step, s.winner) == ("v1", 1, Phase.BREW, 0, None)
    for p in s.players.values():
        assert p.bag == RS.start_bag
        assert p.bag is not RS.start_bag
        assert (p.field, p.droplet_halves, p.points, p.white_total) == (0, 0, 0, 0)
        assert p.status is Status.BREWING


def test_action_names_v1_has_16_actions():
    names = action_names(RS)
    assert names[:4] == [WAIT, DRAW, STOP, DONE]
    assert names[4:] == [buy(i.id) for i in RS.shop]
    assert len(names) == 16
    assert buy("blue_2") == "buy:blue_2"


def test_first_brew_action_must_be_draw():
    s = new_game(RS)
    assert legal_actions(s, RS, "p1") == [DRAW]


def test_brewing_player_after_first_chip_may_draw_or_stop():
    s = new_game(RS)
    s.players["p1"].placed = ["white_1"]
    assert legal_actions(s, RS, "p1") == [DRAW, STOP]


def test_stopped_or_exploded_player_waits():
    s = new_game(RS)
    s.players["p1"].status = Status.STOPPED
    s.players["p2"].status = Status.EXPLODED
    assert legal_actions(s, RS, "p1") == [WAIT]
    assert legal_actions(s, RS, "p2") == [WAIT]


def test_shop_legal_actions_follow_money():
    s = new_game(RS)
    s.phase = Phase.SHOP
    s.players["p1"].money = 5
    assert legal_actions(s, RS, "p1") == [DONE, buy("orange_1"), buy("blue_1"), buy("green_1")]


def test_shop_with_no_money_only_done():
    s = new_game(RS)
    s.phase = Phase.SHOP
    s.players["p1"].money = 0
    assert legal_actions(s, RS, "p1") == [DONE]


def test_shop_after_three_purchases_waits():
    s = new_game(RS)
    s.phase = Phase.SHOP
    p = s.players["p1"]
    p.money, p.purchases, p.shop_done = 30, 3, True
    assert legal_actions(s, RS, "p1") == [WAIT]


def test_remove_white_1_needs_an_owned_white_1_in_bag_or_placed():
    s = new_game(RS)
    s.phase = Phase.SHOP
    p = s.players["p1"]
    p.money = 15
    p.bag.pop("white_1")
    assert buy("remove_white_1") not in legal_actions(s, RS, "p1")
    p.placed = ["white_1"]
    assert buy("remove_white_1") in legal_actions(s, RS, "p1")


def test_no_actions_in_resolve_or_after_game_over():
    s = new_game(RS)
    s.phase = Phase.RESOLVE
    assert legal_actions(s, RS, "p1") == []
    s.phase = Phase.GAME_OVER
    assert legal_actions(s, RS, "p1") == []


def test_state_round_trips_through_json():
    s = new_game(RS)
    s.players["p1"].placed = ["white_1", "green_1"]
    s.players["p1"].final_field = 2
    data = json.loads(json.dumps(state_to_dict(s)))
    assert state_from_dict(data) == s
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with pytest pytest tests/test_state_actions.py`
Expected: FAIL (`ModuleNotFoundError: No module named 'quack_rl.engine'`)

Note: tests import `helpers` from `tests/` through `pythonpath = ["tests"]` (set in Task 1).

- [ ] **Step 3: Write the implementation**

`src/quack_rl/engine/state.py`:

```python
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from quack_rl.rules import Ruleset

SEATS: tuple[str, str] = ("p1", "p2")


class Phase(StrEnum):
    BREW = "brew"
    RESOLVE = "resolve"
    SHOP = "shop"
    GAME_OVER = "game_over"


class Status(StrEnum):
    BREWING = "brewing"
    STOPPED = "stopped"
    EXPLODED = "exploded"


@dataclass
class PlayerState:
    bag: dict[str, int]
    placed: list[str] = field(default_factory=list)
    field: int = 0
    white_total: int = 0
    status: Status = Status.BREWING
    droplet_halves: int = 0
    points: int = 0
    money: int = 0
    purchases: int = 0
    shop_done: bool = False
    final_field: int | None = None

    def owned(self, chip_id: str) -> int:
        return self.bag.get(chip_id, 0) + self.placed.count(chip_id)


@dataclass
class GameState:
    rules_version: str
    round: int
    phase: Phase
    step: int
    players: dict[str, PlayerState]
    winner: str | None = None


def start_field(p: PlayerState, rs: Ruleset) -> int:
    return min(p.droplet_halves // 2, rs.track_end)


def new_game(rs: Ruleset) -> GameState:
    return GameState(
        rules_version=rs.version,
        round=1,
        phase=Phase.BREW,
        step=0,
        players={seat: PlayerState(bag=dict(rs.start_bag)) for seat in SEATS},
    )


def state_to_dict(state: GameState) -> dict[str, Any]:
    return asdict(state)


def state_from_dict(data: dict[str, Any]) -> GameState:
    players = {
        seat: PlayerState(**{**p, "status": Status(p["status"])})
        for seat, p in data["players"].items()
    }
    return GameState(**{**data, "phase": Phase(data["phase"]), "players": players})
```

`src/quack_rl/engine/actions.py`:

```python
from quack_rl.engine.state import GameState, Phase, Status
from quack_rl.rules import Ruleset, ShopItem

WAIT = "wait"
DRAW = "draw"
STOP = "stop"
DONE = "done"
BUY_PREFIX = "buy:"


def buy(item_id: str) -> str:
    return f"{BUY_PREFIX}{item_id}"


def action_names(rs: Ruleset) -> list[str]:
    return [WAIT, DRAW, STOP, DONE, *(buy(item.id) for item in rs.shop)]


def _can_buy(item: ShopItem, money: int, owned: int) -> bool:
    if item.price > money:
        return False
    if item.kind == "remove_chip":
        return owned > 0
    return True


def legal_actions(state: GameState, rs: Ruleset, seat: str) -> list[str]:
    p = state.players[seat]
    if state.phase is Phase.BREW:
        if p.status is not Status.BREWING:
            return [WAIT]
        return [DRAW] if not p.placed else [DRAW, STOP]
    if state.phase is Phase.SHOP:
        if p.shop_done:
            return [WAIT]
        buys = [
            buy(item.id)
            for item in rs.shop
            if _can_buy(item, p.money, p.owned(item.chip) if item.chip else 0)
        ]
        return [DONE, *buys]
    return []
```

`src/quack_rl/engine/__init__.py`:

```python
from quack_rl.engine.actions import (
    BUY_PREFIX,
    DONE,
    DRAW,
    STOP,
    WAIT,
    action_names,
    buy,
    legal_actions,
)
from quack_rl.engine.state import (
    SEATS,
    GameState,
    Phase,
    PlayerState,
    Status,
    new_game,
    start_field,
    state_from_dict,
    state_to_dict,
)

__all__ = [
    "BUY_PREFIX", "DONE", "DRAW", "SEATS", "STOP", "WAIT",
    "GameState", "Phase", "PlayerState", "Status",
    "action_names", "buy", "legal_actions", "new_game", "start_field",
    "state_from_dict", "state_to_dict",
]
```

- [ ] **Step 4: Run the tests**

Run: `uv run --with pytest pytest tests/test_state_actions.py` → PASS
Run: `uv run --with pytest pytest && uv run ruff check . && uv run pyright` → no errors

- [ ] **Step 5: Commit**

```bash
git add src/quack_rl/engine tests/helpers.py tests/test_state_actions.py
git commit -m "Add game state, action names and legal actions"
```

---

### Task 5: Chance sources, the step function and brewing

**Files:**
- Create: `src/quack_rl/engine/chance.py`, `src/quack_rl/engine/brew.py`, `src/quack_rl/engine/game.py`, `tests/test_brew.py`
- Modify: `src/quack_rl/engine/__init__.py` (re-export the new names), `tests/helpers.py`

**Interfaces:**
- Consumes: Tasks 2-4 (`Ruleset`, `get_component`, `GameState`, `legal_actions`, action constants)
- Produces (re-exported from `quack_rl.engine`):
  - `ChanceSource` (Protocol): `draw_chip(bag: Mapping[str, int], seat: str) -> str`, `roll_die(faces: Sequence[DieFace], seat: str) -> str` (returns a face id)
  - `RngChance(seed: int)`, `ScriptedChance(values: Iterable[str])`, `IllegalChance(ValueError)`
  - `ChanceLog(source: ChanceSource, rs: Ruleset)` with `draw_chip(p: PlayerState, seat: str) -> str`, `roll_die(seat: str) -> DieFace`, attribute `outcomes: list[dict]` (each `{"seat", "kind": "draw_chip" | "die", "value"}`)
  - `step(state: GameState, rs: Ruleset, actions: dict[str, str] | None, chance: ChanceSource) -> StepResult`
  - `StepResult` (dataclass): `state: GameState`, `n: int`, `round: int`, `phase: Phase` (phase in which the step happened), `legal: dict[str, list[str]] | None`, `actions: dict[str, str] | None`, `chance: list[dict]`, `events: list[dict]`
  - `needs_actions(state: GameState) -> bool`, `IllegalAction(ValueError)`, `GameOver(RuntimeError)`
  - Events are dicts `{"seat": str | None, "kind": str, ...}`; brew kinds: `place` (`chip`, `from`, `to`, `bonus`), `explode` (`white_total`), `bag_empty`, `stop` (`field`)
  - In this task `step` raises `NotImplementedError` for `Phase.RESOLVE` and `Phase.SHOP`; Tasks 6 and 7 fill them in

- [ ] **Step 1: Write the failing test** `tests/test_brew.py`; extend `tests/helpers.py`

`tests/helpers.py` (replace):

```python
from quack_rl.engine import ScriptedChance, step
from quack_rl.rules import load_ruleset

RS = load_ruleset("v1")


def play(state, p1, p2, *chance):
    """One joint step with scripted chance outcomes (chip ids or die face ids, in order)."""
    return step(state, RS, {"p1": p1, "p2": p2}, ScriptedChance(chance))


def auto(state, *chance):
    """One step without actions (Resolve)."""
    return step(state, RS, None, ScriptedChance(chance))
```

`tests/test_brew.py`:

```python
import pytest

from helpers import RS, play
from quack_rl.engine import (
    DRAW,
    STOP,
    WAIT,
    IllegalAction,
    IllegalChance,
    Phase,
    RngChance,
    Status,
    new_game,
    step,
)


def test_draw_places_chip_and_advances_by_value():
    r = play(new_game(RS), DRAW, DRAW, "white_2", "orange_1")
    p1, p2 = r.state.players["p1"], r.state.players["p2"]
    assert (p1.field, p1.white_total, p1.placed) == (2, 2, ["white_2"])
    assert (p2.field, p2.white_total, p2.placed) == (1, 0, ["orange_1"])
    assert p1.bag["white_2"] == 1
    assert r.chance == [
        {"seat": "p1", "kind": "draw_chip", "value": "white_2"},
        {"seat": "p2", "kind": "draw_chip", "value": "orange_1"},
    ]
    assert r.events[0] == {"seat": "p1", "kind": "place", "chip": "white_2", "from": 0, "to": 2, "bonus": 0}
    assert (r.n, r.round, r.phase, r.legal) == (1, 1, Phase.BREW, {"p1": [DRAW], "p2": [DRAW]})
    assert r.state.step == 1


def test_step_does_not_mutate_the_input_state():
    s = new_game(RS)
    play(s, DRAW, DRAW, "white_2", "orange_1")
    assert s.players["p1"].placed == [] and s.step == 0


def test_illegal_action_is_refused():
    with pytest.raises(IllegalAction):
        play(new_game(RS), STOP, DRAW, "white_1")


def test_impossible_chance_outcome_is_refused():
    with pytest.raises(IllegalChance):
        play(new_game(RS), DRAW, DRAW, "blue_4", "white_1")


def test_explosion_when_white_total_exceeds_seven():
    s = play(new_game(RS), DRAW, DRAW, "white_3", "white_1").state
    s = play(s, DRAW, STOP, "white_2").state
    s = play(s, DRAW, WAIT, "white_2").state  # 7: safe
    assert s.players["p1"].status is Status.BREWING
    r = play(s, DRAW, WAIT, "white_1")  # 8: explodes
    assert r.state.players["p1"].status is Status.EXPLODED
    assert {"seat": "p1", "kind": "explode", "white_total": 8} in r.events


def test_blue_bonus_after_chip_with_value_other_than_one():
    s = new_game(RS)
    s.players["p1"].bag["blue_2"] = 1
    s = play(s, DRAW, DRAW, "white_2", "white_1").state
    r = play(s, DRAW, STOP, "blue_2")
    assert r.state.players["p1"].field == 5  # 2 + 2 + 1 bonus
    assert r.events[0]["bonus"] == 1


def test_field_is_capped_at_53_and_drawing_at_53_is_allowed():
    s = new_game(RS)
    s.players["p1"].field = 52
    s = play(s, DRAW, DRAW, "white_2", "white_1").state
    assert s.players["p1"].field == 53
    r = play(s, DRAW, STOP, "white_1")
    assert r.state.players["p1"].field == 53


def test_empty_bag_stops_the_player():
    s = new_game(RS)
    s.players["p1"].bag = {"orange_1": 1}
    r = play(s, DRAW, DRAW, "orange_1", "white_1")
    assert r.state.players["p1"].status is Status.STOPPED
    assert {"seat": "p1", "kind": "bag_empty"} in r.events


def test_brew_ends_when_nobody_brews_and_final_fields_are_settled():
    s = play(new_game(RS), DRAW, DRAW, "white_2", "orange_1").state
    r = play(s, STOP, STOP)
    assert r.state.phase is Phase.RESOLVE
    assert r.state.players["p1"].final_field == 2
    assert r.state.players["p2"].final_field == 1


def test_rng_chance_is_deterministic_per_seed():
    def draws(seed):
        s, chance, out = new_game(RS), RngChance(seed), []
        for _ in range(3):
            r = step(s, RS, {"p1": DRAW, "p2": DRAW}, chance)
            out.append(r.chance)
            s = r.state
        return out

    assert draws(1) == draws(1)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with pytest pytest tests/test_brew.py`
Expected: FAIL (`ImportError: cannot import name 'ScriptedChance'`)

- [ ] **Step 3: Write the implementation**

`src/quack_rl/engine/chance.py`:

```python
import random
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Protocol

from quack_rl.engine.state import PlayerState
from quack_rl.rules import DieFace, Ruleset


class IllegalChance(ValueError):
    """A chance outcome that is not possible in the current state."""


class ChanceSource(Protocol):
    def draw_chip(self, bag: Mapping[str, int], seat: str) -> str: ...

    def roll_die(self, faces: Sequence[DieFace], seat: str) -> str: ...


class RngChance:
    """Seeded chance. Same seed and same calls give the same outcomes."""

    def __init__(self, seed: int):
        self._rng = random.Random(seed)

    def draw_chip(self, bag: Mapping[str, int], seat: str) -> str:
        ids = sorted(c for c, n in bag.items() if n > 0)
        pick = self._rng.randrange(sum(bag[c] for c in ids))
        for chip_id in ids:
            pick -= bag[chip_id]
            if pick < 0:
                return chip_id
        raise IllegalChance("draw from an empty bag")

    def roll_die(self, faces: Sequence[DieFace], seat: str) -> str:
        pick = self._rng.randrange(sum(f.weight for f in faces))
        for face in faces:
            pick -= face.weight
            if pick < 0:
                return face.id
        raise IllegalChance("die without faces")


class ScriptedChance:
    """Chance outcomes given in order (tests)."""

    def __init__(self, values: Iterable[str]):
        self._values = iter(values)

    def _next(self) -> str:
        try:
            return next(self._values)
        except StopIteration:
            raise IllegalChance("scripted chance is exhausted") from None

    def draw_chip(self, bag: Mapping[str, int], seat: str) -> str:
        return self._next()

    def roll_die(self, faces: Sequence[DieFace], seat: str) -> str:
        return self._next()


class ChanceLog:
    """Asks a ChanceSource, validates each outcome against the state, and records it."""

    def __init__(self, source: ChanceSource, rs: Ruleset):
        self.source = source
        self.rs = rs
        self.outcomes: list[dict[str, Any]] = []

    def draw_chip(self, p: PlayerState, seat: str) -> str:
        chip_id = self.source.draw_chip(p.bag, seat)
        if p.bag.get(chip_id, 0) <= 0:
            raise IllegalChance(f"{seat} drew {chip_id}, which is not in the bag")
        self.outcomes.append({"seat": seat, "kind": "draw_chip", "value": chip_id})
        return chip_id

    def roll_die(self, seat: str) -> DieFace:
        face_id = self.source.roll_die(self.rs.die, seat)
        for face in self.rs.die:
            if face.id == face_id:
                self.outcomes.append({"seat": seat, "kind": "die", "value": face_id})
                return face
        raise IllegalChance(f"{seat} rolled {face_id}, which is not a die face")
```

`src/quack_rl/engine/brew.py`:

```python
from typing import Any

from quack_rl.components import get_component
from quack_rl.engine.actions import DRAW, STOP
from quack_rl.engine.chance import ChanceLog
from quack_rl.engine.state import SEATS, GameState, Phase, PlayerState, Status
from quack_rl.rules import Ruleset


def _draw(p: PlayerState, seat: str, rs: Ruleset, chance: ChanceLog, events: list[dict[str, Any]]) -> None:
    chip_id = chance.draw_chip(p, seat)
    chip = rs.chip(chip_id)
    component = get_component(chip.component)
    previous = rs.chip(p.placed[-1]) if p.placed else None
    bonus = component.place_bonus(chip, previous)
    p.bag[chip_id] -= 1
    if p.bag[chip_id] == 0:
        del p.bag[chip_id]
    start = p.field
    p.field = min(start + chip.value + bonus, rs.track_end)
    p.white_total += component.explosion_weight(chip)
    p.placed.append(chip_id)
    events.append({"seat": seat, "kind": "place", "chip": chip_id, "from": start, "to": p.field, "bonus": bonus})
    if p.white_total > rs.explosion_limit:
        p.status = Status.EXPLODED
        events.append({"seat": seat, "kind": "explode", "white_total": p.white_total})
    elif sum(p.bag.values()) == 0:
        p.status = Status.STOPPED
        events.append({"seat": seat, "kind": "bag_empty"})


def apply_brew(
    state: GameState, rs: Ruleset, actions: dict[str, str], chance: ChanceLog, events: list[dict[str, Any]]
) -> None:
    for seat in SEATS:
        p = state.players[seat]
        if actions[seat] == DRAW:
            _draw(p, seat, rs, chance, events)
        elif actions[seat] == STOP:
            p.status = Status.STOPPED
            events.append({"seat": seat, "kind": "stop", "field": p.field})
    if all(p.status is not Status.BREWING for p in state.players.values()):
        for p in state.players.values():
            p.final_field = p.field
        state.phase = Phase.RESOLVE
```

`src/quack_rl/engine/game.py`:

```python
import copy
from dataclasses import dataclass
from typing import Any

from quack_rl.engine.actions import legal_actions
from quack_rl.engine.brew import apply_brew
from quack_rl.engine.chance import ChanceLog, ChanceSource
from quack_rl.engine.state import SEATS, GameState, Phase
from quack_rl.rules import Ruleset


class IllegalAction(ValueError):
    """An action that is not legal for the seat in the current state."""


class GameOver(RuntimeError):
    """step() was called after the game ended."""


@dataclass
class StepResult:
    state: GameState
    n: int
    round: int
    phase: Phase
    legal: dict[str, list[str]] | None
    actions: dict[str, str] | None
    chance: list[dict[str, Any]]
    events: list[dict[str, Any]]


def needs_actions(state: GameState) -> bool:
    return state.phase in (Phase.BREW, Phase.SHOP)


def step(state: GameState, rs: Ruleset, actions: dict[str, str] | None, chance: ChanceSource) -> StepResult:
    if state.phase is Phase.GAME_OVER:
        raise GameOver("the game is over")
    new = copy.deepcopy(state)
    log = ChanceLog(chance, rs)
    events: list[dict[str, Any]] = []
    legal: dict[str, list[str]] | None = None
    if needs_actions(state):
        if actions is None or set(actions) != set(SEATS):
            raise IllegalAction("a joint action needs exactly one action per seat")
        legal = {seat: legal_actions(state, rs, seat) for seat in SEATS}
        for seat in SEATS:
            if actions[seat] not in legal[seat]:
                raise IllegalAction(f"{seat}: {actions[seat]!r} is not legal (legal: {legal[seat]})")
        if state.phase is Phase.BREW:
            apply_brew(new, rs, actions, log, events)
        else:
            raise NotImplementedError("shop: Task 7")
    else:
        if actions is not None:
            raise IllegalAction("this step takes no actions")
        raise NotImplementedError("resolve: Task 6")
    new.step = state.step + 1
    return StepResult(
        state=new,
        n=new.step,
        round=state.round,
        phase=state.phase,
        legal=legal,
        actions=dict(actions) if actions is not None else None,
        chance=log.outcomes,
        events=events,
    )
```

Add to `src/quack_rl/engine/__init__.py` imports and `__all__`: `ChanceLog`, `ChanceSource`, `IllegalChance`, `RngChance`, `ScriptedChance` (from `chance`), `GameOver`, `IllegalAction`, `StepResult`, `needs_actions`, `step` (from `game`).

- [ ] **Step 4: Run the tests**

Run: `uv run --with pytest pytest tests/test_brew.py` → PASS
Run: `uv run --with pytest pytest && uv run ruff check . && uv run pyright` → no errors

- [ ] **Step 5: Commit**

```bash
git add src/quack_rl/engine tests/helpers.py tests/test_brew.py
git commit -m "Add chance sources, step function and brewing"
```

---

### Task 6: Resolve (rubies, green bonus, bonus die, money)

**Files:**
- Create: `src/quack_rl/engine/resolve.py`, `tests/test_resolve.py`
- Modify: `src/quack_rl/engine/game.py` (call `apply_resolve` instead of `NotImplementedError`)

**Interfaces:**
- Consumes: Task 5 (`ChanceLog`, `step`, `StepResult`), `get_component` (Task 3)
- Produces: `apply_resolve(state: GameState, rs: Ruleset, chance: ChanceLog, events: list[dict]) -> None`; after it, `state.phase is Phase.SHOP`, each player has `money` set, `purchases == 0`, `shop_done is False`. Event kinds: `ruby` (`halves`), `round_end_bonus` (`chip`, `halves`), `die` (`face`), `money` (`amount`)

- [ ] **Step 1: Write the failing test** `tests/test_resolve.py`

```python
from helpers import RS, auto, play
from quack_rl.engine import DRAW, STOP, Phase, Status, new_game


def brewed(p1_field, p2_field, p1_placed=("white_1",), p2_placed=("white_1",), exploded=()):
    """A state at the start of Resolve with settled final fields."""
    s = new_game(RS)
    s.phase = Phase.RESOLVE
    for seat, fld, placed in (("p1", p1_field, p1_placed), ("p2", p2_field, p2_placed)):
        p = s.players[seat]
        p.field = p.final_field = fld
        p.placed = list(placed)
        p.status = Status.EXPLODED if seat in exploded else Status.STOPPED
    return s


def test_resolve_takes_no_actions_and_moves_to_shop():
    r = auto(brewed(4, 3), "money_1")
    assert r.phase is Phase.RESOLVE and r.legal is None and r.actions is None
    assert r.state.phase is Phase.SHOP


def test_money_of_final_field_and_bonus_die_for_furthest():
    r = auto(brewed(20, 12), "money_1")
    assert r.state.players["p1"].money == 17 + 1
    assert r.state.players["p2"].money == 12
    assert r.chance == [{"seat": "p1", "kind": "die", "value": "money_1"}]


def test_exploded_gets_half_money_rounded_down_and_never_rolls():
    r = auto(brewed(21, 4, exploded=("p1",)), "point_1")
    assert r.state.players["p1"].money == 18 // 2
    assert r.chance == [{"seat": "p2", "kind": "die", "value": "point_1"}]
    assert r.state.players["p2"].points == 1


def test_both_exploded_nobody_rolls():
    r = auto(brewed(21, 11, exploded=("p1", "p2")))
    assert r.chance == []
    assert (r.state.players["p1"].money, r.state.players["p2"].money) == (9, 5)


def test_tied_furthest_both_roll():
    r = auto(brewed(10, 10), "droplet_1", "droplet_half")
    assert [c["seat"] for c in r.chance] == ["p1", "p2"]
    assert r.state.players["p1"].droplet_halves == 2
    assert r.state.players["p2"].droplet_halves == 1


def test_ruby_field_gives_half_step_also_after_explosion():
    r = auto(brewed(9, 9, exploded=("p1",)), "money_1")
    assert r.state.players["p1"].droplet_halves == 1
    assert {"seat": "p1", "kind": "ruby", "halves": 1} in r.events


def test_green_in_last_two_gives_half_step_each():
    r = auto(brewed(4, 3, p1_placed=("green_1", "orange_1", "green_2")), "money_1")
    assert r.state.players["p1"].droplet_halves == 1  # only green_2 is in the last two
    r = auto(brewed(4, 3, p1_placed=("white_1", "green_1", "green_2")), "money_1")
    assert r.state.players["p1"].droplet_halves == 2


def test_die_orange_chip_goes_into_the_bag():
    r = auto(brewed(4, 3), "orange_1")
    assert r.state.players["p1"].bag["orange_1"] == 2


def test_full_round_flow_brew_then_resolve():
    s = play(new_game(RS), DRAW, DRAW, "white_2", "orange_1").state
    s = play(s, STOP, STOP).state
    r = auto(s, "money_1")
    assert r.state.players["p1"].money == 2 + 1
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with pytest pytest tests/test_resolve.py`
Expected: FAIL (`NotImplementedError: resolve: Task 6`)

- [ ] **Step 3: Write the implementation** `src/quack_rl/engine/resolve.py`

```python
from typing import Any

from quack_rl.components import get_component
from quack_rl.engine.chance import ChanceLog
from quack_rl.engine.state import SEATS, GameState, Phase, PlayerState, Status
from quack_rl.rules import DieFace, Ruleset


def _apply_face(p: PlayerState, face: DieFace) -> int:
    """Apply a bonus die face; return extra money for this round."""
    if face.kind == "droplet":
        p.droplet_halves += face.halves
    elif face.kind == "chip" and face.chip is not None:
        p.bag[face.chip] = p.bag.get(face.chip, 0) + 1
    elif face.kind == "points":
        p.points += face.points
    elif face.kind == "money":
        return face.amount
    return 0


def apply_resolve(state: GameState, rs: Ruleset, chance: ChanceLog, events: list[dict[str, Any]]) -> None:
    extra_money = {seat: 0 for seat in SEATS}
    for seat in SEATS:
        p = state.players[seat]
        assert p.final_field is not None
        if p.final_field in rs.rubies:
            p.droplet_halves += 1
            events.append({"seat": seat, "kind": "ruby", "halves": 1})
        for position_from_end, chip_id in enumerate(reversed(p.placed[-2:])):
            chip = rs.chip(chip_id)
            halves = get_component(chip.component).round_end_droplet_halves(chip, position_from_end)
            if halves:
                p.droplet_halves += halves
                events.append({"seat": seat, "kind": "round_end_bonus", "chip": chip_id, "halves": halves})
    eligible = [s for s in SEATS if state.players[s].status is not Status.EXPLODED]
    if eligible:
        best = max(state.players[s].final_field or 0 for s in eligible)
        for seat in eligible:
            p = state.players[seat]
            if p.final_field == best:
                face = chance.roll_die(seat)
                extra_money[seat] += _apply_face(p, face)
                events.append({"seat": seat, "kind": "die", "face": face.id})
    for seat in SEATS:
        p = state.players[seat]
        assert p.final_field is not None
        money = rs.money[p.final_field]
        if p.status is Status.EXPLODED:
            money //= 2
        p.money = money + extra_money[seat]
        p.purchases = 0
        p.shop_done = False
        events.append({"seat": seat, "kind": "money", "amount": p.money})
    state.phase = Phase.SHOP
```

In `src/quack_rl/engine/game.py`, replace `raise NotImplementedError("resolve: Task 6")` with `apply_resolve(new, rs, log, events)` and import it.

- [ ] **Step 4: Run the tests**

Run: `uv run --with pytest pytest tests/test_resolve.py` → PASS
Run: `uv run --with pytest pytest && uv run ruff check . && uv run pyright` → no errors

- [ ] **Step 5: Commit**

```bash
git add src/quack_rl/engine tests/test_resolve.py
git commit -m "Add round resolve: rubies, green bonus, bonus die, money"
```

---

### Task 7: Shop, round reset and game end

**Files:**
- Create: `src/quack_rl/engine/shop.py`, `tests/test_shop_end.py`
- Modify: `src/quack_rl/engine/game.py` (call `apply_shop` instead of `NotImplementedError`)

**Interfaces:**
- Consumes: Tasks 4-6
- Produces: `apply_shop(state: GameState, rs: Ruleset, actions: dict[str, str], events: list[dict]) -> None`; `decide_winner(state: GameState) -> str`. Event kinds: `buy` (`item`, `price`), `done`, `round_end` (`next_round`), `game_end` (`winner`, `points`, `final_fields`). After round `rs.rounds`, `state.phase is Phase.GAME_OVER`, `state.winner` is set, and the final fields of the last round are kept (no reset)

- [ ] **Step 1: Write the failing test** `tests/test_shop_end.py`

```python
import pytest

from helpers import RS, play
from quack_rl.engine import DONE, WAIT, GameOver, Phase, RngChance, Status, buy, new_game, step


def shop_state(p1_money=20, p2_money=0):
    s = new_game(RS)
    s.phase = Phase.SHOP
    for seat, money in (("p1", p1_money), ("p2", p2_money)):
        p = s.players[seat]
        p.money, p.status = money, Status.STOPPED
        p.placed = ["white_1", "white_2"]
        p.bag["white_1"] -= 1
        p.bag["white_2"] -= 1
        p.field = p.final_field = 3
    return s


def test_buying_a_chip_puts_it_into_the_bag_and_costs_money():
    r = play(shop_state(), buy("blue_2"), DONE)
    p1 = r.state.players["p1"]
    assert (p1.money, p1.purchases, p1.bag["blue_2"]) == (11, 1, 1)
    assert {"seat": "p1", "kind": "buy", "item": "blue_2", "price": 9} in r.events


def test_points_are_added_at_once():
    r = play(shop_state(p1_money=22), buy("points_10"), DONE)
    assert r.state.players["p1"].points == 10


def test_same_item_may_be_bought_again_and_third_purchase_ends_shopping():
    s = play(shop_state(p1_money=9), buy("orange_1"), DONE).state
    s = play(s, buy("orange_1"), WAIT).state
    r = play(s, buy("orange_1"), WAIT)
    assert r.state.players["p1"].purchases == 3
    assert r.state.phase is Phase.BREW  # both done: next round started


def test_remove_white_1_takes_a_placed_chip_first():
    s = shop_state(p1_money=15)
    s = play(s, buy("remove_white_1"), DONE).state
    assert s.players["p1"].placed == ["white_2"]
    r = play(s, DONE, WAIT)
    # after the reset all chips are back in the bag: 4 white_1 at start, 1 removed
    assert r.state.players["p1"].bag["white_1"] == 3


def test_reset_returns_chips_and_starts_next_round_at_droplet():
    s = shop_state()
    s.players["p1"].droplet_halves = 3
    r = play(s, DONE, DONE)
    p1 = r.state.players["p1"]
    assert r.state.round == 2 and r.state.phase is Phase.BREW
    assert p1.placed == [] and p1.bag == RS.start_bag
    assert (p1.field, p1.money, p1.white_total, p1.final_field) == (1, 0, 0, None)
    assert p1.status is Status.BREWING
    assert {"seat": None, "kind": "round_end", "next_round": 2} in r.events


def test_unspent_money_is_lost():
    r = play(shop_state(p1_money=20), DONE, DONE)
    assert r.state.players["p1"].money == 0


def last_round(p1_points, p2_points, p1_final, p2_final):
    s = shop_state()
    s.round = RS.rounds
    s.players["p1"].points, s.players["p2"].points = p1_points, p2_points
    s.players["p1"].final_field, s.players["p2"].final_field = p1_final, p2_final
    return s


@pytest.mark.parametrize(
    ("p1_points", "p2_points", "p1_final", "p2_final", "winner"),
    [(10, 8, 3, 30, "p1"), (8, 8, 20, 12, "p1"), (8, 8, 12, 20, "p2"), (8, 8, 12, 12, "draw")],
)
def test_game_end_winner(p1_points, p2_points, p1_final, p2_final, winner):
    r = play(last_round(p1_points, p2_points, p1_final, p2_final), DONE, DONE)
    assert r.state.phase is Phase.GAME_OVER
    assert r.state.winner == winner
    assert r.events[-1]["kind"] == "game_end" and r.events[-1]["winner"] == winner


def test_final_field_is_not_changed_by_removing_the_last_placed_chip():
    s = last_round(5, 5, 20, 12)
    s.players["p1"].money = 15
    s.players["p1"].placed = ["white_2", "white_1"]
    s = play(s, buy("remove_white_1"), DONE).state
    r = play(s, DONE, WAIT)
    assert r.state.winner == "p1"
    assert r.state.players["p1"].final_field == 20


def test_step_after_game_over_raises():
    r = play(last_round(1, 0, 3, 3), DONE, DONE)
    with pytest.raises(GameOver):
        step(r.state, RS, {"p1": WAIT, "p2": WAIT}, RngChance(0))
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with pytest pytest tests/test_shop_end.py`
Expected: FAIL (`NotImplementedError: shop: Task 7`)

- [ ] **Step 3: Write the implementation** `src/quack_rl/engine/shop.py`

```python
from typing import Any

from quack_rl.engine.actions import BUY_PREFIX, DONE
from quack_rl.engine.state import SEATS, GameState, Phase, PlayerState, Status, start_field
from quack_rl.rules import Ruleset, ShopItem


def _apply_item(p: PlayerState, item: ShopItem) -> None:
    if item.kind == "chip" and item.chip is not None:
        p.bag[item.chip] = p.bag.get(item.chip, 0) + 1
    elif item.kind == "remove_chip" and item.chip is not None:
        if item.chip in p.placed:
            p.placed.remove(item.chip)
        else:
            p.bag[item.chip] -= 1
            if p.bag[item.chip] == 0:
                del p.bag[item.chip]
    elif item.kind == "droplet":
        p.droplet_halves += item.halves
    elif item.kind == "points":
        p.points += item.points


def decide_winner(state: GameState) -> str:
    p1, p2 = state.players["p1"], state.players["p2"]
    key1 = (p1.points, p1.final_field or 0)
    key2 = (p2.points, p2.final_field or 0)
    if key1 == key2:
        return "draw"
    return "p1" if key1 > key2 else "p2"


def _end_round(state: GameState, rs: Ruleset, events: list[dict[str, Any]]) -> None:
    if state.round >= rs.rounds:
        state.winner = decide_winner(state)
        state.phase = Phase.GAME_OVER
        events.append(
            {
                "seat": None,
                "kind": "game_end",
                "winner": state.winner,
                "points": {s: state.players[s].points for s in SEATS},
                "final_fields": {s: state.players[s].final_field for s in SEATS},
            }
        )
        return
    for p in state.players.values():
        for chip_id in p.placed:
            p.bag[chip_id] = p.bag.get(chip_id, 0) + 1
        p.placed = []
        p.money = 0
        p.white_total = 0
        p.status = Status.BREWING
        p.final_field = None
        p.purchases = 0
        p.shop_done = False
        p.field = start_field(p, rs)
    state.round += 1
    state.phase = Phase.BREW
    events.append({"seat": None, "kind": "round_end", "next_round": state.round})


def apply_shop(state: GameState, rs: Ruleset, actions: dict[str, str], events: list[dict[str, Any]]) -> None:
    for seat in SEATS:
        p = state.players[seat]
        action = actions[seat]
        if action == DONE:
            p.shop_done = True
            events.append({"seat": seat, "kind": "done"})
        elif action.startswith(BUY_PREFIX):
            item = rs.shop_item(action.removeprefix(BUY_PREFIX))
            p.money -= item.price
            p.purchases += 1
            _apply_item(p, item)
            events.append({"seat": seat, "kind": "buy", "item": item.id, "price": item.price})
            if p.purchases >= rs.max_purchases:
                p.shop_done = True
    if all(p.shop_done for p in state.players.values()):
        _end_round(state, rs, events)
```

In `src/quack_rl/engine/game.py`, replace `raise NotImplementedError("shop: Task 7")` with `apply_shop(new, rs, actions, events)` and import it.

- [ ] **Step 4: Run the tests**

Run: `uv run --with pytest pytest tests/test_shop_end.py` → PASS
Run: `uv run --with pytest pytest && uv run ruff check . && uv run pyright` → no errors

- [ ] **Step 5: Commit**

```bash
git add src/quack_rl/engine tests/test_shop_end.py
git commit -m "Add shop, round reset and game end"
```

---

### Task 8: Random bot, game runner and invariant tests

**Files:**
- Create: `src/quack_rl/bots/__init__.py`, `src/quack_rl/bots/random_bot.py`, `src/quack_rl/runner.py`, `tests/test_runner_invariants.py`

**Interfaces:**
- Consumes: the engine API (Tasks 4-7)
- Produces:
  - `quack_rl.runner.Seat` (Protocol): attributes `kind: str` (`"human"` or `"bot"`), `name: str`, `params: dict[str, Any]`; method `choose(state: GameState, seat: str, legal: list[str]) -> str`
  - `quack_rl.runner.StepCallback = Callable[[StepResult, dict[str, int]], None]` (second argument: decision time in ms per human seat)
  - `quack_rl.runner.play_game(rs: Ruleset, seats: Mapping[str, Seat], chance: ChanceSource, on_step: StepCallback | None = None) -> GameState`
  - A seat whose only legal action is `wait` is not asked; it gets `wait` automatically
  - `quack_rl.bots.RandomBot(seed: int | None = None)`: `kind = "bot"`, `name = "random"`, `params = {"seed": seed}`

- [ ] **Step 1: Write the failing test** `tests/test_runner_invariants.py`

```python
from collections import Counter

from hypothesis import given
from hypothesis import strategies as st

from helpers import RS
from quack_rl.bots import RandomBot
from quack_rl.engine import SEATS, Phase, RngChance
from quack_rl.runner import play_game


def run(seed):
    results = []
    final = play_game(
        RS,
        {"p1": RandomBot(seed * 2 + 1), "p2": RandomBot(seed * 2 + 2)},
        RngChance(seed),
        on_step=lambda r, ms: results.append(r),
    )
    return final, results


def test_a_seeded_game_is_reproducible():
    a, ra = run(7)
    b, rb = run(7)
    assert a == b and [r.events for r in ra] == [r.events for r in rb]


def test_a_game_ends_after_nine_rounds_with_a_winner():
    final, results = run(3)
    assert final.phase is Phase.GAME_OVER and final.round == RS.rounds
    assert final.winner in ("p1", "p2", "draw")
    assert [r.n for r in results] == list(range(1, len(results) + 1))


@given(seed=st.integers(min_value=0, max_value=2**31 - 1))
def test_invariants_hold_in_random_games(seed):
    final, results = run(seed)
    acquired = {s: Counter(RS.start_bag) for s in SEATS}
    for r in results:
        for e in r.events:
            if e["kind"] == "buy":
                item = RS.shop_item(e["item"])
                if item.kind == "chip":
                    acquired[e["seat"]][item.chip] += 1
                elif item.kind == "remove_chip":
                    acquired[e["seat"]][item.chip] -= 1
            if e["kind"] == "die":
                face = next(f for f in RS.die if f.id == e["face"])
                if face.kind == "chip":
                    acquired[e["seat"]][face.chip] += 1
        for seat in SEATS:
            p = r.state.players[seat]
            # chip accounting per chip type: owned = start + bought + die - removed = bag + placed
            owned = Counter(p.bag) + Counter(p.placed)
            assert +acquired[seat] == owned
            assert p.money >= 0
            assert 0 <= p.field <= RS.track_end
            assert all(n > 0 for n in p.bag.values())
            if r.actions is not None:
                assert r.actions[seat] in r.legal[seat]
        if any(e["kind"] == "round_end" for e in r.events):
            assert all(not p.placed for p in r.state.players.values())
    assert final.phase is Phase.GAME_OVER
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with pytest pytest tests/test_runner_invariants.py`
Expected: FAIL (`ModuleNotFoundError: No module named 'quack_rl.bots'`)

- [ ] **Step 3: Write the implementation**

`src/quack_rl/bots/random_bot.py`:

```python
import random
from typing import Any

from quack_rl.engine import GameState


class RandomBot:
    """Chooses uniformly among the legal actions."""

    kind = "bot"
    name = "random"

    def __init__(self, seed: int | None = None):
        self._rng = random.Random(seed)
        self.params: dict[str, Any] = {"seed": seed}

    def choose(self, state: GameState, seat: str, legal: list[str]) -> str:
        return self._rng.choice(legal)
```

`src/quack_rl/bots/__init__.py`:

```python
from quack_rl.bots.random_bot import RandomBot

__all__ = ["RandomBot"]
```

`src/quack_rl/runner.py`:

```python
import time
from collections.abc import Callable, Mapping
from typing import Any, Protocol

from quack_rl.engine import (
    SEATS,
    WAIT,
    ChanceSource,
    GameState,
    Phase,
    StepResult,
    legal_actions,
    needs_actions,
    new_game,
    step,
)
from quack_rl.rules import Ruleset


class Seat(Protocol):
    kind: str
    name: str
    params: dict[str, Any]

    def choose(self, state: GameState, seat: str, legal: list[str]) -> str: ...


StepCallback = Callable[[StepResult, dict[str, int]], None]


def play_game(
    rs: Ruleset,
    seats: Mapping[str, Seat],
    chance: ChanceSource,
    on_step: StepCallback | None = None,
) -> GameState:
    state = new_game(rs)
    while state.phase is not Phase.GAME_OVER:
        actions: dict[str, str] | None = None
        decision_ms: dict[str, int] = {}
        if needs_actions(state):
            actions = {}
            for seat in SEATS:
                legal = legal_actions(state, rs, seat)
                if legal == [WAIT]:
                    actions[seat] = WAIT
                    continue
                started = time.perf_counter()
                actions[seat] = seats[seat].choose(state, seat, legal)
                if seats[seat].kind == "human":
                    decision_ms[seat] = round((time.perf_counter() - started) * 1000)
        result = step(state, rs, actions, chance)
        if on_step is not None:
            on_step(result, decision_ms)
        state = result.state
    return state
```

- [ ] **Step 4: Run the tests**

Run: `uv run --with pytest pytest tests/test_runner_invariants.py` → PASS
Run: `uv run --with pytest pytest` → whole suite PASS, under about 30 seconds
Run: `uv run ruff check . && uv run pyright` → no errors

- [ ] **Step 5: Commit**

```bash
git add src/quack_rl/bots src/quack_rl/runner.py tests/test_runner_invariants.py
git commit -m "Add random bot, game runner and invariant tests"
```

---

### Task 9: Record format, writer, store and reader

**Files:**
- Create: `src/quack_rl/record/__init__.py`, `src/quack_rl/record/schema.py`, `src/quack_rl/record/writer.py`, `src/quack_rl/record/store.py`, `src/quack_rl/record/reader.py`, `tests/test_record.py`

**Interfaces:**
- Consumes: `StepResult`, `GameState`, `play_game`, `RandomBot` (Tasks 5-8)
- Produces (re-exported from `quack_rl.record`):
  - `RECORD_SCHEMA_VERSION = 1`
  - `SeatInfo(kind: Literal["human", "bot"], name: str, params: dict[str, Any] = {})`
  - `HeaderLine(type="header", game_id, schema_version, rules_version, seed: int | None, mode: Literal["play", "sim"], seats: dict[str, SeatInfo], ui: dict[str, Any], engine_version, started_at)`
  - `StepLine(type="step", game_id, n, round, phase: str, legal: dict[str, list[str]] | None, actions: dict[str, str] | None, chance: list[dict], events: list[dict], decision_ms: dict[str, int] | None = None)`
  - `FooterLine(type="footer", game_id, points: dict[str, int], final_fields: dict[str, int | None], winner: str)`
  - `record_json_schema() -> dict` (JSON Schema of one line)
  - `GameRecorder(stream: TextIO, header: HeaderLine)` with `on_step(result: StepResult, decision_ms: dict[str, int]) -> None` and `close(state: GameState) -> None`
  - `berlin_stamp(now: datetime | None = None) -> str`, `berlin_iso(now: datetime | None = None) -> str`, `new_game_id() -> str`
  - `RecordStore` (Protocol) and `LocalRecordStore(root: Path = Path("data/records"))` with `new_play_path(rules_version: str, now: datetime | None = None) -> Path`, `new_sim_dir(rules_version: str, now: datetime | None = None) -> Path`, `shard_path(sim_dir: Path, index: int) -> Path`, `list_records(rules_version: str | None = None) -> list[Path]`
  - `RecordedGame(header: HeaderLine, steps: list[StepLine], footer: FooterLine | None)`, `read_games(path: Path) -> Iterator[RecordedGame]`, `RecordFormatError(ValueError)`

- [ ] **Step 1: Write the failing test** `tests/test_record.py`

```python
import io
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from helpers import RS
from quack_rl.bots import RandomBot
from quack_rl.engine import RngChance
from quack_rl.record import (
    GameRecorder,
    HeaderLine,
    LocalRecordStore,
    RecordFormatError,
    SeatInfo,
    berlin_stamp,
    read_games,
    record_json_schema,
)
from quack_rl.runner import play_game


def header(game_id="g1", seed=5):
    return HeaderLine(
        game_id=game_id, schema_version=1, rules_version="v1", seed=seed, mode="sim",
        seats={"p1": SeatInfo(kind="bot", name="random"), "p2": SeatInfo(kind="bot", name="random")},
        ui={}, engine_version="0.1.0", started_at="2026-10-08T21:15:03+02:00",
    )


def record_game(stream, game_id="g1", seed=5):
    rec = GameRecorder(stream, header(game_id, seed))
    final = play_game(RS, {"p1": RandomBot(1), "p2": RandomBot(2)}, RngChance(seed), rec.on_step)
    rec.close(final)
    return final


def test_every_line_is_json_with_game_id_and_type(tmp_path):
    path = tmp_path / "g.jsonl"
    with path.open("w", encoding="utf-8") as f:
        record_game(f)
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert lines[0]["type"] == "header" and lines[-1]["type"] == "footer"
    assert all(line["game_id"] == "g1" for line in lines)
    assert {line["type"] for line in lines[1:-1]} == {"step"}


def test_round_trip_one_game(tmp_path):
    path = tmp_path / "g.jsonl"
    with path.open("w", encoding="utf-8") as f:
        final = record_game(f)
    (game,) = read_games(path)
    assert game.footer is not None and game.footer.winner == final.winner
    assert game.steps[0].n == 1 and game.steps[-1].n == len(game.steps)
    assert game.steps[0].actions == {"p1": "draw", "p2": "draw"}


def test_a_shard_holds_several_games(tmp_path):
    path = tmp_path / "shard-0001.jsonl"
    with path.open("w", encoding="utf-8") as f:
        record_game(f, "g1", 5)
        record_game(f, "g2", 6)
    assert [g.header.game_id for g in read_games(path)] == ["g1", "g2"]


def test_an_aborted_game_has_no_footer(tmp_path):
    path = tmp_path / "g.jsonl"
    with path.open("w", encoding="utf-8") as f:
        GameRecorder(f, header())
    (game,) = read_games(path)
    assert game.footer is None and game.steps == []


def test_step_line_without_header_is_an_error(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text(json.dumps({"type": "step", "game_id": "x", "n": 1, "round": 1, "phase": "brew",
                                "legal": None, "actions": None, "chance": [], "events": []}) + "\n")
    with pytest.raises(RecordFormatError):
        list(read_games(path))


def test_berlin_stamp_uses_summer_and_winter_offsets():
    summer = datetime(2026, 10, 8, 19, 15, 3, tzinfo=ZoneInfo("UTC"))
    winter = datetime(2026, 11, 8, 20, 15, 3, tzinfo=ZoneInfo("UTC"))
    assert berlin_stamp(summer) == "2026-10-08_21-15-03+0200"
    assert berlin_stamp(winter) == "2026-11-08_21-15-03+0100"


def test_local_store_paths(tmp_path):
    store = LocalRecordStore(tmp_path)
    now = datetime(2026, 10, 8, 19, 15, 3, tzinfo=ZoneInfo("UTC"))
    play_path = store.new_play_path("v1", now)
    assert play_path.parent == tmp_path / "v1" / "play"
    assert play_path.name.startswith("2026-10-08_21-15-03+0200_") and play_path.suffix == ".jsonl"
    sim_dir = store.new_sim_dir("v1", now)
    assert sim_dir.parent == tmp_path / "v1" / "sim" and sim_dir.is_dir()
    assert store.shard_path(sim_dir, 1).name == "shard-0001.jsonl"


def test_json_schema_is_available():
    schema = record_json_schema()
    assert "header" in json.dumps(schema) and "footer" in json.dumps(schema)


def test_decision_ms_is_written_only_when_given():
    buf = io.StringIO()
    record_game(buf)
    lines = [json.loads(line) for line in buf.getvalue().splitlines()]
    steps = [line for line in lines if line["type"] == "step"]
    assert steps and all(s["decision_ms"] is None for s in steps)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with pytest pytest tests/test_record.py`
Expected: FAIL (`ModuleNotFoundError: No module named 'quack_rl.record'`)

- [ ] **Step 3: Write the implementation**

`src/quack_rl/record/schema.py`:

```python
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

RECORD_SCHEMA_VERSION = 1


class _Line(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SeatInfo(_Line):
    kind: Literal["human", "bot"]
    name: str
    params: dict[str, Any] = {}


class HeaderLine(_Line):
    type: Literal["header"] = "header"
    game_id: str
    schema_version: int
    rules_version: str
    seed: int | None
    mode: Literal["play", "sim"]
    seats: dict[str, SeatInfo]
    ui: dict[str, Any]
    engine_version: str
    started_at: str


class StepLine(_Line):
    type: Literal["step"] = "step"
    game_id: str
    n: int
    round: int
    phase: str
    legal: dict[str, list[str]] | None
    actions: dict[str, str] | None
    chance: list[dict[str, Any]]
    events: list[dict[str, Any]]
    decision_ms: dict[str, int] | None = None


class FooterLine(_Line):
    type: Literal["footer"] = "footer"
    game_id: str
    points: dict[str, int]
    final_fields: dict[str, int | None]
    winner: str


Line = Annotated[HeaderLine | StepLine | FooterLine, Field(discriminator="type")]
LINE_ADAPTER: TypeAdapter[HeaderLine | StepLine | FooterLine] = TypeAdapter(Line)


def record_json_schema() -> dict[str, Any]:
    return LINE_ADAPTER.json_schema()
```

`src/quack_rl/record/writer.py`:

```python
from typing import TextIO

from pydantic import BaseModel

from quack_rl.engine import SEATS, GameState, StepResult
from quack_rl.record.schema import FooterLine, HeaderLine, StepLine


class GameRecorder:
    """Writes one game as JSON Lines, one line at a time (flushed after each line)."""

    def __init__(self, stream: TextIO, header: HeaderLine):
        self._stream = stream
        self.game_id = header.game_id
        self._write(header)

    def _write(self, line: BaseModel) -> None:
        self._stream.write(line.model_dump_json(exclude_none=False) + "\n")
        self._stream.flush()

    def on_step(self, result: StepResult, decision_ms: dict[str, int]) -> None:
        self._write(
            StepLine(
                game_id=self.game_id,
                n=result.n,
                round=result.round,
                phase=result.phase.value,
                legal=result.legal,
                actions=result.actions,
                chance=result.chance,
                events=result.events,
                decision_ms=decision_ms or None,
            )
        )

    def close(self, state: GameState) -> None:
        self._write(
            FooterLine(
                game_id=self.game_id,
                points={s: state.players[s].points for s in SEATS},
                final_fields={s: state.players[s].final_field for s in SEATS},
                winner=state.winner or "",
            )
        )
```

`src/quack_rl/record/store.py`:

```python
import secrets
from datetime import datetime
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")


def _berlin(now: datetime | None) -> datetime:
    return (now or datetime.now(BERLIN)).astimezone(BERLIN)


def berlin_stamp(now: datetime | None = None) -> str:
    return _berlin(now).strftime("%Y-%m-%d_%H-%M-%S%z")


def berlin_iso(now: datetime | None = None) -> str:
    return _berlin(now).isoformat(timespec="seconds")


def new_game_id() -> str:
    return secrets.token_hex(8)


class RecordStore(Protocol):
    def new_play_path(self, rules_version: str, now: datetime | None = None) -> Path: ...

    def new_sim_dir(self, rules_version: str, now: datetime | None = None) -> Path: ...

    def shard_path(self, sim_dir: Path, index: int) -> Path: ...

    def list_records(self, rules_version: str | None = None) -> list[Path]: ...


class LocalRecordStore:
    """Records as files under data/records/<rules_version>/{play,sim}/ (spec 6.2)."""

    def __init__(self, root: Path = Path("data/records")):
        self.root = root

    def new_play_path(self, rules_version: str, now: datetime | None = None) -> Path:
        folder = self.root / rules_version / "play"
        folder.mkdir(parents=True, exist_ok=True)
        return folder / f"{berlin_stamp(now)}_{secrets.token_hex(2)}.jsonl"

    def new_sim_dir(self, rules_version: str, now: datetime | None = None) -> Path:
        folder = self.root / rules_version / "sim" / f"{berlin_stamp(now)}_{secrets.token_hex(2)}"
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def shard_path(self, sim_dir: Path, index: int) -> Path:
        return sim_dir / f"shard-{index:04d}.jsonl"

    def list_records(self, rules_version: str | None = None) -> list[Path]:
        base = self.root / rules_version if rules_version else self.root
        return sorted(base.glob("**/*.jsonl"))
```

`src/quack_rl/record/reader.py`:

```python
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from quack_rl.record.schema import LINE_ADAPTER, FooterLine, HeaderLine, StepLine


class RecordFormatError(ValueError):
    """A record file that does not follow the record format."""


@dataclass
class RecordedGame:
    header: HeaderLine
    steps: list[StepLine] = field(default_factory=list)
    footer: FooterLine | None = None


def read_games(path: Path) -> Iterator[RecordedGame]:
    """Yield each game of a record file. An unfinished game is yielded with footer None."""
    current: RecordedGame | None = None
    with path.open(encoding="utf-8") as f:
        for number, text in enumerate(f, start=1):
            if not text.strip():
                continue
            try:
                line = LINE_ADAPTER.validate_json(text)
            except ValidationError as e:
                raise RecordFormatError(f"{path}:{number}: {e}") from e
            if isinstance(line, HeaderLine):
                if current is not None:
                    yield current
                current = RecordedGame(header=line)
                continue
            if current is None or current.footer is not None:
                raise RecordFormatError(f"{path}:{number}: {line.type} line outside a game")
            if line.game_id != current.header.game_id:
                raise RecordFormatError(f"{path}:{number}: game_id {line.game_id} inside game {current.header.game_id}")
            if isinstance(line, StepLine):
                current.steps.append(line)
            else:
                current.footer = line
                yield current
                current = None
    if current is not None:
        yield current
```

`src/quack_rl/record/__init__.py`: re-export `RECORD_SCHEMA_VERSION`, `SeatInfo`, `HeaderLine`, `StepLine`, `FooterLine`, `record_json_schema`, `GameRecorder`, `RecordStore`, `LocalRecordStore`, `berlin_stamp`, `berlin_iso`, `new_game_id`, `RecordedGame`, `read_games`, `RecordFormatError`.

Note on `read_games` and a completed game: the generator yields at the footer and sets `current = None`, so a following header starts a new game; a following step line raises `RecordFormatError`.

- [ ] **Step 4: Run the tests**

Run: `uv run --with pytest pytest tests/test_record.py` → PASS
Run: `uv run --with pytest pytest && uv run ruff check . && uv run pyright` → no errors

- [ ] **Step 5: Commit**

```bash
git add src/quack_rl/record tests/test_record.py
git commit -m "Add record format, writer, local record store and reader"
```

---

### Task 10: Replay and verify, with golden and corrupted records

**Files:**
- Create: `src/quack_rl/record/replay.py`, `tests/fixtures/make_golden.py`, `tests/fixtures/golden/v1_random_seed7.jsonl` (generated), `tests/test_verify.py`
- Modify: `src/quack_rl/record/__init__.py` (re-export)

**Interfaces:**
- Consumes: Tasks 2-9
- Produces:
  - `RecordedChance(outcomes: list[dict])`: a `ChanceSource` that returns the recorded outcomes in order and checks seat and kind; `assert_consumed() -> None`; raises `ChanceMismatch(ValueError)`
  - `verify_game(game: RecordedGame) -> list[str]`: problems, empty list = valid
  - `verify_seed(game: RecordedGame) -> list[str]`: replays the recorded actions with `RngChance(header.seed)` and compares chance outcomes

- [ ] **Step 1: Write the golden fixture generator** `tests/fixtures/make_golden.py`

```python
"""Regenerate the golden record. Only run this on purpose: the golden file pins rules v1 behavior.

    uv run python tests/fixtures/make_golden.py
"""

from pathlib import Path

from quack_rl import __version__
from quack_rl.bots import RandomBot
from quack_rl.engine import RngChance
from quack_rl.record import GameRecorder, HeaderLine, SeatInfo
from quack_rl.rules import load_ruleset
from quack_rl.runner import play_game

OUT = Path(__file__).parent / "golden" / "v1_random_seed7.jsonl"


def main() -> None:
    rs = load_ruleset("v1")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    header = HeaderLine(
        game_id="golden-v1-seed7", schema_version=1, rules_version="v1", seed=7, mode="sim",
        seats={"p1": SeatInfo(kind="bot", name="random", params={"seed": 15}),
               "p2": SeatInfo(kind="bot", name="random", params={"seed": 16})},
        ui={}, engine_version=__version__, started_at="2026-10-08T12:00:00+02:00",
    )
    with OUT.open("w", encoding="utf-8") as f:
        rec = GameRecorder(f, header)
        final = play_game(rs, {"p1": RandomBot(15), "p2": RandomBot(16)}, RngChance(7), rec.on_step)
        rec.close(final)


if __name__ == "__main__":
    main()
```

Run: `uv run python tests/fixtures/make_golden.py` after Step 3, and commit the generated file.

- [ ] **Step 2: Write the failing test** `tests/test_verify.py`

```python
import copy
from pathlib import Path

from quack_rl.record import read_games, verify_game, verify_seed

GOLDEN = Path(__file__).parent / "fixtures" / "golden" / "v1_random_seed7.jsonl"


def golden():
    (game,) = read_games(GOLDEN)
    return game


def first_step_with_draw(game):
    return next(s for s in game.steps if any(c["kind"] == "draw_chip" for c in s.chance))


def test_golden_record_verifies():
    assert verify_game(golden()) == []


def test_golden_record_matches_its_seed():
    assert verify_seed(golden()) == []


def test_unsupported_rules_version_is_refused():
    game = golden()
    game.header.rules_version = "v9"
    assert verify_game(game) == ["unsupported rules version 'v9'"]


def test_impossible_chip_draw_is_rejected():
    game = copy.deepcopy(golden())
    first_step_with_draw(game).chance[0]["value"] = "blue_4"  # not in the start bag
    problems = verify_game(game)
    assert problems and "not in the bag" in problems[0]


def test_extra_chance_outcome_is_rejected():
    game = copy.deepcopy(golden())
    s = first_step_with_draw(game)
    s.chance.append({"seat": "p1", "kind": "die", "value": "money_1"})
    problems = verify_game(game)
    assert problems and "extra chance outcome" in problems[0]


def test_missing_chance_outcome_is_rejected():
    game = copy.deepcopy(golden())
    first_step_with_draw(game).chance.clear()
    problems = verify_game(game)
    assert problems and "missing chance outcome" in problems[0]


def test_changed_event_is_reported():
    game = copy.deepcopy(golden())
    game.steps[0].events[0]["to"] = 40
    problems = verify_game(game)
    assert problems and "events differ" in problems[0]


def test_changed_legal_actions_are_reported():
    game = copy.deepcopy(golden())
    game.steps[0].legal = {"p1": ["draw", "stop"], "p2": ["draw"]}
    problems = verify_game(game)
    assert problems and "legal actions differ" in problems[0]


def test_incomplete_game_is_reported_not_crashing():
    game = copy.deepcopy(golden())
    game.steps = game.steps[:10]
    game.footer = None
    assert verify_game(game) == ["incomplete game: no footer"]


def test_wrong_footer_is_reported():
    game = copy.deepcopy(golden())
    assert game.footer is not None
    game.footer.winner = "p2" if game.footer.winner != "p2" else "p1"
    assert any("footer" in p for p in verify_game(game))
```

- [ ] **Step 3: Write the implementation** `src/quack_rl/record/replay.py`

```python
from collections.abc import Mapping, Sequence
from typing import Any

from quack_rl.engine import (
    SEATS,
    GameOver,
    GameState,
    IllegalAction,
    IllegalChance,
    Phase,
    RngChance,
    new_game,
    step,
)
from quack_rl.record.reader import RecordedGame
from quack_rl.rules import SUPPORTED_RULES_VERSIONS, DieFace, load_ruleset


class ChanceMismatch(ValueError):
    """The recorded chance outcomes do not fit the replayed step."""


class RecordedChance:
    """Returns the recorded chance outcomes of one step, in order."""

    def __init__(self, outcomes: list[dict[str, Any]]):
        self._outcomes = outcomes
        self._next = 0

    def _take(self, kind: str, seat: str) -> str:
        if self._next >= len(self._outcomes):
            raise ChanceMismatch(f"missing chance outcome: expected {kind} for {seat}")
        outcome = self._outcomes[self._next]
        if outcome["kind"] != kind or outcome["seat"] != seat:
            raise ChanceMismatch(f"chance outcome {outcome} does not fit: expected {kind} for {seat}")
        self._next += 1
        return outcome["value"]

    def draw_chip(self, bag: Mapping[str, int], seat: str) -> str:
        return self._take("draw_chip", seat)

    def roll_die(self, faces: Sequence[DieFace], seat: str) -> str:
        return self._take("die", seat)

    def assert_consumed(self) -> None:
        if self._next != len(self._outcomes):
            raise ChanceMismatch(f"extra chance outcome: {self._outcomes[self._next:]}")


def _footer_problems(game: RecordedGame, state: GameState) -> list[str]:
    footer = game.footer
    if footer is None:
        return ["incomplete game: no footer"]
    if state.phase is not Phase.GAME_OVER:
        return ["footer before the game ended"]
    expected = (
        {s: state.players[s].points for s in SEATS},
        {s: state.players[s].final_field for s in SEATS},
        state.winner,
    )
    if (footer.points, footer.final_fields, footer.winner) != expected:
        return [f"footer differs: recorded {footer.model_dump()}, replayed {expected}"]
    return []


def verify_game(game: RecordedGame) -> list[str]:
    version = game.header.rules_version
    if version not in SUPPORTED_RULES_VERSIONS:
        return [f"unsupported rules version {version!r}"]
    rs = load_ruleset(version)
    state = new_game(rs)
    for line in game.steps:
        where = f"step {line.n}"
        if (line.n, line.round, line.phase) != (state.step + 1, state.round, state.phase.value):
            return [f"{where}: position differs (replayed step {state.step + 1}, round {state.round}, {state.phase})"]
        chance = RecordedChance(line.chance)
        try:
            result = step(state, rs, line.actions, chance)
            chance.assert_consumed()
        except (IllegalAction, IllegalChance, ChanceMismatch, GameOver) as e:
            return [f"{where}: {e}"]
        if result.legal != line.legal:
            return [f"{where}: legal actions differ: recorded {line.legal}, replayed {result.legal}"]
        if result.events != line.events:
            return [f"{where}: events differ: recorded {line.events}, replayed {result.events}"]
        state = result.state
    return _footer_problems(game, state)


def verify_seed(game: RecordedGame) -> list[str]:
    if game.header.seed is None:
        return ["no seed recorded"]
    if game.header.rules_version not in SUPPORTED_RULES_VERSIONS:
        return [f"unsupported rules version {game.header.rules_version!r}"]
    rs = load_ruleset(game.header.rules_version)
    chance = RngChance(game.header.seed)
    state = new_game(rs)
    for line in game.steps:
        try:
            result = step(state, rs, line.actions, chance)
        except (IllegalAction, IllegalChance, GameOver) as e:
            return [f"step {line.n}: {e}"]
        if result.chance != line.chance:
            return [f"step {line.n}: chance differs from seed: recorded {line.chance}, seed gives {result.chance}"]
        state = result.state
    return []
```

Re-export `ChanceMismatch`, `RecordedChance`, `verify_game`, `verify_seed` from `quack_rl.record`.

- [ ] **Step 4: Generate the golden record and run the tests**

Run: `uv run python tests/fixtures/make_golden.py`
Run: `uv run --with pytest pytest tests/test_verify.py` → PASS
Run: `uv run --with pytest pytest && uv run ruff check . && uv run pyright` → no errors

- [ ] **Step 5: Commit**

```bash
git add src/quack_rl/record tests/fixtures tests/test_verify.py
git commit -m "Add replay and verify with golden and corrupted record tests"
```

---

### Task 11: CLI commands simulate, verify and replay

**Files:**
- Create: `src/quack_rl/cli/seats.py`, `tests/test_cli_sim.py`
- Modify: `src/quack_rl/cli/main.py`

**Interfaces:**
- Consumes: Tasks 8-10 (`play_game`, `RandomBot`, `GameRecorder`, `LocalRecordStore`, `read_games`, `verify_game`, `verify_seed`)
- Produces:
  - `quack_rl.cli.seats.parse_seat(spec: str, seed: int | None) -> Seat`: `"bot:random"` → `RandomBot(seed)`; `"human"` → `HumanSeatRequired` error in this task (Task 12 adds human seats); anything else → `typer.BadParameter`
  - `quack_rl.cli.seats.seat_info(seat: Seat) -> SeatInfo`
  - Commands: `quack-rl simulate [--p1 bot:random] [--p2 bot:random] [--games 100] [--seed 0] [--shard-size 1000] [--rules v1] [--out data/records]`; `quack-rl verify PATH [--seed-check]` (exit code 1 when a problem is found); `quack-rl replay PATH [--game GAME_ID]` (prints each step as one text line)
  - Simulation seeds: game `i` (0-based) uses chance seed `seed + i`, p1 bot seed `2 * (seed + i) + 1`, p2 bot seed `2 * (seed + i) + 2`

- [ ] **Step 1: Write the failing test** `tests/test_cli_sim.py`

```python
from pathlib import Path

from typer.testing import CliRunner

from quack_rl.cli.main import app
from quack_rl.record import read_games

runner = CliRunner()
GOLDEN = Path(__file__).parent / "fixtures" / "golden" / "v1_random_seed7.jsonl"


def sim(tmp_path, *extra):
    return runner.invoke(app, ["simulate", "--games", "5", "--seed", "3", "--out", str(tmp_path), *extra])


def test_simulate_writes_shards_of_games(tmp_path):
    result = sim(tmp_path, "--shard-size", "2")
    assert result.exit_code == 0, result.output
    shards = sorted((tmp_path / "v1" / "sim").glob("*/shard-*.jsonl"))
    assert [s.name for s in shards] == ["shard-0001.jsonl", "shard-0002.jsonl", "shard-0003.jsonl"]
    games = [g for s in shards for g in read_games(s)]
    assert len(games) == 5 and all(g.footer is not None for g in games)
    assert games[0].header.mode == "sim" and games[0].header.seed == 3
    assert "5 games" in result.output


def test_simulate_is_reproducible(tmp_path):
    sim(tmp_path / "a")
    sim(tmp_path / "b")

    def winners(root):
        return [g.footer.winner for s in sorted(root.glob("v1/sim/*/shard-*.jsonl")) for g in read_games(s)]

    assert winners(tmp_path / "a") == winners(tmp_path / "b")


def test_verify_accepts_simulated_records(tmp_path):
    sim(tmp_path)
    (shard,) = (tmp_path / "v1" / "sim").glob("*/shard-0001.jsonl")
    result = runner.invoke(app, ["verify", str(shard), "--seed-check"])
    assert result.exit_code == 0, result.output
    assert "5 games ok" in result.output


def test_verify_fails_on_a_broken_record(tmp_path):
    bad = tmp_path / "bad.jsonl"
    lines = GOLDEN.read_text(encoding="utf-8").splitlines()
    bad.write_text("\n".join(lines[:20]) + "\n", encoding="utf-8")
    result = runner.invoke(app, ["verify", str(bad)])
    assert result.exit_code == 1
    assert "incomplete game" in result.output


def test_replay_prints_steps(tmp_path):
    result = runner.invoke(app, ["replay", str(GOLDEN)])
    assert result.exit_code == 0
    assert "round 1" in result.output and "p1" in result.output


def test_human_seat_is_refused_in_simulate(tmp_path):
    result = sim(tmp_path, "--p1", "human")
    assert result.exit_code != 0
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with pytest pytest tests/test_cli_sim.py`
Expected: FAIL (`No such command 'simulate'`)

- [ ] **Step 3: Write the implementation**

`src/quack_rl/cli/seats.py`:

```python
import typer

from quack_rl.bots import RandomBot
from quack_rl.record import SeatInfo
from quack_rl.runner import Seat


class HumanSeatRequired(typer.BadParameter):
    """A human seat was given where only bots are allowed."""


def parse_seat(spec: str, seed: int | None) -> Seat:
    if spec == "bot:random":
        return RandomBot(seed)
    if spec == "human":
        raise HumanSeatRequired("human seats are only allowed in `quack-rl play`")
    raise typer.BadParameter(f"unknown seat {spec!r} (known: bot:random, human)")


def seat_info(seat: Seat) -> SeatInfo:
    return SeatInfo(kind="human" if seat.kind == "human" else "bot", name=seat.name, params=dict(seat.params))
```

Add to `src/quack_rl/cli/main.py`:

```python
from collections import Counter
from pathlib import Path

from quack_rl.engine import RngChance
from quack_rl.record import (
    RECORD_SCHEMA_VERSION,
    GameRecorder,
    HeaderLine,
    LocalRecordStore,
    berlin_iso,
    new_game_id,
    read_games,
    verify_game,
    verify_seed,
)
from quack_rl.cli.seats import parse_seat, seat_info
from quack_rl.rules import load_ruleset
from quack_rl.runner import play_game


@app.command()
def simulate(
    p1: str = "bot:random",
    p2: str = "bot:random",
    games: int = 100,
    seed: int = 0,
    shard_size: int = 1000,
    rules: str = "v1",
    out: Path = Path("data/records"),
) -> None:
    """Play bot vs bot games and record them in shards."""
    rs = load_ruleset(rules)
    store = LocalRecordStore(out)
    sim_dir = store.new_sim_dir(rules)
    wins: Counter[str] = Counter()
    for shard_index, first in enumerate(range(0, games, shard_size), start=1):
        with store.shard_path(sim_dir, shard_index).open("w", encoding="utf-8") as f:
            for i in range(first, min(first + shard_size, games)):
                game_seed = seed + i
                seats = {"p1": parse_seat(p1, 2 * game_seed + 1), "p2": parse_seat(p2, 2 * game_seed + 2)}
                header = HeaderLine(
                    game_id=new_game_id(), schema_version=RECORD_SCHEMA_VERSION, rules_version=rules,
                    seed=game_seed, mode="sim", seats={s: seat_info(x) for s, x in seats.items()},
                    ui={}, engine_version=__version__, started_at=berlin_iso(),
                )
                recorder = GameRecorder(f, header)
                final = play_game(rs, seats, RngChance(game_seed), recorder.on_step)
                recorder.close(final)
                wins[final.winner or "?"] += 1
    typer.echo(f"{games} games written to {sim_dir}")
    typer.echo(f"wins: p1 {wins['p1']}, p2 {wins['p2']}, draws {wins['draw']}")


@app.command()
def verify(path: Path, seed_check: bool = False) -> None:
    """Replay every game of a record file and check it."""
    failed = 0
    count = 0
    for game in read_games(path):
        count += 1
        problems = verify_game(game)
        if seed_check and not problems:
            problems = verify_seed(game)
        if problems:
            failed += 1
            typer.echo(f"{game.header.game_id}: " + "; ".join(problems))
    if failed:
        typer.echo(f"{failed} of {count} games have problems")
        raise typer.Exit(code=1)
    typer.echo(f"{count} games ok")


@app.command()
def replay(path: Path, game: str | None = None) -> None:
    """Print the steps of a recorded game."""
    for recorded in read_games(path):
        if game is not None and recorded.header.game_id != game:
            continue
        typer.echo(f"game {recorded.header.game_id} (rules {recorded.header.rules_version})")
        for line in recorded.steps:
            actions = ", ".join(f"{s}={a}" for s, a in (line.actions or {}).items()) or "-"
            chance = ", ".join(f"{c['seat']} {c['kind']} {c['value']}" for c in line.chance) or "-"
            typer.echo(f"step {line.n} round {line.round} {line.phase}: actions {actions}; chance {chance}")
        if recorded.footer is not None:
            typer.echo(f"winner {recorded.footer.winner}, points {recorded.footer.points}")
        if game is not None:
            return
```

- [ ] **Step 4: Run the tests**

Run: `uv run --with pytest pytest tests/test_cli_sim.py` → PASS
Run: `uv run --with pytest pytest && uv run ruff check . && uv run pyright` → no errors
Run: `uv run quack-rl simulate --games 20 --out /tmp/qr-check` then `uv run quack-rl verify <printed dir>/shard-0001.jsonl --seed-check` → `20 games ok`

- [ ] **Step 5: Commit**

```bash
git add src/quack_rl/cli tests/test_cli_sim.py
git commit -m "Add simulate, verify and replay commands"
```

---

### Task 12: Terminal play with Rich board and hidden keypress

**Files:**
- Create: `src/quack_rl/cli/render.py`, `src/quack_rl/cli/human.py`, `tests/test_cli_play.py`
- Modify: `src/quack_rl/cli/main.py` (command `play`), `src/quack_rl/cli/seats.py` (human seats), `README.md` (usage)

**Interfaces:**
- Consumes: Tasks 8-11
- Produces:
  - `render_board(state: GameState, rs: Ruleset, bag_assist: bool) -> rich.console.RenderableType`
  - `render_step(result: StepResult) -> str` (the reveal: actions and events of one step, one line per seat)
  - `HumanSeat(label: str, console: Console, bag_assist: bool, rs: Ruleset, read_key: Callable[[], str] | None = None)`: `kind = "human"`, `name = "human"`, `params = {}`; `choose` prints the board and a key menu, then reads one hidden key (default: `click.getchar(echo=False)`) until it maps to a legal action
  - Key map: `d` = draw, `s` = stop, `0` = done, `1`-`9` then `a`-`c` = the legal `buy:` actions in ruleset shop order
  - `parse_seat(spec, seed, *, console=None, rs=None, bag_assist=True, label="")`: `"human"` → `HumanSeat` when a console is given
  - Command `quack-rl play [--p1 human] [--p2 bot:random] [--seed N] [--bag-assist/--no-bag-assist] [--rules v1] [--out data/records]`: records to `LocalRecordStore(out).new_play_path(rules)` with `mode="play"` and `ui={"bag_assist": ...}`; on Ctrl+C the file keeps header and steps (no footer) and the command prints `game aborted, partial record: <path>`

- [ ] **Step 1: Write the failing test** `tests/test_cli_play.py`

```python
import io
import itertools

from rich.console import Console
from typer.testing import CliRunner

from helpers import RS
from quack_rl.cli import human
from quack_rl.cli.human import HumanSeat
from quack_rl.cli.main import app
from quack_rl.cli.render import render_board
from quack_rl.engine import DRAW, STOP, Phase, buy, new_game
from quack_rl.record import read_games, verify_game


def text_of(renderable):
    console = Console(file=io.StringIO(), width=120, color_system=None)
    console.print(renderable)
    return console.file.getvalue()


def test_board_shows_round_seats_and_bag_only_with_assist():
    s = new_game(RS)
    with_bag = text_of(render_board(s, RS, bag_assist=True))
    without_bag = text_of(render_board(s, RS, bag_assist=False))
    assert "Round 1/9" in with_bag and "p1" in with_bag and "p2" in with_bag
    assert "bag" in with_bag and "bag" not in without_bag


def test_human_seat_maps_keys_and_ignores_unknown_keys():
    keys = iter(["x", "s"])
    seat = HumanSeat("P1", Console(file=io.StringIO()), True, RS, read_key=lambda: next(keys))
    s = new_game(RS)
    s.players["p1"].placed = ["white_1"]
    assert seat.choose(s, "p1", [DRAW, STOP]) == STOP


def test_human_seat_shop_keys():
    keys = iter(["2"])
    seat = HumanSeat("P1", Console(file=io.StringIO()), True, RS, read_key=lambda: next(keys))
    s = new_game(RS)
    s.phase = Phase.SHOP
    legal = ["done", buy("orange_1"), buy("blue_1"), buy("green_1")]
    assert seat.choose(s, "p1", legal) == buy("blue_1")


def test_play_human_vs_bot_records_a_verifiable_game(tmp_path, monkeypatch):
    keys = itertools.cycle("ds0")
    monkeypatch.setattr(human, "default_read_key", lambda: next(keys))
    result = CliRunner().invoke(app, ["play", "--seed", "4", "--out", str(tmp_path)])
    assert result.exit_code == 0, result.output
    (path,) = (tmp_path / "v1" / "play").glob("*.jsonl")
    (game,) = read_games(path)
    assert game.header.mode == "play" and game.header.ui == {"bag_assist": True}
    assert game.header.seats["p1"].kind == "human"
    assert verify_game(game) == []
    human_steps = [s for s in game.steps if s.decision_ms]
    assert human_steps and all("p1" in s.decision_ms and "p2" not in s.decision_ms for s in human_steps)


def test_aborted_play_keeps_a_partial_record(tmp_path, monkeypatch):
    calls = itertools.count()

    def key():
        if next(calls) == 3:
            raise KeyboardInterrupt
        return "d"

    monkeypatch.setattr(human, "default_read_key", key)
    result = CliRunner().invoke(app, ["play", "--seed", "4", "--out", str(tmp_path)])
    assert "game aborted, partial record" in result.output
    (path,) = (tmp_path / "v1" / "play").glob("*.jsonl")
    (game,) = read_games(path)
    assert game.footer is None and verify_game(game) == ["incomplete game: no footer"]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with pytest pytest tests/test_cli_play.py`
Expected: FAIL (`ModuleNotFoundError: No module named 'quack_rl.cli.human'`)

- [ ] **Step 3: Write the implementation**

`src/quack_rl/cli/render.py`:

```python
from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text

from quack_rl.engine import SEATS, GameState, StepResult, start_field
from quack_rl.rules import Ruleset

CHIP_STYLE = {"white": "bold white", "orange": "bold dark_orange", "blue": "bold blue", "green": "bold green"}


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
        next_ruby = next((f for f in rs.rubies if f > p.field), None)
        field_text = f"{p.field} (money {rs.money[p.field]}, next ruby {next_ruby})"
        table.add_row(
            seat, p.status.value, f"{p.droplet_halves / 2:g} → start {start_field(p, rs)}", field_text,
            f"{p.white_total}/{rs.explosion_limit}", str(p.points), str(p.money), _chips(p.placed, rs),
        )
    parts: list[RenderableType] = [table]
    if bag_assist:
        for seat in SEATS:
            bag = state.players[seat].bag
            content = Text(" ").join(Text(f"{n}×") + chip_text(c, rs) for c, n in sorted(bag.items()))
            parts.append(Text(f"{seat} bag: ") + content)
    return Group(*parts)


def render_step(result: StepResult) -> str:
    lines = []
    for seat in SEATS:
        action = (result.actions or {}).get(seat, "-")
        events = [e for e in result.events if e.get("seat") == seat]
        summary = ", ".join(
            " ".join(f"{k}={v}" for k, v in e.items() if k != "seat") for e in events
        )
        lines.append(f"{seat}: {action}  {summary}")
    for e in result.events:
        if e.get("seat") is None:
            lines.append(" ".join(f"{k}={v}" for k, v in e.items() if k != "seat"))
    return "\n".join(lines)
```

`src/quack_rl/cli/human.py`:

```python
from collections.abc import Callable
from typing import Any

import click
from rich.console import Console

from quack_rl.cli.render import render_board
from quack_rl.engine import BUY_PREFIX, DONE, DRAW, STOP, GameState
from quack_rl.rules import Ruleset

BUY_KEYS = "123456789abc"


def default_read_key() -> str:
    return click.getchar(echo=False)


def key_map(legal: list[str]) -> dict[str, str]:
    keys: dict[str, str] = {}
    buys = [a for a in legal if a.startswith(BUY_PREFIX)]
    for action in legal:
        if action == DRAW:
            keys["d"] = DRAW
        elif action == STOP:
            keys["s"] = STOP
        elif action == DONE:
            keys["0"] = DONE
    for key, action in zip(BUY_KEYS, buys, strict=False):
        keys[key] = action
    return keys


class HumanSeat:
    kind = "human"
    name = "human"

    def __init__(
        self,
        label: str,
        console: Console,
        bag_assist: bool,
        rs: Ruleset,
        read_key: Callable[[], str] | None = None,
    ):
        self.label = label
        self.console = console
        self.bag_assist = bag_assist
        self.rs = rs
        self.params: dict[str, Any] = {}
        self._read_key = read_key

    def _describe(self, action: str) -> str:
        if action.startswith(BUY_PREFIX):
            item = self.rs.shop_item(action.removeprefix(BUY_PREFIX))
            return f"buy {item.id} ({item.price})"
        return action

    def choose(self, state: GameState, seat: str, legal: list[str]) -> str:
        keys = key_map(legal)
        self.console.print(render_board(state, self.rs, self.bag_assist))
        menu = "   ".join(f"[{k}] {self._describe(a)}" for k, a in keys.items())
        self.console.print(f"{self.label} ({seat}), press your key (hidden): {menu}")
        read = self._read_key or default_read_key
        while True:
            key = read()
            if key in keys:
                return keys[key]
            self.console.print("unknown key, try again (hidden)")
```

Note: `HumanSeat.choose` looks up `default_read_key` at call time (module attribute), so tests can monkeypatch `quack_rl.cli.human.default_read_key`.

Extend `src/quack_rl/cli/seats.py`:

```python
from rich.console import Console

from quack_rl.cli.human import HumanSeat
from quack_rl.rules import Ruleset


def parse_seat(
    spec: str,
    seed: int | None,
    *,
    console: Console | None = None,
    rs: Ruleset | None = None,
    bag_assist: bool = True,
    label: str = "",
) -> Seat:
    if spec == "bot:random":
        return RandomBot(seed)
    if spec == "human":
        if console is None or rs is None:
            raise HumanSeatRequired("human seats are only allowed in `quack-rl play`")
        return HumanSeat(label, console, bag_assist, rs)
    raise typer.BadParameter(f"unknown seat {spec!r} (known: bot:random, human)")
```

Add to `src/quack_rl/cli/main.py`:

```python
import secrets

from rich.console import Console

from quack_rl.cli.render import render_step


@app.command()
def play(
    p1: str = "human",
    p2: str = "bot:random",
    seed: int | None = None,
    bag_assist: bool = True,
    rules: str = "v1",
    out: Path = Path("data/records"),
) -> None:
    """Play a recorded game in the terminal (human vs bot, or hot seat with two humans)."""
    rs = load_ruleset(rules)
    console = Console()
    game_seed = seed if seed is not None else secrets.randbelow(2**31)
    seats = {
        "p1": parse_seat(p1, 2 * game_seed + 1, console=console, rs=rs, bag_assist=bag_assist, label="Player 1"),
        "p2": parse_seat(p2, 2 * game_seed + 2, console=console, rs=rs, bag_assist=bag_assist, label="Player 2"),
    }
    path = LocalRecordStore(out).new_play_path(rules)
    header = HeaderLine(
        game_id=new_game_id(), schema_version=RECORD_SCHEMA_VERSION, rules_version=rules, seed=game_seed,
        mode="play", seats={s: seat_info(x) for s, x in seats.items()}, ui={"bag_assist": bag_assist},
        engine_version=__version__, started_at=berlin_iso(),
    )
    with path.open("w", encoding="utf-8") as f:
        recorder = GameRecorder(f, header)

        def on_step(result, decision_ms):
            recorder.on_step(result, decision_ms)
            console.print(render_step(result))

        try:
            final = play_game(rs, seats, RngChance(game_seed), on_step)
        except KeyboardInterrupt:
            console.print(f"game aborted, partial record: {path}")
            return
        recorder.close(final)
    console.print(render_board(final, rs, bag_assist))
    console.print(f"winner: {final.winner}  points: "
                  f"p1 {final.players['p1'].points}, p2 {final.players['p2'].points}")
    console.print(f"record: {path}")
```

Add to `README.md`:

```markdown
## Play

    uv run quack-rl play                          # you (p1) vs the random bot
    uv run quack-rl play --p2 human               # hot seat on one keyboard
    uv run quack-rl play --no-bag-assist          # hide the bag contents

Keys: `d` draw, `s` stop, `0` done shopping, `1`-`9`/`a`-`c` buy. Your key is not shown.

## Simulate, replay, verify

    uv run quack-rl simulate --games 1000
    uv run quack-rl replay data/records/v1/play/<file>.jsonl
    uv run quack-rl verify data/records/v1/sim/<run>/shard-0001.jsonl --seed-check

Records go to `data/records/` (not committed).
```

- [ ] **Step 4: Run the tests and play once**

Run: `uv run --with pytest pytest tests/test_cli_play.py` → PASS
Run: `uv run --with pytest pytest && uv run ruff check . && uv run pyright` → no errors
Run (by hand, for the engineer's own check): `uv run quack-rl play --seed 1 --out /tmp/qr-play`, play a few steps, press Ctrl+C → `game aborted, partial record: ...`

- [ ] **Step 5: Commit**

```bash
git add src/quack_rl/cli tests/test_cli_play.py README.md
git commit -m "Add terminal play with Rich board and hidden keypress"
```

---

## Spec coverage (self-review)

| Spec item | Task |
|---|---|
| 4.1 engine: pure, serializable state, seeded chance, explicit chance events | 4, 5 |
| 4.2 components and plug-ins, features, ruleset data | 2, 3 |
| 4.3 bots: minimal random bot for M1 (design session is M2) | 8 |
| 5.1 turn structure, `wait`, step boundaries in the log | 4-7 |
| 5.2 bag assist as a UI setting, stored in the record | 12 |
| 5.4 one action list with names, 16 actions | 4 |
| 6.1 event log, legal actions and actions as names, chance validation, version rule | 9, 10 |
| 6.2 files, shards, Berlin time, RecordStore, `data/` gitignored | 9, 11 (`.gitignore` already done) |
| 7.1 terminal: Typer, Rich, play/replay/simulate/verify, hidden keypress, decision time | 8, 11, 12 |
| 8 rule-clause tests, Hypothesis invariants, golden replays, corrupted records, run time | 2-10 |
| 9 stack | 1 |

Out of M1 (spec 10, M2+): observation encodings, PettingZoo/Gymnasium envs, Minari export, step-boundary equivalence test, tournament, bot design session, notebook.
