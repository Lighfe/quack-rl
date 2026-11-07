"""One BC run of one seed of an experiment config, written into a run folder while it runs.

The run folder gets `config.json` at the start (with the dataset path and hash), one `bc.csv`
row per epoch, `checkpoints/epoch_<n>.pt` after each epoch, `model.pt` at the end and `done.json`
when the run has finished. Each `.pt` file holds the state dict of the network, which loads into
`make_mlp(obs_dim, n_actions, config.hidden)`.

torch is imported inside the function (through `quack_rl.rl.offline`), so this module imports
without the `rl` dependency group.
"""

import csv
import json
import os
import time
from pathlib import Path
from typing import Any

from quack_rl.rl.dataset import MANIFEST, Dataset, dataset_sha256
from quack_rl.rl.experiment import ExperimentConfig
from quack_rl.rl.ppo_run import git_commit
from quack_rl.rl.train import library_versions

RULES = "v2.3"
BATCH_SIZE = 256
LR = 1e-3
BC_COLUMNS = ("epoch", "loss", "entropy", "wall_seconds")


def _dataset_hash(dataset: Path) -> tuple[str, bool]:
    """The dataset's sha256 and whether it came from a `manifest.json` next to the dataset."""
    manifest = dataset.parent / MANIFEST
    if manifest.is_file():
        return str(json.loads(manifest.read_text(encoding="utf-8"))["sha256"]), True
    return dataset_sha256(dataset), False


def _save_checkpoint(state: dict[str, Any], folder: Path, epoch: int) -> Path:
    import torch

    path = folder / f"epoch_{epoch}.pt"
    tmp = folder / f"epoch_{epoch}.tmp.pt"
    torch.save(state, tmp)
    os.replace(tmp, path)
    return path


def run_bc_seed(config: ExperimentConfig, seed: int, out: Path) -> Path:
    """Train BC for one seed of `config` into the run folder `out`; return `out`.

    The settings are `config.bc` (`dataset`, `epochs`, `label_smoothing`, `entropy_coef`),
    `config.hidden` and the rules `v2.3`. Raise ValueError before any file is written when
    `config.kind` is not `"bc"`, and FileExistsError when `out` already has a `config.json`.
    """
    if config.kind != "bc" or config.bc is None:
        raise ValueError(f"run_bc_seed needs a bc experiment, not kind {config.kind!r}")
    out = Path(out)
    config_path = out / "config.json"
    if config_path.is_file():
        raise FileExistsError(f"{out} already has a config.json")
    bc = config.bc
    dataset_path = Path(bc.dataset)
    data = Dataset.load(dataset_path)
    sha, has_manifest = _dataset_hash(dataset_path)

    from quack_rl.rl.offline import fit_bc

    checkpoints = out / "checkpoints"
    checkpoints.mkdir(parents=True, exist_ok=True)
    stored = {
        "config": config.model_dump(mode="json"),
        "seed": seed,
        "dataset": bc.dataset,
        "dataset_sha256": sha,
        "manifest": has_manifest,
        "rules": RULES,
        "batch_size": BATCH_SIZE,
        "lr": LR,
        "obs_dim": int(data.obs.shape[1]),
        "n_actions": int(data.mask.shape[1]),
        "git_commit": git_commit(),
        "versions": library_versions(),
    }
    config_path.write_text(json.dumps(stored, indent=2) + "\n")
    csv_path = out / "bc.csv"
    with csv_path.open("w", newline="") as handle:
        csv.writer(handle).writerow(BC_COLUMNS)
    started = time.monotonic()

    def on_epoch(epoch: int, net: Any, loss: float, entropy: float) -> None:
        wall = round(time.monotonic() - started, 3)
        with csv_path.open("a", newline="") as handle:
            csv.writer(handle).writerow([epoch, loss, entropy, wall])
            handle.flush()
            os.fsync(handle.fileno())
        _save_checkpoint(net.state_dict(), checkpoints, epoch)

    net, _ = fit_bc(
        data,
        bc.epochs,
        seed,
        batch_size=BATCH_SIZE,
        lr=LR,
        hidden=config.hidden,
        label_smoothing=bc.label_smoothing,
        entropy_coef=bc.entropy_coef,
        on_epoch=on_epoch,
    )
    train_seconds = round(time.monotonic() - started, 3)
    import torch

    tmp = out / "model.tmp.pt"
    torch.save(net.state_dict(), tmp)
    os.replace(tmp, out / "model.pt")
    done = {"epochs": bc.epochs, "train_seconds": train_seconds}
    (out / "done.json").write_text(json.dumps(done, indent=2) + "\n")
    return out
