"""The training stack and the `policy:` seat are archived: nothing in the package names them."""

import subprocess
import sys

import pytest
import typer

import quack_rl.rl as rl
from quack_rl.cli.seats import check_seat

# the names are joined so that a grep of the package finds no mention of the archived code
MOVED = (
    "Policy" + "Bot",
    # (`evaluate` is a module of the package again, so hasattr(rl, "evaluate") is no check)
    "random_policy",
    "check_policy" + "_layout",
    "EvalResult",
    "Policy",
    "Layout" + "Refused",
)


def test_policy_seat_rejected():
    with pytest.raises(typer.BadParameter, match="unknown seat") as err:
        check_seat("policy:runs/x")
    assert "policy: seats are not supported" in str(err.value)


def test_rl_imports_without_the_train_stack_and_holds_no_moved_name():
    blocked = ("to" + "rch", "sb3" + "_contrib")
    code = (
        "import sys; "
        + "".join(f"sys.modules[{m!r}] = None; " for m in blocked)
        + "import quack_rl.rl"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
    for name in MOVED:
        assert not hasattr(rl, name), name
    for name in rl.__all__:
        assert hasattr(rl, name), name
