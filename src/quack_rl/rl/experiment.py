"""Experiment config: one JSON file per experiment.

An experiment changes exactly one thing against its baseline. ``config_diff``
names the settings in which two experiments differ, so that rule can be
checked.
"""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from quack_rl.bots.presets import PRESET_BOTS

EVAL_OPPONENTS: tuple[str, ...] = (*PRESET_BOTS, "bot:random")

# Fields that describe an experiment, not a setting of it.
_META_FIELDS = frozenset({"id", "baseline", "changes"})
# MaskablePPO settings every ppo config must write out (no code default stands in for them).
PPO_UPDATE_FIELDS = ("n_steps", "batch_size", "target_kl")


class OpponentShare(BaseModel):
    """One opponent of the training mix and its relative weight."""

    model_config = ConfigDict(extra="forbid")

    spec: str
    weight: int = Field(default=1, ge=1)


class BCSettings(BaseModel):
    """Settings of a behaviour cloning run."""

    model_config = ConfigDict(extra="forbid")

    dataset: str
    epochs: int = 10
    label_smoothing: float = 0.0
    entropy_coef: float = 0.0


class ExperimentConfig(BaseModel):
    """One experiment (a PPO or BC run over several seeds)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: Literal["ppo", "bc"]
    baseline: str | None
    changes: str
    seeds: list[int] = [0, 1, 2]
    steps: int | None = None
    opponents: list[OpponentShare] = []
    reward: Literal["win_loss", "margin"] = "win_loss"
    hidden: int = 256
    checkpoint_every: int | None = None
    live_eval_games: int = 50
    final_eval_games: int = 200
    final_eval_seed: int = 2026
    init_from_bc: str | None = None
    """Path of a BC `model.pt` the PPO actor starts from (relative to the current directory).

    Every `{seed}` in it is replaced by the PPO seed (`resolve_bc_path` in
    `quack_rl.rl.ppo_run`), so `data/experiments/B1/seed{seed}/model.pt` starts PPO seed k from
    BC seed k; a path without `{seed}` is used for every seed.
    """
    critic_warmup_steps: int = 0
    n_steps: int | None = None
    """Moves per rollout (MaskablePPO `n_steps`); required for a ppo config, at least 1."""
    batch_size: int | None = None
    """Moves per minibatch (MaskablePPO `batch_size`); required for a ppo config, at least 2, and
    `n_steps` must be a multiple of it."""
    target_kl: float | None = None
    """MaskablePPO `target_kl`: None (no early stop) or > 0. A ppo config must write the key, also
    as `null`."""
    save_games: bool = False
    bc: BCSettings | None = None

    @model_validator(mode="after")
    def _check(self) -> "ExperimentConfig":
        if not self.seeds:
            raise ValueError("seeds must not be empty")
        if len(set(self.seeds)) != len(self.seeds):
            raise ValueError(f"seeds has duplicates: {self.seeds}")
        if self.kind == "ppo":
            if self.steps is None:
                raise ValueError("a ppo experiment needs steps")
            if not self.opponents:
                raise ValueError("a ppo experiment needs at least one opponent")
            self._check_ppo_update()
        if self.kind == "bc" and self.bc is None:
            raise ValueError("a bc experiment needs bc settings")
        return self

    def _check_ppo_update(self) -> None:
        for name in PPO_UPDATE_FIELDS:
            if name not in self.model_fields_set:
                raise ValueError(f"a ppo experiment needs {name}")
        if self.n_steps is None or self.n_steps < 1:
            raise ValueError(f"n_steps must be at least 1, not {self.n_steps}")
        if self.batch_size is None or self.batch_size < 2:
            raise ValueError(f"batch_size must be at least 2, not {self.batch_size}")
        if self.n_steps % self.batch_size:
            raise ValueError(
                f"n_steps {self.n_steps} must be a multiple of batch_size {self.batch_size}"
            )
        if self.target_kl is not None and not self.target_kl > 0:
            raise ValueError(f"target_kl must be null or greater than 0, not {self.target_kl}")


def load_config(path: Path) -> ExperimentConfig:
    """Read an experiment config from a JSON file and validate it."""
    return ExperimentConfig.model_validate_json(Path(path).read_text(encoding="utf-8"))


def config_diff(a: ExperimentConfig, b: ExperimentConfig) -> list[str]:
    """Names of the settings whose values differ, in field declaration order.

    ``id``, ``baseline`` and ``changes`` are ignored. When both ``bc`` values
    are set, each differing BC field is named ``bc.<field>``; when only one is
    set, the name is ``bc``.
    """
    diff: list[str] = []
    for name in ExperimentConfig.model_fields:
        if name in _META_FIELDS:
            continue
        va, vb = getattr(a, name), getattr(b, name)
        if name == "bc" and va is not None and vb is not None:
            diff.extend(
                f"bc.{field}"
                for field in BCSettings.model_fields
                if getattr(va, field) != getattr(vb, field)
            )
        elif va != vb:
            diff.append(name)
    return diff
