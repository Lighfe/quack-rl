"""Agent folders: every trained or planning agent lives in `data/agents/<name>/`.

A folder holds `agent.json` (an `AgentManifest`) and, for `ppo`, `bc` and `cql`, a weights file
(`model.zip` for PPO, `model.pt` with the state dict for BC and CQL). The seat `agent:<name>`
loads it with `load_agent`. This module imports without the `rl` dependency group: torch and SB3
are imported only when a `ppo`, `bc` or `cql` agent is loaded.
"""

import hashlib
import re
import shutil
import warnings
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from quack_rl.rl.encode import BOARD_LAYOUT
from quack_rl.rules import Ruleset
from quack_rl.runner import Seat

AGENTS_ROOT = Path("data/agents")
MANIFEST = "agent.json"
AGENT_PREFIX = "agent:"
NAME_RE = re.compile(r"[a-z0-9][a-z0-9_-]*")
RL_KINDS = ("ppo", "bc", "cql")
WEIGHTS_FILES = {"ppo": "model.zip", "bc": "model.pt", "cql": "model.pt"}


class AgentError(ValueError):
    """An agent folder is missing, broken or does not fit the current rules."""


class AgentManifest(BaseModel):
    name: str
    kind: Literal["ppo", "bc", "cql", "planner"]
    rules: str  # the ruleset version the agent was made for, e.g. `v2.3`
    layout: int  # the observation layout (`BOARD_LAYOUT`)
    weights: str | None = None  # file name in the folder; None for `planner`
    weights_sha256: str | None = None
    settings: dict[str, Any] = {}  # the training settings
    created_at: str


# The planner issue (#273) fills this in: (rules, manifest, seed) -> seat.
PLANNER_FACTORY: Callable[[Ruleset, AgentManifest, int | None], Seat] | None = None


def check_name(name: str) -> None:
    """Raise AgentError when `name` is not an agent name (`[a-z0-9][a-z0-9_-]*`)."""
    if not NAME_RE.fullmatch(name):
        raise AgentError(
            f"agent name {name!r} is not valid: use lower case letters, digits, _ and -, "
            "starting with a letter or digit"
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def save_agent(folder: Path, manifest: AgentManifest) -> None:
    """Write `agent.json` to `folder`; the hash of the weights file is computed here."""
    check_name(manifest.name)
    folder = Path(folder)
    sha = None
    if manifest.weights is not None:
        weights = folder / manifest.weights
        if not weights.is_file():
            raise AgentError(f"the weights file {weights} does not exist")
        sha = _sha256(weights)
    data = manifest.model_copy(update={"weights_sha256": sha})
    folder.mkdir(parents=True, exist_ok=True)
    (folder / MANIFEST).write_text(data.model_dump_json(indent=2) + "\n", encoding="utf-8")


def read_manifest(folder: Path) -> AgentManifest:
    """The manifest of an agent folder. Raises AgentError when it is missing or broken."""
    path = Path(folder) / MANIFEST
    if not path.is_file():
        raise AgentError(f"no agent in {Path(folder)}: {path} does not exist")
    try:
        return AgentManifest.model_validate_json(path.read_text(encoding="utf-8"))
    except (ValidationError, ValueError) as err:
        raise AgentError(f"{path} is not a valid agent manifest: {err}") from err


def ensure_new_agent(name: str, root: Path = AGENTS_ROOT) -> Path:
    """The folder for a new agent `name`. Raises AgentError when `agent.json` already exists."""
    check_name(name)
    folder = Path(root) / name
    if (folder / MANIFEST).exists():
        raise AgentError(f"the agent {name!r} already exists: {folder / MANIFEST}")
    return folder


def write_agent(
    name: str,
    kind: Literal["ppo", "bc", "cql"],
    weights: Path,
    rules: str,
    settings: dict[str, Any],
    root: Path = AGENTS_ROOT,
) -> Path:
    """Copy a trained weights file into a new agent folder and write its manifest."""
    folder = ensure_new_agent(name, root)
    folder.mkdir(parents=True, exist_ok=True)
    target = WEIGHTS_FILES[kind]
    shutil.copyfile(weights, folder / target)
    manifest = AgentManifest(
        name=name,
        kind=kind,
        rules=rules,
        layout=BOARD_LAYOUT,
        weights=target,
        settings=settings,
        created_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )
    save_agent(folder, manifest)
    return folder


def checked_manifest(name: str, rules: Ruleset, root: Path = AGENTS_ROOT) -> AgentManifest:
    """Read and check the manifest of agent `name` against `rules`, without loading weights."""
    check_name(name)
    folder = Path(root) / name
    manifest = read_manifest(folder)
    if manifest.rules != rules.version:
        raise AgentError(
            f"agent {name!r} was made for rules {manifest.rules}, not the current {rules.version}"
        )
    if manifest.layout != BOARD_LAYOUT:
        raise AgentError(
            f"agent {name!r} was made for layout {manifest.layout}, not the current {BOARD_LAYOUT}"
        )
    if manifest.kind in RL_KINDS:
        if manifest.weights is None:
            raise AgentError(f"agent {name!r} of kind {manifest.kind} names no weights file")
        weights = folder / manifest.weights
        if not weights.is_file():
            raise AgentError(f"the weights file {weights} of agent {name!r} does not exist")
        if _sha256(weights) != manifest.weights_sha256:
            raise AgentError(f"the weights file {weights} does not match the hash in {MANIFEST}")
    return manifest


def _require_rl(kind: str) -> None:
    try:
        import torch  # noqa: F401
        import sb3_contrib  # noqa: F401  # isort: skip
    except ImportError as err:
        raise AgentError(
            f"an agent of kind {kind} needs the `rl` dependency group: run with `uv run --group rl`"
        ) from err


def load_agent(
    name: str, rules: Ruleset, seed: int | None = None, root: Path = AGENTS_ROOT
) -> Seat:
    """Load agent `name` from `root` as a seat that plays with `rules`."""
    manifest = checked_manifest(name, rules, root)
    label = AGENT_PREFIX + name
    if manifest.kind == "planner":
        if PLANNER_FACTORY is None:
            raise AgentError(f"agent {name!r} is a planner, and no planner is available yet")
        return PLANNER_FACTORY(rules, manifest, seed)
    _require_rl(manifest.kind)
    assert manifest.weights is not None
    weights = Path(root) / name / manifest.weights
    try:
        if manifest.kind == "ppo":
            from sb3_contrib import MaskablePPO

            from quack_rl.rl.policy_bot import PolicyBot

            return PolicyBot(MaskablePPO.load(str(weights), device="cpu"), rules, label)
        import torch

        from quack_rl.rl.offline import OfflinePolicy, make_mlp

        s = manifest.settings
        net = make_mlp(int(s["obs_dim"]), int(s["n_actions"]), int(s.get("hidden", 256)))
        net.load_state_dict(torch.load(weights, map_location="cpu", weights_only=True))
        return OfflinePolicy(net, rules, label)
    except (KeyError, RuntimeError, OSError, ValueError) as err:
        raise AgentError(f"agent {name!r} could not be loaded from {weights}: {err}") from err


def list_agents(root: Path = AGENTS_ROOT) -> list[AgentManifest]:
    """The manifests of the agent folders under `root`, by name. A broken folder is skipped
    with a warning."""
    root = Path(root)
    if not root.is_dir():
        return []
    found: list[AgentManifest] = []
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        try:
            found.append(read_manifest(folder))
        except AgentError as err:
            warnings.warn(f"skipped agent folder {folder}: {err}", stacklevel=2)
    return found
