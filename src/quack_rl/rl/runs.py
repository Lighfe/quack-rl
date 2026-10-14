"""Save and load a training run: a folder with the config, the log rows, the evaluations, the model.

Files in `<path>/`: `config.json`, `episodes.csv`, `metrics.csv`, `eval.json`, `model.zip` and
`checkpoints/step_<n>.zip`. Nothing is written unless a run name or an explicit save asks for it.
SB3 is imported only in `load_model`.
"""

import csv
import dataclasses
import json
from pathlib import Path
from typing import Any

import quack_rl
from quack_rl.rl.encode import OBSERVATION_LAYOUT, vector_names
from quack_rl.rl.evaluate import EvalResult
from quack_rl.rules import load_ruleset

EPISODE_COLUMNS = (
    "episode", "timestep", "result", "points_own", "points_opponent", "explosions_own", "decisions",
)  # fmt: skip
METRIC_COLUMNS = (
    "timestep",
    "policy_gradient_loss",
    "value_loss",
    "entropy_loss",
    "approx_kl",
    "explained_variance",
)


class LayoutMismatch(ValueError):
    """The saved model was trained with another observation layout or vector."""


def run_path(runs_dir: Path, name: str) -> Path:
    """`runs_dir / name`, after checking that `name` is one plain folder name."""
    if not name or name in (".", "..") or "/" in name or "\\" in name or ".." in name:
        raise ValueError(
            f"run name {name!r} must be a plain folder name (no path separator, no '..')"
        )
    return Path(runs_dir) / name


def _refuse_existing(path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"run folder {path} already exists; pick another run name")


def full_config(config: dict) -> dict:
    """The config of `train` plus the package version, the layout version and the vector names."""
    return {
        **config,
        "package_version": quack_rl.__version__,
        "layout": OBSERVATION_LAYOUT,
        "vector_names": vector_names(load_ruleset(config["rules"])),
    }


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n")


def _write_csv(path: Path, columns: tuple[str, ...], rows: list[dict]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, columns)
        writer.writeheader()
        writer.writerows(rows)


def _append_csv(path: Path, columns: tuple[str, ...], row: dict) -> None:
    with path.open("a", newline="") as f:
        csv.DictWriter(f, columns).writerow(row)


def eval_dict(result: Any) -> dict[str, dict]:
    """The `EvalResult` fields of a `TrainResult` that are not None, as dicts."""
    out = {}
    for f in dataclasses.fields(result):
        value = getattr(result, f.name)
        if isinstance(value, EvalResult):
            out[f.name] = dataclasses.asdict(value)
    return out


class RunFolder:
    """A `RunSink` that writes into `path` as the run goes. The folder appears at `start`."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        _refuse_existing(self.path)

    def start(self, config: dict) -> None:
        self.path.mkdir(parents=True, exist_ok=False)
        _write_json(self.path / "config.json", full_config(config))
        _write_csv(self.path / "episodes.csv", EPISODE_COLUMNS, [])
        _write_csv(self.path / "metrics.csv", METRIC_COLUMNS, [])

    def episode(self, row: dict) -> None:
        _append_csv(self.path / "episodes.csv", EPISODE_COLUMNS, row)

    def metrics(self, row: dict) -> None:
        _append_csv(self.path / "metrics.csv", METRIC_COLUMNS, row)

    def checkpoint(self, model: Any, timestep: int) -> None:
        folder = self.path / "checkpoints"
        folder.mkdir(exist_ok=True)
        model.save(str(folder / f"step_{timestep}.zip"))

    def finish(self, result: Any) -> None:
        _write_json(self.path / "eval.json", eval_dict(result))
        result.model.save(str(self.path / "model.zip"))


class ResumedRun(RunFolder):
    """A `RunFolder` for a run folder that exists: `start` writes nothing, the rest appends."""

    def __init__(self, path: Path | str):
        self.path = Path(path)

    def start(self, config: dict) -> None:
        pass


@dataclasses.dataclass
class ResumeState:
    path: Path
    config: dict
    n: int  # timestep of the newest checkpoint
    checkpoint: Path


def _checkpoint_steps(folder: Path) -> dict[int, Path]:
    found = {}
    for f in folder.glob("step_*.zip"):
        digits = f.stem[len("step_") :]
        if digits.isdigit():
            found[int(digits)] = f
    return found


def check_resumable(runs_dir: Path, name: str) -> ResumeState:
    """The newest checkpoint of an interrupted run; a one-line error if it cannot resume."""
    path = run_path(runs_dir, name)
    if not path.is_dir():
        raise FileNotFoundError(f"run folder {path} does not exist")
    config_file = path / "config.json"
    if not config_file.is_file():
        raise FileNotFoundError(f"{config_file} is missing; nothing to resume")
    try:
        config = json.loads(config_file.read_text())
    except ValueError as err:
        raise ValueError(f"{config_file} is not valid JSON: {err}") from err
    if not isinstance(config, dict) or "steps" not in config:
        raise ValueError(f"{config_file} has no 'steps' key; cannot resume")
    for key in ("rules", "opponent", "seed", "eval_games"):
        if key not in config:
            raise ValueError(f"{config_file} has no {key!r} key; cannot resume")
    if (path / "model.zip").exists() or (path / "eval.json").exists():
        raise ValueError(
            f"run {path} is finished (model.zip or eval.json exists); nothing to resume"
        )
    if (path / "selfplay.csv").exists():
        raise ValueError(
            f"run {path} is a self-play run; resume of self-play runs is not supported"
        )
    steps_found = _checkpoint_steps(path / "checkpoints")
    if not steps_found:
        raise FileNotFoundError(f"{path / 'checkpoints'} has no step_<n>.zip checkpoint")
    n = max(steps_found)
    if n >= config["steps"]:
        raise ValueError(
            f"run {path}: newest checkpoint is at step {n}, steps is {config['steps']}; "
            "no steps left to resume"
        )
    if config.get("layout") != OBSERVATION_LAYOUT:
        raise LayoutMismatch(
            f"run {path} has observation layout {config.get('layout')}, "
            f"the code has {OBSERVATION_LAYOUT}"
        )
    if config.get("vector_names") != vector_names(load_ruleset(config["rules"])):
        raise LayoutMismatch(f"run {path} has other vector names than rules {config['rules']!r}")
    return ResumeState(path, config, n, steps_found[n])


def truncate_logs(path: Path, n: int) -> tuple[list[dict], list[dict]]:
    """Cut the rows after timestep `n` from the two logs; return the kept rows."""
    kept = []
    for name, columns in (("episodes.csv", EPISODE_COLUMNS), ("metrics.csv", METRIC_COLUMNS)):
        file = path / name
        with file.open(newline="") as f:
            rows = list(csv.DictReader(f))
        keep = [r for r in rows if int(r["timestep"]) <= n]
        if len(keep) != len(rows):
            _write_csv(file, columns, keep)
        kept.append([{k: _number(v) for k, v in r.items() if v != ""} for r in keep])
    return kept[0], kept[1]


def save_run(path: Path | str, result: Any, config: dict) -> None:
    """Write the run files (no checkpoints) from an in-memory `TrainResult`."""
    sink = RunFolder(path)
    sink.start(config)
    for row in result.log.episodes:
        sink.episode(row)
    for row in result.log.metrics:
        sink.metrics(row)
    sink.finish(result)


def _number(text: str) -> Any:
    for kind in (int, float):
        try:
            return kind(text)
        except ValueError:
            pass
    return text


def _read_csv(path: Path) -> list[dict]:
    with path.open(newline="") as f:
        return [{k: _number(v) for k, v in row.items() if v != ""} for row in csv.DictReader(f)]


def load_run(path: Path | str) -> tuple[dict, list[dict], list[dict], dict]:
    """(config, episodes, metrics, evaluation) of a saved run. Numbers come back as numbers."""
    path = Path(path)
    config = json.loads((path / "config.json").read_text())
    episodes = _read_csv(path / "episodes.csv")
    metrics = _read_csv(path / "metrics.csv")
    evaluation = json.loads((path / "eval.json").read_text())
    return config, episodes, metrics, evaluation


def load_model(path: Path | str, rules: str) -> Any:
    """Load `model.zip` of a run, after checking the layout and the vector names."""
    path = Path(path)
    config = json.loads((path / "config.json").read_text())
    if config.get("layout") != OBSERVATION_LAYOUT:
        raise LayoutMismatch(
            f"run {path} has observation layout {config.get('layout')}, "
            f"the code has {OBSERVATION_LAYOUT}"
        )
    if config.get("vector_names") != vector_names(load_ruleset(rules)):
        raise LayoutMismatch(f"run {path} has other vector names than rules {rules!r}")
    try:
        from sb3_contrib import MaskablePPO
    except ImportError as err:
        raise ImportError(
            "loading a model needs sb3-contrib and torch: run `uv sync --group train`"
        ) from err
    return MaskablePPO.load(str(path / "model.zip"), device="cpu")
