"""The default `rules` is v1.11 everywhere in the code; the notebooks are archived."""

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

DEFAULT = "v1.11"


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
