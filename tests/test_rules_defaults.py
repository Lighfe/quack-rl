"""Nothing picks up v1.8 by accident: no default of `rules` is v1.8, the notebooks name v1.1 once."""

import ast
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCANNED = sorted((ROOT / "src" / "quack_rl").rglob("*.py")) + sorted((ROOT / "notebooks").glob("*.py"))


def _const(node: ast.AST | None):
    return node.value if isinstance(node, ast.Constant) else None


def rules_defaults(source: str) -> list[tuple[str, object, int]]:
    """Every default of a name `rules` as (where, value, line): parameters, fields, `.get("rules", x)`."""
    found: list[tuple[str, object, int]] = []
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            args = node.args
            positional = args.posonlyargs + args.args
            for arg, default in zip(positional[len(positional) - len(args.defaults):], args.defaults):
                if arg.arg == "rules":
                    found.append((f"param {getattr(node, 'name', 'lambda')}", _const(default), default.lineno))
            for arg, default in zip(args.kwonlyargs, args.kw_defaults):
                if arg.arg == "rules" and default is not None:
                    found.append((f"param {getattr(node, 'name', 'lambda')}", _const(default), default.lineno))
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if (
                    isinstance(item, ast.AnnAssign)
                    and isinstance(item.target, ast.Name)
                    and item.target.id == "rules"
                    and item.value is not None
                ):
                    found.append((f"field {node.name}", _const(item.value), item.lineno))
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and len(node.args) == 2
            and _const(node.args[0]) == "rules"
        ):
            found.append(("get", _const(node.args[1]), node.lineno))
    return found


def scan(files) -> list[tuple[str, str, object, int]]:
    out = []
    for path in files:
        for where, value, line in rules_defaults(Path(path).read_text(encoding="utf-8")):
            out.append((Path(path).name, where, value, line))
    return out


def test_no_rules_default_is_v1_8():
    found = scan(SCANNED)
    bad = [f for f in found if f[2] == "v1.8"]
    assert not bad, f"default rules v1.8 found: {bad}"


def test_scan_finds_the_known_defaults():
    found = scan(SCANNED)
    assert any(f[:3] == ("tournament.py", "field TournamentConfig", "v1") for f in found)
    cli = [f for f in found if f[0] == "main.py" and f[1].startswith("param")]
    assert len(cli) >= 3 and all(f[2] == "v1" for f in cli[:3])
    assert any(f[0] == "single_env.py" and f[1] == "param __init__" and f[2] == "v1.1" for f in found)
    assert any(f[0] == "report.py" and f[1] == "get" and f[2] == "v1" for f in found)


@pytest.mark.parametrize(
    "name", ["src/quack_rl/rl/single_env.py", "src/quack_rl/tournament.py", "src/quack_rl/report.py"]
)
def test_scan_fails_on_a_planted_v1_8(tmp_path, name):
    copy = tmp_path / Path(name).name
    text = (ROOT / name).read_text(encoding="utf-8")
    planted = re.sub(r'(rules[^=\n]*= |"rules", )"v1(\.1)?"', r'\1"v1.8"', text, count=1)
    assert planted != text
    copy.write_text(planted, encoding="utf-8")
    assert any(f[2] == "v1.8" for f in scan([copy]))


def test_tournament_notebook_has_no_version_string():
    text = (ROOT / "notebooks" / "tournament_run.py").read_text(encoding="utf-8")
    for version in ("v1", "v1.1", "v1.8"):
        assert f'"{version}"' not in text and f"'{version}'" not in text


@pytest.mark.parametrize("name", ["rl_env.py", "offline_rl.py"])
def test_rl_notebooks_set_the_version_once(name):
    lines = [
        line
        for line in (ROOT / "notebooks" / name).read_text(encoding="utf-8").splitlines()
        if '"v1' in line
    ]
    assert [line.strip() for line in lines] == ['RULES = "v1.1"']


def test_saved_v1_1_data_still_loads_and_plays():
    runs = sorted(p.parent for p in (ROOT / "data" / "runs").glob("*/model.zip"))
    if not runs:
        pytest.skip("no saved runs in data/runs (data/ is not in git)")
    pytest.importorskip("sb3_contrib")
    from quack_rl.bots import RandomBot
    from quack_rl.engine import Phase, RngChance
    from quack_rl.rl import PolicyBot
    from quack_rl.rl.runs import load_model
    from quack_rl.rules import load_ruleset
    from quack_rl.runner import play_game

    rs = load_ruleset("v1.1")
    for run in runs:
        assert load_model(run, "v1.1") is not None
        bot = PolicyBot.from_run(run, "v1.1")
        final = play_game(rs, {"p1": bot, "p2": RandomBot(1)}, RngChance(4))
        assert final.phase is Phase.GAME_OVER


def test_saved_datasets_read():
    import polars as pl

    files = sorted((ROOT / "data" / "datasets").glob("*.parquet"))
    if not files:
        pytest.skip("no saved datasets in data/datasets (data/ is not in git)")
    for f in files:
        assert pl.read_parquet(f).columns


def test_data_folder_is_unchanged():
    out = subprocess.run(
        ["git", "status", "--porcelain", "data/"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout
    assert out == ""
