import secrets
from datetime import datetime
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")


def _berlin(now: datetime | None) -> datetime:
    return (now or datetime.now(BERLIN)).astimezone(BERLIN)


def berlin_stamp(now: datetime | None = None) -> str:
    return _berlin(now).strftime("%Y-%m-%d_%H-%M-%S%z")


def berlin_iso(now: datetime | None = None) -> str:
    return _berlin(now).isoformat(timespec="seconds")


def new_game_id() -> str:
    return secrets.token_hex(8)


class RecordStore(Protocol):
    def new_play_path(self, rules_version: str, now: datetime | None = None) -> Path: ...

    def new_sim_dir(self, rules_version: str, now: datetime | None = None) -> Path: ...

    def shard_path(self, sim_dir: Path, index: int) -> Path: ...

    def list_records(self, rules_version: str | None = None) -> list[Path]: ...


class LocalRecordStore:
    """Records as files under data/records/<rules_version>/{play,sim}/ (spec 6.2)."""

    def __init__(self, root: Path = Path("data/records")):
        self.root = root

    def new_play_path(self, rules_version: str, now: datetime | None = None) -> Path:
        folder = self.root / rules_version / "play"
        folder.mkdir(parents=True, exist_ok=True)
        return folder / f"{berlin_stamp(now)}_{secrets.token_hex(2)}.jsonl"

    def new_sim_dir(self, rules_version: str, now: datetime | None = None) -> Path:
        folder = self.root / rules_version / "sim" / f"{berlin_stamp(now)}_{secrets.token_hex(2)}"
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def shard_path(self, sim_dir: Path, index: int) -> Path:
        return sim_dir / f"shard-{index:04d}.jsonl"

    def list_records(self, rules_version: str | None = None) -> list[Path]:
        base = self.root / rules_version if rules_version else self.root
        return sorted(base.glob("**/*.jsonl"))
