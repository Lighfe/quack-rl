"""The default `rules` is v2.3 everywhere in the code; the notebooks are archived."""

import ast
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCANNED = sorted((ROOT / "src" / "quack_rl").rglob("*.py"))


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


CODE_FILES = sorted((ROOT / "src" / "quack_rl").rglob("*.py")) + sorted((ROOT / "scripts").glob("*.py"))
DEFAULT = "v2.3"


def test_every_rules_default_in_code_is_v2_3():
    found = scan(CODE_FILES)
    assert found
    bad = [f for f in found if f[2] != DEFAULT]
    assert not bad, f"default rules other than {DEFAULT} found: {bad}"


def test_scan_finds_the_known_defaults():
    found = scan(SCANNED)
    assert any(f[:3] == ("tournament.py", "field TournamentConfig", DEFAULT) for f in found)
    cli = [f for f in found if f[0] == "main.py" and f[1].startswith("param")]
    assert len(cli) >= 3 and all(f[2] == DEFAULT for f in cli[:3])
    assert any(f[0] == "single_env.py" and f[1] == "param __init__" and f[2] == DEFAULT for f in found)
    assert any(f[0] == "report.py" and f[1] == "get" and f[2] == DEFAULT for f in found)


PLANTED = ["v3", "v2.0", "v0", "v2.1", "v2.2", DEFAULT]  # old-version-ok


@pytest.mark.parametrize(
    "name", ["src/quack_rl/rl/single_env.py", "src/quack_rl/tournament.py", "src/quack_rl/report.py"]
)
@pytest.mark.parametrize("planted_version", PLANTED)
def test_check_fails_on_a_planted_version(tmp_path, name, planted_version):
    copy = tmp_path / Path(name).name
    text = (ROOT / name).read_text(encoding="utf-8")
    planted = re.sub(r'(rules[^=\n]*= |"rules", )"v2.3"', rf'\1"{planted_version}"', text, count=1)
    assert (planted != text) == (planted_version != DEFAULT)
    copy.write_text(planted, encoding="utf-8")
    bad = [f for f in scan([copy]) if f[2] != DEFAULT]
    assert bool(bad) == (planted_version != DEFAULT)


def test_grep_of_the_issue_shows_only_v2_3():
    out = subprocess.run(
        ["grep", "-rnE", r'rules[^=]*=\s*"v[0-9]+(\.[0-9]+)?"', "src", "scripts"],
        cwd=ROOT, capture_output=True, text=True,
    ).stdout
    lines = [ln for ln in out.splitlines() if "__pycache__" not in ln and ".pyc" not in ln]
    assert lines and all('"v2.3"' in ln for ln in lines), lines


def test_service_and_tournament_columns_use_the_default():
    from quack_rl.tournament import CSV_COLUMNS, csv_columns
    from quack_rl.rules import load_ruleset
    from quack_rl.web.app import RULES

    assert RULES == DEFAULT
    assert CSV_COLUMNS == csv_columns(load_ruleset(DEFAULT))


def test_data_folder_is_unchanged():
    out = subprocess.run(
        ["git", "status", "--porcelain", "data/"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout
    assert out == ""
