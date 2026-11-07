"""Tests for one BC run of one seed (`quack_rl.rl.bc_run`)."""

import csv
import json

import pytest

torch = pytest.importorskip("torch")

from quack_rl.rl.bc_run import BC_COLUMNS, run_bc_seed  # noqa: E402
from quack_rl.rl.dataset import (  # noqa: E402
    MANIFEST,
    build_dataset,
    dataset_sha256,
    write_dataset_manifest,
)
from quack_rl.rl.experiment import ExperimentConfig  # noqa: E402
from quack_rl.rl.offline import make_mlp  # noqa: E402

CONFIG_FIELDS = {
    "config",
    "seed",
    "dataset",
    "dataset_sha256",
    "manifest",
    "git_commit",
    "versions",
}


def b0(dataset: str, **bc) -> ExperimentConfig:
    return ExperimentConfig.model_validate(
        {
            "id": "B0",
            "kind": "bc",
            "baseline": None,
            "changes": "BC control",
            "bc": {"dataset": dataset, "epochs": 2, **bc},
        }
    )


@pytest.fixture(scope="module")
def dataset_folder(tmp_path_factory):
    folder = tmp_path_factory.mktemp("data")
    build_dataset("bot:random", "bot:random", 3, seed=0).save(folder / "dataset.npz")
    return folder


def test_wrong_kind_raises_before_any_file(tmp_path, dataset_folder):
    ppo = ExperimentConfig.model_validate(
        {
            "id": "P0",
            "kind": "ppo",
            "baseline": None,
            "changes": "x",
            "steps": 2048,
            "opponents": [{"spec": "bot:random"}],
        }
    )
    out = tmp_path / "run"
    with pytest.raises(ValueError, match="bc"):
        run_bc_seed(ppo, 0, out)
    assert not out.exists()


def test_existing_config_raises_and_changes_nothing(tmp_path, dataset_folder):
    (tmp_path / "config.json").write_text("{}")
    with pytest.raises(FileExistsError):
        run_bc_seed(b0(str(dataset_folder / "dataset.npz")), 0, tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["config.json"]
    assert (tmp_path / "config.json").read_text() == "{}"


@pytest.mark.parametrize("with_manifest", [False, True])
def test_run_writes_the_run_folder(tmp_path, with_manifest):
    folder = tmp_path / "data"
    build_dataset("bot:random", "bot:random", 3, seed=0).save(folder / "dataset.npz")
    if with_manifest:
        write_dataset_manifest(
            folder, bots=["bot:random"], games_per_pairing=3, seed=0, rules="v2.3", command=["t"]
        )
        # a recognisable hash shows that the manifest's value is the one recorded
        manifest = json.loads((folder / MANIFEST).read_text())
        manifest["sha256"] = "ab" * 32
        (folder / MANIFEST).write_text(json.dumps(manifest))
    dataset = str(folder / "dataset.npz")
    config = b0(dataset, label_smoothing=0.1, entropy_coef=0.05)
    out = tmp_path / "run"

    assert run_bc_seed(config, 4, out) == out

    stored = json.loads((out / "config.json").read_text())
    assert CONFIG_FIELDS <= set(stored)
    assert stored["config"] == config.model_dump(mode="json")
    assert stored["seed"] == 4
    assert stored["dataset"] == dataset
    assert stored["manifest"] is with_manifest
    expected = "ab" * 32 if with_manifest else dataset_sha256(folder / "dataset.npz")
    assert stored["dataset_sha256"] == expected
    assert isinstance(stored["git_commit"], str) and stored["git_commit"]
    assert "torch" in stored["versions"]

    with (out / "bc.csv").open(newline="") as handle:
        reader = csv.reader(handle)
        assert tuple(next(reader)) == BC_COLUMNS == ("epoch", "loss", "entropy", "wall_seconds")
        data_rows = list(reader)
    assert [row[0] for row in data_rows] == ["1", "2"]
    for row in data_rows:
        assert all(float(x) == float(x) for x in row[1:])  # numbers, no NaN

    names = sorted(p.name for p in (out / "checkpoints").iterdir())
    assert names == ["epoch_1.pt", "epoch_2.pt"]

    done = json.loads((out / "done.json").read_text())
    assert done["epochs"] == 2 and done["train_seconds"] >= 0

    from quack_rl.rl.dataset import Dataset

    data = Dataset.load(dataset)
    for path in (out / "model.pt", out / "checkpoints" / "epoch_1.pt"):
        net = make_mlp(data.obs.shape[1], data.mask.shape[1], config.hidden)
        net.load_state_dict(torch.load(path, weights_only=True))
