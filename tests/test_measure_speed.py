import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "measure_speed", Path(__file__).parent.parent / "scripts" / "measure_speed.py"
)
assert _spec and _spec.loader
measure_speed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(measure_speed)


def test_format_row_divides_totals_by_games():
    row = measure_speed.format_row("bot:x", 10, 0.5, 100_000, 20_000)
    assert row.split() == ["bot:x", "50.00", "10.00", "2.00"]


def test_measure_small_run():
    row = measure_speed.measure("bot:random", 2, 0).split()
    assert row[0] == "bot:random"
    assert len(row) == 4 and float(row[2]) > float(row[3]) > 0
